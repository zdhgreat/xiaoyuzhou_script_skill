<div align="center">

# 🎙️ 小宇宙播客爬虫

**Claude Code Skill — 通过小宇宙官方 API 搜索、浏览、下载播客内容，支持批量爬取与音频转录**

[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![AgentSkills Standard](https://img.shields.io/badge/AgentSkills-Standard-green.svg)](https://github.com/anthropics/skills)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**多平台兼容**：Claude Code · Hermes · OpenClaw · Codex

[English](#english) · [功能概览](#-功能概览) · [快速开始](#-快速开始) · [使用指南](#-使用指南) · [CLI 参考](#-cli-参考) · [常见问题](#-常见问题)

</div>

---

## ✨ 功能概览

| 功能 | 描述 |
|------|------|
| **ADB 一键登录** | 自动从 MuMu/夜神模拟器提取 `refresh_token` + `device_id`，无需手动抓包 |
| **智能搜索** | 默认走 iTunes API（无需登录），无结果自动 fallback 到小宇宙搜索 |
| **单集详情** | 获取元信息、内置字幕、付费内容音频 URL |
| **音频下载** | 断点续传、付费内容自动获取私链 |
| **批量爬取** | 字幕优先 + faster-whisper 本地转录兜底，逐集后处理立即输出 |
| **音频转录** | 支持 tiny/base/small/medium/large-v3 五档模型，subprocess 真超时控制 |
| **CSV 导出** | 一键导出飞书多维表格导入格式（UTF-8 BOM，RFC 4180 标准） |
| **Token 自动管理** | 401 自动刷新，支持手动检查/刷新/验证 |

## 🚀 快速开始

### 环境要求

- **Python 3.10+**
- **ffmpeg**（音频转录需要）— Windows: `winget install ffmpeg`
- **ADB 工具**（自动登录需要）— MuMu 模拟器自带，或安装 Android SDK Platform Tools

### 安装

```bash
# 克隆仓库
git clone https://github.com/<your-username>/xiaoyuzhou-skill.git
cd xiaoyuzhou-skill

# 安装依赖
pip install requests

# （可选）音频转录功能
pip install faster-whisper
```

### 配置为 Claude Code Skill

将本项目添加到你的 Claude Code Skills 目录：

```bash
# 方式一：直接复制到 skills 目录
cp -r . ~/.claude/skills/xiaoyuzhou

# 方式二：在 Claude Code 设置中指定路径
# 编辑 ~/.claude/settings.json，将 scripts 路径加入 allowedTools
```

其他 Agent 平台（Hermes、OpenClaw、Codex）请参考各自的 Skill 安装方式。本项目遵循 [AgentSkills 标准](https://github.com/anthropics/skills)，核心入口为 `SKILL.md`。

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

**方式二：手动抓包**

```bash
pip install mitmproxy
mitmweb -p 8080
# 在模拟器中设置 WiFi 代理为电脑 IP:8080
# 打开小宇宙 App 随便浏览
# 在 http://127.0.0.1:8081 找到 api.xiaoyuzhoufm.com 的请求
# 复制 x-jike-refresh-token 和 x-jike-device-id

python scripts/xyz.py login -t <refresh_token> -d <device_id>
```

> **注意**：短信验证码登录已失效（API 返回错误 1003），请使用以上两种方式。

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

# 指定转录模型
python scripts/xyz.py crawl <播客ID> --whisper-model small

# 无字幕时跳过转录
python scripts/xyz.py crawl <播客ID> --no-transcribe

# 重新开始（忽略已有进度）
python scripts/xyz.py crawl <播客ID> --reset

# 爬取结束后自动导出 CSV
python scripts/xyz.py crawl <播客ID> --csv -o ./output
```

#### 爬取策略

**两轮扫描**：
1. **第 1 轮（快速）**：遍历所有目标集，有内置字幕的直接保存
2. **第 2 轮（慢速）**：无字幕的下载音频，用 faster-whisper 本地转录

#### 输出目录结构

```
output/
└── 播客名/
    ├── 01_2024-06-17_标题.md     # 最早（按发布日期排序）
    ├── 02_2024-07-10_标题.md
    ├── ...
    ├── 10_2025-01-23_标题.md     # 最新
    ├── audio/                    # 音频文件（m4a）
    └── crawl_state.json          # 爬取进度（支持断点续爬）
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

本集概要描述...

## 时间轴

00:00 开场话题
02:30 第一个讨论点
05:00 第二个讨论点
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

## 📋 CLI 参考

| 子命令 | 功能 | 需要登录 |
|--------|------|----------|
| `login --adb` | ADB 自动提取凭据登录（推荐） | 否 |
| `login -t TOKEN -d ID` | 手动输入凭据登录 | 否 |
| `search <关键词>` | 搜索播客（iTunes + 小宇宙 fallback） | 否（小宇宙搜索需登录） |
| `token` | 查看 Token 状态 | 是 |
| `token --refresh` | 手动刷新 Token | 是 |
| `token --verify` | 验证 Token 有效性 | 是 |
| `podcast <ID/URL>` | 播客详情 | 是 |
| `episodes <ID> [--max-pages N]` | 节目列表（支持分页） | 是 |
| `episode <ID/URL>` | 单集详情（含字幕数据） | 是 |
| `download <ID> [-o DIR] [--with-subtitles] [--force]` | 下载音频（断点续传） | 是 |
| `subtitles <ID> [-f srt/txt/json]` | 获取字幕 | 是 |
| `crawl <ID> [-n N] [-o DIR] [--csv] [--whisper-model MODEL] [--no-transcribe] [--transcribe-timeout SEC] [--reset]` | 批量爬取播客 | 是 |
| `crawl-one <ID> --seq N [-o DIR] [--csv] [--whisper-model MODEL] [--no-transcribe] [--transcribe-timeout SEC]` | 处理单集（逐集爬取） | 是 |
| `export <DIR>` | 将已有 MD 文件导出为 CSV | 否 |

## 📁 项目结构

```
xiaoyuzhou-skill/
├── SKILL.md              # Skill 配置文件（Claude Code / Agent 平台读取）
├── README.md             # 本文件
├── reference.md          # API 端点参考（按需加载）
├── requirements.txt      # Python 依赖
├── scripts/
│   ├── xyz.py            # 主工具（所有子命令，~2100 行）
│   └── extract_creds.py  # ADB 凭据提取工具
└── output/               # 运行时输出（已 gitignore）
```

## 🔧 技术架构

```
用户指令
   │
   ▼
┌──────────┐     ┌─────────────┐     ┌──────────────┐
│  Search  │────▶│   iTunes    │────▶│  Fallback:   │
│  搜索    │     │   API       │     │  小宇宙搜索   │
└──────────┘     └─────────────┘     └──────────────┘
                                          │
                                          ▼
┌──────────┐     ┌─────────────┐     ┌──────────────┐
│  Crawl   │────▶│  字幕检测   │────▶│  有字幕:     │
│  爬取    │     │             │     │  直接保存    │
└──────────┘     └─────────────┘     └──────────────┘
                       │                    │
                       ▼                    ▼
                 ┌─────────────┐     ┌──────────────┐
                 │  无字幕:    │     │  后处理      │
                 │  Whisper转录│     │  时间轴+分节 │
                 └─────────────┘     └──────────────┘
                                          │
                                          ▼
                                   ┌──────────────┐
                                   │  MD + CSV    │
                                   │  双格式输出   │
                                   └──────────────┘
```

## ❓ 常见问题

| 问题 | 解决方案 |
|------|---------|
| 短信登录失败 (error 1003) | 短信登录已封禁，使用 `login --adb` 或手动抓包 |
| ADB 连不上设备 | 确保模拟器已启动；尝试端口 7555（MuMu）、62001（夜神）、5555 |
| MuMu 找不到 ADB | 通常在 `C:\Program Files\Netease\MuMu\nx_main\adb.exe` |
| `su` 命令失败 | MuMu 默认 `adb root` 不需要 su；夜神需在设置中开启 Root |
| device_id 不匹配 | `refresh_token` 和 `device_id` 必须来自同一设备同一登录 |
| Token 过期 | 重新运行 `login --adb` |
| HuggingFace 下载超时 | 已内置 `hf-mirror.com` 镜像，自动使用 |
| `libiomp5md.dll` 报错 | 已内置 `KMP_DUPLICATE_LIB_OK=TRUE` 环境变量 |
| 转录中文质量差 | 使用 small 或以上模型，tiny/base 对中文效果不好 |
| 转录超时 | 默认无超时限制（0）。如需设置，确保 ≥ 实际转录时间 |
| 飞书 CSV 乱码 | 文件已包含 UTF-8 BOM，导入时确认编码为 UTF-8 |

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
- 单集后处理可能消耗大量上下文窗口
- 批量堆叠导致用户长时间看不到产出
- 逐集输出让用户可以随时中断，已完成的不受影响

### 后处理内容

每集 `.md` 文件输出后，需要进行以下后处理：

1. **修正转录文本**（仅音频转录需要）— 添加标点断句、修正识别错误
2. **生成时间轴** — `MM:SS 话题标题` 格式（超过 1 小时用 `HH:MM:SS`）
3. **按时间轴分节** — 正文用 `### MM:SS 话题标题` 分节，与时间轴一一对应
4. **补充简介** — 如果 API 没有返回 description，根据正文生成摘要

## 📄 License

MIT License — 仅供学习交流使用。请遵守小宇宙平台的使用条款，合理使用 API。
