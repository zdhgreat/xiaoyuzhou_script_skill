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
- **环境配置**: 运行 SKILL_SETUP.md 完成依赖安装和 `.env` 配置
- **核心依赖**: `pip install -r requirements.txt`（含 faster-whisper, psycopg2-binary 等）
- **预下载模型**: `python xyz.py setup`
- **系统依赖**: `ffmpeg`（音频转录必需）
- ADB 工具（用于 `--adb` 自动提取模式）：MuMu 模拟器自带 adb（推荐），夜神模拟器自带 nox_adb，或安装 Android SDK Platform Tools

## 核心脚本

```
{baseDir}/scripts/xyz.py          # 主工具（所有爬取/操作功能）
{baseDir}/scripts/query_db.py     # 数据库只读查询工具
{baseDir}/scripts/extract_creds.py # ADB 凭据提取工具
```

> **数据库查询**：`query_db.py` 是独立的只读查询工具，完整文档见 `SKILL_QUERY.md`。

所有功能通过子命令调用（`xyz.py`）：

| 子命令 | 功能 | 需要登录 |
|--------|------|----------|
| `login --adb` | 从 ADB 设备自动提取凭据登录（推荐） | 否 |
| `login -t TOKEN -d ID` | 手动输入凭据登录 | 否 |
| `search` | 搜索播客（iTunes + 小宇宙 fallback） | 否（小宇宙搜索需登录） |
| `token` | 检查/刷新 token | 已登录 |
| `podcast` | 播客详情 | 是 |
| `episodes` | 节目列表 | 是 |
| `episode` | 单集详情 | 是 |
| `download` | 下载音频 | 是 |
| `subtitles` | 获取字幕 | 是 |
| `setup` | 预下载 Whisper 模型（安装时使用） | 否 |
| `crawl` | 批量爬取播客（字幕优先+转录兜底，逐集后处理） | 是 |
| `crawl-one` | 处理单集（供逐集爬取+后处理使用） | 是 |
| `export` | 将已有 .md 文件导出为 CSV（飞书导入格式） | 否 |
| `list-accounts` | 列出所有已登录账户 | 否 |
| `serve` | 守护进程模式：自动循环爬取 | 是 |

**多账号支持**：所有命令支持 `--account NAME` / `-A NAME` 参数，指定使用哪个账户。不指定时使用默认账户。

## 工作流程

### 第一步：登录（首次使用）

**短信验证码登录已失效**（API 返回错误 1003），推荐使用以下两种方式之一：

#### 方式一：ADB 自动提取（推荐，一键登录）

前提：MuMu/夜神模拟器或真机上已安装小宇宙 App 并已登录。

```bash
python "{baseDir}/scripts/xyz.py" login --adb
```

自动检测 ADB 设备，提取 `refresh_token` 和 `device_id`，保存并验证。

也可以单独运行提取工具：
```bash
python "{baseDir}/scripts/extract_creds.py" --verify
```

#### 方式二：手动输入凭据

```bash
python "{baseDir}/scripts/xyz.py" login \
  --refresh-token <从抓包获取的refresh_token> \
  --device-id <从抓包获取的device_id>
```

Token 保存在 `~/.xiaoyuzhou/credentials.json`，后续自动使用。

#### 多账号登录（MuMu 多开）

MuMu 模拟器支持多开实例（每个实例使用连续端口：7555、7556、7557...），每个实例可登录不同账号：

```bash
# 列出已登录账户
python "{baseDir}/scripts/xyz.py" list-accounts

# MuMu 实例1 (端口 7555) → 账号 phone1
python "{baseDir}/scripts/xyz.py" login --adb --device 127.0.0.1:7555 --account phone1

# MuMu 实例2 (端口 7556) → 账号 phone2
python "{baseDir}/scripts/xyz.py" login --adb --device 127.0.0.1:7556 --account phone2

# 使用指定账户操作
python "{baseDir}/scripts/xyz.py" search "播客名" --account phone1
python "{baseDir}/scripts/xyz.py" crawl-one <eid> --seq 1 --account phone2 -o "./output/播客名"
```

账户配置文件存储在 `~/.xiaoyuzhou/profiles/<账户名>.json`，默认账户仍在 `~/.xiaoyuzhou/credentials.json`。

### 第二步：搜索播客

```bash
# 默认先搜 iTunes，无结果时自动 fallback 到小宇宙搜索
python "{baseDir}/scripts/xyz.py" search "播客名"

# 强制使用小宇宙搜索（可搜到独占播客，需登录）
python "{baseDir}/scripts/xyz.py" search "播客名" -x
```

搜索流程：先走 iTunes API（无需登录，速度快），如果没找到结果，自动 fallback 到小宇宙原生搜索 API（需要登录）。

> **提示**：小宇宙播客 ID 为 24 位十六进制（如 `643928f99361a4e7c38a9555`），与 iTunes 纯数字 ID 不同。
> 如果知道播客链接，也可以直接提供 URL 或 ID，跳过搜索。

### 第三步：浏览节目

```bash
# 获取播客信息
python "{baseDir}/scripts/xyz.py" podcast <播客ID或URL>

# 获取节目列表（支持分页）
python "{baseDir}/scripts/xyz.py" episodes <播客ID> --max-pages 3
```

### 第四步：获取详情或下载

```bash
# 获取单集详情（含字幕数据）
python "{baseDir}/scripts/xyz.py" episode <单集ID或URL>

# 下载音频（默认启用断点续传）
python "{baseDir}/scripts/xyz.py" download <单集ID> -o ./output --with-subtitles

# 强制重新下载（忽略已存在文件）
python "{baseDir}/scripts/xyz.py" download <单集ID> -o ./output --force

# 单独获取字幕（默认输出全部格式：srt+txt+json）
python "{baseDir}/scripts/xyz.py" subtitles <单集ID> -f srt
```

### 第五步：批量爬取（逐集处理）

> **[重要] 必须逐集后处理，禁止批量堆到最后再做**
>
> 每爬完一集 → 立即后处理 → 保存 → 向用户报告 → 再爬下一集。
> **绝对不能**先把所有集爬完再统一后处理。原因：
> - 单集后处理（修正转录、生成时间轴、分节）可能消耗大量上下文窗口
> - 批量堆叠会导致等待时间极长，用户长时间看不到任何产出
> - 逐集输出让用户可以随时中断，已完成的不受影响
>
> 正确流程：`crawl-one 第1集` → `后处理第1集` → `crawl-one 第2集` → `后处理第2集` → ...
>
> 错误流程：~~`crawl-one 第1集` → `crawl-one 第2集` → `crawl-one 第3集` → `后处理所有集`~~

**推荐方式：逐集爬取+后处理**（用户可以每爬完一集就看到结果）

步骤：
1. 获取播客信息和节目列表：
```bash
python "{baseDir}/scripts/xyz.py" podcast <播客ID>
python "{baseDir}/scripts/xyz.py" episodes <播客ID> --max-pages 3
```

2. 根据节目列表，按发布日期从旧到新排序，确定每集的序号（01, 02, ...）

3. **逐集处理**——对每一集重复以下步骤：
```bash
# 处理单集（自动检测字幕/转录）
python "{baseDir}/scripts/xyz.py" crawl-one <单集ID> --seq <序号> -o "./output/<播客名>"

# 限制转录时间（10分钟超时）
python "{baseDir}/scripts/xyz.py" crawl-one <单集ID> --seq 1 --transcribe-timeout 600

# 指定 whisper 模型
python "{baseDir}/scripts/xyz.py" crawl-one <单集ID> --seq 1 --whisper-model tiny
```
> **注意**：`crawl-one` 的 `-o` 参数直接作为输出目录（不会自动创建播客名子文件夹），而 `crawl` 会自动在 `-o` 下创建播客名子文件夹。
   - 先保存元信息 .md，即使转录超时也不会丢失节目信息
   - 读取输出的 `.md` 文件
   - 立即后处理（见下方"单集后处理"）
   - 向用户报告该集完成
   - 继续下一集

**单集后处理**（每集爬取完成后**必须立即执行**）：

爬取输出的 .md 是原始数据，必须经过后处理才能成为成品文件。后处理步骤：

1. **修正转录文本**（仅音频转录需要，内置字幕可跳过）
   - 添加标点断句
   - 修正识别错误（人名、术语、品牌名等，如"规谷"→"硅谷"、"AZN"→"Agent"）
   - 保留对话格式（对话体播客保留 `问：/答：` 或自然对话流）

2. **生成时间轴**
   - 格式：`MM:SS 话题标题`（超过1小时的节目用 `HH:MM:SS`）
   - 每行一条，简洁的标题，不带描述
   - 根据正文内容按话题划分节点，估算每个话题开始的时间戳
   - 条目数量：通常 8-15 条（16分钟节目约10条，60分钟节目约12-15条）
   - **时间轴不能和简介内容重复**。如果 API 返回的 shownotes 和 description 内容相同，必须根据正文自己生成

3. **按时间轴分节**
   - 正文用 `### MM:SS 话题标题` 分节，每节标题**必须和时间轴条目一一对应**
   - 小节内保留完整对话内容，不做删减

4. **补充简介**（如果 API 没有返回 description）
   - 根据正文生成 1-3 句摘要

**后处理示例**（时间轴格式）：
```
## 时间轴

00:00 开场：AI Agent有能力却无合法身份
01:30 AI Agent的现状困境：想工作却没有身份
03:00 AI Agent技术突破：开源工具、MCP协议、A2A协议
05:00 核心障碍：AI缺少"经济身份证"

## 正文

### 00:00 开场：AI Agent有能力却无合法身份
（对应正文内容...）

### 01:30 AI Agent的现状困境：想工作却没有身份
（对应正文内容...）

### 03:00 AI Agent技术突破：开源工具、MCP协议、A2A协议
（对应正文内容...）
```

后处理完成后保存文件，向用户报告该集完成，继续下一集。

**备选方式：批量 crawl**（一次性爬取所有集，后处理在全部完成后进行）
```bash
python "{baseDir}/scripts/xyz.py" crawl <播客ID> -n 10 -o ./output --whisper-model base
```
- `-n` 获取最新 N 集（默认10），按发布日期升序编号
- `--whisper-model` 默认 base，可选 tiny/base/small/medium/large-v3
- `--transcribe-timeout` 限制单集转录时间（秒），0=无限制
- `--reset` 清除爬取进度，从头开始

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
  - 时间轴：`MM:SS 话题标题` 格式，根据正文按话题生成，正文用 `###` 分节对应
  - 正文：字幕文本或转录文本，按时间轴分节

**转录文本说明**：
- 内置字幕：有标点断句，质量高，通常只需补充简介/时间轴
- 音频转录：原始文本**无标点断句**，可能存在识别错误（人名、术语等），需要重点后处理

### 多账号并行爬取

> 使用多个小宇宙账号同时爬取不同集数，提高速度。

**前置条件**：已通过 MuMu 多开登录多个账号（见"多账号登录"章节）。

**并行爬取流程**：

1. 获取播客信息和节目列表（任意一个账号即可）：
```bash
python "{baseDir}/scripts/xyz.py" podcast <播客ID>
python "{baseDir}/scripts/xyz.py" episodes <播客ID> --max-pages 3
```

2. 将集数分配给不同账号，**并行执行** `crawl-one`：
```bash
# 账号A爬第1集
python "{baseDir}/scripts/xyz.py" crawl-one <eid1> --seq 1 --account phone1 -o "./output/播客名" &

# 账号B爬第2集（同时进行）
python "{baseDir}/scripts/xyz.py" crawl-one <eid2> --seq 2 --account phone2 -o "./output/播客名" &

wait
```

3. 每集爬完后**立即后处理**（逐集流程不变），然后继续下一集。

4. 全部完成后导出 CSV：
```bash
python "{baseDir}/scripts/xyz.py" export "./output/播客名"
```

> **注意**：并行 `crawl-one` 共享同一输出目录和 `audio/` 子目录，但每个集数有独立文件名，不会冲突。CSV 导出建议在全部爬取完成后统一执行，避免并行写入冲突。

**其他输出**：
- `audio/` — 下载的音频文件（m4a）
- `crawl_state.json` — 爬取状态（支持断点续爬）。包含 `crawled`（已完成）和 `metadata_only`（仅元信息，可重新转录）
- `<播客名>_飞书导入.csv` — CSV 格式（使用 `--csv` 或 `export` 命令时生成）

### CSV 导出（飞书表格导入）

爬取的播客内容可导出为 CSV 文件，直接导入飞书多维表格。

**方式一：爬取时自动导出**
```bash
# crawl 批量爬取结束后自动生成 CSV
python "{baseDir}/scripts/xyz.py" crawl <播客ID> -n 10 --csv -o ./output

# crawl-one 逐集追加 CSV 行
python "{baseDir}/scripts/xyz.py" crawl-one <单集ID> --seq 1 --csv -o "./output/<播客名>"
```

**方式二：对已有 MD 文件批量导出**
```bash
python "{baseDir}/scripts/xyz.py" export "./output/<播客名>"
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
| 单集ID | 24位hex |
| 内容来源 | 内置字幕/音频转录 |
| 播客 | 播客名称 |

**飞书导入步骤**：
1. 打开飞书多维表格
2. 点击"导入" → 选择 CSV 文件
3. 确认编码为 UTF-8，分隔符为逗号
4. 映射列（自动识别），时间轴和正文列设为"多行文本"类型
5. 导入完成

### 守护进程模式（serve）

自动循环爬取：刷新 token → 爬取 → 休息，适合长期无人值守运行。

```bash
# 基本用法：每 6 小时爬取一次，每次最多 10 集
python "{baseDir}/scripts/xyz.py" serve --pids <PID1> <PID2> --interval 6

# 指定参数
python "{baseDir}/scripts/xyz.py" serve \
  --pids <PID1> <PID2> \
  --interval 4 \
  --max-episodes 5

# 参数说明：
# --interval N       爬取间隔（小时，默认 6）
# --max-episodes N   每轮最多爬取集数（默认 10）
# --pids PID1 PID2   指定播客 PID 列表
```

- 支持 SIGINT/SIGTERM 优雅退出
- token 刷新失败时自动告警，写入 `crawler_alerts.jsonl`
- 不指定 `--pids` 时会提示无可爬目标

## Token 管理

Token 会在 API 返回 401 时自动刷新，通常不需要手动操作。

```bash
python "{baseDir}/scripts/xyz.py" token
python "{baseDir}/scripts/xyz.py" token --refresh
python "{baseDir}/scripts/xyz.py" token --verify
```

## Gotchas（已知坑）

> **[重要] 转录超时问题说明**
>
> `--transcribe-timeout` 默认值为 **0（无限制）**，脚本本身不会主动超时。
> 如果转录失败并提示超时，说明是调用方手动传了一个过小的 `--transcribe-timeout` 值。
>
> **CPU 转录参考耗时：**
> | 音频时长 | tiny 模型 | base 模型 |
> |---------|----------|----------|
> | 10 分钟 | ~30 秒 | ~60 秒 |
> | 30 分钟 | ~90 秒 | ~3 分钟 |
> | 50 分钟 | ~150 秒 | ~6-8 分钟 |
> | 120 分钟 | ~360 秒 | ~15-20 分钟 |
>
> 如果必须设置超时，建议值：
> - 30 分钟以内音频：`--transcribe-timeout 600`（10 分钟）
> - 30-60 分钟音频：`--transcribe-timeout 1200`（20 分钟）
> - 60 分钟以上音频：`--transcribe-timeout 0`（不限制）或 `1800+`
>
> **超时只是兜底保护，不是正常的流程控制手段。转录是 CPU 密集型任务，请预留充足时间。**

| 坑 | 说明 |
|----|------|
| 短信登录已失效 | sendCode API 返回错误 1003，推荐使用 `--adb` 自动提取方式登录 |
| ADB 自动提取 | 需要 Root 权限（MuMu 模拟器默认 adb root，夜神需手动开启） |
| MuMu 多开端口 | 实例0=7555, 实例1=7556, 实例2=7557...，用 `--device 127.0.0.1:PORT` 指定 |
| 多账号配置 | 默认 `credentials.json`，命名账户存在 `profiles/<名称>.json` |
| Token 位置 | iOS 模式 token 在 response body，Android 模式在 response headers |
| SSL 验证 | API 请求需关闭 SSL 验证（verify=False），脚本已处理 |
| device_id 必须匹配 | refresh_token 和 device_id 必须来自同一设备/同一会话 |
| 付费内容 | 自动通过 /v1/private-media/get 获取付费音频 URL |
| 分页 | 使用 loadMoreKey，每页建议间隔 0.5 秒 |
| 字幕格式 | API 返回词级 JSON，脚本自动按 500ms 间隔分组合成 SRT |
| 搜索 | 默认走 iTunes API，无结果时自动 fallback 到小宇宙搜索（需登录）。加 `-x` 强制用小宇宙搜索 |
| 转录依赖 | 需要安装 faster-whisper 和 ffmpeg，中国大陆需设置 HF_ENDPOINT |
| 环境变量 | 中国大陆需设置 `HF_ENDPOINT=https://hf-mirror.com`（脚本已内置） |

## Hard Stop 规则

- API 调用失败时自动跳过该集，继续处理下一集
- 登录时验证码发送失败，不重试（避免短信轰炸）
- 下载中断后可使用断点续传恢复（默认开启）
- 爬取支持断点续爬（通过 crawl_state.json 记录进度）

## PostgreSQL 集成

PG 集成通过 `.env` 配置（参见 SKILL_SETUP.md Step 3）。

- **query_db.py** (`scripts/query_db.py`): 只读查询已爬取内容，使用 `POSTGRES_READONLY_USER`
- **hub_adapter.py** (仓库根目录): Hub 爬取生命周期管理，使用 `POSTGRES_USER` 读写
- **xyz.py** (核心爬虫): 不直接依赖 PG，PG 不可用时爬取功能不受影响

PG 同步由 `hub_adapter.py` 调用 `xyz.py` 后解析输出实现。如需 PG 同步，请参考根目录的 `hub_adapter.py` 和 `schema.sql`。
