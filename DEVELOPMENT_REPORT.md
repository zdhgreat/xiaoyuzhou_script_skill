# 小宇宙播客爬虫 Skill — 完整开发报告

> 项目周期：2026-05-10 ~ 2026-05-13（4 天）
> 最终交付：Agent Skill v0.2.0（可跨设备安装，多 Agent 平台兼容）
> 代码规模：xyz.py ~2100 行 + extract_creds.py 553 行 + 文档 ~1200 行 = **~4000 行**
> 版本历史：v0.1.0（初始版本）→ v0.2.0（全面修复 + CSV 导出 + 重写文档）

---

## 一、项目启动 — 需求与构思

### 1.1 起因

用户希望构建一个 Agent Skill，通过小宇宙（Xiaoyuzhou FM）官方 API 实现播客内容的搜索、浏览、下载和批量爬取。核心诉求：

- **非技术用户可用**：通过 AI Agent 自然语言触发，无需手动操作 API
- **完整内容获取**：不仅下载音频，还要获取字幕、节目元数据、主播信息
- **批量爬取能力**：一次爬取整个播客的最新 N 集
- **音频转录兜底**：对于没有内置字幕的节目，用 faster-whisper 本地转录
- **可移植**：打包为标准 Skill，换台电脑装上就能用
- **多平台兼容**：支持多种 Agent 平台（Hermes、OpenClaw、Codex 等）

### 1.2 调研阶段

项目启动前，进行了两轮完整的技术调研：

**第一轮调研**（调研报告-小宇宙播客爬虫.md）：

对比了两种爬取路径：

| 对比项 | RSS 路径 | API 路径 |
|--------|----------|----------|
| 认证需求 | 不需要 | 需要抓包获取 token |
| 字幕/文字稿 | 不支持 | 支持 |
| 付费内容 | 不支持 | 支持 |
| 技术难度 | 低 | 中高 |

结论：选择 API 路径以获取完整功能。

**第二轮调研**（调研报告-小宇宙API爬虫深度分析.md）：

逆向分析了 [xyz-dl](https://github.com/shiquda/xyz-dl) 源码，发现了 API 认证的核心机制：
- Token 刷新在响应头而非响应体
- 需要完整的 Android 设备指纹
- `x-jike-device-id` 必须与 token 来自同一设备

同时参考了 [xiaoyuzhou-podcast](https://github.com/rrrrrredy/xiaoyuzhou-podcast) 的 Skill 结构，以及 [Firecrawl Skill 教程](https://www.firecrawl.dev/blog/claude-code-skill) 的最佳实践。

### 1.3 技术选型

| 决策 | 选择 | 原因 |
|------|------|------|
| 语言 | Python 3.10+ | 生态丰富，Whisper 库可用 |
| HTTP 客户端 | requests | 简单可靠，支持 SSL 关闭 |
| 音频转录 | faster-whisper | CTranslate2 后端，CPU 友好 |
| 凭据提取 | ADB + shared_prefs | 从模拟器直接读取，无需抓包 |
| 输出格式 | Markdown + CSV | 人类可读 + 飞书表格导入 |
| 分发格式 | AgentSkills Standard | 兼容所有主流 Agent 平台 |

### 1.4 架构设计

```
xiaoyuzhou-skill/
├── SKILL.md              # Skill 入口（Agent 平台读取）
├── README.md             # 用户文档
├── reference.md          # API 端点参考（按需加载）
├── requirements.txt      # 依赖
├── .gitignore
└── scripts/
    ├── xyz.py            # 主工具（所有子命令，单文件架构）
    └── extract_creds.py  # ADB 凭据提取（可独立运行）
```

**单文件架构决策**：`xyz.py` 包含所有子命令（login, search, podcast, episodes, episode, download, subtitles, crawl, crawl-one, export），约 2100 行。选择单文件而非模块化拆分，因为：
1. Skill 安装只需要复制一个目录
2. 减少文件间 import 的复杂性
3. Agent 平台加载 Skill 时只读一个文件
4. 参考 Firecrawl 的单脚本模式已被验证

---

## 二、v0.1.0 开发过程 — 从零到第一个可用版本

### 阶段一：API 认证与基础功能（2026-05-10 ~ 05-11）

#### 2.1 Token 认证机制 — 第一个坑

小宇宙使用双 token 机制：
- `refresh_token`：长期有效，用于刷新 access_token
- `access_token`：短期有效，每次 API 请求携带
- `x-jike-device-id`：设备标识，必须与 token 来自同一设备

**两种 API 模式**（这是第一个重要发现）：
- **iOS 模式**：POST 刷新 token，token 在响应体（body）中返回
- **Android 模式**：GET 刷新 token，token 在响应头（headers）中返回

代码需要同时处理两种位置：

```python
# 先尝试 body（iOS 模式）
new_access = body.get("x-jike-access-token") or resp.json().get("x-jike-access-token")
# fallback 到 headers（Android 模式）
if not new_access:
    new_access = resp.headers.get("x-jike-access-token")
```

这个差异花费了大量调试时间。最初只实现了 body 方式，一直拿不到 token，后来通过对比 xyz-dl 源码才发现了 headers 方式。

#### 2.2 短信登录封禁 — 第一次方案失败

最初实现了完整的短信验证码登录流程（`/v1/auth/sendCode` + `/v1/auth/loginOrSignUpWithSMS`），包括：
- 发送验证码
- 用户输入验证码
- 从响应头提取 token

但测试时发现 `sendCode` API 返回 **错误 1003**——该接口已被小宇宙封禁。这是一个关键发现，直接导致登录方案转向 ADB 自动提取。短信登录的代码白写了，但教训深刻：**应该先验证 API 可用性再开发功能**。

#### 2.3 ADB 自动凭据提取 — device_id 的坑

开发了 `extract_creds.py`（553 行），从 Android 模拟器/真机中自动提取凭据。

**工作流程**：
1. 检测 ADB 工具（系统 PATH → MuMu/夜神模拟器路径）
2. 连接设备（自动尝试常见端口 7555、62001、5555）
3. 获取 Root 权限（`adb root` 或 `su -c`）
4. 从 `/data/data/app.podcast.cosmos/shared_prefs/` 读取 XML
5. 解析 `refresh_token`、`device_id`（guid 字段）
6. 保存到 `~/.xiaoyuzhou/credentials.json`

**最坑的发现**：`x-jike-device-id` 对应的是 `utils_podcast.xml` 中的 **`guid`** 字段，**不是** `identity.xml` 中的 `uuid`。这个发现花了大量调试时间——所有 API 调用都返回 401，但 token 看起来是对的，最后发现是因为 device_id 用错了字段。

**三种提取策略**（fallback 机制）：
1. 直接 cat 已知 XML 文件（最快）
2. grep 搜索整个 shared_prefs 目录
3. ls + 逐文件读取（最慢但最可靠）

#### 2.4 搜索 — 第二次方案失败

小宇宙 API **没有公开搜索端点**。最初用 iTunes Search API 替代，但很多中文播客只在小宇宙独家发布，iTunes 搜不到（如"科技前哨"）。

v0.1.0 的方案：只用 iTunes API。这个决策导致后续用户无法搜索独占播客。

#### 2.5 基础 API 功能

实现了 search、podcast、episodes、episode、download、subtitles 六个子命令。每个都踩了不同的坑：

| 功能 | 踩的坑 |
|------|--------|
| `podcast` | reference.md 文档写的 `id=xxx`，实际应为 `pid=xxx` |
| `episodes` | 响应可能是 list 或 dict，两种类型都要处理 |
| `download` | SSL 证书验证失败，必须 `verify=False` |
| `subtitles` | API 返回词级 JSON（每词一条），需要按时间间隔分组合成 SRT |

### 阶段二：批量爬取与转录（2026-05-11 ~ 05-12）

#### 2.6 批量爬取（crawl 命令）

设计了两轮策略：
1. **第1轮（快速）**：遍历所有目标集，有内置字幕的直接保存
2. **第2轮（慢速）**：无字幕的下载音频，用 faster-whisper 转录

**输出格式**：
- 按播客名建文件夹
- 按发布日期排序编号（01=最早，NN=最新）
- 每集一个 `.md` 文件，包含元信息、简介、时间轴、正文

#### 2.7 错误处理重构 — sys.exit → APIError

**核心问题**：最初 `api_request()` 失败时直接 `sys.exit(1)`，这在单次操作中没问题，但在批量爬取时会导致整个脚本退出，丢失已爬取的进度。

**解决方案**：创建 `APIError` 异常类，`api_request()` 抛出异常而非退出。子命令在 `main()` 中统一捕获，批量操作中的单次失败改为 `continue` 跳过。

修改了 5 处 `except SystemExit` → `except (SystemExit, APIError)`。

这个重构影响了整个代码库，是 v0.1.0 最大的架构变更之一。教训：**错误处理要从一开始就设计好**。

#### 2.8 音频转录 — 环境适配

使用 faster-whisper，支持 tiny/base/small/medium/large-v3 五档模型。

**中国大陆环境适配**：
- 设置 `HF_ENDPOINT=https://hf-mirror.com` 下载模型
- 设置 `KMP_DUPLICATE_LIB_OK=TRUE` 解决 OMP 库冲突
- `sys.stdout.reconfigure(encoding="utf-8")` 解决 Windows 终端乱码

#### 2.9 逐集后处理（crawl-one 命令）

**用户痛点**：`crawl` 是一次性批量命令，所有集爬取完成后才能后处理。对于急需查看内容的用户，等待时间过长。

**解决方案**：
1. 提取单集处理逻辑为 `_process_single_episode()`
2. 新增 `crawl-one` 子命令，处理单集
3. SKILL.md 工作流改为：逐集调用 crawl-one → 立即后处理 → 报告用户 → 下一集

v0.1.0 到此完成，zip 包约 32KB，包含 7 个文件。

---

## 三、v0.1.0 跨 Agent 测试 — 发现问题

v0.1.0 完成后，在多个 Agent 平台（Hermes、OpenClaw 等）上进行了实测。外部 Agent 生成了分析报告（`xiaoyuzhou-skill-分析报告.md`），发现了 11 个问题：

### 致命 Bug

| Bug | 问题 | 影响 |
|-----|------|------|
| Bug 1 | `cmd_crawl_one` 引用了未定义的 `podcast_title` 和 `state` 变量 | 转录失败后脚本崩溃 (NameError) |
| Bug 2 | `duration` 单位理解错误（代码以为是毫秒，实际是秒） | 所有节目显示 "0分钟" |

### 严重问题

| 问题 | 描述 |
|------|------|
| 问题 3 | 搜索只能走 iTunes，找不到小宇宙独占播客 |
| 问题 4 | crawl-one 无字幕时走 whisper 转录，超时后整个流程失败 |
| 问题 5 | 超时后没有生成 .md 文件，已下载音频成为垃圾文件 |

### 中等问题

| 问题 | 描述 |
|------|------|
| 问题 6 | SKILL.md 示例命令引号位置错误 |
| 问题 7 | `loadNextKey` 拼写冗余（不存在此字段） |

### 优化建议

| 建议 | 描述 |
|------|------|
| 建议 9 | 利用小宇宙服务端的转录 API（避免本地 whisper） |
| 建议 10 | crawl-one 增加 `--auto-seq` 自动推断序号 |
| 建议 11 | `_strip_html` 对 `<figure>` 标签处理不佳 |

---

## 四、v0.2.0 开发 — 全面修复与功能升级（2026-05-13）

### 4.1 搜索 Fallback — 让独占播客可搜

**设计方案**：
1. 先走 iTunes API（无需登录，速度快）
2. 如果没找到结果，自动 fallback 到小宇宙搜索 API (`POST /v1/search/create`)
3. 新增 `-x` / `--xiaoyuzhou` 参数，强制跳过 iTunes 直接搜小宇宙

**实现过程**：
1. 从 `cmd_search` 中提取 `_search_itunes()` 函数
2. 创建新的 `_search_xiaoyuzhou()` 函数
3. 重写 `cmd_search()` 实现双层 fallback

**实测结果**：
- `search "科技前哨" -x` → 成功找到（iTunes 找不到的独占播客）
- `search "忽左忽右"` → iTunes 直接找到，无需 fallback
- 搜索 fallback 完全正常工作

### 4.2 服务端转录 API 探索 — 失败

分析报告中提到 API 返回了 `transcriptMediaId` 字段，暗示可能有服务端转录端点。

**探索过程**：构造了 8 个候选端点逐一测试：
- `/v1/transcript/get`
- `/v1/media/transcript`
- `/v1/episode/transcript`
- 等等

**结果**：全部返回 404。`transcriptMediaId` 只是内部元数据，没有公开读取端点。

**结论**：本地 Whisper 转录是唯一方案，无法绕过。

### 4.3 灾难性事件 — 文件全部恢复

在修复工作进行到一半时，用户不小心将所有文件恢复到了早上（v0.1.0）的状态。之前实现的所有修复（搜索 fallback、转录改进、文档更新）全部丢失。

**影响**：不是修复 2 个剩余问题，而是需要从头重新修复全部 11 个问题。

**重建过程**（约 30 分钟内完成）：
1. Bug 6：修复 SKILL.md 引号位置
2. Bug 1：修复 `_process_single_episode` 缺失参数
3. Bug 4+5：实现转录超时 + 超时前保存元信息
4. Bug 7：清理 `loadNextKey` 冗余
5. 建议 11：改进 `_strip_html` 的 `<figure>` 处理
6. Bug 3：重新实现搜索 fallback
7. Bug 2：确认 duration 已是 `// 60`（秒），无需修复
8. 更新 CLI 参数（`--xiaoyuzhou`, `--no-transcribe`, `--transcribe-timeout`）
9. 更新 SKILL.md、reference.md 文档

### 4.4 端到端测试 — Web3+ 播客

用 Web3+ 播客进行完整的端到端测试：

1. **搜索**：`search "Web3+"` → 找到（ID: `69080367b1ef1d2693c406e9`，296 集）
2. **列表**：`episodes` → 获取最新 3 集信息
3. **爬取**：`crawl ... -n 3 --no-transcribe` → 3 集全部成功

**发现的新问题**：`--no-transcribe` 参数被 `cmd_crawl` 的第 2 轮转录循环忽略了。转录仍然执行，但幸好 base 模型在合理时间内完成了。

### 4.5 时间轴与简介重复 — 第三个方案失败

**用户发现**：输出 MD 文件中，"时间轴"和"简介"两部分内容完全相同——都来自 API 的 `description` 字段。

**第一次修复**：当 `shownotes` 和 `description` 内容相同时，时间轴显示 `[待补充]`。

**用户反馈**："你直接待补充，那用户无法了解了"——这个方案被否决。

**第二次修复**：保留 API 数据，由 AI Agent 在后处理阶段根据正文内容重新生成时间轴。最终方案确定：

1. AI 读取转录/字幕文本
2. 根据内容按话题划分节点，生成 `MM:SS 话题标题` 格式时间轴
3. 正文用 `### MM:SS 话题标题` 分节，与时间轴一一对应
4. 分节后保留完整对话内容，不做删减

### 4.6 后处理格式标准化

用户提供了标准格式示例，AI 据此制定了后处理规范：

```
## 时间轴

00:00 开场话题
02:30 第一个讨论点
05:00 第二个讨论点

## 正文

### 00:00 开场话题

正文内容...

### 02:30 第一个讨论点

正文内容...
```

此规范被写入 SKILL.md，确保所有用户都能获得一致的输出格式。

### 4.7 三集后处理实战

对 Web3+ 播客最新 3 集进行了完整后处理：

| 集数 | 音频时长 | 转录模型 | 转录耗时 | 字数 |
|------|---------|---------|---------|------|
| 第 1 集 | 16 分钟 | tiny | 71 秒 | ~4000 字 |
| 第 2 集 | 9 分钟 | tiny | 40 秒 | ~2500 字 |
| 第 3 集 | 23 分钟 | tiny | 182 秒 | ~7900 字 |

后处理包括：
- 修正转录错误（"规谷"→"硅谷"、"AZN"→"Agent"）
- 添加标点断句
- 生成时间轴（每集 8-15 条）
- 按 `###` 分节
- 补充简介

**Windows 编码问题**：第 3 集正文较长，Windows 终端的 heredoc/编码导致内容损坏。解决方案：改用 Python 脚本直接写入文件，绕过 shell 编码问题。

### 4.8 全面代码审查 — 发现隐藏 Bug

用户要求："确认一下是否 skill 已经完全符合我的实现要求，假如这个 skill 给其他用户使用也是相同的效果"

启动了 3 个并行审查 Agent，分别审查代码、文档、输出。发现了之前未被注意到的问题：

#### Bug A：转录超时是假的 — ThreadPoolExecutor 陷阱

**问题**：`transcribe_audio` 使用 `ThreadPoolExecutor.result(timeout=X)` 实现超时。但 Python 的 ThreadPoolExecutor 在超时后**只抛出 TimeoutError，线程仍在后台运行**。对于 CPU 密集的 Whisper 转录，线程不会被中断，超时形同虚设。

```python
# 旧代码（假超时）
with ThreadPoolExecutor(max_workers=1) as executor:
    future = executor.submit(transcribe_fn, audio_path, model)
    try:
        result = future.result(timeout=timeout_sec)  # 超时抛异常，但线程继续跑！
    except TimeoutError:
        return ""  # 假装超时了，实际 Whisper 还在后台吃 CPU
```

**修复**：改用 `subprocess.run(timeout=...)`，超时后操作系统会直接杀死子进程。

```python
# 新代码（真超时）
result = subprocess.run(
    [sys.executable, "-c", whisper_script],
    timeout=timeout_sec if timeout_sec > 0 else None,
    capture_output=True, text=True
)
```

这是 v0.2.0 最关键的设计变更之一。

#### Bug B：空转录被标记为已完成

**问题**：`cmd_crawl` 第 2 轮转录失败时（返回空字符串），仍然调用 `_save_episode` 并将该集加入 `state["crawled"]`。结果是：转录失败 → 标记为已完成 → 永远不会重试。

**修复**：添加 `if transcript:` 守卫，空转录不标记为已完成。

#### Bug C：--no-transcribe 永久标记

**问题**：使用 `--no-transcribe` 的集被加入 `state["crawled"]`，之后去掉此参数重跑也不会重新转录。

**修复**：新增 `state["metadata_only"]` 列表，与 `state["crawled"]` 分开追踪。

#### Bug D：resume 误匹配

**问题**：断点续爬检查用 `if eid in content` 判断是否已爬取。但 eid 可能出现在其他集的正文（如提及往期节目）中，导致误跳过。

**修复**：改为 `if f"**单集ID**: {eid}" in content`，精确匹配元信息字段。

#### Bug E：description 未 HTML 清理

**问题**：`_save_episode` 对 `shownotes` 做了 `html.unescape()`，但 `description` 字段也可能包含 HTML 实体（`&amp;` 等），却没有清理。

**修复**：添加 `_strip_html(desc) if '<' in desc else desc`。

#### Bug F：时间轴/正文标题不匹配

**问题**：第 3 集有 3 个时间轴条目与正文 `###` 标题文字略有不同（多了或少了几个字），导致无法一一对应。

**修复**：手动修正 3 处不匹配的条目。

### 4.9 Hermes/OpenClaw 转录超时投诉

外部 Agent（hermes/openclaw）报告转录失败，超时时间分别为 300 秒和 550 秒。

**调查结果**：脚本的 `--transcribe-timeout` 默认值为 **0（无限制）**。300/550 秒的超时是外部 Agent 自己传入的过小值，不是脚本的问题。

**但教训深刻**：即使默认值合理，也需要在文档中明确说明，否则其他 Agent 开发者会犯错。

**文档修复**：
1. 在 SKILL.md Gotchas 区域添加醒目的 blockquote 警告
2. 提供转录耗时参考表（按音频时长 × 模型大小）
3. 给出建议超时值（30 分钟音频 ≥ 600 秒，60 分钟以上 ≥ 1800 秒）
4. 明确声明："超时只是兜底保护，不是正常的流程控制手段"

### 4.10 逐集后处理强制规则

用户发现外部 Agent 可能批量爬取后再统一后处理，导致等待时间极长。

**SKILL.md 新增的醒目规则**：
```
> **[重要] 必须逐集后处理，禁止批量堆到最后再做**
>
> ✅ 正确流程：crawl-one 第1集 → 后处理第1集 → crawl-one 第2集 → 后处理第2集
> ❌ 错误流程：crawl-one 第1集 → crawl-one 第2集 → crawl-one 第3集 → 后处理所有集
```

三条理由：
1. 单集后处理可能消耗大量上下文窗口
2. 批量堆叠导致用户长时间看不到任何产出
3. 逐集输出让用户可以随时中断，已完成的不受影响

### 4.11 CSV 导出 — 飞书表格集成

**用户需求**：爬取的内容需要保存到飞书多维表格，现有 Markdown 格式无法直接导入。

**设计方案**：
- 每集一行 CSV，11 列
- UTF-8 BOM 编码（飞书/Excel 正确识别中文）
- RFC 4180 标准（正文/时间轴含换行，用双引号包裹，引号用 `""` 转义）

**实现**：
1. `_parse_md_to_csv(md_path)` — 解析 MD 文件为 dict
2. `_save_csv_row(csv_path, episode_data)` — 追加写入单行
3. `_export_csv(output_dir)` — 批量导出
4. `cmd_export()` — 新的 `export` 子命令
5. `crawl` 和 `crawl-one` 新增 `--csv` 参数

**CSV 列定义**（11 列）：

| 列名 | 说明 |
|------|------|
| 序号 | 按发布日期排序 |
| 标题 | 单集标题 |
| 发布日期 | YYYY-MM-DD |
| 时长 | 如"23分49秒" |
| 主播/嘉宾 | 多个用换行分隔 |
| 简介 | 完整简介文本 |
| 时间轴 | `MM:SS 标题` 格式，多行 |
| 正文 | 完整正文（含 `###` 分节标题） |
| 单集ID | 24 位 hex |
| 内容来源 | 内置字幕/音频转录 |
| 播客 | 播客名称 |

**实测**：`python xyz.py export "output/Web3+"` → 成功生成 `Web3+_飞书导入.csv`，3 行数据，11 列全部正确。

### 4.12 README 重写 — 对标高星 Skill 仓库

用户要求 README 质量达到 [colleague-skill](https://github.com/titanwings/colleague-skill)（15k stars）和 [anthropics/skills](https://github.com/anthropics/skills) 的水准。

**分析了两个参考仓库的 README 结构**：
- colleague-skill：badges、功能概览、多语言、更新日志、安装指南、架构图、FAQ
- anthropics/skills：简洁的 SKILL.md 规范、渐进式加载理念

**重写后的 README 结构**：
1. Badges（Python 3.10+、AgentSkills Standard、MIT License）
2. 多平台兼容声明（Hermes / OpenClaw / Codex 等）
3. 功能概览表（8 项核心能力）
4. 快速开始（环境要求、安装、Skill 配置、两种登录方式）
5. 完整使用指南（9 个功能模块）
6. CLI 参考表（全部 15 个子命令及参数）
7. 项目结构树 + 技术架构流程图
8. Whisper 模型对比表 + 转录耗时参考表
9. 常见问题表（11 个 FAQ）
10. 重要注意事项（逐集后处理规则、后处理步骤说明）

---

## 五、Git 与发布

### 5.1 Git 仓库初始化

```
xiaoyuzhou-skill/
├── .gitignore        # Python cache、output、credentials、IDE、*.csv
├── SKILL.md          # Skill 配置（341 行）
├── README.md         # 用户文档（417 行）
├── reference.md      # API 参考（160 行）
├── requirements.txt  # 依赖
└── scripts/
    ├── xyz.py        # 主工具（~2100 行）
    └── extract_creds.py  # ADB 提取（553 行）
```

### 5.2 GitHub 发布 — 版本标签策略

用户要求远程仓库保留版本历史：
- **v0.1.0**：远程已有的旧版本（4 个 commit）
- **v0.2.0**：当前全面修复后的版本

**操作过程**：
1. `git fetch origin` — 拉取远程 4 个 commit
2. 首次尝试 `git rebase origin/main` — **失败**（独立历史，冲突太多）
3. 改用 `git reset --soft origin/main` — 将本地所有改动放在暂存区
4. 清理 `__pycache__` 文件（远程有，本地 .gitignore 已忽略）
5. 提交为 "feat: v0.2.0 — 全面升级"
6. 打 tag：`v0.1.0` 指向远程旧 commit，`v0.2.0` 指向新 commit
7. `git push origin main --tags` — 推送成功

**GitHub 仓库**：https://github.com/zdhgreat/xiaoyuzhou_script_skill

---

## 六、关键设计决策回顾

### 6.1 为什么用 `APIError` 而不是 `sys.exit`

批量爬取时，某一集的 API 失败不应中断整个任务。`APIError` 允许 `cmd_crawl` 捕获异常、跳过失败集、继续处理下一集。而 CLI 单命令场景在 `main()` 中统一捕获并打印错误。

### 6.2 为什么 subprocess 而不是 ThreadPoolExecutor

Python 的 `ThreadPoolExecutor.result(timeout=X)` 超时后只抛出 `TimeoutError`，线程继续运行。对于 CPU 密集的 Whisper 转录（无 GIL 释放），这意味着超时是假的——Whisper 会一直吃到转完为止。`subprocess.run(timeout=X)` 由操作系统直接终止子进程，是唯一可靠的超时方案。

### 6.3 为什么新增 `crawl-one` 而不是修改 `crawl`

`crawl` 的两轮策略（字幕优先 + 转录兜底）是经过验证的批量方案。逐集处理是不同的使用场景，强行合并会增加复杂度。拆分为两个命令，各自职责清晰。

### 6.4 为什么默认 Whisper 模型用 base 而非 small

base 模型在 CPU 上转录 120 分钟音频约 15-20 分钟，small 需要 40 分钟。对于中文内容，small 质量明显更好，但 base 作为默认值可以快速验证流程。用户可通过 `--whisper-model small` 切换。

### 6.5 为什么输出 Markdown + CSV 双格式

1. Markdown 人类可读，用户可以直接打开查看
2. AI 后处理更自然（AI Agent 直接读取、增强、保存）
3. CSV 满足飞书/Notion 等表格工具导入需求
4. 两种格式各有场景，互不替代

### 6.6 为什么 `state["metadata_only"]` 与 `state["crawled"]` 分开

`--no-transcribe` 的用户意图是"先保存元信息，以后再转录"。如果和 `crawled` 混在一起，去掉 `--no-transcribe` 后重跑也不会重新转录。分开追踪后，`crawl` 可以自动检测 `metadata_only` 的集并尝试转录。

---

## 七、完整设计变更记录

| 变更 | 从 | 到 | 原因 |
|------|----|----|------|
| 错误处理 | `sys.exit(1)` | `APIError` 异常 | 批量操作中 sys.exit 杀死整个脚本 |
| 转录超时 | `ThreadPoolExecutor.result(timeout=X)` | `subprocess.run(timeout=X)` | 前者超时后线程继续跑，不会真正中断 |
| 搜索策略 | 仅 iTunes | iTunes + 小宇宙 fallback | iTunes 找不到独占播客 |
| 转录来源 | 期望服务端 API | 本地 Whisper only | 8 个候选端点全部 404 |
| 后处理方式 | 批量（全部完成后） | 逐集（每集完成后立即） | 用户等待时间过长，无法中断 |
| 时间轴生成 | 复制 API shownotes | AI 根据正文生成 | shownotes 常与 description 重复 |
| 输出格式 | Markdown only | Markdown + CSV | 飞书表格导入需求 |
| 默认 Whisper 模型 | `small` | `base` | small 在 CPU 上对长音频太慢 |
| 爬取状态追踪 | 单一 `crawled` 列表 | `crawled` + `metadata_only` | `--no-transcribe` 不应永久标记为已完成 |
| 断点检测 | `eid in content` 子串匹配 | `**单集ID**: {eid}` 精确匹配 | 子串匹配导致误跳过 |
| duration 处理 | `// 1000 // 60`（以为是毫秒） | `// 60`（秒） | API 实际返回秒，不是毫秒 |
| HTML 清理 | 仅 shownotes | shownotes + description | description 也可能含 HTML 实体 |
| 空转录处理 | 无条件标记为已完成 | `if transcript:` 守卫 | 转录失败不应标记为已完成 |

---

## 八、遇到的所有问题与解决方案汇总

### 8.1 API 层面

| 问题 | 原因 | 解决方案 |
|------|------|---------|
| 短信登录失败 (error 1003) | 小宇宙封禁了短信登录接口 | 转向 ADB 自动提取 |
| Token 位置不一致 | iOS 在 body，Android 在 headers | 先读 body，fallback 到 headers |
| `podcast/get` 参数错误 | reference.md 文档错误 | 修正为 `pid=xxx` |
| SSL 证书验证失败 | 小宇宙 API 的 SSL 证书问题 | `verify=False` + 抑制警告 |
| 搜索无端点 | 小宇宙无公开搜索 API | iTunes API + 小宇宙搜索 fallback |
| 付费内容音频 URL | 普通详情不含付费 URL | 额外调用 `/v1/private-media/get` |
| 分页格式不一致 | 响应可能是 list 或 dict | 两种类型都处理 |
| 服务端转录 API | 不存在 | 本地 Whisper 是唯一方案 |

### 8.2 ADB/设备层面

| 问题 | 原因 | 解决方案 |
|------|------|---------|
| device_id 不匹配 | 错误使用 `identity.xml` 的 uuid | 正确使用 `utils_podcast.xml` 的 guid |
| MuMu 连不上 | 需要手动 `adb connect` | 自动尝试常见端口（7555、62001、5555） |
| 夜神 Root 模式不同 | 夜神需要 `su -c` | 检测两种模式并适配 |

### 8.3 代码/工程层面

| 问题 | 原因 | 解决方案 |
|------|------|---------|
| `sys.exit(1)` 中断批量操作 | 错误处理策略不当 | 引入 `APIError` 异常 |
| 假超时（ThreadPoolExecutor） | Python 线程无法被杀死 | subprocess 方案 |
| 空转录标记为已完成 | 缺少空值检查 | `if transcript:` 守卫 |
| `--no-transcribe` 永久标记 | 状态追踪不区分 | `metadata_only` 独立追踪 |
| resume 误匹配 | 子串匹配 | 精确匹配 `**单集ID**: {eid}` |
| HTML 实体未转义 | description 字段被忽略 | 添加 `_strip_html()` |
| 时间轴与简介重复 | API 返回相同内容 | AI 后处理重新生成时间轴 |
| Windows 终端编码 | heredoc 中文损坏 | 改用 Python 脚本直接写文件 |

### 8.4 环境层面

| 问题 | 原因 | 解决方案 |
|------|------|---------|
| Windows 终端乱码 | 默认编码非 UTF-8 | `sys.stdout.reconfigure(encoding="utf-8")` |
| HuggingFace 下载超时 | 中国大陆网络 | `HF_ENDPOINT=https://hf-mirror.com` |
| `libiomp5md.dll` 冲突 | 多个 OMP 库加载 | `KMP_DUPLICATE_LIB_OK=TRUE` |
| ffmpeg 未安装 | 转录需要 ffmpeg 做 WAV 转换 | 检测并提示安装 |

---

## 九、最终功能清单

### 子命令（15 个）

| 子命令 | 功能 | 行数 |
|--------|------|------|
| `login --adb` | ADB 自动提取凭据 | ~130 行 |
| `login -t -d` | 手动输入凭据 | ~30 行 |
| `token` | 查看/刷新/验证 token | ~80 行 |
| `search` | iTunes + 小宇宙搜索 | ~120 行 |
| `podcast` | 播客详情 | ~70 行 |
| `episodes` | 节目列表（分页） | ~70 行 |
| `episode` | 单集详情 | ~55 行 |
| `download` | 下载音频（断点续传） | ~120 行 |
| `subtitles` | 获取字幕 (SRT/TXT/JSON) | ~120 行 |
| `crawl` | 批量爬取（两轮策略） | ~250 行 |
| `crawl-one` | 单集处理 | ~60 行 |
| `export` | MD → CSV 导出 | ~60 行 |

### 辅助函数

| 函数 | 功能 |
|------|------|
| `_process_single_episode()` | 单集处理核心逻辑 |
| `_save_episode()` | 保存 .md 文件 |
| `transcribe_audio()` | faster-whisper 转录（subprocess 真超时） |
| `_convert_for_whisper()` | 音频转 16kHz WAV |
| `_strip_html()` | HTML → 纯文本 |
| `_parse_md_to_csv()` | MD → CSV 行数据 |
| `_save_csv_row()` | 追加写入单行 CSV |
| `_export_csv()` | 批量导出 CSV |
| `_search_itunes()` | iTunes API 搜索 |
| `_search_xiaoyuzhou()` | 小宇宙原生搜索 |
| `subtitle_to_text()` / `subtitle_to_srt()` | 字幕格式转换 |

---

## 十、文件清单与规模

| 文件 | 行数 | 说明 |
|------|------|------|
| `scripts/xyz.py` | ~2100 | 主工具，所有子命令 |
| `scripts/extract_creds.py` | 553 | ADB 凭据提取 |
| `SKILL.md` | 341 | Skill 配置 + 工作流 |
| `README.md` | 417 | 用户文档 |
| `reference.md` | 160 | API 端点参考 |
| `requirements.txt` | 5 | 依赖声明 |
| `.gitignore` | 27 | 忽略规则 |
| `DEVELOPMENT_REPORT.md` | ~650 | 本文件 |
| **合计** | **~4250** | |

---

## 十一、经验教训

### 教训 1：先验证 API 可用性再开发功能

短信登录开发了完整的发送验证码 + 验证码登录流程，最后发现 API 返回 error 1003（已封禁）。白写了大量代码。

**改进**：开发前先用 curl 验证端点是否可用。

### 教训 2：设备指纹字段的映射需要确认

`x-jike-device-id` 对应 `utils_podcast.xml` 的 `guid`，不是 `identity.xml` 的 `uuid`。这个错误导致所有 API 调用返回 401，排查了很久。

**改进**：抓包时同时记录字段名和来源文件，建立映射关系。

### 教训 3：错误处理要从一开始就设计好

`sys.exit(1)` → `APIError` 的重构影响了整个代码库（5 处修改）。如果一开始就用异常，就不需要重构。

**改进**：CLI 工具的入口函数统一做异常捕获，内部函数永远抛异常。

### 教训 4：Python 线程超时是假的

`ThreadPoolExecutor.result(timeout=X)` 看似能超时，实际上只是通知调用方"超时了"，线程继续运行。对于 CPU 密集任务，必须用 subprocess 才能真正超时终止。

**改进**：CPU 密集任务一律用 subprocess，不用线程池。

### 教训 5：用户等待时间比总耗时更重要

批量后处理改为逐集后处理，总耗时不变，但用户可以每爬完一集就看到结果，体验提升巨大。外部 Agent 也受益——可以在中途中断而不丢失已完成的工作。

**改进**：所有长时间操作都要支持增量输出。

### 教训 6：文档和代码要保持一致

reference.md 的 `id=` vs `pid=` 问题、SKILL.md 引号位置错误，都会导致其他开发者/Agent 踩坑。

**改进**：每次修改 API 参数后立即更新文档。

### 教训 7：环境差异要提前考虑

中国大陆 HuggingFace 下载超时、Windows 编码问题、OMP 库冲突——这些问题在开发机上可能不存在，但在用户机器上会频繁出现。

**改进**：在脚本中内置环境适配逻辑，不依赖用户手动配置。

### 教训 8：默认值要充分考虑

Whisper 模型默认 `small` 在 CPU 上对长音频太慢，默认 `base` 更合理。转录超时默认 0（无限制）需要明确说明，否则外部 Agent 会传入过小的值。

**改进**：所有默认值都要附带说明文字和使用建议。

---

## 十二、交付物

- **GitHub 仓库**：https://github.com/zdhgreat/xiaoyuzhou_script_skill
  - `v0.1.0` tag：初始版本
  - `v0.2.0` tag：全面修复 + CSV 导出 + 文档重写
- **全局 Skill**：已同步到系统全局 skills 目录
- **桌面 zip**：`xiaoyuzhou-skill.zip`（最新版本）
- **测试输出**：`output/Web3+/` 目录下 3 集完整后处理的 MD 文件 + CSV

---

## 附录 A：版本对比

| 特性 | v0.1.0 | v0.2.0 |
|------|--------|--------|
| 搜索 | 仅 iTunes | iTunes + 小宇宙 fallback |
| 转录超时 | 假超时（ThreadPoolExecutor） | 真超时（subprocess） |
| 空转录处理 | 标记为已完成 | 不标记，可重试 |
| `--no-transcribe` | 永久标记 | `metadata_only` 独立追踪 |
| 断点检测 | 子串匹配（有误判） | 精确匹配 |
| HTML 清理 | 仅 shownotes | shownotes + description |
| 输出格式 | Markdown | Markdown + CSV |
| 后处理规则 | 未明确 | 逐集处理，SKILL.md 强制规定 |
| 超时文档 | 无说明 | 参考表 + 建议值 + 醒目警告 |
| README | 基础 | 高星标准（badges、架构图、FAQ） |
| 子命令数 | 11 个 | 12 个（新增 export） |

## 附录 B：开发时间线

```
2026-05-10  项目启动，调研阶段
            ├─ 完成第一轮调研（RSS vs API 路径对比）
            └─ 完成第二轮调研（API 深度分析，逆向 xyz-dl）

2026-05-11  v0.1.0 核心开发
            ├─ Token 认证实现
            ├─ 短信登录 → 发现 error 1003 → 转向 ADB
            ├─ ADB 凭据提取 → 发现 device_id 用错字段 → 修复
            ├─ 6 个基础子命令实现
            ├─ 批量爬取（crawl 命令）
            ├─ 音频转录（faster-whisper）
            └─ sys.exit → APIError 重构

2026-05-12  v0.1.0 完善
            ├─ crawl-one 逐集处理命令
            ├─ 环境适配（HF mirror、OMP、编码）
            └─ 打包为 zip，跨 Agent 测试开始

2026-05-13  v0.2.0 全面升级
            ├─ 跨 Agent 测试报告分析（11 个问题）
            ├─ 搜索 fallback 实现（iTunes + 小宇宙）
            ├─ 服务端转录 API 探索 → 失败（全部 404）
            ├─ 文件恢复灾难 → 从头重新修复所有问题
            ├─ Web3+ 播客端到端测试（3 集）
            ├─ 时间轴/简介重复问题 → 3 次方案迭代
            ├─ 后处理格式标准化
            ├─ 3 集完整后处理实战
            ├─ 全面代码审查 → 发现 6 个隐藏 Bug
            ├─ ThreadPoolExecutor → subprocess 超时重构
            ├─ 转录超时文档强化（参考表 + 醒目警告）
            ├─ 逐集后处理强制规则
            ├─ CSV 导出（飞书表格集成）
            ├─ README 重写（对标高星 Skill）
            ├─ Git 仓库初始化 + GitHub 发布
            └─ 版本标签：v0.1.0 / v0.2.0
```
