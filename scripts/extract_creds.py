#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
小宇宙播客 — ADB 自动凭据提取工具

自动从 ADB 连接的设备（MuMu/夜神模拟器/真机）中提取小宇宙 App 的
refresh_token 和 device_id，并保存到 ~/.xiaoyuzhou/credentials.json。

用法:
  python extract_creds.py                    # 自动检测 ADB 并提取
  python extract_creds.py --adb-path PATH    # 指定 ADB 路径
  python extract_creds.py --device SERIAL    # 指定设备序列号
  python extract_creds.py --verify           # 提取后验证凭据有效性
"""

import json
import os
import platform
import re
import subprocess
import sys
import time
from pathlib import Path
from xml.etree import ElementTree as ET

# Fix Windows terminal encoding
if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# ============================================================
# Constants
# ============================================================

PKG = "app.podcast.cosmos"
SHARED_PREFS_DIR = f"/data/data/{PKG}/shared_prefs"
CONFIG_DIR = Path.home() / ".xiaoyuzhou"
CREDENTIALS_FILE = CONFIG_DIR / "credentials.json"

# Emulator ADB default paths (Windows)
EMU_ADB_PATHS = [
    # MuMu emulator (priority)
    r"C:\Program Files\Netease\MuMu\nx_main\adb.exe",
    r"D:\Program Files\Netease\MuMu\nx_main\adb.exe",
    r"C:\Program Files\Netease\MuMuPlayer-12.0\shell\adb.exe",
    # Nox emulator
    r"C:\Program Files\Nox\bin\nox_adb.exe",
    r"C:\Program Files (x86)\Nox\bin\nox_adb.exe",
    r"D:\Program Files\Nox\bin\nox_adb.exe",
    r"D:\Nox\bin\nox_adb.exe",
]


# ============================================================
# ADB Helpers
# ============================================================

def find_adb(custom_path=None):
    """Find ADB binary. Priority: custom_path > system PATH > emulator paths."""
    if custom_path:
        if os.path.isfile(custom_path):
            return custom_path
        print(f"错误: 指定的 ADB 路径不存在: {custom_path}")
        sys.exit(1)

    # Try system adb
    adb_name = "adb.exe" if platform.system() == "Windows" else "adb"
    try:
        result = subprocess.run(
            [adb_name, "version"],
            capture_output=True, timeout=5,
            encoding="utf-8", errors="replace",
        )
        if result.returncode == 0:
            return adb_name
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # Try emulator paths
    for path in EMU_ADB_PATHS:
        if os.path.isfile(path):
            return path

    print("错误: 未找到 ADB 工具")
    print("  请选择以下方式之一:")
    print("  1. 安装 Android SDK Platform Tools 并添加到 PATH")
    print("  2. 安装 MuMu/夜神模拟器（自动检测 ADB）")
    print("  3. 使用 --adb-path 指定 ADB 路径")
    sys.exit(1)


def adb_run(adb_path, args, device=None, timeout=15):
    """Run an ADB command, return (stdout, stderr, returncode) or None on timeout."""
    cmd = [adb_path]
    if device:
        cmd += ["-s", device]
    cmd += args
    try:
        r = subprocess.run(
            cmd, capture_output=True, timeout=timeout,
            encoding="utf-8", errors="replace",
        )
        return r
    except subprocess.TimeoutExpired:
        return None
    except FileNotFoundError:
        print(f"错误: ADB 工具不存在: {adb_path}")
        sys.exit(1)


def shell_cmd(adb_path, device, shell_args, root_mode, timeout=15):
    """Build and run a shell command with the right root prefix.

    root_mode: 'adb_root' = shell already root (MuMu, adb root)
               'su'       = need su -c prefix
    shell_args: list of strings or a single command string
    """
    if isinstance(shell_args, list):
        cmd_str = " ".join(shell_args)
    else:
        cmd_str = shell_args

    if root_mode == "su":
        return adb_run(adb_path, ["shell", "su", "-c", cmd_str], device, timeout)
    else:
        # adb_root: pass as single string so shell expands globs
        return adb_run(adb_path, ["shell", cmd_str], device, timeout)


# ============================================================
# Device Discovery
# ============================================================

def list_devices(adb_path):
    """List connected ADB devices. Returns [(serial, state), ...]."""
    result = adb_run(adb_path, ["devices"])
    if not result or result.returncode != 0:
        print("错误: 无法执行 adb devices")
        if result:
            print(f"  {result.stderr.strip()}")
        sys.exit(1)

    devices = []
    for line in result.stdout.strip().splitlines()[1:]:
        line = line.strip()
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) == 2:
            serial, state = parts
            if state == "device":
                devices.append((serial, state))

    return devices


def select_device(adb_path, preferred_serial=None):
    """Select a device. Returns serial string."""
    devices = list_devices(adb_path)

    if not devices:
        print("未检测到已连接的设备。")
        print("提示:")
        print("  - 确保 MuMu/夜神模拟器已启动")
        print("  - 真机需要开启 USB 调试或无线调试")
        print()
        # Try auto-connect common emulator ports
        ports = ["7555", "62001", "5555", "16384"]
        for port in ports:
            target = f"127.0.0.1:{port}"
            print(f"  尝试连接 {target}...")
            r = adb_run(adb_path, ["connect", target])
            if r and "connected" in (r.stdout or "").lower():
                print(f"  已连接 {target}")
                return target
            elif r and "already connected" in (r.stdout or "").lower():
                print(f"  已连接 {target}")
                return target

        # Retry device listing
        devices = list_devices(adb_path)
        if not devices:
            print("仍然无法检测到设备，请手动检查连接。")
            sys.exit(1)

    if preferred_serial:
        for serial, _ in devices:
            if serial == preferred_serial:
                return serial
        print(f"警告: 指定的设备 {preferred_serial} 未找到")

    if len(devices) == 1:
        serial, _ = devices[0]
        print(f"检测到设备: {serial}")
        return serial

    # Multiple devices — let user choose
    print("检测到多个设备:")
    for i, (serial, _) in enumerate(devices):
        print(f"  [{i + 1}] {serial}")
    while True:
        try:
            choice = input("请选择设备编号: ").strip()
            idx = int(choice) - 1
            if 0 <= idx < len(devices):
                return devices[idx][0]
        except (ValueError, IndexError):
            pass
        print("无效选择，请重试")


# ============================================================
# Root Access
# ============================================================

def get_root_mode(adb_path, device):
    """Determine root access mode.

    Returns: 'adb_root' | 'su' | False
    """
    # Try 'adb root' — output may be in stdout OR stderr
    r = adb_run(adb_path, ["root"], device=device)
    if r:
        combined = (r.stdout or "") + (r.stderr or "")
        if "already running as root" in combined:
            return "adb_root"
        if "restarting adbd as root" in combined:
            import time
            time.sleep(2)
            return "adb_root"
        if "cannot run as root" not in combined and r.returncode == 0:
            # Some emulators return success without explicit message
            # Verify by testing access
            r2 = adb_run(adb_path, ["shell", "ls", SHARED_PREFS_DIR], device=device)
            if r2 and r2.returncode == 0 and "Permission denied" not in (r2.stderr or ""):
                return "adb_root"

    # Try 'su -c' (works on rooted devices / some emulators)
    r = adb_run(adb_path, ["shell", "su", "-c", "id"], device=device)
    if r and "uid=0" in (r.stdout or ""):
        return "su"

    return False


# ============================================================
# Credential Extraction
# ============================================================

def extract_via_cat(adb_path, device, root_mode):
    """Strategy A: Read known key files directly.

    token_prefs_default.xml → refresh_token + access_token
    utils_podcast.xml       → device_id (guid)
    identity.xml            → fallback device_id (uuid)
    """
    # Read token file
    r_token = shell_cmd(adb_path, device,
        ["cat", f"{SHARED_PREFS_DIR}/token_prefs_default.xml"], root_mode, timeout=10)
    # Read utils_podcast for guid (the actual x-jike-device-id)
    r_guid = shell_cmd(adb_path, device,
        ["cat", f"{SHARED_PREFS_DIR}/utils_podcast.xml"], root_mode, timeout=10)
    # Read identity file as fallback
    r_id = shell_cmd(adb_path, device,
        ["cat", f"{SHARED_PREFS_DIR}/identity.xml"], root_mode, timeout=10)

    combined = ""
    for r in [r_token, r_guid, r_id]:
        if r and r.returncode == 0 and r.stdout.strip():
            combined += r.stdout + "\n"

    if not combined.strip():
        return None

    return parse_credentials(combined)


def extract_via_grep(adb_path, device, root_mode):
    """Strategy B: Grep for tokens in app data."""
    r = shell_cmd(adb_path, device,
        ["grep", "-rn", "refresh_token", f"{SHARED_PREFS_DIR}/"],
        root_mode, timeout=10)

    if not r or r.returncode != 0:
        r = shell_cmd(adb_path, device,
            ["grep", "-rn", "refresh_token", f"/data/data/{PKG}/"],
            root_mode, timeout=15)

    if not r or r.returncode != 0:
        return None

    return parse_grep_output(r.stdout)


def extract_via_file_by_file(adb_path, device, root_mode):
    """Strategy C: List files then cat each one individually."""
    r = shell_cmd(adb_path, device, ["ls", f"{SHARED_PREFS_DIR}/"], root_mode)
    if not r or r.returncode != 0:
        return None

    all_xml = ""
    for fname in r.stdout.strip().splitlines():
        fname = fname.strip()
        if not fname:
            continue
        r2 = shell_cmd(adb_path, device,
            ["cat", f"{SHARED_PREFS_DIR}/{fname}"], root_mode)
        if r2 and r2.returncode == 0:
            all_xml += r2.stdout + "\n"

    if not all_xml.strip():
        return None

    return parse_credentials(all_xml)


# ============================================================
# XML / Text Parsing
# ============================================================

def parse_credentials(xml_content):
    """Parse XML content to extract tokens and device_id."""
    refresh_token = None
    access_token = None
    device_id = None

    # Split into individual XML documents
    chunks = re.split(r'<\?xml[^?]*\?>', xml_content)

    for chunk in chunks:
        chunk = chunk.strip()
        if not chunk or not chunk.startswith("<"):
            continue

        try:
            wrapped = f"<root>{chunk}</root>"
            root = ET.fromstring(wrapped)
        except ET.ParseError:
            continue

        for elem in root.iter():
            name = elem.get("name", "").lower()
            text = (elem.text or "").strip()

            # Match x-jike-refresh-token
            if "refresh" in name and "token" in name and text and len(text) > 20:
                refresh_token = text
            # Match x-jike-access-token (don't overwrite refresh)
            elif "access" in name and "token" in name and text and len(text) > 20:
                access_token = text
            # uuid from identity.xml is the x-jike-device-id (fallback)
            if name == "uuid" and text and not device_id:
                device_id = text
            # guid from utils_podcast.xml is the ACTUAL x-jike-device-id (highest priority)
            if name == "guid" and text:
                device_id = text

    result = {}
    if refresh_token:
        result["refresh_token"] = refresh_token
    if access_token:
        result["access_token"] = access_token
    if device_id:
        result["device_id"] = device_id

    return result if result else None


def parse_grep_output(output):
    """Parse grep output to extract tokens."""
    refresh_token = None
    device_id = None

    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue

        # Match refresh_token or refresh-token (both underscore and hyphen)
        m = re.search(r'refresh[-_]token["\']>([^<]+)', line, re.IGNORECASE)
        if m:
            val = m.group(1).strip()
            if len(val) > 20:
                refresh_token = val

        m = re.search(r'(?:device[-_]?id|x-jike-device-id|uuid)["\']>([^<]+)', line, re.IGNORECASE)
        if m:
            val = m.group(1).strip()
            if val:
                device_id = val

        if not refresh_token:
            m = re.search(r'refresh[-_]token.*?["\'>]([A-Za-z0-9_\-+/=]{30,})', line, re.IGNORECASE)
            if m:
                refresh_token = m.group(1)

    result = {}
    if refresh_token:
        result["refresh_token"] = refresh_token
    if device_id:
        result["device_id"] = device_id
    return result if result else None


# ============================================================
# Save & Verify
# ============================================================

def save_credentials(creds):
    """Save extracted credentials to ~/.xiaoyuzhou/credentials.json."""
    existing = {}
    if CREDENTIALS_FILE.exists():
        try:
            with open(CREDENTIALS_FILE, "r", encoding="utf-8") as f:
                existing = json.load(f)
        except (json.JSONDecodeError, OSError):
            pass

    existing.update(creds)
    existing["extract_time"] = time.strftime("%Y-%m-%d %H:%M:%S")

    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CREDENTIALS_FILE, "w", encoding="utf-8") as f:
        json.dump(existing, f, indent=2, ensure_ascii=False)

    return existing


def verify_credentials(config):
    """Verify credentials by calling refresh_access_token from xyz.py."""
    try:
        sys.path.insert(0, str(Path(__file__).parent))
        from xyz import refresh_access_token
        config = refresh_access_token(config)
        return config
    except SystemExit:
        return None
    except Exception as e:
        print(f"验证失败: {e}")
        return None


# ============================================================
# Main Entry (callable from xyz.py)
# ============================================================

def extract_from_adb(adb_path=None, device_serial=None):
    """Main extraction logic. Returns config dict or None."""
    adb = find_adb(adb_path)
    print(f"ADB 工具: {adb}")

    device = select_device(adb, device_serial)
    print(f"使用设备: {device}")

    # Determine root access mode
    print("检查 Root 权限...")
    root_mode = get_root_mode(adb, device)
    if not root_mode:
        print("警告: 未获得 Root 权限")
        print("  MuMu: 默认已开启 adb root")
        print("  夜神: 在模拟器设置中开启 Root")
        print("  真机: 需要 Root 或使用 mitmproxy 抓包方式")
        return None

    mode_name = "ADB Root" if root_mode == "adb_root" else "su"
    print(f"Root 权限已获取 (模式: {mode_name})")

    # Try extraction strategies
    print("正在提取凭据...")

    creds = extract_via_cat(adb, device, root_mode)
    strategy = "XML 批量读取"

    if not creds:
        print("  方式A (cat XML) 未找到，尝试方式B (grep)...")
        creds = extract_via_grep(adb, device, root_mode)
        strategy = "grep 搜索"

    if not creds:
        print("  方式B (grep) 未找到，尝试方式C (逐文件读取)...")
        creds = extract_via_file_by_file(adb, device, root_mode)
        strategy = "逐文件读取"

    if not creds:
        print()
        print("未能提取到凭据。可能的原因:")
        print(f"  - 小宇宙 App 未在设备上安装 (包名: {PKG})")
        print("  - 小宇宙 App 未登录")
        print("  - 数据存储方式已变更")
        print()
        print("建议:")
        print("  - 确认小宇宙 App 已安装并登录")
        print("  - 尝试 mitmproxy 抓包方式")
        return None

    print(f"  提取成功 (策略: {strategy})")
    if "refresh_token" in creds:
        print(f"  refresh_token: {creds['refresh_token'][:20]}...")
    if "access_token" in creds:
        print(f"  access_token:  {creds['access_token'][:20]}...")
    if "device_id" in creds:
        print(f"  device_id:     {creds['device_id']}")

    return creds


def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="从小宇宙 App 中自动提取凭据 (via ADB)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--adb-path", help="ADB 工具路径 (自动检测如果省略)")
    parser.add_argument("--device", help="设备序列号 (自动选择如果省略)")
    parser.add_argument("--verify", action="store_true", help="提取后验证凭据有效性")
    args = parser.parse_args()

    print("=" * 50)
    print("小宇宙凭据自动提取工具 (ADB)")
    print("=" * 50)
    print()

    creds = extract_from_adb(
        adb_path=args.adb_path,
        device_serial=args.device,
    )

    if not creds:
        sys.exit(1)

    # Save
    config = save_credentials(creds)
    print(f"\n凭据已保存到: {CREDENTIALS_FILE}")

    # Verify
    if args.verify:
        print("\n正在验证凭据...")
        result = verify_credentials(config)
        if result:
            print("验证成功! Token 已刷新")
            print(f"  access_token:  {result.get('access_token', 'N/A')[:20]}...")
            print(f"  refresh_token: {result.get('refresh_token', 'N/A')[:20]}...")
        else:
            print("验证失败: 凭据可能已过期，请重新在 App 中登录后再试")
            sys.exit(1)
    else:
        print("\n提示: 使用 --verify 参数可在提取后自动验证凭据有效性")
        print("  也可以手动验证: python xyz.py token --verify")


if __name__ == "__main__":
    main()
