# notion-md-uploader

Upload local Markdown files to Notion pages via the [Notion API](https://developers.notion.com/), bypassing LLM context windows.

Instead of passing large page content through MCP tools (which burns tokens), this script reads a `.md` file from disk and creates or updates a Notion page directly — only the final URL goes through the LLM.

## Prerequisites

1. A **Notion Internal Integration** — create one at [notion.so/my-integrations](https://www.notion.so/my-integrations)
2. Grant the integration access to your target pages/databases (via the page's `...` → Connections menu)
3. Store the integration token:
   ```bash
   export NOTION_TOKEN="ntn_..."          # or
   echo "ntn_..." > ~/.notion_token       # script auto-reads this
   ```

## Usage

```bash
pip install notion-client
python3 scripts/notion_upload_md.py <file.md> [OPTIONS]
```

### Create a page in a Notion database

```bash
python3 scripts/notion_upload_md.py lecture.md \
  --database YOUR_DATABASE_ID \
  --title "Lecture Notes" \
  --prop "Tags=course" \
  --prop "Status=draft"
```

### Create a page under a parent page

```bash
python3 scripts/notion_upload_md.py notes.md --parent PAGE_ID --title "My Notes"
```

### Update an existing page

```bash
# Full content replacement
python3 scripts/notion_upload_md.py fixed.md --update PAGE_ID

# Append to existing page
python3 scripts/notion_upload_md.py appendix.md --append PAGE_ID
```

### Preview without writing

```bash
python3 scripts/notion_upload_md.py test.md --dry-run
```

## Markdown Support

The script converts Markdown to native Notion blocks:

| Markdown | Notion Block |
|----------|-------------|
| `# ## ###` | heading_1/2/3 |
| `**bold**` `*italic*` | bold / italic rich text |
| `` `code` `` | inline code |
| `~~strike~~` | strikethrough |
| `[text](url)` | link |
| `$E=mc^2$` | inline equation |
| `$$f(x) = \int ...$$` | block equation |
| `` ```code``` `` | code block |
| `- item` `1. item` | bulleted / numbered list |
| `> quote` | quote |
| `---` | divider |
| GFM table | table (with header row) |

**Not supported**: nested lists, images, Mermaid diagrams, raw HTML, task lists, footnotes.

## Why Not MCP?

Notion MCP tools require passing the full page content as a tool-call parameter. For large pages with formulas, code blocks, and tables, this can consume 10k–50k+ tokens per write. This script uses the Notion API directly from the shell — only the result URL goes through the LLM.

## Directory

```
notion-md-uploader/
├── README.md
├── SKILL.md                    # Claude Code skill definition
└── scripts/
    └── notion_upload_md.py     # main upload script
```
