-- 小宇宙播客数据表 (v2: xiaoyuzhou_ 前缀，符合抓取系统.md 规范)
-- 三表分离：episodes (元数据) + audio (音频) + transcripts (文字内容)
-- 不含 subtitles 表：字幕和转录统一存 xiaoyuzhou_episode_transcripts

CREATE TABLE IF NOT EXISTS xiaoyuzhou_podcasts (
    pid TEXT PRIMARY KEY,
    title TEXT NOT NULL DEFAULT '',
    author TEXT DEFAULT '',
    description TEXT DEFAULT '',
    episode_count INTEGER DEFAULT 0,
    subscription_count INTEGER DEFAULT 0,
    cover_url TEXT DEFAULT '',
    podcasters JSONB DEFAULT '[]',
    raw_data JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS xiaoyuzhou_episodes (
    eid TEXT PRIMARY KEY,
    pid TEXT NOT NULL DEFAULT '',
    title TEXT NOT NULL DEFAULT '',
    description TEXT DEFAULT '',
    shownotes TEXT DEFAULT '',
    duration INTEGER DEFAULT 0,
    pub_date TEXT DEFAULT '',
    is_private BOOLEAN DEFAULT FALSE,
    podcasters JSONB DEFAULT '[]',
    status TEXT DEFAULT 'pending',
    raw_data JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS xiaoyuzhou_episode_audio (
    eid TEXT PRIMARY KEY REFERENCES xiaoyuzhou_episodes(eid) ON DELETE CASCADE,
    audio_url TEXT DEFAULT '',
    audio_local_path TEXT DEFAULT '',
    audio_file_size BIGINT DEFAULT 0,
    status TEXT DEFAULT 'pending',
    raw_data JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS xiaoyuzhou_episode_transcripts (
    eid TEXT PRIMARY KEY REFERENCES xiaoyuzhou_episodes(eid) ON DELETE CASCADE,
    transcript_text TEXT DEFAULT '',
    transcript_source TEXT DEFAULT '',       -- "字幕" 或 "转录"
    word_count INTEGER DEFAULT 0,
    status TEXT DEFAULT 'pending',           -- pending/transcribing/transcript_ready/transcript_failed
    raw_data JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS xiaoyuzhou_crawl_state (
    pid TEXT PRIMARY KEY,
    crawled_eids JSONB DEFAULT '[]',
    count INTEGER DEFAULT 0,
    last_crawl_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_xy_ep_pid ON xiaoyuzhou_episodes(pid);
CREATE INDEX IF NOT EXISTS idx_xy_ep_pub_date ON xiaoyuzhou_episodes(pub_date);
CREATE INDEX IF NOT EXISTS idx_xy_ep_status ON xiaoyuzhou_episodes(status);
CREATE INDEX IF NOT EXISTS idx_xy_audio_status ON xiaoyuzhou_episode_audio(status);
CREATE INDEX IF NOT EXISTS idx_xy_trans_status ON xiaoyuzhou_episode_transcripts(status);
