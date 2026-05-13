#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys, os
# Fix Windows terminal encoding for Chinese output
if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

"""
小宇宙播客 API 工具
用于搜索、浏览和下载小宇宙播客内容。

子命令:
  login      - 登录（支持 refresh_token+device_id 方式，短信登录已失效）
  token      - 检查/刷新 token
  search     - 搜索播客（通过 iTunes API）
  podcast    - 获取播客信息
  episodes   - 获取节目列表（分页）
  episode    - 获取单集详情（含字幕）
  download   - 下载音频（支持断点续传）
  subtitles  - 获取并转换字幕（SRT/TXT/JSON）

用法示例:
  python xyz.py login --refresh-token TOKEN --device-id DEVICE_ID
  python xyz.py search 忽左忽右
  python xyz.py episodes <podcast_id> --max-pages 2
  python xyz.py download <episode_id> -o ./output
  python xyz.py subtitles <episode_id> -f srt
"""

import argparse
import json
import time
import uuid
from pathlib import Path
from urllib.parse import urlparse, quote

try:
    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
except ImportError:
    print("错误: 需要安装 requests 库")
    print("  运行: pip install requests")
    sys.exit(3)

# Suppress SSL warnings (we use verify=False for xiaoyuzhou API)
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class APIError(Exception):
    """Raised when an API request fails. Allows batch operations to continue."""
    pass


# ============================================================
# Constants
# ============================================================

BASE_URL = "https://api.xiaoyuzhoufm.com"
CONFIG_DIR = Path.home() / ".xiaoyuzhou"
CREDENTIALS_FILE = CONFIG_DIR / "credentials.json"
DEFAULT_OUTPUT_DIR = Path.cwd() / "downloads"


# ============================================================
# Config Management
# ============================================================

def load_config():
    """Load credentials from local file."""
    if CREDENTIALS_FILE.exists():
        with open(CREDENTIALS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_config(config):
    """Save credentials to local file."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CREDENTIALS_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


# ============================================================
# Device Fingerprint (Android mode only)
# ============================================================

FIXED_DEVICE_ID = "81ADBFD6-6921-482B-9AB9-A29E7CC7BB55"  # iOS mode: hardcoded


def generate_device_id():
    """Generate a random device ID (plain UUID, matching xyz-dl)."""
    return str(uuid.uuid4())


def generate_device_properties(device_id=None):
    """Generate Android device properties. uuid field uses device_id."""
    if not device_id:
        device_id = str(uuid.uuid4())
    return {
        "uuid": device_id,
        "android_id": uuid.uuid4().hex[:16],
        "oaid": "",
        "vaid": "",
        "aaid": "",
    }


# ============================================================
# HTTP Headers — iOS (default, verified working) + Android (fallback)
# ============================================================

def get_ios_headers():
    """iOS-style headers (verified working, from MosesHe/xiaoyuzhoufm-mcp)."""
    from datetime import datetime, timezone as tz
    now = datetime.now(tz.utc)
    local_time = now.strftime('%Y-%m-%dT%H:%M:%SZ')
    return {
        "Host": "api.xiaoyuzhoufm.com",
        "Content-Type": "application/json",
        "User-Agent": "Xiaoyuzhou/2.57.1 (build:1576; iOS 17.4.1)",
        "Market": "AppStore",
        "App-BuildNo": "1576",
        "OS": "ios",
        "Manufacturer": "Apple",
        "BundleID": "app.podcast.cosmos",
        "abtest-info": '{"old_user_discovery_feed":"enable"}',
        "Accept-Language": "zh-Hans-CN;q=1.0",
        "Model": "iPhone14,2",
        "app-permissions": "4",
        "Accept": "*/*",
        "App-Version": "2.57.1",
        "Accept-Encoding": "gzip, deflate, br",
        "WifiConnected": "true",
        "OS-Version": "17.4.1",
        "Local-Time": local_time,
        "Timezone": "Asia/Shanghai",
    }


def get_android_headers():
    """Android-style headers (updated for current app version)."""
    from datetime import datetime
    now = datetime.now()
    local_time = now.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + "+0800"
    return {
        "Host": "api.xiaoyuzhoufm.com",
        "User-Agent": "okhttp/4.12.0",
        "os": "android",
        "os-version": "32",
        "manufacturer": "vivo",
        "model": "V2366GA",
        "resolution": "1080x1920",
        "market": "update",
        "applicationid": "app.podcast.cosmos",
        "app-version": "2.108.1",
        "app-buildno": "1576",
        "webviewversion": "101.0.4951.61",
        "app-permissions": "100100",
        "wificonnected": "true",
        "timezone": "Asia/Shanghai",
        "local-time": local_time,
        "content-type": "application/json;charset=utf-8",
        "Accept-Encoding": "gzip",
        "sentry-trace": "00000000000000000000000000000000-0000000000000000-0",
    }


def get_default_headers(config=None):
    """Dispatch headers based on config mode. Default: ios."""
    mode = (config or {}).get("mode", "ios")
    if mode == "android":
        return get_android_headers()
    return get_ios_headers()


def get_auth_headers(config):
    """Get headers with authentication token."""
    headers = get_default_headers(config)
    if "access_token" in config:
        headers["x-jike-access-token"] = config["access_token"]
    # Use device_id from config if available (required for refresh_token login)
    if "device_id" in config:
        headers["x-jike-device-id"] = config["device_id"]
    else:
        mode = (config or {}).get("mode", "ios")
        if mode == "ios":
            headers["x-jike-device-id"] = FIXED_DEVICE_ID
    if "device_properties" in config:
        headers["x-jike-device-properties"] = json.dumps(
            config["device_properties"], separators=(",", ":")
        )
    return headers


def get_login_headers(config):
    """Get headers for SMS auth endpoints."""
    headers = get_default_headers(config)
    # Android mode: add device fingerprint
    if (config or {}).get("mode", "ios") == "android":
        if "device_id" in config:
            headers["x-jike-device-id"] = config["device_id"]
        if "device_properties" in config:
            headers["x-jike-device-properties"] = json.dumps(
                config["device_properties"], separators=(",", ":")
            )
    return headers


def create_session():
    """Create a requests session with retry strategy."""
    session = requests.Session()
    retry = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


# ============================================================
# Authentication
# ============================================================

def refresh_access_token(config):
    """Refresh access_token using refresh_token.

    iOS mode: POST, tokens from response BODY (fallback headers).
    Android mode: GET, tokens from response HEADERS.
    """
    if "refresh_token" not in config:
        print("错误: 未找到 refresh_token，请先登录")
        print("  运行: python xyz.py login")
        sys.exit(1)

    mode = config.get("mode", "ios")
    session = create_session()
    headers = get_default_headers(config)
    headers["x-jike-refresh-token"] = config["refresh_token"]

    # Use device_id from config if available
    if "device_id" in config:
        headers["x-jike-device-id"] = config["device_id"]
    elif mode == "ios":
        headers["x-jike-device-id"] = FIXED_DEVICE_ID

    if mode == "ios":
        # iOS: POST method, form-urlencoded content-type
        headers["Content-Type"] = "application/x-www-form-urlencoded; charset=utf-8"
        resp = session.post(
            f"{BASE_URL}/app_auth_tokens.refresh",
            headers=headers,
            verify=False,
        )
    else:
        # Android: GET method
        resp = session.get(
            f"{BASE_URL}/app_auth_tokens.refresh",
            headers=headers,
            verify=False,
        )

    if resp.status_code == 401:
        print("错误: refresh_token 已过期，请重新登录")
        print("  运行: python xyz.py login")
        sys.exit(1)

    if resp.status_code != 200:
        print(f"错误: 刷新 token 失败 [{resp.status_code}] {resp.text[:200]}")
        sys.exit(1)

    # Extract tokens: try body first (iOS), then headers (Android fallback)
    new_access = None
    new_refresh = None

    try:
        body = resp.json()
        new_access = body.get("x-jike-access-token")
        new_refresh = body.get("x-jike-refresh-token")
    except (json.JSONDecodeError, ValueError):
        pass

    if not new_access:
        new_access = resp.headers.get("x-jike-access-token")
    if not new_refresh:
        new_refresh = resp.headers.get("x-jike-refresh-token")

    if new_access:
        config["access_token"] = new_access
    if new_refresh:
        config["refresh_token"] = new_refresh

    config["last_refresh"] = time.strftime("%Y-%m-%d %H:%M:%S")
    save_config(config)
    return config


def ensure_auth(config):
    """Ensure we have a valid access_token, refreshing if needed."""
    if "access_token" not in config:
        if "refresh_token" in config:
            print("access_token 缺失，正在用 refresh_token 刷新...")
            return refresh_access_token(config)
        print("错误: 未登录，请先运行: python xyz.py login")
        sys.exit(1)
    return config


def api_request(method, path, config, **kwargs):
    """Make an authenticated API request with auto-retry on 401.

    Raises APIError on failure instead of sys.exit, so batch operations can continue.
    """
    config = ensure_auth(config)
    session = create_session()
    headers = get_auth_headers(config)

    url = f"{BASE_URL}{path}" if path.startswith("/") else path

    resp = session.request(method, url, headers=headers, verify=False, **kwargs)

    # Auto-refresh on 401
    if resp.status_code == 401:
        config = refresh_access_token(config)
        headers = get_auth_headers(config)
        headers["Content-Type"] = "application/json"
        resp = session.request(method, url, headers=headers, verify=False, **kwargs)

    if resp.status_code != 200:
        msg = f"API 错误 [{resp.status_code}]: {path} — {resp.text[:300]}"
        raise APIError(msg)

    return resp.json()


# ============================================================
# Utility
# ============================================================

def parse_input(input_str):
    """Parse input as xiaoyuzhou URL or plain ID.

    Supports:
      - https://www.xiaoyuzhoufm.com/podcast/61158abc...
      - https://www.xiaoyuzhoufm.com/episode/67890abc...
      - 61158abc... (plain ID)
    """
    input_str = input_str.strip()
    if "xiaoyuzhoufm.com" in input_str:
        # Remove query params and trailing slash
        clean = input_str.split("?")[0].rstrip("/")
        parts = clean.split("/")
        if len(parts) >= 2:
            return parts[-1]
    return input_str


def sanitize_filename(name):
    """Remove characters not allowed in filenames."""
    invalid = '<>:"/\\|?*\n\r\t'
    for ch in invalid:
        name = name.replace(ch, "")
    name = name.strip(". ")
    return name[:200] if name else "untitled"


def get_audio_ext(url):
    """Get audio file extension from URL."""
    parsed = urlparse(url)
    path = parsed.path.lower()
    for ext in [".m4a", ".mp3", ".wav", ".ogg", ".flac", ".aac"]:
        if ext in path:
            return ext
    return ".m4a"


# ============================================================
# CLI Commands
# ============================================================

def cmd_login(args):
    """Login via ADB auto-extract, refresh_token + device_id, or SMS (deprecated)."""
    config = load_config()

    # --- ADB auto-extract mode (recommended) ---
    if getattr(args, "adb", False):
        try:
            sys.path.insert(0, str(Path(__file__).parent))
            from extract_creds import extract_from_adb
        except ImportError:
            print("错误: 无法导入 extract_creds.py，请确认文件存在于 scripts/ 目录")
            sys.exit(1)

        creds = extract_from_adb(
            adb_path=getattr(args, "adb_path", None),
            device_serial=getattr(args, "device", None),
        )
        if not creds:
            print("\nADB 凭据提取失败")
            print("可以尝试手动方式:")
            print("  python xyz.py login --refresh-token TOKEN --device-id DEVICE_ID")
            sys.exit(1)

        config.update(creds)
        config["mode"] = args.mode or "android"
        save_config(config)

        # If we extracted an access_token, try using it directly first
        if "access_token" in creds:
            print("\n已提取 access_token，正在验证...")
            try:
                session = create_session()
                headers = get_auth_headers(config)
                resp = session.get(
                    f"{BASE_URL}/v1/profile/get",
                    headers=headers, verify=False, timeout=15,
                )
                if resp.status_code == 200:
                    print("验证成功! (直接使用提取的 access_token)")
                    print(f"\n登录成功! (模式: {config['mode']})")
                    print(f"  Token 已保存到: {CREDENTIALS_FILE}")
                    print(f"  access_token:  {config.get('access_token', 'N/A')[:20]}...")
                    print(f"  refresh_token: {config.get('refresh_token', 'N/A')[:20]}...")
                    print(f"  device_id:     {config.get('device_id', 'N/A')}")
                    return
            except Exception:
                pass
            print("  access_token 无效，尝试刷新...")

        print("正在用 refresh_token 刷新...")
        try:
            config = refresh_access_token(config)
        except (SystemExit, APIError):
            print("\n验证失败: 提取的凭据可能已过期")
            print("请在小宇宙 App 中重新登录后再试")
            sys.exit(1)

        print(f"\n登录成功! (模式: {config['mode']})")
        print(f"  Token 已保存到: {CREDENTIALS_FILE}")
        print(f"  access_token:  {config.get('access_token', 'N/A')[:20]}...")
        print(f"  refresh_token: {config['refresh_token'][:20]}...")
        print(f"  device_id:     {config.get('device_id', 'N/A')}")
        return

    # --- refresh_token + device_id mode (preferred) ---
    if args.refresh_token or args.device_id:
        rt = args.refresh_token or input("请输入 refresh_token: ").strip()
        did = args.device_id or input("请输入 device_id: ").strip()
        if not rt:
            print("错误: refresh_token 不能为空")
            sys.exit(2)
        if not did:
            print("错误: device_id 不能为空")
            sys.exit(2)

        config["refresh_token"] = rt
        config["device_id"] = did
        config["mode"] = args.mode or "ios"
        save_config(config)

        # Validate by refreshing the access_token
        print("正在验证凭证...")
        try:
            config = refresh_access_token(config)
        except (SystemExit, APIError):
            print("\n验证失败: refresh_token 可能已过期或不匹配 device_id")
            print("请确保 refresh_token 和 device_id 来自同一设备/同一会话")
            sys.exit(1)

        print(f"\n登录成功! (模式: {config['mode']})")
        print(f"  Token 已保存到: {CREDENTIALS_FILE}")
        print(f"  access_token:  {config['access_token'][:20]}...")
        print(f"  refresh_token: {config['refresh_token'][:20]}...")
        print(f"  device_id:     {config['device_id']}")
        return

    # --- SMS login mode (deprecated, likely broken with error 1003) ---
    print("=" * 50)
    print("注意: 短信验证码登录已失效 (API 返回错误 1003)")
    print("推荐使用 refresh_token + device_id 方式登录:")
    print("  python xyz.py login --refresh-token TOKEN --device-id DEVICE_ID")
    print("=" * 50)
    print()

    mode = args.mode or "ios"
    config["mode"] = mode

    if mode == "android" and "device_id" not in config:
        config["device_id"] = str(uuid.uuid4())
        config["device_properties"] = generate_device_properties(config["device_id"])
        print(f"已生成设备指纹 (Android)")

    save_config(config)

    phone = args.phone or input("请输入手机号: ").strip()
    if not phone:
        print("错误: 手机号不能为空")
        sys.exit(2)
    area_code = args.area_code or "+86"

    session = create_session()
    headers = get_login_headers(config)

    print(f"正在发送验证码到 {phone}... (模式: {mode})")
    try:
        resp = session.post(
            f"{BASE_URL}/v1/auth/sendCode",
            headers=headers,
            data=json.dumps({"mobilePhoneNumber": phone, "areaCode": area_code}),
            verify=False,
            timeout=30,
        )
    except requests.exceptions.RequestException as e:
        print(f"网络错误: {e}")
        sys.exit(1)

    if resp.status_code != 200:
        print(f"发送验证码失败 [{resp.status_code}]: {resp.text[:200]}")
        if resp.status_code == 400:
            try:
                err = resp.json()
                if err.get("code") == 1003:
                    print("\n此错误表示短信登录已被小宇宙官方限制。")
                    print("请改用 refresh_token + device_id 方式登录。")
                    print("获取方法: 从小宇宙 APP 抓包获取 refresh_token 和 device_id")
            except (json.JSONDecodeError, ValueError):
                pass
        sys.exit(1)

    print("验证码已发送! 请查看手机短信。")
    code = input("请输入验证码: ").strip()
    if not code:
        print("错误: 验证码不能为空")
        sys.exit(2)

    print("正在验证...")
    try:
        resp = session.post(
            f"{BASE_URL}/v1/auth/loginOrSignUpWithSMS",
            headers=headers,
            data=json.dumps({
                "mobilePhoneNumber": phone,
                "areaCode": area_code,
                "verifyCode": code,
            }),
            verify=False,
            timeout=30,
        )
    except requests.exceptions.RequestException as e:
        print(f"网络错误: {e}")
        sys.exit(1)

    if resp.status_code != 200:
        print(f"登录失败 [{resp.status_code}]: {resp.text[:200]}")
        sys.exit(1)

    access_token = resp.headers.get("x-jike-access-token")
    refresh_token = resp.headers.get("x-jike-refresh-token")

    if not access_token or not refresh_token:
        print("错误: 登录响应中未找到 token")
        print(f"  响应头: {json.dumps(dict(resp.headers), indent=2)}")
        sys.exit(1)

    config["access_token"] = access_token
    config["refresh_token"] = refresh_token
    config["phone"] = phone
    config["login_time"] = time.strftime("%Y-%m-%d %H:%M:%S")
    save_config(config)

    print(f"\n登录成功! (模式: {mode})")
    print(f"  Token 已保存到: {CREDENTIALS_FILE}")
    print(f"  access_token:  {access_token[:20]}...")
    print(f"  refresh_token: {refresh_token[:20]}...")


def cmd_token(args):
    """Check or refresh token status."""
    config = load_config()

    if not config:
        print("未找到配置文件，请先登录: python xyz.py login")
        return

    print(f"配置文件: {CREDENTIALS_FILE}")
    print(f"  模式:        {config.get('mode', 'N/A')}")
    print(f"  手机号:      {config.get('phone', 'N/A')}")
    print(f"  登录时间:    {config.get('login_time', 'N/A')}")
    print(f"  上次刷新:    {config.get('last_refresh', 'N/A')}")
    print(f"  access_token:  {config.get('access_token', 'N/A')[:20]}...")
    print(f"  refresh_token: {config.get('refresh_token', 'N/A')[:20]}...")

    if args.refresh:
        print("\n正在刷新 token...")
        config = refresh_access_token(config)
        print("Token 已刷新!")

    if args.verify:
        print("\n正在验证 token...")
        try:
            data = api_request("GET", "/v1/profile/get", config)
            user = data.get("data", data)
            nickname = user.get("nickname", "Unknown")
            print(f"Token 有效! 当前用户: {nickname}")
        except (SystemExit, APIError):
            print("Token 无效或已过期")


def cmd_search(args):
    """Search podcasts via iTunes Search API (no auth needed)."""
    query = args.query
    limit = args.limit or 10

    url = f"https://itunes.apple.com/search?term={quote(query)}&media=podcast&country=CN&limit={limit}"

    print(f"正在搜索: {query}...")
    try:
        resp = requests.get(url, timeout=15)
    except requests.exceptions.RequestException as e:
        print(f"网络错误: {e}")
        sys.exit(1)

    if resp.status_code != 200:
        print(f"搜索失败 [{resp.status_code}]")
        sys.exit(1)

    data = resp.json()
    results = data.get("results", [])

    if not results:
        print("未找到相关播客")
        return

    print(f"\n找到 {len(results)} 个结果:\n")
    for i, r in enumerate(results, 1):
        name = r.get("collectionName", "Unknown")
        artist = r.get("artistName", "")
        feed_url = r.get("feedUrl", "")
        page_url = r.get("collectionViewUrl", "")

        print(f"  {i}. {name}")
        print(f"     作者: {artist}")
        if page_url:
            print(f"     页面: {page_url}")
        if feed_url:
            print(f"     RSS:  {feed_url}")
        print()

    print("提示: 小宇宙播客 ID 可从页面 URL 中获取")
    print("  例如 https://www.xiaoyuzhoufm.com/podcast/XXXXX 中的 XXXXX 就是播客 ID")


def cmd_podcast(args):
    """Get podcast details."""
    podcast_id = parse_input(args.id)
    config = load_config()
    data = api_request("GET", f"/v1/podcast/get?pid={podcast_id}", config)

    podcast = data.get("data", data)

    # Pretty print
    title = podcast.get("title", "Unknown")
    desc = podcast.get("description", "")
    author = podcast.get("author", "")
    ep_count = podcast.get("episodeCount", 0)

    print(f"标题: {title}")
    print(f"作者: {author}")
    print(f"节目数: {ep_count}")
    if desc:
        print(f"简介: {desc[:300]}")
    print()

    if args.save_json:
        output = Path(args.save_json)
        output.write_text(
            json.dumps(podcast, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(f"详情已保存到: {output}")

    if args.raw:
        print(json.dumps(podcast, indent=2, ensure_ascii=False))


def cmd_episodes(args):
    """List episodes of a podcast with pagination."""
    podcast_id = parse_input(args.podcast_id)
    config = load_config()

    all_episodes = []
    page = 0
    limit = args.limit or 20
    max_pages = args.max_pages or 1

    payload = {
        "pid": podcast_id,
        "limit": limit,
        "order": "desc",
    }

    while page < max_pages:
        if page > 0:
            print(f"正在加载第 {page + 1} 页...")
            time.sleep(0.5)

        data = api_request("POST", "/v1/episode/list", config, json=payload)

        result = data.get("data", data)
        if isinstance(result, list):
            episodes = result
        elif isinstance(result, dict):
            episodes = result.get("episodes", [])
        else:
            episodes = []

        if not episodes:
            break

        all_episodes.extend(episodes)

        # Pagination: loadMoreKey
        load_more = data.get("loadMoreKey") or result.get("loadMoreKey")
        if not load_more:
            break

        payload["loadMoreKey"] = load_more
        page += 1

    # Display
    print(f"\n共 {len(all_episodes)} 集:\n")
    for ep in all_episodes:
        title = ep.get("title", "Untitled")
        eid = ep.get("eid", ep.get("id", ""))
        duration = ep.get("duration", 0)
        pub_date = ep.get("pubDate", "")
        private = ep.get("isPrivateMedia", False)

        duration_min = duration // 1000 // 60 if isinstance(duration, (int, float)) else 0
        private_tag = " [付费]" if private else ""

        print(f"  {eid}  {title}{private_tag}")
        print(f"    时长: {duration_min}分钟 | 发布: {pub_date}")

    # Save
    if args.save_json:
        output = Path(args.save_json)
        output.write_text(
            json.dumps(all_episodes, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(f"\n已保存到: {output}")


def cmd_episode(args):
    """Get single episode detail (includes subtitle data)."""
    episode_id = parse_input(args.id)
    config = load_config()
    data = api_request("GET", f"/v1/episode/get?eid={episode_id}", config)

    episode = data.get("data", data)

    # Summary
    title = episode.get("title", "Untitled")
    description = episode.get("description", "")
    duration = episode.get("duration", 0)
    duration_min = duration // 1000 // 60 if isinstance(duration, (int, float)) else 0
    private = episode.get("isPrivateMedia", False)
    subtitle_count = episode.get("subtitleCount", 0)

    print(f"标题: {title}")
    print(f"时长: {duration_min} 分钟")
    if private:
        print("类型: 付费内容")
    if subtitle_count:
        print(f"字幕: 有 ({subtitle_count} 段)")
    if description:
        print(f"简介: {description[:300]}")

    # Audio info
    audio_url = episode.get("enclosure", {}).get("url")

    if private and not args.skip_media:
        print("\n正在获取付费内容音频 URL...")
        try:
            priv_data = api_request(
                "GET", f"/v1/private-media/get?eid={episode_id}", config
            )
            priv_info = priv_data.get("data", priv_data)
            audio_url = priv_info.get("url", audio_url)
        except (SystemExit, APIError):
            print("获取付费内容失败 (可能需要订阅)")

    if audio_url:
        print(f"\n音频 URL: {audio_url}")

    # Save
    if args.save_json:
        output = Path(args.save_json)
        output.write_text(
            json.dumps(episode, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(f"详情已保存到: {output}")

    if args.raw:
        print(json.dumps(episode, indent=2, ensure_ascii=False))


def cmd_download(args):
    """Download episode audio with resume support."""
    episode_id = parse_input(args.episode_id)
    config = load_config()

    # Get episode info
    print("正在获取节目信息...")
    data = api_request("GET", f"/v1/episode/get?eid={episode_id}", config)
    episode = data.get("data", data)

    title = episode.get("title", "Untitled")
    private = episode.get("isPrivateMedia", False)

    # Get audio URL
    audio_url = episode.get("enclosure", {}).get("url")

    if private:
        print("正在获取付费内容音频 URL...")
        try:
            priv_data = api_request(
                "GET", f"/v1/private-media/get?eid={episode_id}", config
            )
            priv_info = priv_data.get("data", priv_data)
            audio_url = priv_info.get("url", audio_url)
        except (SystemExit, APIError):
            print("获取付费内容失败")
            sys.exit(1)

    if not audio_url:
        print("错误: 未找到音频 URL")
        sys.exit(1)

    # Output path
    output_dir = Path(args.output) if args.output else DEFAULT_OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    safe_title = sanitize_filename(title)
    ext = get_audio_ext(audio_url)
    output_file = output_dir / f"{safe_title}{ext}"
    tmp_file = output_file.with_suffix(output_file.suffix + ".tmp")

    # Skip if already exists
    if output_file.exists() and not args.force:
        print(f"文件已存在: {output_file}")
        print("使用 --force 强制重新下载")
        return

    print(f"正在下载: {title}")
    print(f"保存到: {output_file}")

    # Resume support
    headers = {}
    existing_size = 0
    if tmp_file.exists() and args.resume:
        existing_size = tmp_file.stat().st_size
        if existing_size > 0:
            headers["Range"] = f"bytes={existing_size}-"
            print(f"断点续传: 已有 {existing_size / 1024 / 1024:.1f} MB")

    # Download with progress
    session = create_session()
    try:
        resp = session.get(audio_url, headers=headers, stream=True, verify=False, timeout=60)
    except requests.exceptions.RequestException as e:
        print(f"\n网络错误: {e}")
        sys.exit(1)

    if resp.status_code == 416:
        # Range not satisfiable — file already complete
        tmp_file.rename(output_file)
        print("文件已下载完成!")
        return

    total_size = int(resp.headers.get("content-length", 0))
    if existing_size > 0 and resp.status_code == 200:
        # Server doesn't support range, restart
        existing_size = 0

    downloaded = existing_size
    last_print = 0
    mode = "ab" if existing_size > 0 and resp.status_code == 206 else "wb"

    with open(tmp_file, mode) as f:
        for chunk in resp.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)
                downloaded += len(chunk)

                # Print progress every 0.5s
                now = time.time()
                if now - last_print > 0.5:
                    if total_size:
                        full_size = existing_size + total_size
                        pct = downloaded / full_size * 100
                        mb = downloaded / 1024 / 1024
                        total_mb = full_size / 1024 / 1024
                        print(
                            f"\r  下载中: {pct:.1f}% ({mb:.1f}/{total_mb:.1f} MB)",
                            end="",
                            flush=True,
                        )
                    else:
                        mb = downloaded / 1024 / 1024
                        print(f"\r  下载中: {mb:.1f} MB", end="", flush=True)
                    last_print = now

    print()  # New line after progress

    # Rename tmp to final
    if tmp_file.exists():
        tmp_file.rename(output_file)

    print(f"下载完成: {output_file}")
    final_size = output_file.stat().st_size / 1024 / 1024
    print(f"文件大小: {final_size:.1f} MB")

    # Download subtitles if requested
    if args.with_subtitles:
        _download_subtitles(config, episode_id, output_dir, safe_title)


def _download_subtitles(config, episode_id, output_dir, safe_title):
    """Helper: download and save subtitles."""
    print("正在获取字幕...")
    data = api_request("GET", f"/v1/episode/get?eid={episode_id}", config)
    episode = data.get("data", data)

    subtitles = episode.get("subtitle", [])
    if not subtitles:
        subtitles = episode.get("subtitles", [])

    if not subtitles:
        print("该集没有字幕数据")
        return

    # Save SRT
    srt_content = subtitle_to_srt(subtitles)
    srt_file = output_dir / f"{safe_title}.srt"
    srt_file.write_text(srt_content, encoding="utf-8")
    print(f"字幕 (SRT): {srt_file}")

    # Save TXT
    txt_content = subtitle_to_text(subtitles)
    txt_file = output_dir / f"{safe_title}.txt"
    txt_file.write_text(txt_content, encoding="utf-8")
    print(f"字幕 (TXT): {txt_file}")


def cmd_subtitles(args):
    """Get and convert episode subtitles."""
    episode_id = parse_input(args.episode_id)
    config = load_config()

    print("正在获取字幕数据...")
    data = api_request("GET", f"/v1/episode/get?eid={episode_id}", config)
    episode = data.get("data", data)

    subtitles = episode.get("subtitle", [])
    if not subtitles:
        subtitles = episode.get("subtitles", [])

    if not subtitles:
        print("该集没有字幕数据")
        return

    print(f"找到 {len(subtitles)} 条字幕数据")

    output_dir = Path(args.output) if args.output else Path.cwd()
    output_dir.mkdir(parents=True, exist_ok=True)

    fmt = args.format or "all"
    base_name = sanitize_filename(
        episode.get("title", episode_id)
    )

    if fmt in ("srt", "all"):
        content = subtitle_to_srt(subtitles)
        fpath = output_dir / f"{base_name}.srt"
        fpath.write_text(content, encoding="utf-8")
        print(f"SRT 已保存: {fpath}")

    if fmt in ("txt", "all"):
        content = subtitle_to_text(subtitles)
        fpath = output_dir / f"{base_name}.txt"
        fpath.write_text(content, encoding="utf-8")
        print(f"TXT 已保存: {fpath}")

    if fmt in ("json", "all"):
        content = json.dumps(subtitles, indent=2, ensure_ascii=False)
        fpath = output_dir / f"{base_name}.json"
        fpath.write_text(content, encoding="utf-8")
        print(f"JSON 已保存: {fpath}")


# ============================================================
# Subtitle Conversion
# ============================================================

def word_level_to_sentences(words, gap_ms=500):
    """Group word-level subtitle entries into sentences by silence gap.

    Each word: {"text": "...", "startMs": N, "durationMs": N}
    If gap between words > gap_ms, start a new sentence.
    """
    if not words:
        return []

    sentences = []
    cur_text = words[0].get("text", "")
    cur_start = words[0].get("startMs", 0)
    cur_end = cur_start + words[0].get("durationMs", 0)

    for word in words[1:]:
        w_start = word.get("startMs", 0)
        w_text = word.get("text", "")
        w_dur = word.get("durationMs", 0)

        if w_start - cur_end > gap_ms:
            # Gap detected — save current sentence, start new one
            sentences.append(
                {"text": cur_text, "startMs": cur_start, "endMs": cur_end}
            )
            cur_text = w_text
            cur_start = w_start
        else:
            cur_text += w_text

        cur_end = w_start + w_dur

    # Last sentence
    if cur_text:
        sentences.append({"text": cur_text, "startMs": cur_start, "endMs": cur_end})

    return sentences


def ms_to_srt_time(ms):
    """Convert milliseconds to SRT timestamp: HH:MM:SS,mmm"""
    hours = ms // 3600000
    minutes = (ms % 3600000) // 60000
    seconds = (ms % 60000) // 1000
    millis = ms % 1000
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"


def subtitle_to_srt(subtitles, gap_ms=500):
    """Convert word-level subtitle array to SRT format string."""
    sentences = word_level_to_sentences(subtitles, gap_ms)
    lines = []

    for i, s in enumerate(sentences, 1):
        start = ms_to_srt_time(s["startMs"])
        end = ms_to_srt_time(s["endMs"])
        lines.append(str(i))
        lines.append(f"{start} --> {end}")
        lines.append(s["text"])
        lines.append("")

    return "\n".join(lines)


def subtitle_to_text(subtitles):
    """Convert subtitle array to plain text."""
    return "".join(w.get("text", "") for w in subtitles)


# ============================================================
# Audio Transcription (faster-whisper)
# ============================================================

def _convert_for_whisper(audio_path):
    """Convert audio to 16kHz mono WAV for faster whisper processing."""
    import subprocess as sp
    wav_path = audio_path.with_suffix(".wav")
    if wav_path.exists():
        return wav_path
    print("    转换音频为 16kHz mono...")
    sp.run([
        "ffmpeg", "-y", "-i", str(audio_path),
        "-ar", "16000", "-ac", "1", "-b:a", "32k",
        str(wav_path)
    ], capture_output=True, check=True)
    wav_mb = wav_path.stat().st_size / 1024 / 1024
    print(f"    转换后: {wav_mb:.1f}MB")
    return wav_path


def _cleanup_wav(audio_path):
    """Remove temporary WAV file created for whisper."""
    wav_path = audio_path.with_suffix(".wav")
    if wav_path.exists():
        wav_path.unlink()


def transcribe_audio(audio_path, model_size="small"):
    """Transcribe audio file using faster-whisper. Returns full text."""
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        print("    错误: 需要安装 faster-whisper (pip install faster-whisper)")
        return ""

    # Ensure environment for China / Windows
    os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
    os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

    wav_path = _convert_for_whisper(audio_path)

    print(f"    加载 Whisper 模型 ({model_size})...")
    model = WhisperModel(model_size, device="cpu", compute_type="int8")

    print("    正在转录...")
    t0 = time.time()
    segments, info = model.transcribe(
        str(wav_path),
        language="zh",
        beam_size=3,
        vad_filter=True,
        vad_parameters=dict(min_silence_duration_ms=500),
    )

    text_parts = [seg.text.strip() for seg in segments]
    elapsed = time.time() - t0
    full_text = "".join(text_parts)
    audio_min = info.duration / 60
    print(f"    转录完成: {len(full_text)} 字, 音频 {audio_min:.1f} 分钟, 耗时 {elapsed:.0f}s")

    # Clean up temp WAV
    _cleanup_wav(audio_path)

    return full_text


# ============================================================
# Crawl Command
# ============================================================

def _process_single_episode(eid, seq, output_dir, audio_dir, config, whisper_model="small"):
    """Process a single episode: get details, subtitle or transcribe, save .md.

    Returns the saved file path on success, None on failure.
    """
    print(f"\n  [{seq}] {eid}")

    try:
        detail = api_request("GET", f"/v1/episode/get?eid={eid}", config)
    except APIError as e:
        print(f"    跳过: {e}")
        return None

    ep_data = detail.get("data", detail)
    title = ep_data.get("title", "Unknown")
    desc = ep_data.get("description", "")
    duration = ep_data.get("duration", 0)
    shownotes = ep_data.get("shownotes", "")
    pub_date = ep_data.get("pubDate", "")[:10]
    subtitles_raw = ep_data.get("subtitle", [])
    enclosure = ep_data.get("enclosure", {})
    audio_url = enclosure.get("url", "") if isinstance(enclosure, dict) else ""

    # Metadata
    podcast_info = ep_data.get("podcast", {})
    podcasters_raw = podcast_info.get("podcasters", [])
    ep_meta = {
        "pub_date": pub_date,
        "podcast_title": podcast_info.get("title", "N/A"),
        "podcasters": [
            {"nickname": p.get("nickname", ""), "bio": p.get("bio", "")}
            for p in podcasters_raw if p.get("nickname")
        ],
    }

    # Check for private media
    if not audio_url and ep_data.get("isPrivateMedia"):
        try:
            pm = api_request("GET", f"/v1/private-media/get?eid={eid}", config)
            pm_data = pm.get("data", pm)
            audio_url = pm_data.get("url", "")
        except APIError:
            pass

    # Try subtitles first
    subtitle_text = ""
    if subtitles_raw:
        subtitle_text = subtitle_to_text(subtitles_raw)

    if subtitle_text:
        print(f"    {pub_date} {title}")
        print(f"    内置字幕: {len(subtitle_text)} 字")
        md_file = _save_episode(output_dir, seq, pub_date, eid, title, desc,
                                duration, shownotes, "内置字幕", subtitle_text, ep_meta)
        return md_file

    # No subtitles — download and transcribe
    if not audio_url:
        print(f"    {pub_date} {title} — 无音频无字幕，跳过")
        return None

    print(f"    {pub_date} {title} — 下载音频...")
    audio_file = audio_dir / f"{eid}.m4a"
    if not audio_file.exists():
        session = create_session()
        resp = session.get(audio_url, stream=True, verify=False, timeout=300)
        with open(audio_file, "wb") as f:
            for chunk in resp.iter_content(chunk_size=65536):
                f.write(chunk)
        mb = audio_file.stat().st_size / 1024 / 1024
        print(f"    下载完成: {mb:.1f}MB")
    else:
        mb = audio_file.stat().st_size / 1024 / 1024
        print(f"    音频已存在 ({mb:.1f}MB)")

    transcript = transcribe_audio(audio_file, whisper_model)
    md_file = _save_episode(output_dir, seq, pub_date, eid, title, desc,
                            duration, shownotes, "音频转录", transcript, ep_meta)
    return md_file


def cmd_crawl(args):
    """Batch-crawl a podcast: subtitle-first, audio-transcription fallback."""
    podcast_id = parse_input(args.podcast_id)
    config = load_config()

    max_episodes = args.max_episodes
    whisper_model = args.whisper_model

    # Get podcast info first (for folder name)
    print("获取播客信息...")
    try:
        pod_data = api_request("GET", f"/v1/podcast/get?pid={podcast_id}", config)
    except APIError as e:
        print(f"错误: 无法获取播客信息: {e}")
        return
    pod_info = pod_data.get("data", pod_data)
    podcast_title = pod_info.get("title", podcast_id)
    safe_podcast = sanitize_filename(podcast_title)

    # Output dir: output/<podcast_name>/
    base_dir = Path(args.output)
    output_dir = base_dir / safe_podcast
    output_dir.mkdir(parents=True, exist_ok=True)
    audio_dir = output_dir / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    state_file = output_dir / "crawl_state.json"

    print(f"播客: {podcast_title}")
    print(f"输出目录: {output_dir}")

    # Load state
    state = {"crawled": [], "count": 0}
    if state_file.exists() and not args.reset:
        with open(state_file, "r", encoding="utf-8") as f:
            state = json.load(f)

    if state["count"] >= max_episodes and not args.reset:
        print(f"已完成 {state['count']} 次爬取，任务结束！（使用 --reset 重新开始）")
        return

    # Get ALL episodes (need full list for date-based ordering)
    print("获取节目列表...")
    all_episodes = []
    payload = {"pid": podcast_id, "limit": 20, "order": "desc"}
    while True:
        try:
            data = api_request("POST", "/v1/episode/list", config, json=payload)
        except APIError as e:
            print(f"  获取列表失败: {e}")
            break
        batch = data.get("data", data)
        if isinstance(batch, list):
            all_episodes.extend(batch)
        elif isinstance(batch, dict):
            all_episodes.extend(batch.get("episodes", []))
        load_more = data.get("loadMoreKey") or data.get("loadNextKey")
        if not load_more:
            break
        payload["loadMoreKey"] = load_more
        time.sleep(0.5)

    # Sort by pubDate descending first to pick the latest N episodes
    all_episodes.sort(key=lambda ep: ep.get("pubDate", ""), reverse=True)
    latest_episodes = all_episodes[:max_episodes]

    # Re-sort the selected subset ascending for naming (oldest=01)
    latest_episodes.sort(key=lambda ep: ep.get("pubDate", ""))

    print(f"共 {len(all_episodes)} 集节目，取最新 {len(latest_episodes)} 集（按发布日期升序编号）")

    # Build target set and sequence map from the selected subset only
    target_eids = set()
    for i, ep in enumerate(latest_episodes):
        eid = ep.get("eid", ep.get("id", ""))
        target_eids.add(eid)

    seq_map = {}
    for i, ep in enumerate(latest_episodes):
        eid = ep.get("eid", ep.get("id", ""))
        seq_map[eid] = i + 1

    # Filter to uncrawled episodes from target set
    crawled_eids = set(state["crawled"])
    remaining = max_episodes - state["count"]
    uncrawled = []
    for ep in latest_episodes:
        eid = ep.get("eid", ep.get("id", ""))
        if eid not in crawled_eids and len(uncrawled) < remaining:
            uncrawled.append(eid)

    if not uncrawled:
        print("所有节目已爬取完毕！")
        return

    print(f"待爬取: {len(uncrawled)} 集")

    # ── Pass 1: Quick scan — save those with subtitles ──
    print("\n" + "=" * 60)
    print("【第1轮】快速扫描 — 优先保存有字幕的节目")
    print("=" * 60)

    needs_transcription = []

    for eid in uncrawled:
        try:
            detail = api_request("GET", f"/v1/episode/get?eid={eid}", config)
        except APIError as e:
            print(f"  跳过 {eid}: {e}")
            continue

        ep_data = detail.get("data", detail)
        title = ep_data.get("title", "Unknown")
        desc = ep_data.get("description", "")
        duration = ep_data.get("duration", 0)
        shownotes = ep_data.get("shownotes", "")
        pub_date = ep_data.get("pubDate", "")[:10]
        subtitles_raw = ep_data.get("subtitle", [])
        enclosure = ep_data.get("enclosure", {})
        audio_url = enclosure.get("url", "") if isinstance(enclosure, dict) else ""

        # Extract metadata
        podcast_info = ep_data.get("podcast", {})
        podcasters_raw = podcast_info.get("podcasters", [])
        ep_meta = {
            "pub_date": pub_date,
            "podcast_title": podcast_info.get("title", podcast_title),
            "podcasters": [
                {"nickname": p.get("nickname", ""), "bio": p.get("bio", "")}
                for p in podcasters_raw if p.get("nickname")
            ],
        }

        # Check for private media
        if not audio_url and ep_data.get("isPrivateMedia"):
            try:
                pm = api_request("GET", f"/v1/private-media/get?eid={eid}", config)
                pm_data = pm.get("data", pm)
                audio_url = pm_data.get("url", "")
            except APIError:
                pass

        subtitle_text = ""
        if subtitles_raw:
            subtitle_text = subtitle_to_text(subtitles_raw)

        seq = seq_map.get(eid, state["count"] + 1)

        if subtitle_text:
            print(f"  [{seq}] {pub_date} {title}")
            print(f"    内置字幕: {len(subtitle_text)} 字")
            _save_episode(output_dir, seq, pub_date, eid, title, desc, duration, shownotes, "内置字幕", subtitle_text, ep_meta)
            state["crawled"].append(eid)
            state["count"] += 1
            _save_state(state_file, state)
        else:
            has_audio = bool(audio_url)
            label = "有音频，需转录" if has_audio else "无音频无字幕"
            print(f"  [排队] {pub_date} {title} — {label}")
            if has_audio:
                needs_transcription.append({
                    "eid": eid, "seq": seq, "pub_date": pub_date,
                    "title": title, "description": desc,
                    "duration": duration, "shownotes": shownotes, "audio_url": audio_url,
                    "ep_meta": ep_meta,
                })

        time.sleep(0.3)

    # ── Pass 2: Audio transcription ──
    if needs_transcription:
        print("\n" + "=" * 60)
        print(f"【第2轮】音频转录 — {len(needs_transcription)} 集需要转录")
        print("=" * 60)

        for ep in needs_transcription:
            if state["count"] >= max_episodes:
                break

            eid = ep["eid"]
            title = ep["title"]
            seq = ep["seq"]
            pub_date = ep["pub_date"]
            print(f"\n  [{seq}] {pub_date} {title}")

            audio_file = audio_dir / f"{eid}.m4a"

            if not audio_file.exists():
                print(f"    下载音频...")
                session = create_session()
                resp = session.get(ep["audio_url"], stream=True, verify=False, timeout=300)
                with open(audio_file, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=65536):
                        f.write(chunk)
                mb = audio_file.stat().st_size / 1024 / 1024
                print(f"    下载完成: {mb:.1f}MB")
            else:
                mb = audio_file.stat().st_size / 1024 / 1024
                print(f"    音频已存在 ({mb:.1f}MB)，跳过下载")

            transcript = transcribe_audio(audio_file, whisper_model)

            _save_episode(output_dir, seq, pub_date, eid, title, ep["description"],
                          ep["duration"], ep["shownotes"], "音频转录", transcript,
                          ep.get("ep_meta"))
            state["crawled"].append(eid)
            state["count"] += 1
            _save_state(state_file, state)

    # ── Summary ──
    print("\n" + "=" * 60)
    print(f"爬取完成! {podcast_title} — 共 {state['count']} 集")
    print(f"输出目录: {output_dir}")
    print("=" * 60)


def cmd_crawl_one(args):
    """Process a single episode: get details, subtitle or transcribe, save .md."""
    eid = parse_input(args.episode_id)
    config = load_config()
    seq = args.seq

    # Output dir
    base_dir = Path(args.output)
    output_dir = base_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    audio_dir = output_dir / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)

    md_file = _process_single_episode(eid, seq, output_dir, audio_dir, config, args.whisper_model)
    if md_file:
        print(f"\n完成! 输出: {md_file}")
    else:
        print(f"\n处理失败: {eid}")

    # ── Summary ──
    print("\n" + "=" * 60)
    print(f"爬取完成! {podcast_title} — 共 {state['count']} 集")
    print(f"输出目录: {output_dir}")
    print("=" * 60)


def _save_episode(output_dir, seq, pub_date, eid, title, desc, duration, shownotes, source, text, ep_meta=None):
    """Save episode as a single Markdown file.

    File naming: NN_YYYY-MM-DD_标题.md (ordered by publication date, oldest first)
    """
    safe_title = sanitize_filename(title)[:60]
    date_prefix = pub_date if pub_date else "unknown-date"
    meta = ep_meta or {}

    # Format duration
    if duration:
        hours, remainder = divmod(duration, 3600)
        minutes, seconds = divmod(remainder, 60)
        duration_text = f"{hours}小时{minutes}分{seconds}秒" if hours else f"{minutes}分{seconds}秒"
    else:
        duration_text = "未知"

    # Podcasters info
    podcasters = meta.get("podcasters", [])

    # Build Markdown
    md_file = output_dir / f"{seq:02d}_{date_prefix}_{safe_title}.md"
    with open(md_file, "w", encoding="utf-8") as f:
        # Title
        f.write(f"# {title}\n\n")

        # --- Meta ---
        f.write(f"- **播客**: {meta.get('podcast_title', 'N/A')}\n")
        f.write(f"- **发布日期**: {pub_date or 'N/A'}\n")
        f.write(f"- **时长**: {duration_text}\n")
        f.write(f"- **内容来源**: {source}\n")
        f.write(f"- **单集ID**: {eid}\n")

        # Podcasters
        if podcasters:
            f.write(f"- **主播/嘉宾**:\n")
            for p in podcasters:
                nick = p.get("nickname", "")
                bio = p.get("bio", "")
                if bio:
                    f.write(f"  - {nick} — {bio}\n")
                else:
                    f.write(f"  - {nick}\n")

        # --- 简介 ---
        f.write(f"\n## 简介\n\n")
        if desc:
            f.write(f"{desc}\n")
        else:
            f.write(f"[待补充：请根据正文内容生成简介摘要]\n")

        # --- 时间轴 ---
        f.write(f"\n## 时间轴\n\n")
        if shownotes:
            shownotes_text = _strip_html(shownotes)
            if shownotes_text:
                f.write(f"{shownotes_text}\n")
            else:
                f.write("[待补充：请根据正文内容生成时间轴/章节摘要]\n")
        else:
            f.write("[待补充：请根据正文内容生成时间轴/章节摘要]\n")

        # --- 正文 ---
        f.write(f"\n## 正文\n\n")
        if text:
            if source == "音频转录":
                f.write("> [!note]\n")
                f.write("> 以下为语音识别原始文本，**无标点断句**，可能存在识别错误（人名、术语等）。\n")
                f.write("> 请在此基础上进行后处理：添加标点、修正错误、按话题分段。\n\n")
            f.write(text)
        else:
            f.write("[无文本内容]\n")

    chars = len(text) if text else 0
    print(f"    已保存: {md_file} ({chars} 字)")


def _save_state(state_file, state):
    """Save crawl state to JSON."""
    with open(state_file, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def _strip_html(html_str):
    """Simple HTML to plain text conversion."""
    import re as _re
    import html as _html
    text = _re.sub(r'<br\s*/?>', '\n', html_str)
    text = _re.sub(r'</p>', '\n', text)
    text = _re.sub(r'<[^>]+>', '', text)
    text = _html.unescape(text)
    text = _re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


# ============================================================
# CLI Entry Point
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="小宇宙播客 API 工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python xyz.py login --adb                     # 从 ADB 设备自动提取凭据（推荐）
  python xyz.py login -t TOKEN -d DEVICE_ID     # 手动输入凭据登录
  python xyz.py search 忽左忽右                  # 搜索播客
  python xyz.py episodes <podcast_id>            # 列出节目
  python xyz.py download <episode_id>            # 下载音频
  python xyz.py subtitles <episode_id> -f srt    # 获取字幕
  python xyz.py crawl <podcast_id> -n 10          # 批量爬取播客（含转录）

播客/单集 ID 可以是纯 ID，也可以是完整 URL:
  python xyz.py podcast https://www.xiaoyuzhoufm.com/podcast/xxxxx

获取 refresh_token 和 device_id:
  方式1 (推荐): python xyz.py login --adb  # 自动从 MuMu/夜神模拟器/真机提取
  方式2 (手动): 使用抓包工具（如 Charles/mitmproxy）捕获请求头
        """,
    )
    sub = parser.add_subparsers(dest="command", help="可用命令")

    # ---- login ----
    p_login = sub.add_parser("login", help="登录（推荐 refresh_token 或 ADB 方式）")
    p_login.add_argument("--refresh-token", "-t", help="refresh_token（从小宇宙APP抓包获取）")
    p_login.add_argument("--device-id", "-d", help="device_id（需与 refresh_token 匹配）")
    p_login.add_argument("--adb", action="store_true",
                         help="从 ADB 连接的设备自动提取凭据（推荐）")
    p_login.add_argument("--adb-path", help="ADB 工具路径（--adb 模式专用，自动检测如果省略）")
    p_login.add_argument("--device", help="ADB 设备序列号（--adb 模式专用，自动选择如果省略）")
    p_login.add_argument("--phone", "-p", help="手机号（短信登录，已失效）")
    p_login.add_argument("--area-code", "-a", default="+86", help="区号 (默认 +86)")
    p_login.add_argument("--mode", "-m", choices=["ios", "android"], default="ios",
                         help="请求头模式 (默认 ios，推荐)")

    # ---- token ----
    p_token = sub.add_parser("token", help="检查/刷新/验证 token")
    p_token.add_argument("--refresh", "-r", action="store_true", help="刷新 token")
    p_token.add_argument("--verify", "-v", action="store_true", help="验证 token 是否有效")

    # ---- search ----
    p_search = sub.add_parser("search", help="搜索播客 (iTunes API，无需登录)")
    p_search.add_argument("query", help="搜索关键词")
    p_search.add_argument("--limit", "-n", type=int, default=10, help="结果数量 (默认 10)")

    # ---- podcast ----
    p_podcast = sub.add_parser("podcast", help="获取播客详情")
    p_podcast.add_argument("id", help="播客 ID 或 URL")
    p_podcast.add_argument("--save-json", metavar="FILE", help="保存为 JSON 文件")
    p_podcast.add_argument("--raw", action="store_true", help="输出完整 JSON")

    # ---- episodes ----
    p_episodes = sub.add_parser("episodes", help="获取播客节目列表")
    p_episodes.add_argument("podcast_id", help="播客 ID 或 URL")
    p_episodes.add_argument("--limit", "-n", type=int, default=20, help="每页数量 (默认 20)")
    p_episodes.add_argument("--max-pages", type=int, default=1, help="最大页数 (默认 1)")
    p_episodes.add_argument("--save-json", metavar="FILE", help="保存为 JSON 文件")

    # ---- episode ----
    p_episode = sub.add_parser("episode", help="获取单集详情（含字幕数据）")
    p_episode.add_argument("id", help="单集 ID 或 URL")
    p_episode.add_argument("--save-json", metavar="FILE", help="保存为 JSON 文件")
    p_episode.add_argument("--raw", action="store_true", help="输出完整 JSON")
    p_episode.add_argument("--skip-media", action="store_true", help="跳过付费内容音频 URL 获取")

    # ---- download ----
    p_download = sub.add_parser("download", help="下载音频文件")
    p_download.add_argument("episode_id", help="单集 ID 或 URL")
    p_download.add_argument("-o", "--output", default=str(DEFAULT_OUTPUT_DIR), help="输出目录")
    p_download.add_argument("--no-resume", dest="resume", action="store_false", help="不使用断点续传")
    p_download.add_argument("--force", "-f", action="store_true", help="强制重新下载")
    p_download.add_argument("--with-subtitles", "-s", action="store_true", help="同时下载字幕")

    # ---- subtitles ----
    p_sub = sub.add_parser("subtitles", help="获取并转换字幕")
    p_sub.add_argument("episode_id", help="单集 ID 或 URL")
    p_sub.add_argument("-o", "--output", default=".", help="输出目录")
    p_sub.add_argument(
        "-f",
        "--format",
        choices=["srt", "txt", "json", "all"],
        default="all",
        help="字幕格式 (默认 all)",
    )

    # ---- crawl ----
    p_crawl = sub.add_parser("crawl", help="批量爬取播客（字幕优先，音频转录兜底）")
    p_crawl.add_argument("podcast_id", help="播客 ID 或 URL")
    p_crawl.add_argument("-n", "--max-episodes", type=int, default=10, help="爬取集数 (默认 10)")
    p_crawl.add_argument("-o", "--output", default=str(DEFAULT_OUTPUT_DIR / "crawl"),
                         help="输出目录 (默认 ./downloads/crawl)")
    p_crawl.add_argument("--whisper-model", default="small",
                         choices=["tiny", "base", "small", "medium", "large-v3"],
                         help="Whisper 模型 (默认 small，需安装 faster-whisper)")
    p_crawl.add_argument("--reset", action="store_true", help="重置状态，从头开始")

    # ---- crawl-one ----
    p_crawl_one = sub.add_parser("crawl-one", help="处理单集（供逐集爬取使用）")
    p_crawl_one.add_argument("episode_id", help="单集 ID 或 URL")
    p_crawl_one.add_argument("--seq", type=int, default=1, help="序号 (默认 1)")
    p_crawl_one.add_argument("-o", "--output", default=str(DEFAULT_OUTPUT_DIR / "crawl"),
                             help="输出目录")
    p_crawl_one.add_argument("--whisper-model", default="small",
                             choices=["tiny", "base", "small", "medium", "large-v3"],
                             help="Whisper 模型 (默认 small)")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    commands = {
        "login": cmd_login,
        "token": cmd_token,
        "search": cmd_search,
        "podcast": cmd_podcast,
        "episodes": cmd_episodes,
        "episode": cmd_episode,
        "download": cmd_download,
        "subtitles": cmd_subtitles,
        "crawl": cmd_crawl,
        "crawl-one": cmd_crawl_one,
    }

    cmd_func = commands.get(args.command)
    if cmd_func:
        try:
            cmd_func(args)
        except APIError as e:
            print(f"错误: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
