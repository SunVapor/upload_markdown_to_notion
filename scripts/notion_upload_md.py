#!/usr/bin/env python3
"""
Upload local Markdown files to Notion pages via notion_client API.

Usage:
    python3 notion_upload_md.py <file.md> [OPTIONS]

Token sources (priority):
    1. Environment variable NOTION_TOKEN
    2. File ~/.notion_token

Prerequisites:
    pip install notion-client

Options:
    --database DB_ID       Target database ID
    --parent PAGE_ID       Target parent page ID
    --title TITLE          Page title (default: filename stem)
    --class-name NAME      Database select property value (if applicable)
    --summary TEXT         Database text property value (if applicable)
    --update PAGE_ID       Replace all content of an existing page
    --append PAGE_ID       Append content to an existing page
    --dry-run              Print generated blocks without writing to Notion
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path
from notion_client import Client
from notion_client.errors import APIResponseError

# ── Token ──────────────────────────────────────────────

def resolve_token() -> str:
    t = os.environ.get("NOTION_TOKEN")
    if t:
        return t
    # Also check ~/.notion_token for convenience
    token_file = Path.home() / ".notion_token"
    if token_file.exists():
        return token_file.read_text().strip()
    return ""


# ── Inline Markdown Parser ─────────────────────────────

# Annotation types for rich_text
ANNOTATIONS = {
    "bold":          {"bold": True},
    "italic":        {"italic": True},
    "strikethrough": {"strikethrough": True},
    "code":          {"code": True},
}


def _make_rich_text(text: str, anno_type: str | None = None, link_url: str | None = None,
                    equation: bool = False) -> dict:
    """Build one Notion rich_text dict."""
    if equation:
        return {
            "type": "equation",
            "equation": {"expression": text},
            "annotations": {"bold": False, "italic": False, "strikethrough": False,
                           "underline": False, "code": False, "color": "default"},
            "plain_text": text,
        }
    d = {
        "type": "text",
        "text": {"content": text} | ({"link": {"url": link_url}} if link_url else {}),
        "annotations": {
            "bold": False, "italic": False, "strikethrough": False,
            "underline": False, "code": False, "color": "default",
        },
        "plain_text": text,
    }
    if anno_type:
        d["annotations"] |= ANNOTATIONS.get(anno_type, {})
    return d


def parse_inline(text: str) -> list[dict]:
    """Convert inline Markdown text to Notion rich_text array.

    Supports: **bold**, *italic*, `code`, $inline-equation$, [link](url), ~~strike~~,
              nested formatting (e.g. **bold `code`**), backslash escapes (\\*, \\$).
    """
    if not text:
        return []

    tokens = []
    pos = 0
    n = len(text)
    plain_start = 0

    while pos < n:
        # E3: backslash escape — next char is literal
        if text[pos] == '\\' and pos + 1 < n:
            if pos > plain_start:
                tokens.append(_make_rich_text(text[plain_start:pos]))
            tokens.append(_make_rich_text(text[pos + 1]))
            pos += 2
            plain_start = pos
            continue

        markers = list(_scan_markers(text, pos))

        if markers:
            if pos > plain_start:
                tokens.append(_make_rich_text(text[plain_start:pos]))

            _start, end, fn = markers[0]
            t, anno, link_url, is_eq = fn()

            # E2: nested formatting — recurse inside bold/italic/strikethrough
            if anno and anno != "code":
                inner = parse_inline(t)
                for tok in inner:
                    if tok["type"] == "text":
                        tok["annotations"] = {**tok["annotations"], **ANNOTATIONS[anno]}
                    tokens.append(tok)
            else:
                tokens.append(_make_rich_text(t, anno_type=anno, link_url=link_url, equation=is_eq))

            pos = end
            plain_start = pos
        else:
            pos += 1

    # Flush trailing plain text
    if pos > plain_start:
        tokens.append(_make_rich_text(text[plain_start:pos]))

    # Merge adjacent plain-text tokens with matching annotations
    merged = []
    for tok in tokens:
        if (merged and tok["type"] == "text" and merged[-1]["type"] == "text"
                and tok["annotations"] == merged[-1]["annotations"]
                and not tok["text"].get("link")
                and not merged[-1]["text"].get("link")):
            merged[-1]["text"]["content"] += tok["text"]["content"]
            merged[-1]["plain_text"] += tok["plain_text"]
            continue
        merged.append(tok)

    return merged


def _scan_markers(text: str, pos: int):
    """Yield (start_index, end_index, payload_fn) for markers found at or after pos.
    payload_fn returns (text, anno_type_or_None, link_url_or_None, is_equation)."""
    if pos >= len(text):
        return

    ch = text[pos]

    # $ ... $  inline equation  (highest priority — non-greedy)
    if ch == "$" and not (pos + 1 < len(text) and text[pos + 1] == "$"):
        m = re.match(r"\$(.+?)\$", text[pos:])
        if m:
            yield (pos, pos + len(m.group(0)), lambda t=m.group(1): (t.strip(), None, None, True))

    # ** bold **
    if text[pos:pos+2] == "**":
        m = re.match(r"\*\*(.+?)\*\*", text[pos:])
        if m:
            yield (pos, pos + len(m.group(0)), lambda t=m.group(1): (t, "bold", None, False))

    # * italic *  (single *, not part of **)
    elif ch == "*":
        m = re.match(r"\*(?!\*)(.+?)(?<!\*)\*(?!\*)", text[pos:])
        if m:
            yield (pos, pos + len(m.group(0)), lambda t=m.group(1): (t, "italic", None, False))

    # ` code `
    if ch == "`":
        m = re.match(r"`(.+?)`", text[pos:])
        if m:
            yield (pos, pos + len(m.group(0)), lambda t=m.group(1): (t, "code", None, False))

    # ~~ strikethrough ~~
    if text[pos:pos+2] == "~~":
        m = re.match(r"~~(.+?)~~", text[pos:])
        if m:
            yield (pos, pos + len(m.group(0)), lambda t=m.group(1): (t, "strikethrough", None, False))

    # [link text](url)
    if ch == "[":
        m = re.match(r"\[(.+?)\]\((.+?)\)", text[pos:])
        if m:
            yield (pos, pos + len(m.group(0)), lambda t=m.group(1), u=m.group(2): (t, None, u, False))


# ── Block-level Parser ─────────────────────────────────


def md_to_blocks(text: str) -> list[dict]:
    """Convert Markdown source text to a list of Notion block objects."""
    blocks: list[dict] = []
    lines = text.split("\n")
    i = 0
    n = len(lines)

    # Track table accumulation
    in_table = False
    table_lines: list[str] = []

    while i < n:
        line = lines[i]

        # ── Fenced code block ──
        if line.strip().startswith("```"):
            lang = line.strip()[3:].strip()
            code_lines = []
            i += 1
            while i < n and not lines[i].strip().startswith("```"):
                code_lines.append(lines[i])
                i += 1
            i += 1  # skip closing ```
            code_text = "\n".join(code_lines)
            block = {
                "object": "block",
                "type": "code",
                "code": {
                    "rich_text": [{"type": "text", "text": {"content": code_text}}],
                    "language": lang if lang else "plain text",
                },
            }
            blocks.append(block)
            continue

        # ── Block equation $$ ... $$ ──
        if line.strip().startswith("$$"):
            stripped = line.strip()
            # One-liner: $$ ... $$
            if stripped.endswith("$$") and len(stripped) > 4:
                expression = stripped[2:-2].strip()
                blocks.append({
                    "object": "block",
                    "type": "equation",
                    "equation": {"expression": expression},
                })
                i += 1
                continue
            # Multi-line: $$ (open), content, $$ (close)
            eq_lines = []
            i += 1
            while i < n and not lines[i].strip().startswith("$$"):
                eq_lines.append(lines[i])
                i += 1
            i += 1  # skip closing $$
            expression = "\n".join(eq_lines).strip()
            blocks.append({
                "object": "block",
                "type": "equation",
                "equation": {"expression": expression},
            })
            continue

        # ── Blank line (table boundary) ──
        if not line.strip():
            if in_table:
                blocks.extend(_build_table_blocks(table_lines))
                in_table = False
                table_lines = []
            i += 1
            continue

        # ── Heading ──
        if line.startswith("# "):
            blocks.append({
                "object": "block", "type": "heading_1",
                "heading_1": {"rich_text": parse_inline(line[2:].strip())},
            })
            i += 1
            continue
        if line.startswith("## "):
            blocks.append({
                "object": "block", "type": "heading_2",
                "heading_2": {"rich_text": parse_inline(line[3:].strip())},
            })
            i += 1
            continue
        if line.startswith("### "):
            blocks.append({
                "object": "block", "type": "heading_3",
                "heading_3": {"rich_text": parse_inline(line[4:].strip())},
            })
            i += 1
            continue

        # ── Divider ──
        if line.strip() in ("---", "***", "___"):
            blocks.append({"object": "block", "type": "divider", "divider": {}})
            i += 1
            continue

        # ── Table detection ──
        if "|" in line and line.strip().startswith("|"):
            # If previous line was also table, or we're at start of table
            table_lines.append(line)
            # Check if next non-blank line is a separator row (|---|---|)
            if not in_table:
                # peek next: if it's a separator, we're in a table
                ni = i + 1
                while ni < n and not lines[ni].strip():
                    ni += 1
                if ni < n and _is_table_sep(lines[ni]):
                    table_lines.append(lines[ni])
                    in_table = True
                    i = ni + 1
                    continue
                else:
                    # Single pipe line, not a table — treat as paragraph
                    blocks.append({
                        "object": "block", "type": "paragraph",
                        "paragraph": {"rich_text": parse_inline(line.strip())},
                    })
                    table_lines = []
                    i += 1
                    continue
            i += 1
            continue

        # ── Unordered list ──
        if re.match(r"^[-*+]\s", line):
            list_items = []
            while i < n and re.match(r"^[-*+]\s", lines[i]):
                body = re.sub(r"^[-*+]\s+", "", lines[i], count=1)
                list_items.append(body)
                i += 1
            for item_text in list_items:
                blocks.append({
                    "object": "block",
                    "type": "bulleted_list_item",
                    "bulleted_list_item": {"rich_text": parse_inline(item_text)},
                })
            continue

        # ── Ordered list ──
        if re.match(r"^\d+\.\s", line):
            list_items = []
            while i < n and re.match(r"^\d+\.\s", lines[i]):
                body = re.sub(r"^\d+\.\s+", "", lines[i], count=1)
                list_items.append(body)
                i += 1
            for item_text in list_items:
                blocks.append({
                    "object": "block",
                    "type": "numbered_list_item",
                    "numbered_list_item": {"rich_text": parse_inline(item_text)},
                })
            continue

        # ── Blockquote ──
        if line.startswith("> "):
            quote_lines = []
            while i < n and lines[i].startswith("> "):
                quote_lines.append(lines[i][2:])
                i += 1
            quote_text = "\n".join(quote_lines)
            blocks.append({
                "object": "block",
                "type": "quote",
                "quote": {"rich_text": parse_inline(quote_text)},
            })
            continue

        # ── Paragraph (default) ──
        para_lines = []
        while i < n and lines[i].strip() and \
                not lines[i].startswith(("#", "- ", "* ", "+ ", "> ", "```", "$$", "|")) and \
                not re.match(r"^\d+\.\s", lines[i]) and \
                lines[i].strip() not in ("---", "***", "___"):
            para_lines.append(lines[i])
            i += 1

        if para_lines:
            para_text = "\n".join(para_lines)
            blocks.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {"rich_text": parse_inline(para_text)},
            })
        else:
            i += 1

    # Flush remaining table
    if in_table and table_lines:
        blocks.extend(_build_table_blocks(table_lines))

    return blocks


def _is_table_sep(line: str) -> bool:
    """Check if line is a markdown table separator like |---|---|"""
    return bool(re.match(r"^\|?[\s:-]+\|", line.strip())) and "---" in line


def _build_table_blocks(lines: list[str]) -> list[dict]:
    """Build Notion table block with nested table_row children."""
    if len(lines) < 2:
        return []
    cleaned = [l for l in lines if not _is_table_sep(l)]
    if not cleaned:
        return []

    rows = []
    for line in cleaned:
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        rows.append(cells)

    if not rows:
        return []

    col_count = max(len(r) for r in rows)

    children = []
    for row in rows:
        while len(row) < col_count:
            row.append("")
        cells = [parse_inline(c) if parse_inline(c) else [{"type": "text", "text": {"content": c}}] for c in row]
        children.append({
            "object": "block",
            "type": "table_row",
            "table_row": {"cells": cells},
        })

    table_block = {
        "object": "block",
        "type": "table",
        "table": {
            "table_width": col_count,
            "has_column_header": True,
            "has_row_header": False,
            "children": children,
        },
    }
    return [table_block]


# ── Block Writer ─────────────────────────────────────

def _write_blocks(client: Client, parent_id: str, blocks: list[dict]):
    """Write blocks to a parent, in chunks of 100."""
    for start in range(0, len(blocks), 100):
        chunk = blocks[start:start + 100]
        client.blocks.children.append(parent_id, children=chunk)


# ── Notion API wrappers ────────────────────────────────

def create_page(client: Client, title: str, content: str, *,
                database_id: str = "", parent_id: str = "",
                props: list[str] | None = None, title_prop: str = "Name",
                class_name: str = "", summary: str = "",
                dry_run: bool = False) -> str:
    """Create a new Notion page and fill it with content blocks.

    props: list of "key=value" strings for generic rich_text properties.
    title_prop: name of the title property in the database (default "Name").
    class_name: shorthand that creates a select property named "Class".
    summary: shorthand that creates a rich_text property named "内容".
    """
    if props is None:
        props = []

    if database_id:
        parent = {"type": "database_id", "database_id": database_id.replace("-", "")}
        properties: dict = {
            title_prop: {"title": [{"text": {"content": title}}]},
        }
        for p in props:
            if "=" not in p:
                continue
            k, v = p.split("=", 1)
            k = k.strip()
            v = v.strip()
            # "Key:type=Value" — type defaults to rich_text
            if ":" in k:
                k, ptype = k.split(":", 1)
                k = k.strip()
                ptype = ptype.strip()
            else:
                ptype = "rich_text"

            if ptype == "select":
                properties[k] = {"select": {"name": v}}
            elif ptype == "number":
                try:
                    v_num = float(v) if "." in v else int(v)
                except ValueError:
                    v_num = v
                properties[k] = {"number": v_num}
            elif ptype == "date":
                properties[k] = {"date": {"start": v}}
            elif ptype == "checkbox":
                properties[k] = {"checkbox": v.lower() in ("yes", "true", "1", "checked")}
            else:
                properties[k] = {"rich_text": [{"text": {"content": v}}]}
        # Shorthand: --class-name → select property (not rich_text)
        if class_name:
            properties["Class"] = {"select": {"name": class_name}}
        if summary:
            properties["内容"] = {"rich_text": [{"text": {"content": summary}}]}
    elif parent_id:
        parent = {"type": "page_id", "page_id": parent_id.replace("-", "")}
        properties = {"title": [{"text": {"content": title}}]}
    else:
        print("错误: 需要 --database 或 --parent 指定目标位置", file=sys.stderr)
        return "error"

    blocks = md_to_blocks(content)

    if dry_run:
        print("=== DRY RUN (not writing to Notion) ===")
        print(f"Parent: {json.dumps(parent, indent=2)}")
        print(f"Properties: {json.dumps(properties, indent=2, ensure_ascii=False)}")
        print(f"Blocks ({len(blocks)}):")
        for i, b in enumerate(blocks):
            print(f"  [{i}] {b['type']}: {json.dumps(b[b['type']], ensure_ascii=False)[:200]}")
        return "dry-run"

    page = client.pages.create(parent=parent, properties=properties)
    page_id = page["id"]
    _write_blocks(client, page_id, blocks)
    return page_id


def replace_page_content(client: Client, page_id: str, content: str):
    """Delete all children of a page and write new content."""
    pid = page_id.replace("-", "")

    # Delete existing children (handle pagination — API returns max 100 per page)
    all_children = []
    cursor = None
    while True:
        resp = client.blocks.children.list(pid, start_cursor=cursor)
        all_children.extend(resp.get("results", []))
        if not resp.get("has_more"):
            break
        cursor = resp["next_cursor"]
    for child in all_children:
        client.blocks.delete(child["id"])

    blocks = md_to_blocks(content)
    _write_blocks(client, pid, blocks)


def append_to_page(client: Client, page_id: str, content: str):
    """Append content blocks to an existing page."""
    pid = page_id.replace("-", "")
    blocks = md_to_blocks(content)
    _write_blocks(client, pid, blocks)


# ── Main ────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Upload local Markdown file to Notion page via notion_client API",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Create page in a database (with property values)
    python3 notion_upload_md.py notes.md --database YOUR_DB_ID \\
        --title "My Note" --class-name "Course" --summary "Key takeaways"

    # Create page under a parent page
    python3 notion_upload_md.py notes.md --parent PAGE_ID --title "My Notes"

    # Update existing page (full content replacement)
    python3 notion_upload_md.py notes.md --update PAGE_ID

    # Append to existing page
    python3 notion_upload_md.py notes.md --append PAGE_ID

    # Preview without writing
    python3 notion_upload_md.py test.md --dry-run
        """,
    )
    parser.add_argument("file", help="Path to local .md file")
    parser.add_argument("--database", default="", help="Target database ID")
    parser.add_argument("--parent", default="", help="Target parent page ID")
    parser.add_argument("--title", default="", help="Page title (default: filename stem)")
    parser.add_argument("--title-prop", default="Name", help="Name of the title property in the database (default: Name)")
    parser.add_argument("--prop", action="append", default=[], metavar="KEY=VALUE",
                        help="Database property (repeatable). e.g. --prop 'Tags=important'")
    parser.add_argument("--class-name", default="", help="[shorthand] Same as --prop 'Class=VALUE'")
    parser.add_argument("--summary", default="", help="[shorthand] Same as --prop '内容=VALUE'")
    parser.add_argument("--update", default="", help="Replace all content of an existing page ID")
    parser.add_argument("--append", default="", help="Append content to an existing page ID")
    parser.add_argument("--dry-run", action="store_true", help="Print blocks without writing to Notion")

    args = parser.parse_args()

    # Shorthand: --class-name / --summary are handled in create_page() directly
    # (class_name → select type, summary → rich_text)

    filepath = Path(args.file)
    if not filepath.exists():
        print(f"错误: 文件不存在: {args.file}", file=sys.stderr)
        sys.exit(1)

    content = filepath.read_text(encoding="utf-8")
    title = args.title or filepath.stem

    # dry-run: no token needed
    if args.dry_run:
        if args.update:
            blocks = md_to_blocks(content)
            pid = args.update.replace("-", "")
            print(f"=== DRY RUN: would replace content of page {pid} with {len(blocks)} blocks ===")
            for i, b in enumerate(blocks):
                print(f"  [{i}] {b['type']}: {json.dumps(b[b['type']], ensure_ascii=False)[:200]}")
        elif args.append:
            blocks = md_to_blocks(content)
            pid = args.append.replace("-", "")
            print(f"=== DRY RUN: would append {len(blocks)} blocks to page {pid} ===")
            for i, b in enumerate(blocks):
                print(f"  [{i}] {b['type']}: {json.dumps(b[b['type']], ensure_ascii=False)[:200]}")
        else:
            create_page(None, title, content,
                       database_id=args.database, parent_id=args.parent,
                       props=args.prop, title_prop=args.title_prop,
                       class_name=args.class_name, summary=args.summary,
                       dry_run=True)
        return

    token = resolve_token()
    if not token:
        print("错误: 未找到 Notion token。请设置环境变量 NOTION_TOKEN", file=sys.stderr)
        print("获取 Integration Token: https://www.notion.so/my-integrations", file=sys.stderr)
        sys.exit(1)

    client = Client(auth=token)

    try:
        if args.update:
            replace_page_content(client, args.update, content)
            pid = args.update.replace("-", "")
            print(f"页面已更新: https://www.notion.so/{pid}")
        elif args.append:
            append_to_page(client, args.append, content)
            pid = args.append.replace("-", "")
            print(f"内容已追加: https://www.notion.so/{pid}")
        else:
            page_id = create_page(client, title, content,
                                 database_id=args.database, parent_id=args.parent,
                                 props=args.prop, title_prop=args.title_prop,
                                 class_name=args.class_name, summary=args.summary,
                                 dry_run=False)
            print(f"页面已创建: https://www.notion.so/{page_id.replace('-', '')}")
    except APIResponseError as e:
        print(f"Notion API 错误 [{e.code}]: {e.body}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"错误: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
