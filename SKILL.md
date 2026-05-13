---
name: xiaoyuzhou
description: |
  搜索、浏览和下载小宇宙播客内容。使用小宇宙官方 API 获取完整数据。
  支持功能：ADB自动凭据提取、refresh_token+device_id 登录、搜索播客、浏览节目列表、
  获取单集详情、下载音频文件（断点续传）、获取字幕并转换为 SRT/TXT 格式、
  批量爬取播客（字幕优先，音频转录兜底，逐集后处理立即输出）、faster-whisper 本地音频转录。
  用户可以说"下载小宇宙播客"、"获取小宇宙字幕"、"搜索播客XXX"、
  "帮我登录小宇宙"、"爬取这个播客"等来触发。
  注意：短信验证码登录已失效（API 返回错误 1003），推荐使用 ADB 自动提取方式登录。
allowed-tools: ["Bash", "Read", "Write"]
---

# 小宇宙播客 Skill

通过小宇宙官方 API 搜索、浏览和下载播客内容，支持批量爬取与音频转录。

## 前置条件

- Python 3.10+
- **核心依赖**: `pip install requests`
- **音频转录**（可选）: `pip install faster-whisper` + 系统安装 `ffmpeg`
- ADB 工具（用于 `--adb` 自动提取模式）：MuMu 模拟器自带 adb（推荐），夜神模拟器自带 nox_adb，或安装 Android SDK Platform Tools

## 核心脚本

```
${CLAUDE_SKILL_DIR}/scripts/xyz.py          # 主工具（所有功能）
${CLAUDE_SKILL_DIR}/scripts/extract_creds.py # ADB 凭据提取工具
```

所有功能通过子命令调用：

| 子命令 | 功能 | 需要登录 |
|--------|------|----------|
| `login --adb` | 从 ADB 设备自动提取凭据登录（推荐） | 否 |
| `login -t TOKEN -d ID` | 手动输入凭据登录 | 否 |
| `search` | 搜索播客 | 否 |
| `token` | 检查/刷新 token | 已登录 |
| `podcast` | 播客详情 | 是 |
| `episodes` | 节目列表 | 是 |
| `episode` | 单集详情 | 是 |
| `download` | 下载音频 | 是 |
| `subtitles` | 获取字幕 | 是 |
| `crawl` | 批量爬取播客（字幕优先+转录兜底，逐集后处理） | 是 |
| `crawl-one` | 处理单集（供逐集爬取+后处理使用） | 是 |

## 工作流程

### 第一步：登录（首次使用）

**短信验证码登录已失效**（API 返回错误 1003），推荐使用以下两种方式之一：

#### 方式一：ADB 自动提取（推荐，一键登录）

前提：MuMu/夜神模拟器或真机上已安装小宇宙 App 并已登录。

```bash
python "${CLAUDE_SKILL_DIR}/scripts/xyz.py" login --adb
```

自动检测 ADB 设备，提取 `refresh_token` 和 `device_id`，保存并验证。

也可以单独运行提取工具：
```bash
python "${CLAUDE_SKILL_DIR}/scripts/extract_creds.py --verify"
```

#### 方式二：手动输入凭据

```bash
python "${CLAUDE_SKILL_DIR}/scripts/xyz.py" login \
  --refresh-token <从抓包获取的refresh_token> \
  --device-id <从抓包获取的device_id>
```

Token 保存在 `~/.xiaoyuzhou/credentials.json`，后续自动使用。

### 第二步：搜索播客

```bash
python "${CLAUDE_SKILL_DIR}/scripts/xyz.py" search "播客名"
```

通过 iTunes API 搜索，不需要登录。

### 第三步：浏览节目

```bash
# 获取播客信息
python "${CLAUDE_SKILL_DIR}/scripts/xyz.py" podcast <播客ID或URL>

# 获取节目列表（支持分页）
python "${CLAUDE_SKILL_DIR}/scripts/xyz.py" episodes <播客ID> --max-pages 3
```

### 第四步：获取详情或下载

```bash
# 获取单集详情（含字幕数据）
python "${CLAUDE_SKILL_DIR}/scripts/xyz.py" episode <单集ID或URL>

# 下载音频
python "${CLAUDE_SKILL_DIR}/scripts/xyz.py" download <单集ID> -o ./output --with-subtitles

# 单独获取字幕
python "${CLAUDE_SKILL_DIR}/scripts/xyz.py" subtitles <单集ID> -f srt
```

### 第五步：批量爬取（逐集处理）

**推荐方式：逐集爬取+后处理**（用户可以每爬完一集就看到结果）

步骤：
1. 获取播客信息和节目列表：
```bash
python "${CLAUDE_SKILL_DIR}/scripts/xyz.py" podcast <播客ID>
python "${CLAUDE_SKILL_DIR}/scripts/xyz.py" episodes <播客ID> --max-pages 3
```

2. 根据节目列表，按发布日期从旧到新排序，确定每集的序号（01, 02, ...）

3. **逐集处理**——对每一集重复以下步骤：
```bash
# 处理单集（自动检测字幕/转录）
python "${CLAUDE_SKILL_DIR}/scripts/xyz.py" crawl-one <单集ID> --seq <序号> -o "./output/<播客名>"
```
   - 读取输出的 `.md` 文件
   - 立即后处理（见下方"单集后处理"）
   - 向用户报告该集完成
   - 继续下一集

**单集后处理**（每集爬取完成后必须立即执行）：
- `[待补充]` 的简介 → 根据正文生成摘要
- `[待补充]` 的时间轴 → 根据正文生成章节摘要
- 音频转录文本 → 添加标点、修正识别错误、按话题分段（内置字幕无需此步）
- 缺少嘉宾简介 → 根据内容识别并补充
- 保存增强后的文件后，报告给用户

**备选方式：批量 crawl**（一次性爬取所有集，后处理在全部完成后进行）
```bash
python "${CLAUDE_SKILL_DIR}/scripts/xyz.py" crawl <播客ID> -n 10 -o ./output --whisper-model small
```

**输出文件**（按播客名建文件夹，按发布日期排序）：
```
output/
└── AI局内人 | AGI Insider/           # 播客名作为文件夹
    ├── 01_2024-06-17_Vol20...md     # 最早期 = 01
    ├── 02_2024-07-10_Vol21...md
    ├── ...
    ├── 15_2025-01-23_Vol28...md     # 最新
    ├── audio/                       # 音频文件
    └── crawl_state.json             # 爬取进度（crawl 模式）
```
- `NN_YYYY-MM-DD_标题.md` — Markdown 文件，包含：
  - 元信息：播客名、发布日期、时长、主播/嘉宾（昵称+简介）
  - 简介：来自 API，缺少时标注 `[待补充]` 需根据正文生成
  - 时间轴：来自 Shownotes（嘉宾介绍、章节时间点），缺少时标注 `[待补充]`
  - 正文：字幕文本或转录文本

**转录文本说明**：
- 内置字幕：有标点断句，质量高，通常只需补充简介/时间轴
- 音频转录：原始文本**无标点断句**，可能存在识别错误（人名、术语等），需要重点后处理

**其他输出**：
- `audio/` — 下载的音频文件（m4a）
- `crawl_state.json` — 爬取状态（crawl 批量模式支持断点续爬）

## Token 管理

Token 会在 API 返回 401 时自动刷新，通常不需要手动操作。

```bash
python "${CLAUDE_SKILL_DIR}/scripts/xyz.py" token
python "${CLAUDE_SKILL_DIR}/scripts/xyz.py" token --refresh
python "${CLAUDE_SKILL_DIR}/scripts/xyz.py" token --verify
```

## Gotchas（已知坑）

| 坑 | 说明 |
|----|------|
| 短信登录已失效 | sendCode API 返回错误 1003，推荐使用 `--adb` 自动提取方式登录 |
| ADB 自动提取 | 需要 Root 权限（MuMu 模拟器默认 adb root，夜神需手动开启） |
| Token 位置 | iOS 模式 token 在 response body，Android 模式在 response headers |
| SSL 验证 | API 请求需关闭 SSL 验证（verify=False），脚本已处理 |
| device_id 必须匹配 | refresh_token 和 device_id 必须来自同一设备/同一会话 |
| 付费内容 | 自动通过 /v1/private-media/get 获取付费音频 URL |
| 分页 | 使用 loadMoreKey，每页建议间隔 0.5 秒 |
| 字幕格式 | API 返回词级 JSON，脚本自动按 500ms 间隔分组合成 SRT |
| 搜索 | 小宇宙 API 无搜索端点，使用 iTunes API 替代 |
| 转录耗时 | small 模型转录 120 分钟音频约需 40 分钟（CPU） |
| 转录依赖 | 需要安装 faster-whisper 和 ffmpeg，中国大陆需设置 HF_ENDPOINT |
| 环境变量 | 中国大陆需设置 `HF_ENDPOINT=https://hf-mirror.com`（脚本已内置） |

## Hard Stop 规则

- API 调用失败时自动跳过该集，继续处理下一集
- 登录时验证码发送失败，不重试（避免短信轰炸）
- 下载中断后可使用断点续传恢复（默认开启）
- 爬取支持断点续爬（通过 crawl_state.json 记录进度）
