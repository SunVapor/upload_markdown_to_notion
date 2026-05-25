---
name: notion-md-uploader
description: 将本地 Markdown 文件直接上传到 Notion 页面，走 notion_client API，内容不经过 LLM 上下文。用于需要创建或更新 Notion 页面但不想通过 MCP 工具传递全量内容的场景。
---

# upload_markdown_to_notion

将本地 `.md` 文件直接上传到 Notion，走 `notion_client` API，内容不经过 LLM 上下文。

## 前置条件

1. Notion Internal Integration token（[notion.so/my-integrations](https://www.notion.so/my-integrations)）
2. 将 Integration 授权到目标页面/数据库（页面 `...` → Connections → 添加 Integration）
3. Token 保存在 `NOTION_TOKEN` 环境变量或 `~/.notion_token` 文件

## 工作流

1. 将准备好的 Markdown 内容写入本地 `.md` 文件（如 `/tmp/notion_upload.md`）
2. 运行上传脚本：

```bash
python3 scripts/notion_upload_md.py <file.md> [OPTIONS]
```

## 选项

| 选项 | 说明 |
|------|------|
| `--database DB_ID` | 目标数据库 ID |
| `--parent PAGE_ID` | 目标父页面 ID |
| `--title TITLE` | 页面标题（默认取文件名） |
| `--title-prop NAME` | 数据库 title 属性名（默认 `Name`） |
| `--prop KEY=VALUE` | 数据库属性（可重复使用），支持 `Key:type=Value` |
| `--update PAGE_ID` | 替换已有页面全部内容 |
| `--append PAGE_ID` | 追加内容到已有页面末尾 |
| `--dry-run` | 只预览生成的 blocks，不实际写入（无需 token） |

## 示例

```bash
# 在数据库中创建页面
python3 scripts/notion_upload_md.py notes.md \
  --database YOUR_DB_ID \
  --title "笔记标题" \
  --prop "Tags=课程" \
  --prop "Status=draft"

# 在父页面下创建子页面
python3 scripts/notion_upload_md.py notes.md --parent PAGE_ID --title "笔记"

# 替换已有页面内容
python3 scripts/notion_upload_md.py fixed.md --update PAGE_ID

# 预览不写入
python3 scripts/notion_upload_md.py test.md --dry-run
```

## 支持的 Markdown

| Markdown | Notion Block |
|----------|-------------|
| `# ## ###` | heading_1/2/3 |
| `**加粗**` `*斜体*` | rich text |
| `` `行内代码` `` | inline code |
| `~~删除线~~` | strikethrough |
| `[链接](url)` | link |
| `$E=mc^2$` | inline equation |
| `$$...$$` | block equation |
| `` ```code``` `` | code block |
| `- 项目` `1. 项目` | bulleted / numbered list |
| `> 引用` | quote |
| `---` | divider |
| `\| 表格 \|` | table（含表头行，单元格支持 inline 格式） |

不支持：嵌套列表、图片、Mermaid、HTML、task list、footnote。

## 为什么不用 MCP？

MCP 工具需要将全量页面内容作为 LLM 工具调用参数传递。大页面（含公式、代码、表格）单次写入消耗 10k–50k+ token。本脚本从 shell 直接调用 Notion API，只有结果 URL 经过 LLM。
