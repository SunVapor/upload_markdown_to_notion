---
name: notion-md-uploader
description: Upload a local Markdown file directly to Notion via the Notion API (notion_client), bypassing the LLM context. Use when a .md file needs to be created or updated as a Notion page without passing the full content through MCP tools.
---

# Notion Markdown Uploader

将本地 `.md` 文件直接上传到 Notion，走 `notion_client` API，内容不经过 LLM 上下文。

## When to Use

- 用户要求将 `.md` 文件写入/创建/更新 Notion 页面
- 需要避免通过 MCP 工具传递大量页面内容（节省 token）
- 用户说"上传这个md到notion"、"把这个笔记写入notion"、"创建notion页面"

## Prerequisites

需要 Notion Integration Token。来源优先级：
1. 环境变量 `NOTION_TOKEN`
2. `~/.notion_token` 文件

如果两者都没有，告诉用户去 https://www.notion.so/my-integrations 创建 Integration 并授权到目标数据库/页面。

## Workflow

### 1. Prepare the .md file

先用 Write 工具将准备好的 Markdown 内容写入本地 `.md` 文件（例如 `/tmp/notion_upload.md` 或 workspace 内路径）。

### 2. Run the upload script

```bash
python3 ~/.claude/skills/notion-md-uploader/scripts/notion_upload_md.py <file.md> [OPTIONS]
```

常用选项：
- `--dry-run` : 只预览生成的 blocks，不实际写入（不需要 token）
- `--title "页面标题"` : 页面标题（默认取文件名 stem）
- `--database DB_ID` : 目标数据库 ID
- `--class-name "编译原理"` : 数据库 Class 属性
- `--summary "内容摘要"` : 数据库 内容 属性
- `--parent PAGE_ID` : 普通父页面 ID
- `--update PAGE_ID` : 替换已有页面全部内容
- `--append PAGE_ID` : 追加到已有页面末尾

### 3. Report

把脚本输出的 Notion URL 告诉用户。

## Target Databases

- **Class Notes**: database `27982023103981a999dee7afbbd12bb4`, title property `Name`, select property `Class`, text property `内容`
- 创建 CP 笔记示例：
  ```bash
  python3 .../notion_upload_md.py CP16.md \
    --database 27982023103981a999dee7afbbd12bb4 \
    --title "CP16 语义分析" \
    --class-name "编译原理" \
    --summary "语义分析基础"
  ```

## Supported Markdown

脚本将以下 Markdown 转换为 Notion 原生 blocks：

| Markdown | Notion Block |
|----------|-------------|
| `# ## ###` | heading_1/2/3 |
| `**bold**` `*italic*` | bold / italic rich text |
| `` `code` `` | inline code |
| `~~strike~~` | strikethrough |
| `[text](url)` | link |
| `$...$` | inline equation |
| `$$...$$` | block equation |
| ` ```code``` ` | code block |
| `- item` `1. item` | bulleted / numbered list |
| `> quote` | quote |
| `---` | divider |
| `\| table \|` | table |

不支持：嵌套列表、图片、Mermaid、HTML。

## Limitations

- 需要有效的 Notion Integration Token（与 MCP OAuth token 不同，需单独创建）
- Table 单元格内不支持 inline 格式
- 不支持 GFM 扩展语法（task list、footnote 等）
