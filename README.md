<div align="center">

# 🎙️ 小宇宙播客爬虫

**Agent Skill — 通过小宇宙官方 API 搜索、浏览、下载播客内容，支持批量爬取与音频转录**

[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![AgentSkills Standard](https://img.shields.io/badge/AgentSkills-Standard-green.svg)](https://github.com/anthropics/skills)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**多平台兼容**：支持多种 Agent 平台（Hermes · OpenClaw · Codex 等）

[功能概览](#-功能概览) · [快速开始](#-快速开始) · [使用指南](#-使用指南) · [CLI 参考](#-cli-参考) · [常见问题](#-常见问题)

</div>

---

## ✨ 功能概览

| 功能 | 描述 |
|------|------|
| **ADB 一键登录** | 自动从 MuMu/夜神模拟器提取 `refresh_token` + `device_id`，无需手动抓包 |
| **多账号支持** | MuMu 多开实例并行爬取，`--account` 指定账号，互不干扰 |
| **智能搜索** | 默认走 iTunes API（无需登录），无结果自动 fallback 到小宇宙搜索 |
| **单集详情** | 获取元信息、内置字幕、付费内容音频 URL |
| **音频下载** | 断点续传、ffprobe 完整性校验、付费内容自动获取私链 |
| **字幕导出** | 词级字幕自动合并为句子，支持 SRT / TXT / JSON 三种格式 |
| **批量爬取** | 字幕优先 + faster-whisper 本地转录兜底，两轮扫描策略 |
| **音频转录** | 支持 tiny/base/small/medium/large-v3 五档模型，subprocess 真超时控制 |
| **CSV 导出** | 一键导出飞书多维表格导入格式（UTF-8 BOM，RFC 4180 标准） |
| **PostgreSQL 集成** | 爬取结果同步到 PG 数据库，支持只读查询（`query_db.py`） |
| **Hub 集成** | 通过 `hub_adapter.py` 接入 Financial Hub，支持 crawl 生命周期管理 |
| **守护进程** | `serve` 模式自动循环爬取，Token 刷新 + 异常告警，适合长期无人值守 |
| **Token 自动管理** | 401 自动刷新，支持手动检查/刷新/验证 |

---

## 🚀 快速开始

### 环境要求

- **Python 3.10+**
- **ffmpeg**（音频转录需要）— `winget install ffmpeg` / `brew install ffmpeg` / `sudo apt install ffmpeg`
- **ADB 工具**（自动登录需要）— MuMu 模拟器自带，或安装 Android SDK Platform Tools
- **PostgreSQL**（数据库查询/Hub 集成需要）— 可选，核心爬取功能不依赖

### 安装

```bash
# 克隆仓库
git clone https://github.com/<your-username>/xiaoyuzhou-skill.git
cd xiaoyuzhou-skill

# 创建虚拟环境并安装所有依赖
python -m venv .venv
source .venv/bin/activate   # Linux/macOS
# .venv\Scripts\activate    # Windows

pip install -r requirements.txt

# 配置数据库连接（query_db.py 和 hub_adapter.py 需要）
cp .env.example .env
# 编辑 .env 填入实际的 PostgreSQL 连接信息

# 预下载 Whisper 模型（约 150MB，仅首次需要）
python scripts/xyz.py setup
```

> **完整安装指引**（含虚拟环境、依赖说明、.env 配置详解、只读用户创建）见 **`SKILL_SETUP.md`**。

### 依赖说明

| 依赖 | 用途 | 必需 |
|------|------|:---:|
| `requests` | HTTP 客户端 | ✅ |
| `faster-whisper` | 本地音频转录 | ✅ |
| `ffmpeg` | 音频转码（系统级） | ✅ |
| `psycopg2-binary` | PostgreSQL 驱动 | 可选 |
| `python-dotenv` | 加载 `.env` 配置 | 可选 |
| `financial-hub-postgres` | Hub 共享客户端库 | 可选 |

> PG 相关依赖仅 `query_db.py` 和 `hub_adapter.py` 使用。核心爬虫 `xyz.py` 不依赖 PG，PG 不可用时爬取功能不受影响。

### 配置为 Agent Skill

将本项目添加到你的 Agent Skills 目录。具体安装方式请参考你所使用 Agent 平台的 Skill 安装文档。

本项目遵循 [AgentSkills 标准](https://github.com/anthropics/skills)，核心入口为 `SKILL.md`。

### 首次登录

**方式一：ADB 自动提取（推荐）**

1. 安装 [MuMu 模拟器](https://mumu.163.com/)（Android 12 版本）
2. 在模拟器内安装小宇宙 App 并用手机号登录
3. 运行：

```bash
python scripts/xyz.py login --adb
```

预期输出：
```
ADB 工具: C:\Program Files\Netease\MuMu\nx_main\adb.exe
使用设备: 127.0.0.1:7555
Root 权限已获取 (模式: ADB Root)
正在提取凭据...
  提取成功 (策略: XML 批量读取)
  refresh_token: eyJhbGciOiJIUzI1NiIs...
  device_id:     xxxxxxxx

登录成功!
  Token 已保存到: ~/.xiaoyuzhou/credentials.json
```

**方式二：手动输入凭据**

```bash
python scripts/xyz.py login \
  --refresh-token <从小宇宙 App 抓包获取的 refresh_token> \
  --device-id <对应的 device_id>
```

> **注意**：短信验证码登录已失效（API 返回错误 1003），请使用以上两种方式。

---

## 📖 使用指南

### 搜索播客

```bash
# 默认先搜 iTunes，无结果时自动 fallback 到小宇宙搜索
python scripts/xyz.py search "忽左忽右"

# 强制使用小宇宙搜索（可搜到独占播客，需登录）
python scripts/xyz.py search "科技前哨" -x
```

### 查看播客与节目列表

```bash
python scripts/xyz.py podcast <播客ID或URL>
python scripts/xyz.py episodes <播客ID> --max-pages 3
```

支持传入完整 URL（如 `https://www.xiaoyuzhoufm.com/podcast/xxxxx`）或纯 ID。

### 获取单集详情

```bash
python scripts/xyz.py episode <单集ID或URL>
```

### 下载音频

```bash
python scripts/xyz.py download <单集ID> -o ./output
python scripts/xyz.py download <单集ID> -o ./output --with-subtitles  # 同时下载字幕
python scripts/xyz.py download <单集ID> -o ./output --force           # 强制重新下载
```

### 获取字幕

```bash
python scripts/xyz.py subtitles <单集ID> -f srt   # SRT 格式
python scripts/xyz.py subtitles <单集ID> -f txt   # 纯文本
python scripts/xyz.py subtitles <单集ID> -f json  # 原始 JSON
python scripts/xyz.py subtitles <单集ID>           # 全部格式
```

### 批量爬取

#### 逐集爬取 + 后处理（推荐）

```bash
# 1. 获取播客信息和节目列表
python scripts/xyz.py podcast <播客ID>
python scripts/xyz.py episodes <播客ID> --max-pages 3

# 2. 按发布日期从旧到新排序，逐集处理
python scripts/xyz.py crawl-one <单集ID> --seq 1 -o "./output/<播客名>"
python scripts/xyz.py crawl-one <单集ID> --seq 2 -o "./output/<播客名>"
# ... 每爬完一集立即后处理，再爬下一集
```

#### 批量爬取（一次性）

```bash
# 爬取最新 10 集
python scripts/xyz.py crawl <播客ID> -n 10 -o ./output

# 指定转录模型（默认 base）
python scripts/xyz.py crawl <播客ID> --whisper-model small

# 限制单集转录时间（秒，0=无限制）
python scripts/xyz.py crawl <播客ID> --transcribe-timeout 600

# 重新开始（忽略已有进度）
python scripts/xyz.py crawl <播客ID> --reset

# 爬取结束后自动导出 CSV
python scripts/xyz.py crawl <播客ID> --csv -o ./output
```

#### 爬取策略

**两轮扫描**：
1. **第 1 轮（快速）**：遍历所有目标集，有内置字幕的直接保存为 `.md`
2. **第 2 轮（慢速）**：无字幕的下载音频 → ffmpeg 转码 → faster-whisper 转录 → 保存

#### 输出目录结构

```
output/
└── 播客名/
    ├── podcast_info.json        # 播客元信息
    ├── 01_2024-06-17_标题.md    # 最早（按发布日期升序编号）
    ├── 02_2024-07-10_标题.md
    ├── ...
    ├── 10_2025-01-23_标题.md    # 最新
    ├── audio/                   # 音频文件（m4a）+ 临时转码（wav）
    ├── crawl_state.json         # 爬取进度（支持断点续爬）
    └── <播客名>_飞书导入.csv    # CSV 导出（--csv 时生成）
```

#### Markdown 输出格式

每集输出一个 `.md` 文件，结构如下：

```markdown
# 单集标题

- **播客**: 播客名
- **发布日期**: 2025-01-23
- **时长**: 45分30秒
- **内容来源**: 内置字幕 / 音频转录
- **单集ID**: 69faa7b2e05c0efcd6f16f30
- **主播/嘉宾**:
  - 嘉宾名 — 简介

## 简介

本集概要描述...（API 无数据时标注 [待补充]）

## 时间轴

00:00 开场话题
02:30 第一个讨论点
...

## 正文

### 00:00 开场话题

正文内容...

### 02:30 第一个讨论点

正文内容...
```

#### Whisper 模型选择

| 模型 | 转录速度 | 中文质量 | 适用场景 |
|------|---------|---------|---------|
| tiny | 最快 | 差 | 快速测试 |
| **base** | **快** | **一般** | **默认** |
| small | 中等 | 良好 | 中文推荐 |
| medium | 慢 | 很好 | 追求质量 |
| large-v3 | 最慢 | 最佳 | 最终版本 |

转录耗时参考（CPU）：

| 音频时长 | base 模型 | small 模型 |
|---------|----------|-----------|
| 10 分钟 | ~60 秒 | ~2 分钟 |
| 30 分钟 | ~3 分钟 | ~8 分钟 |
| 50 分钟 | ~6-8 分钟 | ~15 分钟 |
| 120 分钟 | ~15-20 分钟 | ~40 分钟 |

> **转录超时说明**：`--transcribe-timeout` 默认值为 **0（无限制）**。转录是 CPU 密集型任务，请预留充足时间。如需设置超时，建议 30 分钟音频 ≥ 600 秒，60 分钟以上 ≥ 1800 秒或不限制。

### 数据库查询

已爬取的内容会同步到 PostgreSQL 数据库（通过 `hub_adapter.py`），可使用 `query_db.py` 进行只读查询：

```bash
# 查看统计概览
python scripts/query_db.py stats

# 列出所有播客
python scripts/query_db.py podcasts

# 搜索播客
python scripts/query_db.py podcasts --search "AI"

# 查询节目（按播客、关键词、状态、日期范围过滤）
python scripts/query_db.py episodes --podcast <PID> --limit 10
python scripts/query_db.py episodes --search "Agent" --status ready
python scripts/query_db.py episodes --since 2025-01-01 --until 2025-06-01

# 查看单集完整正文
python scripts/query_db.py episodes --id <EID> --full
```

> 完整查询文档见 **`SKILL_QUERY.md`**。数据库连接配置见 **`SKILL_SETUP.md`**。

### 多账号与并行爬取

利用 MuMu 模拟器多开实例，多个账号同时爬取不同集数：

```bash
# 1. 登录多个账号（MuMu 实例端口 7555、7556...）
python scripts/xyz.py login --adb --device 127.0.0.1:7555 --account phone1
python scripts/xyz.py login --adb --device 127.0.0.1:7556 --account phone2

# 2. 列出已登录账户
python scripts/xyz.py list-accounts

# 3. 并行爬取
python scripts/xyz.py crawl-one <eid1> --seq 1 --account phone1 -o "./output/播客名" &
python scripts/xyz.py crawl-one <eid2> --seq 2 --account phone2 -o "./output/播客名" &
wait
```

### 守护进程模式（serve）

自动循环爬取，适合长期无人值守运行：

```bash
# 每 6 小时爬取一次，每次最多 10 集
python scripts/xyz.py serve --pids <PID1> <PID2> --interval 6

# 自定义参数
python scripts/xyz.py serve \
  --pids <PID1> <PID2> \
  --interval 4 \
  --max-episodes 5
```

- Token 自动刷新，失败时写入 `crawler_alerts.jsonl` 告警
- 支持 `Ctrl+C` (SIGINT) 优雅退出

### CSV 导出（飞书表格导入）

```bash
# 爬取时自动导出
python scripts/xyz.py crawl <播客ID> --csv -o ./output

# 逐集追加 CSV
python scripts/xyz.py crawl-one <单集ID> --seq 1 --csv -o "./output/<播客名>"

# 对已有 MD 文件批量导出
python scripts/xyz.py export "./output/<播客名>"
```

**CSV 列定义**（11 列）：

| 列名 | 说明 |
|------|------|
| 序号 | 按发布日期排序的编号 |
| 标题 | 单集标题 |
| 发布日期 | YYYY-MM-DD |
| 时长 | 如"23分49秒" |
| 主播/嘉宾 | 多个用换行分隔 |
| 简介 | 完整简介文本 |
| 时间轴 | `MM:SS 标题` 格式，多行 |
| 正文 | 完整正文（含 `###` 分节标题） |
| 单集ID | 24 位 hex |
| 内容来源 | 内置字幕 / 音频转录 |
| 播客 | 播客名称 |

**飞书导入步骤**：
1. 打开飞书多维表格 → 点击「导入」→ 选择 CSV 文件
2. 确认编码 UTF-8，分隔符为逗号
3. 映射列（自动识别），时间轴和正文列设为「多行文本」类型
4. 导入完成

### Token 管理

```bash
python scripts/xyz.py token            # 查看状态
python scripts/xyz.py token --refresh  # 手动刷新
python scripts/xyz.py token --verify   # 验证有效性
```

Token 在 API 返回 401 时会自动刷新。`refresh_token` 过期后需重新登录。

---

## 📋 CLI 参考

### xyz.py（核心工具）

| 子命令 | 功能 | 需要登录 |
|--------|------|:---:|
| `login --adb` | ADB 自动提取凭据登录（推荐） | — |
| `login -t TOKEN -d ID` | 手动输入凭据登录 | — |
| `list-accounts` | 列出所有已登录账户 | — |
| `search <关键词> [-x]` | 搜索播客（iTunes + 小宇宙 fallback） | 小宇宙搜索需要 |
| `token [--refresh\|--verify]` | 查看/刷新/验证 Token | 是 |
| `podcast <ID/URL>` | 播客详情 | 是 |
| `episodes <ID> [--max-pages N]` | 节目列表（支持分页） | 是 |
| `episode <ID/URL>` | 单集详情（含字幕数据） | 是 |
| `download <ID> [-o DIR] [--with-subtitles] [--force]` | 下载音频（断点续传） | 是 |
| `subtitles <ID> [-f srt\|txt\|json\|all]` | 获取字幕 | 是 |
| `setup` | 预下载 Whisper 模型 | — |
| `crawl <ID> [-n N] [-o DIR] [--csv] [--whisper-model M] [--transcribe-timeout S] [--reset]` | 批量爬取播客 | 是 |
| `crawl-one <ID> --seq N [-o DIR] [--csv] [--whisper-model M] [--transcribe-timeout S]` | 处理单集（逐集爬取） | 是 |
| `export <DIR>` | 将已有 MD 文件导出为 CSV | — |
| `serve --pids PID... [--interval H] [--max-episodes N]` | 守护进程模式 | 是 |

所有命令支持 `--account NAME` / `-A NAME` 指定多账号。

### query_db.py（数据库查询）

| 子命令 | 功能 |
|--------|------|
| `podcasts [--search KEYWORD]` | 列出/搜索播客 |
| `episodes [--podcast PID] [--search KW] [--since DATE] [--until DATE] [--status S] [--id EID] [--full] [--limit N]` | 查询节目 |
| `stats` | 统计概览 |

---

## 📁 项目结构

```
xiaoyuzhou-skill/
├── SKILL.md              # Skill 配置文件（Agent 平台读取）
├── SKILL_SETUP.md        # 环境安装指引（venv、依赖、.env、模型、DB）
├── SKILL_QUERY.md        # 数据库只读查询 Skill
├── README.md             # 本文件
├── reference.md          # API 端点参考（按需加载）
├── .env.example          # 环境变量模板（PG 连接信息）
├── requirements.txt      # Python 依赖（含 PG 驱动）
├── schema.sql            # 数据库表定义（v2，xiaoyuzhou_ 前缀，三表分离）
├── scripts/
│   ├── xyz.py            # 主工具（所有子命令，~2400 行）
│   ├── query_db.py       # 数据库只读查询工具
│   └── extract_creds.py  # ADB 凭据提取工具
├── output/               # 运行时输出（已 gitignore）
└── downloads/            # 下载音频缓存（已 gitignore）
```

仓库根目录另有：
- `hub_adapter.py` — Financial Hub 集成（crawl 生命周期 + PG 同步）
- `schema_v2.sql` — 与 skill 内 `schema.sql` 相同的表定义
- `requirements-hub.txt` — Hub 集成额外依赖

---

## 🔧 技术架构

```
用户指令 / Agent
       │
       ▼
┌──────────────────────────────────────────────────┐
│                    xyz.py (CLI)                   │
│  login │ search │ podcast │ episode │ download   │
│  subtitles │ crawl │ crawl-one │ export │ serve  │
└──────────────────────┬───────────────────────────┘
                       │
         ┌─────────────┼─────────────┐
         ▼             ▼             ▼
    ┌─────────┐  ┌──────────┐  ┌──────────┐
    │ iTunes  │  │ 小宇宙    │  │ faster-  │
    │ API     │  │ API      │  │ whisper  │
    └─────────┘  └──────────┘  └──────────┘
         │             │             │
         └─────────────┼─────────────┘
                       │
                       ▼
              ┌─────────────────┐
              │  本地输出        │
              │  .md + audio/   │
              │  + crawl_state  │
              └────────┬────────┘
                       │
                       ▼
              ┌─────────────────┐
              │  hub_adapter.py │  ← 仓库根目录
              │  crawl 生命周期  │
              │  PG 同步写入     │
              └────────┬────────┘
                       │
                       ▼
              ┌─────────────────┐
              │  PostgreSQL      │
              │  xiaoyuzhou_*   │
              │  crawl_targets  │
              │  crawl_runs     │
              └────────┬────────┘
                       │
                       ▼
              ┌─────────────────┐
              │  query_db.py    │
              │  只读查询        │
              │  (hub_readonly) │
              └─────────────────┘
```

### 数据存储三层架构

| 层级 | 组件 | 存储 | 读/写 |
|------|------|------|:---:|
| 爬取层 | `xyz.py` | 本地 `.md` + `audio/` | 写 |
| 同步层 | `hub_adapter.py` | PostgreSQL (`xiaoyuzhou_*`) | 写 |
| 查询层 | `query_db.py` | PostgreSQL (`xiaoyuzhou_*`) | 只读 |

核心爬虫 `xyz.py` 不直接访问 PG。PG 不可用时爬取功能不受影响，只是无法使用 `query_db.py` 和 Hub 集成。

---

## ❓ 常见问题

### 登录与认证

| 问题 | 解决方案 |
|------|---------|
| 短信登录失败 (error 1003) | 短信登录已封禁，使用 `login --adb` 或手动抓包 |
| ADB 连不上设备 | 确保模拟器已启动；尝试端口 7555（MuMu）、62001（夜神）、5555 |
| MuMu 找不到 ADB | 通常在 `C:\Program Files\Netease\MuMu\nx_main\adb.exe` |
| `su` 命令失败 | MuMu 默认 `adb root` 不需要 su；夜神需在设置中开启 Root |
| device_id 不匹配 | `refresh_token` 和 `device_id` 必须来自同一设备同一登录会话 |
| Token 过期 | 重新运行 `login --adb` |

### 转录

| 问题 | 解决方案 |
|------|---------|
| HuggingFace 下载超时 | 已内置 `hf-mirror.com` 镜像，自动使用 |
| `libiomp5md.dll` 报错 | 已内置 `KMP_DUPLICATE_LIB_OK=TRUE` 环境变量 |
| 转录中文质量差 | 使用 small 或以上模型，tiny/base 对中文效果不好 |
| 转录超时 | 默认无超时限制（0）。如需设置，确保 ≥ 实际转录时间 |
| ffmpeg 找不到 | 确认 ffmpeg 在 PATH 中：`ffmpeg -version` |

### 数据库

| 问题 | 解决方案 |
|------|---------|
| `query_db.py` 连接失败 | 检查 `.env` 文件是否存在且配置正确（参考 `.env.example`） |
| `hub_readonly` 用户不存在 | 运行 `SKILL_SETUP.md` Step 6 创建只读用户 |
| PG 不可用影响爬取吗？ | 不影响。`xyz.py` 核心爬虫不依赖 PG，仅 `query_db.py` 查询功能受影响 |
| 飞书 CSV 乱码 | 文件已包含 UTF-8 BOM，导入时确认编码为 UTF-8 |

### 其他

| 问题 | 解决方案 |
|------|---------|
| 多账号配置文件在哪？ | 默认 `~/.xiaoyuzhou/credentials.json`，命名账户 `~/.xiaoyuzhou/profiles/<名称>.json` |
| 如何并行爬取？ | 使用不同 `--account` 参数并行运行多个 `crawl-one` 进程 |
| 断点续爬怎么恢复？ | `crawl_state.json` 自动记录进度，重新运行 `crawl` 即可继续 |
| HTTP 407 错误 | 某些 Windows 代理导致，尝试关闭系统代理或设置 `--mode android` |

---

## ⚠️ 重要注意事项

### 逐集后处理（必须）

批量爬取时，**必须逐集后处理**，禁止批量堆到最后再做：

```
✅ 正确流程：
crawl-one 第1集 → 后处理第1集 → crawl-one 第2集 → 后处理第2集 → ...

❌ 错误流程：
crawl-one 第1集 → crawl-one 第2集 → crawl-one 第3集 → 后处理所有集
```

原因：
- 单集后处理（修正转录、生成时间轴、分节）可能消耗大量上下文窗口
- 批量堆叠导致用户长时间看不到产出
- 逐集输出让用户可以随时中断，已完成的不受影响

### 后处理内容

每集 `.md` 文件输出后，需要进行以下后处理：

1. **修正转录文本**（仅音频转录需要）— 添加标点断句、修正识别错误（人名、术语等）
2. **生成时间轴** — `MM:SS 话题标题` 格式（超过 1 小时用 `HH:MM:SS`），通常 8-15 条
3. **按时间轴分节** — 正文用 `### MM:SS 话题标题` 分节，与时间轴一一对应
4. **补充简介** — 如果 API 没有返回 description，根据正文生成摘要

---

## 📄 License

MIT License — 仅供学习交流使用。请遵守小宇宙平台的使用条款，合理使用 API。
