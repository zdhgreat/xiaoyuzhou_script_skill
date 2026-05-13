# 小宇宙播客 (Xiaoyuzhou Podcast Scraper)

Claude Code Skill — 通过小宇宙官方 API 搜索、浏览、下载播客内容，支持批量读取与音频转录。

## 前置条件

### 必需

- **Python 3.10+**
- **pip install requests**
- **小宇宙 App 凭据** — 需要从一个已登录的小宇宙 App 中提取 `refresh_token` 和 `device_id`
- **Android 模拟器**（用于自动提取凭据）

### 可选

- **faster-whisper** (`pip install faster-whisper`) — 音频转录，无此库则只能爬取有内置字幕的节目
- **ffmpeg** — 音频格式转换（转录必需），Windows 用户需下载并加入 PATH
- **ADB 工具** — 模拟器自带或安装 Android SDK Platform Tools

## 安装与配置

### 第一步：安装 Python 依赖

```bash
pip install requests

# 如需音频转录功能：
pip install faster-whisper
```

### 第二步：安装 ffmpeg（转录功能需要）

**Windows:**
```bash
# 方式一：使用 winget
winget install ffmpeg

# 方式二：使用 choco
choco install ffmpeg

# 方式三：手动下载 https://ffmpeg.org/download.html 并加入 PATH
```

验证安装：
```bash
ffmpeg -version
```

### 第三步：安装 MuMu 模拟器

MuMu 模拟器用于运行小宇宙 App，自动提取登录凭据。

1. 下载安装 [MuMu 模拟器](https://mumu.163.com/)（要求 Android 12 版本）
2. 启动模拟器
3. 在模拟器内打开浏览器，访问 `xiaoyuzhoufm.com/download`，下载安装小宇宙 App
4. 打开小宇宙，用手机号登录

> MuMu 默认开启 `adb root`，无需额外配置 Root 权限。
>
> 夜神模拟器也可以使用，但需在设置中手动开启 Root，且 Android 版本需 10 以上。
>
> 真机也可以使用，需要开启 USB 调试 + Root 权限。

### 第四步：登录

在模拟器中小宇宙 App 已登录的状态下：

```bash
python scripts/xyz.py login --adb
```

脚本会自动：
1. 检测 MuMu/夜神模拟器的 ADB 工具
2. 连接设备并获取 Root 权限
3. 从小宇宙 App 数据中提取 `refresh_token` 和 `device_id`
4. 验证凭据有效性
5. 保存到 `~/.xiaoyuzhou/credentials.json`

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

**如果自动提取失败**，可以手动抓包获取凭据：

1. 安装 mitmproxy: `pip install mitmproxy`
2. 运行 `mitmweb -p 8080`
3. 在模拟器中设置 WiFi 代理为电脑 IP:8080
4. 在模拟器浏览器打开 `mitm.it` 安装证书
5. 打开小宇宙 App 随便浏览
6. 在电脑浏览器 `http://127.0.0.1:8081` 找到 `api.xiaoyuzhoufm.com` 的请求
7. 复制请求头中 `x-jike-refresh-token` 和 `x-jike-device-id`

```bash
python scripts/xyz.py login -t <refresh_token> -d <device_id>
```

> 抓完后记得把模拟器代理设置改回"无"。

## 功能说明

### 搜索播客

```bash
python scripts/xyz.py search "忽左忽右"
```

通过 iTunes API 搜索，不需要登录。从搜索结果的 URL 中可以提取播客 ID。

### 查看播客信息

```bash
python scripts/xyz.py podcast <播客ID或URL>
python scripts/xyz.py episodes <播客ID> --max-pages 3
```

支持传入完整 URL（如 `https://www.xiaoyuzhoufm.com/podcast/xxxxx`）或纯 ID。

### 获取单集详情

```bash
python scripts/xyz.py episode <单集ID或URL>
```

包含字幕数据。付费内容会自动获取音频 URL。

### 下载音频

```bash
python scripts/xyz.py download <单集ID> -o ./output
python scripts/xyz.py download <单集ID> -o ./output --with-subtitles  # 同时下载字幕
```

支持断点续传，中断后重新运行会自动恢复。

### 导出字幕

```bash
python scripts/xyz.py subtitles <单集ID> -f srt   # SRT 格式
python scripts/xyz.py subtitles <单集ID> -f txt   # 纯文本
python scripts/xyz.py subtitles <单集ID> -f json  # 原始 JSON
```

### 批量爬取（核心功能）

```bash
# 爬取10集，有字幕的快速保存，没字幕的自动转录
python scripts/xyz.py crawl <播客ID> -n 10 -o ./output

# 指定转录模型
python scripts/xyz.py crawl <播客ID> --whisper-model medium

# 重新开始（忽略已有进度）
python scripts/xyz.py crawl <播客ID> --reset
```

**两轮策略**：
1. 第1轮（快速）：遍历所有目标集，有内置字幕的直接保存
2. 第2轮（慢速）：无字幕的下载音频，用 faster-whisper 本地转录

**输出目录**（按播客名建文件夹，按发布日期排序）：
```
output/
└── AI局内人 | AGI Insider/
    ├── 01_2024-06-17_Vol20...md     # 最早
    ├── ...
    ├── 15_2025-01-23_Vol28...md     # 最新
    ├── audio/
    └── crawl_state.json
```

缺少简介或时间轴的集会标注 `[待补充]`，爬取完成后 AI 会逐集处理：补充简介、生成时间轴、对转录文本添加标点断句。每集处理完立即可见，无需等待全部完成。

**Whisper 模型选择**：

| 模型 | 转录速度 | 中文质量 | 适用场景 |
|------|---------|---------|---------|
| tiny | 最快 | 差 | 快速测试 |
| base | 快 | 一般 | 英文内容 |
| **small** | 中等 | **良好** | **中文推荐最低配置** |
| medium | 慢 | 很好 | 追求质量 |
| large-v3 | 最慢 | 最佳 | 最终版本 |

转录耗时参考（CPU，small 模型）：120 分钟音频约需 40 分钟。

### Token 管理

```bash
python scripts/xyz.py token            # 查看状态
python scripts/xyz.py token --refresh  # 手动刷新
python scripts/xyz.py token --verify   # 验证有效性
```

Token 在 API 返回 401 时会自动刷新。`refresh_token` 过期后需重新登录。

## 项目结构

```
├── SKILL.md              # Skill 配置 + 详细用法（Claude 读取）
├── reference.md          # API 端点参考（按需加载）
├── requirements.txt      # Python 依赖
├── scripts/
│   ├── xyz.py            # 主工具（所有子命令）
│   └── extract_creds.py  # ADB 凭据提取
└── output/               # 运行时输出（已 gitignore）
```

## 常见问题

| 问题 | 解决方案 |
|------|---------|
| 短信登录失败 (error 1003) | 短信登录已封禁，使用 `login --adb` 或手动抓包 |
| ADB 连不上设备 | 确保模拟器已启动；尝试端口 7555、62001、5555 |
| MuMu 找不到 ADB | 检查安装路径，通常在 `C:\Program Files\Netease\MuMu\nx_main\adb.exe` |
| su 命令失败 | MuMu 默认 adb root 不需要 su；夜神需在设置中开启 Root |
| device_id 不匹配 | refresh_token 和 device_id 必须来自同一设备同一登录 |
| Token 过期 | 重新运行 `login --adb` |
| HuggingFace 下载超时 | 已内置 hf-mirror.com 镜像，自动使用 |
| `libiomp5md.dll` 报错 | 已内置 KMP_DUPLICATE_LIB_OK=TRUE 环境变量 |
| 转录中文质量差 | 使用 small 或以上模型，tiny/base 对中文效果不好 |
