---
name: xiaoyuzhou-query
description: Query Xiaoyuzhou podcast episodes, podcasts, and transcript data stored in the local PostgreSQL database. Read-only — no data modification.
metadata:
  openclaw:
    requires:
      bins: ["python3"]
---

# 小宇宙播客数据库查询 Skill

本 skill 查询已爬取并存储在 PostgreSQL 数据库中的小宇宙播客内容（节目、播客、字幕）。

**本 skill 严格只读。不执行任何 INSERT, UPDATE, DELETE 操作。**

## 适用场景

用于以下情况：
- 从数据库中读取或搜索小宇宙播客节目
- 列出已爬取的播客
- 按关键词、播客ID、状态或日期范围查找节目
- 查看某集节目的完整转录文本
- 获取已爬取内容的统计信息

**不要**用于爬取/下载新的播客内容（那是不同的工作流）。

## 命令

所有命令使用相同的基础调用：

```bash
python {baseDir}/scripts/query_db.py <command> [options]
```

### 1. 查询节目

```bash
python {baseDir}/scripts/query_db.py episodes [options]
```

选项：
- `--podcast PID` — 按播客ID过滤
- `--search KEYWORD` — 搜索标题、正文和简介（不区分大小写）
- `--since YYYY-MM-DD` — 起始日期 (含)
- `--until YYYY-MM-DD` — 截止日期 (含)
- `--status STATUS` — 按状态过滤：`pending`, `ready`, `pending_transcription`
- `--limit N` — 最多返回条数 (默认: 20, 最大: 500)
- `--offset N` — 跳过前 N 条 (分页)
- `--id EID` — 按单集ID精确查询单条
- `--full` — 显示完整转录文本 (默认只显示预览)

### 2. 列出播客

```bash
python {baseDir}/scripts/query_db.py podcasts [--search KEYWORD]
```

返回所有已爬取的播客，包含标题、作者、节目数。

### 3. 查看统计

```bash
python {baseDir}/scripts/query_db.py stats
```

返回播客总数、节目总数，以及按状态和转录来源分类统计。

## 输出格式

每集节目以稳定的结构化格式输出：

```
标题: <title>
来源: xiaoyuzhou
类型: podcast_episode
单集ID: <eid>
播客ID: <pid>
发布时间: <datetime>
时长: N 分钟
转录来源: <内置字幕|音频转录>
状态: <pending|ready|pending_transcription>
主播/嘉宾: <name1>, <name2>
正文预览: <first 200 chars>  (默认)
--- 正文 ---              (带 --full 参数)
<full transcript text>
```

条目之间用 `============` 分隔线分隔。

## 示例

用户说: "数据库里有哪些播客节目"
→ 运行: `python {baseDir}/scripts/query_db.py episodes --limit 10`

用户说: "搜索小宇宙里关于AI的播客节目"
→ 运行: `python {baseDir}/scripts/query_db.py episodes --search AI`

用户说: "查看播客 xxx 的最新10集"
→ 运行: `python {baseDir}/scripts/query_db.py episodes --podcast xxx --limit 10`

用户说: "看看节目 eid123 的完整转录"
→ 运行: `python {baseDir}/scripts/query_db.py episodes --id eid123 --full`

用户说: "有哪些已经转录完成的节目"
→ 运行: `python {baseDir}/scripts/query_db.py episodes --status ready --limit 20`

用户说: "小宇宙数据库里有多少数据"
→ 运行: `python {baseDir}/scripts/query_db.py stats`

## Setup

This skill shares the virtual environment with the Xiaoyuzhou crawler. If the virtual environment does not exist:

```bash
python3 -m venv {baseDir}/.venv
{baseDir}/.venv/bin/pip install -r {baseDir}/requirements.txt
```

Database connection is configured via `{baseDir}/.env`, using `POSTGRES_READONLY_USER` (hub_readonly) for read-only access.
