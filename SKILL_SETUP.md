---
name: xiaoyuzhou-setup
description: Install dependencies and configure environment variables for the Xiaoyuzhou podcast skill. Run this before using any other Xiaoyuzhou skills.
metadata:
  openclaw:
    requires:
      bins: ["python3"]
---

# 小宇宙播客项目环境配置 Skill

本 skill 指引 agent 完成项目依赖安装和环境变量配置，确保其他 skill（查询、爬虫）可以正常运行。

**本 skill 不涉及数据操作，仅做环境初始化。**

## When to use

Use this skill when:
- The project is freshly cloned and has not been set up yet
- The virtual environment `.venv/` does not exist
- The `.env` file does not exist
- The user explicitly asks to install or set up the project
- Other skills fail due to missing dependencies or missing `.env`

## Step 1: Create virtual environment

Check if `{baseDir}/.venv` exists. If not, create it:

```bash
python3 -m venv {baseDir}/.venv
```

## Step 2: Install Python dependencies

```bash
{baseDir}/.venv/bin/pip install -r {baseDir}/requirements.txt
```

Key dependencies (defined in `requirements.txt`):

| Dependency | Purpose |
|---|---|
| `requests` | HTTP client for the scraper |
| `faster-whisper` | Local audio transcription (requires `ffmpeg` on system) |
| `psycopg2-binary` | PostgreSQL driver (for `query_db.py` and `hub_adapter`) |
| `python-dotenv` | Load `.env` config |
| `financial-hub-postgres` | Shared database client library |

### System dependency: ffmpeg

ffmpeg is required for audio transcription. Install if not already present:

- **Windows**: `winget install Gyan.FFmpeg` or `choco install ffmpeg`
- **macOS**: `brew install ffmpeg`
- **Linux**: `sudo apt install ffmpeg`

Verify: `ffmpeg -version`

## Step 3: Configure environment variables

Check if `{baseDir}/.env` exists. If not, copy from the example file:

```bash
cp {baseDir}/.env.example {baseDir}/.env
```

Then ask the user to fill in the actual values. The variables are:

| Variable | Description | Example |
|---|---|---|
| `POSTGRES_HOST` | PostgreSQL server address | `127.0.0.1` |
| `POSTGRES_PORT` | PostgreSQL server port | `5432` |
| `POSTGRES_USER` | Database user (for crawler, read-write) | `hub_user` |
| `POSTGRES_PASSWORD` | Password for the read-write user | `hub_password` |
| `POSTGRES_DB` | Database name | `financial_hub` |
| `POSTGRES_READONLY_USER` | Database user (for query skill, read-only) | `hub_readonly` |
| `POSTGRES_READONLY_PASSWORD` | Password for the read-only user | `hub_password` |

**Note**: The core scraper (`xyz.py`) works without PostgreSQL. However, `query_db.py` and `hub_adapter.py` require PG. Setting up `.env` now ensures all features are available.

**Important:** The `.env` file contains sensitive credentials and should be in `.gitignore`. Never commit it to version control.

## Step 4: Pre-download Whisper model

```bash
{baseDir}/.venv/bin/python {baseDir}/scripts/xyz.py setup
```

This downloads the Whisper base model (~150MB) from HuggingFace mirror, ensuring transcription is immediately available without first-run delays. In mainland China, the script automatically sets `HF_ENDPOINT=https://hf-mirror.com`.

## Step 5: Verify setup

### 5a. Verify core scraper

```bash
{baseDir}/.venv/bin/python {baseDir}/scripts/xyz.py list-accounts
```

This should print account information without errors (may show "no accounts" if not yet logged in, which is fine).

### 5b. Verify database connection

```bash
{baseDir}/.venv/bin/python {baseDir}/scripts/query_db.py stats
```

If this command prints statistics without errors, the PG setup is complete.

If it fails with a connection error, ask the user to check:
1. Is PostgreSQL running and accessible at the configured host/port?
2. Are the database credentials in `.env` correct?
3. Does the database and the readonly user exist?

If the scraper works but PG is unavailable, the skill is still usable for crawling -- only the query skill and hub adapter will be affected.

## Step 6: Create readonly database user (if needed)

If Step 5b fails because the `hub_readonly` user does not exist, create it by running:

```bash
{baseDir}/.venv/bin/python -c "
import psycopg2, os
from dotenv import load_dotenv
load_dotenv('{baseDir}/.env')
conn = psycopg2.connect(
    host=os.getenv('POSTGRES_HOST', '127.0.0.1'),
    port=int(os.getenv('POSTGRES_PORT', '5432')),
    user=os.getenv('POSTGRES_USER'),
    password=os.getenv('POSTGRES_PASSWORD'),
    dbname=os.getenv('POSTGRES_DB'),
)
conn.autocommit = True
cur = conn.cursor()
ro_user = os.getenv('POSTGRES_READONLY_USER', 'hub_readonly')
ro_pass = os.getenv('POSTGRES_READONLY_PASSWORD', 'hub_password')
cur.execute(f\"CREATE ROLE {ro_user} WITH LOGIN PASSWORD '{ro_pass}'\")
cur.execute(f'GRANT CONNECT ON DATABASE {os.getenv(\"POSTGRES_DB\")} TO {ro_user}')
cur.execute(f'GRANT USAGE ON SCHEMA public TO {ro_user}')
cur.execute(f'GRANT SELECT ON ALL TABLES IN SCHEMA public TO {ro_user}')
cur.execute(f'ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO {ro_user}')
cur.close()
conn.close()
print(f'Created readonly user: {ro_user}')
"
```

Then re-run Step 5b to verify.

## Step 7: Login (if using crawler features)

```bash
{baseDir}/.venv/bin/python {baseDir}/scripts/xyz.py login --adb
```

This uses ADB to automatically extract credentials from a connected Android emulator/device. See `SKILL.md` for alternative login methods.

## Examples

User says: "帮我安装小宇宙技能的依赖"
→ Execute Step 1 and Step 2.

User says: "配置小宇宙项目的环境变量"
→ Execute Step 3, then ask the user for actual database credentials.

User says: "初始化小宇宙项目"
→ Execute Step 1 through Step 5.

User says: "小宇宙查询工具连不上数据库"
→ Check `.env` is present and correct (Step 3), then run Step 5b to diagnose. If readonly user missing, run Step 6.

User says: "预下载小宇宙转录模型"
→ Execute Step 4.

## Project structure reference

```
{baseDir}/
├── .env.example           ← Environment variable template
├── .env                   ← Actual config (not in git)
├── .venv/                 ← Python virtual environment (not in git)
├── requirements.txt       ← Python dependencies
├── schema.sql             ← Database table definitions (v2, xiaoyuzhou_ prefix)
├── SKILL.md               ← Crawler + operations skill definition
├── SKILL_SETUP.md         ← This file (setup skill)
├── SKILL_QUERY.md         ← Database query skill definition
├── README.md              ← User-facing documentation
├── reference.md           ← API reference (on-demand)
├── scripts/
│   ├── xyz.py             ← Main tool (all crawl/operations)
│   ├── query_db.py        ← Database query tool (read-only)
│   └── extract_creds.py   ← ADB credential extraction
├── output/                ← Crawl output (not in git)
└── downloads/             ← Downloaded audio (not in git)
```
