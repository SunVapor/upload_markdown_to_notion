# upload_markdown_to_notion

将本地 Markdown 文件直接上传到 Notion 页面，走 [Notion API](https://developers.notion.com/)，内容不经过 LLM 上下文。

通过 MCP 工具写入 Notion 需要把全量页面内容作为工具调用参数传递，大页面（含公式、表格、代码块）单次写入消耗 10k–50k+ token。本脚本从磁盘读取 `.md` 文件，直接调用 Notion API，只有结果 URL 经过 LLM。

## 前置条件

1. 创建 **Notion Internal Integration**：[notion.so/my-integrations](https://www.notion.so/my-integrations)
2. 在目标页面/数据库右上角 `...` → Connections → 添加刚创建的 Integration
3. 保存 token：
   ```bash
   export NOTION_TOKEN="ntn_..."          # 环境变量
   echo "ntn_..." > ~/.notion_token       # 或写入文件，脚本自动读取
   ```

## 使用方法

```bash
pip install notion-client
python3 scripts/notion_upload_md.py <file.md> [OPTIONS]
```

### 在数据库中创建页面

```bash
python3 scripts/notion_upload_md.py lecture.md \
  --database YOUR_DATABASE_ID \
  --title "笔记标题" \
  --prop "Tags=课程" \
  --prop "Status=draft"
```

`--prop` 支持类型标注：`Key:type=Value`。支持的类型：`rich_text`（默认）、`select`、`number`、`date`、`checkbox`。

```bash
--prop "Priority:select=High"
--prop "Score:number=95"
--prop "Deadline:date=2024-12-31"
--prop "Done:checkbox=true"
```

### 在父页面下创建子页面

```bash
python3 scripts/notion_upload_md.py notes.md --parent PAGE_ID --title "笔记"
```

### 更新已有页面

```bash
# 全量替换内容
python3 scripts/notion_upload_md.py fixed.md --update PAGE_ID

# 追加到末尾
python3 scripts/notion_upload_md.py appendix.md --append PAGE_ID
```

### 预览（不实际写入，无需 token）

```bash
python3 scripts/notion_upload_md.py test.md --dry-run
```

### 完整选项

| 选项 | 说明 |
|------|------|
| `--database DB_ID` | 目标数据库 ID |
| `--parent PAGE_ID` | 目标父页面 ID |
| `--title TITLE` | 页面标题（默认取文件名） |
| `--title-prop NAME` | 数据库 title 属性名（默认 `Name`） |
| `--prop KEY=VALUE` | 数据库属性，可重复使用，支持 `Key:type=Value` |
| `--update PAGE_ID` | 替换已有页面全部内容 |
| `--append PAGE_ID` | 追加内容到已有页面末尾 |
| `--dry-run` | 只打印生成的 blocks，不实际写入 |

## 支持的 Markdown 语法

| Markdown | Notion Block |
|----------|-------------|
| `# ## ###` | heading_1/2/3 |
| `**加粗**` `*斜体*` | bold / italic |
| `` `行内代码` `` | inline code |
| `~~删除线~~` | strikethrough |
| `[链接](url)` | link |
| `$E=mc^2$` | inline equation |
| `$$...$$` | block equation |
| `` ```code``` `` | code block |
| `- 项目` `1. 项目` | bulleted / numbered list |
| `> 引用` | quote |
| `---` | divider |
| GFM 表格 | table（含表头行，单元格内支持 inline 格式） |

**不支持**：嵌套列表、图片、Mermaid、HTML、task list、footnote。

## 目录结构

```
upload_markdown_to_notion/
├── README.md
├── SKILL.md                          # Claude Code skill 定义
└── scripts/
    └── notion_upload_md.py           # 主上传脚本
```
