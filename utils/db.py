"""Async SQLite layer for Dr Aura"""

import aiosqlite
import json
from datetime import datetime
from pathlib import Path
from config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS groups (
    chat_id INTEGER PRIMARY KEY,
    title TEXT,
    settings TEXT DEFAULT '{}',
    welcome TEXT,
    goodbye TEXT,
    rules TEXT,
    warn_limit INTEGER DEFAULT 3,
    locks TEXT DEFAULT '{}',
    force_join TEXT DEFAULT '[]',
    antidelete INTEGER DEFAULT 0,
    antilink TEXT DEFAULT 'off',
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS warns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER,
    user_id INTEGER,
    reason TEXT,
    admin_id INTEGER,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER,
    name TEXT,
    content TEXT,
    media_type TEXT,
    media_id TEXT,
    admin_only INTEGER DEFAULT 0,
    UNIQUE(chat_id, name)
);

CREATE TABLE IF NOT EXISTS filters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER,
    keyword TEXT,
    reply TEXT,
    media_type TEXT,
    media_id TEXT,
    exact INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    full_name TEXT,
    is_banned INTEGER DEFAULT 0,
    last_seen TEXT
);

CREATE TABLE IF NOT EXISTS sudos (
    user_id INTEGER PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS owners (
    user_id INTEGER PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER,
    action TEXT,
    admin_id INTEGER,
    target_id INTEGER,
    detail TEXT,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS antidelete_cache (
    chat_id INTEGER,
    message_id INTEGER,
    data TEXT,
    PRIMARY KEY (chat_id, message_id)
);

CREATE TABLE IF NOT EXISTS global_settings (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""

async def get_db():
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    await db.executescript(SCHEMA)
    await db.commit()
    return db

async def ensure_group(db, chat_id: int, title: str = ""):
    await db.execute(
        "INSERT OR IGNORE INTO groups (chat_id, title, created_at) VALUES (?, ?, ?)",
        (chat_id, title, datetime.utcnow().isoformat())
    )
    await db.commit()

async def get_group(db, chat_id: int):
    async with db.execute("SELECT * FROM groups WHERE chat_id=?", (chat_id,)) as cur:
        return await cur.fetchone()

async def set_group_setting(db, chat_id: int, key: str, value):
    row = await get_group(db, chat_id)
    settings = json.loads(row["settings"] or "{}") if row else {}
    settings[key] = value
    await db.execute(
        "UPDATE groups SET settings=? WHERE chat_id=?",
        (json.dumps(settings), chat_id)
    )
    await db.commit()

async def get_setting(db, chat_id: int, key: str, default=None):
    row = await get_group(db, chat_id)
    if not row:
        return default
    settings = json.loads(row["settings"] or "{}")
    return settings.get(key, default)

async def add_warn(db, chat_id: int, user_id: int, reason: str, admin_id: int):
    await db.execute(
        "INSERT INTO warns (chat_id, user_id, reason, admin_id, created_at) VALUES (?,?,?,?,?)",
        (chat_id, user_id, reason, admin_id, datetime.utcnow().isoformat())
    )
    await db.commit()
    async with db.execute(
        "SELECT COUNT(*) as c FROM warns WHERE chat_id=? AND user_id=?",
        (chat_id, user_id)
    ) as cur:
        r = await cur.fetchone()
        return r["c"]

async def reset_warns(db, chat_id: int, user_id: int):
    await db.execute("DELETE FROM warns WHERE chat_id=? AND user_id=?", (chat_id, user_id))
    await db.commit()

async def get_warn_count(db, chat_id: int, user_id: int) -> int:
    async with db.execute(
        "SELECT COUNT(*) as c FROM warns WHERE chat_id=? AND user_id=?",
        (chat_id, user_id)
    ) as cur:
        r = await cur.fetchone()
        return r["c"] if r else 0

async def log_action(db, chat_id: int, action: str, admin_id: int, target_id: int = 0, detail: str = ""):
    await db.execute(
        "INSERT INTO logs (chat_id, action, admin_id, target_id, detail, created_at) VALUES (?,?,?,?,?,?)",
        (chat_id, action, admin_id, target_id, detail, datetime.utcnow().isoformat())
    )
    await db.commit()

async def is_sudo(db, user_id: int) -> bool:
    async with db.execute("SELECT 1 FROM sudos WHERE user_id=?", (user_id,)) as cur:
        return await cur.fetchone() is not None

async def is_owner_db(db, user_id: int) -> bool:
    async with db.execute("SELECT 1 FROM owners WHERE user_id=?", (user_id,)) as cur:
        return await cur.fetchone() is not None

async def add_sudo(db, user_id: int):
    await db.execute("INSERT OR IGNORE INTO sudos (user_id) VALUES (?)", (user_id,))
    await db.commit()

async def del_sudo(db, user_id: int):
    await db.execute("DELETE FROM sudos WHERE user_id=?", (user_id,))
    await db.commit()

async def list_sudos(db):
    async with db.execute("SELECT user_id FROM sudos") as cur:
        rows = await cur.fetchall()
        return [r["user_id"] for r in rows]

async def set_global(db, key: str, value: str):
    await db.execute(
        "INSERT OR REPLACE INTO global_settings (key, value) VALUES (?, ?)",
        (key, value)
    )
    await db.commit()

async def get_global(db, key: str, default=None):
    async with db.execute("SELECT value FROM global_settings WHERE key=?", (key,)) as cur:
        row = await cur.fetchone()
        return row["value"] if row else default
