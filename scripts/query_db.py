"""
小宇宙播客数据库查询工具 (只读)。

提供 CLI 访问 xiaoyuzhou_podcasts, xiaoyuzhou_episodes, xiaoyuzhou_episode_audio,
xiaoyuzhou_episode_transcripts 表。
严格只读 — 不执行 INSERT, UPDATE, DELETE 操作。

用法:
    python query_db.py episodes [--podcast PID] [--search KEYWORD]
                                [--since DATE] [--until DATE] [--status STATUS]
                                [--limit N] [--offset N] [--id EID] [--full]
    python query_db.py podcasts [--search KEYWORD]
    python query_db.py stats
"""

import os
import sys
import json
import argparse

# Fix Windows console encoding
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv


# Load environment variables from .env (search upward)
_env_dir = os.path.dirname(__file__)
for _ in range(4):
    _env_path = os.path.join(_env_dir, ".env")
    if os.path.exists(_env_path):
        load_dotenv(_env_path, encoding="utf-8")
        break
    _env_dir = os.path.dirname(_env_dir)


def get_db_connection():
    """Create a read-only database connection using .env config (readonly user)."""
    conn = psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "127.0.0.1"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        user=os.getenv("POSTGRES_READONLY_USER", "hub_readonly"),
        password=os.getenv("POSTGRES_READONLY_PASSWORD", "hub_password"),
        dbname=os.getenv("POSTGRES_DB", "financial_hub"),
    )
    conn.set_session(readonly=True, autocommit=True)
    return conn


# ---------------------------------------------------------------------------
# Output formatting — stable structure for AI Agent consumption
# ---------------------------------------------------------------------------

ITEM_SEPARATOR = "\n" + "=" * 60 + "\n"


def format_episode(row: dict, full: bool = False) -> str:
    """Format a single episode record."""
    title = row.get("title") or "(无标题)"
    eid = row.get("eid") or ""
    pid = row.get("pid") or ""
    pub_date = row.get("pub_date") or ""
    duration = row.get("duration") or 0
    duration_min = duration // 60 if isinstance(duration, (int, float)) else 0
    status = row.get("status") or ""
    source = row.get("transcript_source") or ""

    lines = [
        f"标题: {title}",
        f"来源: xiaoyuzhou",
        f"类型: podcast_episode",
        f"单集ID: {eid}",
        f"播客ID: {pid}",
        f"发布时间: {pub_date}",
        f"时长: {duration_min} 分钟",
        f"转录来源: {source}",
        f"状态: {status}",
    ]

    # Podcasters
    podcasters = row.get("podcasters") or []
    if isinstance(podcasters, str):
        try:
            podcasters = json.loads(podcasters)
        except (json.JSONDecodeError, TypeError):
            podcasters = []
    if podcasters:
        names = [p.get("nickname", "") for p in podcasters if p.get("nickname")]
        if names:
            lines.append(f"主播/嘉宾: {', '.join(names)}")

    # Body text
    body = row.get("transcript_text") or row.get("description") or ""
    if full:
        lines.append("")
        lines.append("--- 正文 ---")
        lines.append(body if body else "(无正文)")
    else:
        preview = body[:200].replace("\n", " ") if body else "(无正文)"
        if len(body) > 200:
            preview += "..."
        lines.append(f"正文预览: {preview}")

    return "\n".join(lines)


def format_podcast(row: dict) -> str:
    """Format a single podcast record."""
    lines = [
        f"播客ID: {row.get('pid')}",
        f"标题: {row.get('title') or ''}",
        f"作者: {row.get('author') or ''}",
        f"简介: {(row.get('description') or '')[:200]}",
        f"节目数: {row.get('episode_count') or 0}",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Query functions
# ---------------------------------------------------------------------------

def cmd_episodes(conn, args):
    """Query episodes with optional filters."""
    conditions = []
    params = []

    if args.podcast:
        conditions.append("pid = %s")
        params.append(args.podcast)

    if args.search:
        conditions.append("(e.title ILIKE %s OR t.transcript_text ILIKE %s OR e.description ILIKE %s)")
        pattern = f"%{args.search}%"
        params.extend([pattern, pattern, pattern])

    if args.since:
        conditions.append("e.pub_date >= %s")
        params.append(args.since)

    if args.until:
        conditions.append("e.pub_date <= %s")
        params.append(args.until)

    if args.status:
        conditions.append("e.status = %s")
        params.append(args.status)

    if args.id:
        conditions.append("e.eid = %s")
        params.append(args.id)

    where = ""
    if conditions:
        where = "WHERE " + " AND ".join(conditions)

    limit = min(args.limit, 500)
    offset = args.offset

    sql = f"""
        SELECT e.*,
               a.audio_url, a.audio_local_path, a.audio_file_size, a.status AS audio_status,
               t.transcript_text, t.transcript_source, t.word_count, t.status AS transcript_status
        FROM xiaoyuzhou_episodes e
        LEFT JOIN xiaoyuzhou_episode_audio a ON e.eid = a.eid
        LEFT JOIN xiaoyuzhou_episode_transcripts t ON e.eid = t.eid
        {where}
        ORDER BY e.pub_date DESC NULLS LAST
        LIMIT %s OFFSET %s
    """
    params.extend([limit, offset])

    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()

    if not rows:
        print("没有找到匹配的节目。")
        return

    # Count total
    count_sql = f"SELECT COUNT(*) FROM xiaoyuzhou_episodes e {where}"
    with conn.cursor() as cur:
        cur.execute(count_sql, params[:-2])
        total = cur.fetchone()[0]

    print(f"查询结果: {len(rows)} 条 (共 {total} 条匹配, offset={offset}, limit={limit})\n")
    print(ITEM_SEPARATOR.join(format_episode(r, full=args.full) for r in rows))


def cmd_podcasts(conn, args):
    """List podcasts."""
    conditions = []
    params = []

    if args.search:
        conditions.append("(title ILIKE %s OR author ILIKE %s OR description ILIKE %s)")
        pattern = f"%{args.search}%"
        params.extend([pattern, pattern, pattern])

    where = ""
    if conditions:
        where = "WHERE " + " AND ".join(conditions)

    sql = f"SELECT * FROM xiaoyuzhou_podcasts {where} ORDER BY title"

    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()

    if not rows:
        print("没有找到匹配的播客。")
        return

    print(f"共 {len(rows)} 个播客:\n")
    print(ITEM_SEPARATOR.join(format_podcast(r) for r in rows))


def cmd_stats(conn, args):
    """Show statistics overview."""
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT COUNT(*) AS cnt FROM xiaoyuzhou_podcasts")
        podcast_count = cur.fetchone()["cnt"]

        cur.execute("SELECT COUNT(*) AS cnt FROM xiaoyuzhou_episodes")
        episode_count = cur.fetchone()["cnt"]

        cur.execute(
            "SELECT status, COUNT(*) AS cnt FROM xiaoyuzhou_episodes GROUP BY status ORDER BY cnt DESC"
        )
        status_rows = cur.fetchall()

        cur.execute(
            "SELECT transcript_source, COUNT(*) AS cnt FROM xiaoyuzhou_episode_transcripts "
            "WHERE transcript_source != '' GROUP BY transcript_source ORDER BY cnt DESC"
        )
        source_rows = cur.fetchall()

    lines = [
        "统计概览",
        f"播客总数: {podcast_count}",
        f"节目总数: {episode_count}",
        "",
        "按状态统计:",
    ]
    for r in status_rows:
        lines.append(f"  {r['status'] or '(未知)'}: {r['cnt']} 条")

    if source_rows:
        lines.append("")
        lines.append("按转录来源统计:")
        for r in source_rows:
            lines.append(f"  {r['transcript_source']}: {r['cnt']} 条")

    print("\n".join(lines))


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="小宇宙播客数据库只读查询工具",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # --- episodes ---
    p_episodes = subparsers.add_parser("episodes", help="查询节目")
    p_episodes.add_argument("--podcast", type=str, default=None, help="按播客ID过滤")
    p_episodes.add_argument("--search", type=str, default=None, help="按关键词搜索标题和正文")
    p_episodes.add_argument("--since", type=str, default=None, help="起始日期 (含), 格式 YYYY-MM-DD")
    p_episodes.add_argument("--until", type=str, default=None, help="截止日期 (含), 格式 YYYY-MM-DD")
    p_episodes.add_argument("--status", type=str, default=None, help="按状态过滤 (pending/ready/pending_transcription)")
    p_episodes.add_argument("--limit", type=int, default=20, help="返回条数上限 (默认 20, 最大 500)")
    p_episodes.add_argument("--offset", type=int, default=0, help="跳过前 N 条 (分页用)")
    p_episodes.add_argument("--id", type=str, default=None, help="按单集ID精确查询单条")
    p_episodes.add_argument("--full", action="store_true", help="显示完整正文 (默认只显示预览)")

    # --- podcasts ---
    p_podcasts = subparsers.add_parser("podcasts", help="列出播客")
    p_podcasts.add_argument("--search", type=str, default=None, help="按标题、作者或简介搜索")

    # --- stats ---
    subparsers.add_parser("stats", help="查看统计信息")

    args = parser.parse_args()

    conn = get_db_connection()
    try:
        if args.command == "episodes":
            cmd_episodes(conn, args)
        elif args.command == "podcasts":
            cmd_podcasts(conn, args)
        elif args.command == "stats":
            cmd_stats(conn, args)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
