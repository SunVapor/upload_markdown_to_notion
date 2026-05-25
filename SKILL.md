---
name: notion-md-uploader
description: Upload a local Markdown file directly to Notion via the Notion API (notion_client), bypassing the LLM context. Use when a .md file needs to be created or updated as a Notion page without passing the full content through MCP tools.
---

# Notion Markdown Uploader

Upload local `.md` files directly to Notion via `notion_client` API — content never passes through the LLM context window.

## Prerequisites

1. A Notion Internal Integration token ([notion.so/my-integrations](https://www.notion.so/my-integrations))
2. Grant the integration access to target pages/databases (page `...` → Connections → add integration)
3. Token stored as `NOTION_TOKEN` env var or `~/.notion_token` file

## Workflow

1. Write the prepared Markdown content to a local `.md` file (e.g. `/tmp/notion_upload.md`)
2. Run the upload script:

```bash
python3 scripts/notion_upload_md.py <file.md> [OPTIONS]
```

## Options

| Option | Description |
|--------|-------------|
| `--database DB_ID` | Target database ID |
| `--parent PAGE_ID` | Target parent page ID |
| `--title TITLE` | Page title (default: filename stem) |
| `--title-prop NAME` | Title property name in database (default: `Name`) |
| `--prop KEY=VALUE` | Database property (repeatable). e.g. `--prop "Tags=note"` |
| `--update PAGE_ID` | Replace all content of existing page |
| `--append PAGE_ID` | Append content to existing page |
| `--dry-run` | Preview blocks without writing (no token needed) |

## Examples

```bash
# Create page in a database with custom properties
python3 scripts/notion_upload_md.py notes.md \
  --database YOUR_DB_ID \
  --title "My Note" \
  --prop "Tags=important" \
  --prop "Status=draft"

# Create page under a parent page
python3 scripts/notion_upload_md.py notes.md --parent PAGE_ID --title "Notes"

# Replace existing page content
python3 scripts/notion_upload_md.py fixed.md --update PAGE_ID

# Preview only
python3 scripts/notion_upload_md.py test.md --dry-run
```

## Supported Markdown

| Markdown | Notion Block |
|----------|-------------|
| `# ## ###` | heading_1/2/3 |
| `**bold**` `*italic*` | rich text |
| `` `code` `` | inline code |
| `~~strike~~` | strikethrough |
| `[text](url)` | link |
| `$E=mc^2$` | inline equation |
| `$$...$$` | block equation |
| `` ```code``` `` | code block |
| `- item` `1. item` | bulleted / numbered list |
| `> quote` | quote |
| `---` | divider |
| `\| table \|` | table (with header row) |

Not supported: nested lists, images, Mermaid, HTML, task lists, footnotes.

## Why Not MCP?

MCP tools require passing full page content as LLM parameters — a large page can consume 10k–50k+ tokens per write. This script calls the Notion API directly from the shell; only the result URL goes through the LLM.
