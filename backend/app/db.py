"""Async SQLite database wrapper with WAL mode and FTS5 course search."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator, Iterable, Optional

import aiosqlite

SCHEMA_SQL = """
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA foreign_keys = ON;
PRAGMA busy_timeout = 5000;

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'user' CHECK (role IN ('admin', 'user')),
    priority_tier INTEGER NOT NULL DEFAULT 1,
    discord_user_id TEXT,
    discord_ping_enabled INTEGER NOT NULL DEFAULT 1,
    personal_webhook_url TEXT,
    web_push_enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS invites (
    code TEXT PRIMARY KEY,
    created_by INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    max_uses INTEGER NOT NULL DEFAULT 1,
    uses_count INTEGER NOT NULL DEFAULT 0,
    note TEXT NOT NULL DEFAULT '',
    expires_at TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS rosters (
    slug TEXT PRIMARY KEY,
    descr TEXT NOT NULL,
    is_default INTEGER NOT NULL DEFAULT 0,
    archive_mode INTEGER NOT NULL DEFAULT 0,
    strm TEXT NOT NULL DEFAULT '',
    last_modified_dttm TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS subjects (
    roster TEXT NOT NULL,
    value TEXT NOT NULL,
    descr TEXT NOT NULL,
    synced_at TEXT,
    PRIMARY KEY (roster, value)
);

CREATE TABLE IF NOT EXISTS courses_meta (
    roster TEXT NOT NULL,
    subject TEXT NOT NULL,
    catalog_nbr TEXT NOT NULL,
    title_short TEXT NOT NULL,
    title_long TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    crse_id INTEGER,
    acad_career TEXT NOT NULL DEFAULT '',
    acad_group TEXT NOT NULL DEFAULT '',
    catalog_prereq TEXT NOT NULL DEFAULT '',
    catalog_coreq TEXT NOT NULL DEFAULT '',
    catalog_forbidden_overlaps TEXT NOT NULL DEFAULT '',
    crse_attrs_json TEXT NOT NULL DEFAULT '[]',
    catalog_num INTEGER NOT NULL DEFAULT 0,
    units_min REAL NOT NULL DEFAULT 0.0,
    units_max REAL NOT NULL DEFAULT 0.0,
    has_letter_grade INTEGER NOT NULL DEFAULT 1,
    crosslists_json TEXT NOT NULL DEFAULT '[]',
    components_json TEXT NOT NULL DEFAULT '[]',
    enroll_groups_json TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (roster, subject, catalog_nbr)
);

CREATE TABLE IF NOT EXISTS roster_sections (
    roster TEXT NOT NULL,
    subject TEXT NOT NULL,
    catalog_nbr TEXT NOT NULL,
    class_nbr INTEGER NOT NULL,
    enroll_group_idx INTEGER NOT NULL,
    ssr_component TEXT NOT NULL,
    section TEXT NOT NULL,
    open_status TEXT NOT NULL,
    components_required_json TEXT NOT NULL DEFAULT '[]',
    meetings_summary TEXT NOT NULL DEFAULT '',
    instructors_summary TEXT NOT NULL DEFAULT '',
    campus TEXT NOT NULL DEFAULT '',
    instruction_mode TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (roster, class_nbr)
);

CREATE INDEX IF NOT EXISTS idx_roster_sections_course
    ON roster_sections (roster, subject, catalog_nbr);

CREATE INDEX IF NOT EXISTS idx_roster_sections_subject
    ON roster_sections (roster, subject);

CREATE VIRTUAL TABLE IF NOT EXISTS courses_fts USING fts5(
    roster UNINDEXED,
    subject,
    catalog_nbr,
    course_code,
    title_long,
    description,
    class_nbrs
);

CREATE TABLE IF NOT EXISTS watches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    roster TEXT NOT NULL,
    subject TEXT NOT NULL,
    catalog_nbr TEXT NOT NULL,
    course_title TEXT NOT NULL,
    class_nbr INTEGER,
    enroll_group_idx INTEGER,
    component_filter TEXT,
    mode TEXT NOT NULL DEFAULT 'exact' CHECK (mode IN ('exact', 'linked_group', 'any_section')),
    trigger_on TEXT NOT NULL DEFAULT 'open' CHECK (trigger_on IN ('open', 'open_or_waitlist')),
    priority INTEGER NOT NULL DEFAULT 1,
    active INTEGER NOT NULL DEFAULT 1,
    auto_pause INTEGER NOT NULL DEFAULT 0,
    cooldown_sec INTEGER NOT NULL DEFAULT 60,
    last_observed_status TEXT,
    last_notified_status TEXT,
    last_notified_at TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_watches_active_bucket
    ON watches (active, roster, subject);

CREATE INDEX IF NOT EXISTS idx_watches_user
    ON watches (user_id, active);

CREATE TABLE IF NOT EXISTS push_subscriptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    endpoint TEXT NOT NULL UNIQUE,
    p256dh TEXT NOT NULL,
    auth TEXT NOT NULL,
    device_label TEXT NOT NULL DEFAULT 'Browser',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS status_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    roster TEXT NOT NULL,
    subject TEXT NOT NULL,
    catalog_nbr TEXT NOT NULL,
    class_nbr INTEGER NOT NULL,
    section_label TEXT NOT NULL,
    old_status TEXT,
    new_status TEXT NOT NULL,
    poll_rtt_ms INTEGER NOT NULL DEFAULT 0,
    detected_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_status_events_time
    ON status_events (detected_at DESC);

CREATE TABLE IF NOT EXISTS delivery_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id INTEGER REFERENCES status_events(id) ON DELETE CASCADE,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    channel_kind TEXT NOT NULL,
    status TEXT NOT NULL,
    latency_ms INTEGER NOT NULL DEFAULT 0,
    error_text TEXT,
    sent_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_delivery_logs_user
    ON delivery_logs (user_id, sent_at DESC);

CREATE TABLE IF NOT EXISTS app_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS course_insights_cache (
    subject TEXT NOT NULL,
    catalog_nbr TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    found INTEGER NOT NULL DEFAULT 1,
    fetched_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (subject, catalog_nbr)
);

CREATE TABLE IF NOT EXISTS rmp_instructor_cache (
    name_key TEXT PRIMARY KEY,
    payload_json TEXT NOT NULL,
    found INTEGER NOT NULL DEFAULT 1,
    fetched_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def build_fts_query(raw_query: str) -> str:
    """Escape raw user search input into safe FTS5 prefix terms."""
    cleaned = "".join(ch if ch.isalnum() or ch.isspace() else " " for ch in raw_query)
    tokens = [tok.strip() for tok in cleaned.split() if tok.strip()]
    if not tokens:
        return ""
    return " AND ".join(f'"{tok}"*' for tok in tokens)


_COURSES_META_MIGRATIONS: tuple[tuple[str, str], ...] = (
    ("acad_career", "TEXT NOT NULL DEFAULT ''"),
    ("acad_group", "TEXT NOT NULL DEFAULT ''"),
    ("catalog_prereq", "TEXT NOT NULL DEFAULT ''"),
    ("catalog_coreq", "TEXT NOT NULL DEFAULT ''"),
    ("catalog_forbidden_overlaps", "TEXT NOT NULL DEFAULT ''"),
    ("crse_attrs_json", "TEXT NOT NULL DEFAULT '[]'"),
    ("catalog_num", "INTEGER NOT NULL DEFAULT 0"),
    ("units_min", "REAL NOT NULL DEFAULT 0.0"),
    ("units_max", "REAL NOT NULL DEFAULT 0.0"),
    ("has_letter_grade", "INTEGER NOT NULL DEFAULT 1"),
    ("crosslists_json", "TEXT NOT NULL DEFAULT '[]'"),
    ("components_json", "TEXT NOT NULL DEFAULT '[]'"),
)


class Database:
    """Managed async SQLite connection with serialized write lock."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._conn: Optional[aiosqlite.Connection] = None
        self._write_lock = asyncio.Lock()

    async def connect(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(self.db_path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.executescript(SCHEMA_SQL)
        await self._migrate_courses_meta()
        await self._conn.commit()

    async def _migrate_courses_meta(self) -> None:
        """Add CS-elective metadata columns idempotently on existing SQLite databases."""
        cursor = await self.conn.execute("PRAGMA table_info(courses_meta)")
        existing_cols = {str(r["name"]) for r in await cursor.fetchall()}
        had_metadata = "acad_group" in existing_cols
        for col_name, col_def in _COURSES_META_MIGRATIONS:
            if col_name not in existing_cols:
                await self.conn.execute(f"ALTER TABLE courses_meta ADD COLUMN {col_name} {col_def}")
        await self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_courses_meta_roster_level ON courses_meta (roster, subject, catalog_num)"
        )
        if not had_metadata:
            # Force cached subjects from older DB schema to re-sync prereq and college metadata cleanly
            await self.conn.execute("UPDATE subjects SET synced_at = NULL WHERE synced_at IS NOT NULL")

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    @property
    def conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("Database is not connected")
        return self._conn

    @asynccontextmanager
    async def write_tx(self) -> AsyncIterator[aiosqlite.Connection]:
        """Serialize multi-statement write transactions cleanly."""
        async with self._write_lock:
            conn = self.conn
            try:
                yield conn
                await conn.commit()
            except Exception:
                await conn.rollback()
                raise

    async def execute(self, sql: str, params: Iterable[Any] = ()) -> aiosqlite.Cursor:
        async with self._write_lock:
            cursor = await self.conn.execute(sql, tuple(params))
            await self.conn.commit()
            return cursor

    async def fetch_one(self, sql: str, params: Iterable[Any] = ()) -> Optional[dict[str, Any]]:
        cursor = await self.conn.execute(sql, tuple(params))
        row = await cursor.fetchone()
        return dict(row) if row is not None else None

    async def fetch_all(self, sql: str, params: Iterable[Any] = ()) -> list[dict[str, Any]]:
        cursor = await self.conn.execute(sql, tuple(params))
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    async def get_setting(self, key: str, default: str = "") -> str:
        row = await self.fetch_one("SELECT value FROM app_settings WHERE key = ?", (key,))
        return row["value"] if row is not None else default

    async def set_setting(self, key: str, value: str) -> None:
        await self.execute(
            """
            INSERT INTO app_settings (key, value, updated_at)
            VALUES (?, ?, datetime('now'))
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                updated_at = datetime('now')
            """,
            (key, value),
        )
