"""Federation system — shared bans across groups"""

import json
from datetime import datetime
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from utils.emoji import pe
from utils.helpers import is_owner, is_group_admin
from utils.db import get_db

# Ensure fed tables exist
FED_SCHEMA = """
CREATE TABLE IF NOT EXISTS federations (
    fed_id TEXT PRIMARY KEY,
    name TEXT,
    owner_id INTEGER,
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS fed_chats (
    fed_id TEXT,
    chat_id INTEGER,
    PRIMARY KEY (fed_id, chat_id)
);
CREATE TABLE IF NOT EXISTS fed_bans (
    fed_id TEXT,
    user_id INTEGER,
    reason TEXT,
    admin_id INTEGER,
    created_at TEXT,
    PRIMARY KEY (fed_id, user_id)
);
CREATE TABLE IF NOT EXISTS fed_admins (
    fed_id TEXT,
    user_id INTEGER,
    PRIMARY KEY (fed_id, user_id)
);
"""

async def ensure_fed_tables(db):
    await db.executescript(FED_SCHEMA)
    await db.commit()

async def newfed_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_owner(update.effective_user.id, context.bot_data.get("db")):
        if not await is_group_admin(update, context):
            return
    if not context.args:
        await update.message.reply_text("Usage: /newfed FedName")
        return
    name = " ".join(context.args)
    fed_id = f"fed_{update.effective_user.id}_{int(datetime.utcnow().timestamp())}"
    db = context.bot_data["db"]
    await ensure_fed_tables(db)
    await db.execute(
        "INSERT INTO federations (fed_id, name, owner_id, created_at) VALUES (?,?,?,?)",
        (fed_id, name, update.effective_user.id, datetime.utcnow().isoformat())
    )
    await db.execute(
        "INSERT INTO fed_admins (fed_id, user_id) VALUES (?,?)",
        (fed_id, update.effective_user.id)
    )
    await db.commit()
    await update.message.reply_text(
        f"{pe('crown','👑')} Federation created\nName: <b>{name}</b>\nID: <code>{fed_id}</code>\n\nUse /joinfed {fed_id} in groups.",
        parse_mode=ParseMode.HTML
    )

async def joinfed_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_group_admin(update, context):
        return
    if not context.args:
        await update.message.reply_text("Usage: /joinfed FED_ID")
        return
    fed_id = context.args[0]
    db = context.bot_data["db"]
    await ensure_fed_tables(db)
    async with db.execute("SELECT name FROM federations WHERE fed_id=?", (fed_id,)) as cur:
        row = await cur.fetchone()
    if not row:
        await update.message.reply_text("Federation not found.")
        return
    await db.execute(
        "INSERT OR IGNORE INTO fed_chats (fed_id, chat_id) VALUES (?,?)",
        (fed_id, update.effective_chat.id)
    )
    await db.commit()
    await update.message.reply_text(f"{pe('check','✅')} Joined federation <b>{row['name']}</b>", parse_mode=ParseMode.HTML)

async def leavefed_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_group_admin(update, context):
        return
    if not context.args:
        await update.message.reply_text("Usage: /leavefed FED_ID")
        return
    fed_id = context.args[0]
    db = context.bot_data["db"]
    await db.execute(
        "DELETE FROM fed_chats WHERE fed_id=? AND chat_id=?",
        (fed_id, update.effective_chat.id)
    )
    await db.commit()
    await update.message.reply_text("Left federation.")

async def fedban_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = context.bot_data["db"]
    await ensure_fed_tables(db)
    # find feds this chat belongs to where user is fed admin
    async with db.execute(
        "SELECT fc.fed_id, f.name FROM fed_chats fc JOIN federations f ON f.fed_id=fc.fed_id WHERE fc.chat_id=?",
        (update.effective_chat.id,)
    ) as cur:
        feds = await cur.fetchall()
    if not feds:
        await update.message.reply_text("This group is not in any federation.")
        return
    uid = None
    if update.message.reply_to_message:
        uid = update.message.reply_to_message.from_user.id
    elif context.args:
        try:
            uid = int(context.args[0])
        except ValueError:
            pass
    if not uid:
        await update.message.reply_text("Reply to user or give id: /fedban USER_ID reason")
        return
    reason = " ".join(context.args[1:]) if context.args and len(context.args) > 1 else "Fed ban"
    banned_in = 0
    for fed in feds:
        fed_id = fed["fed_id"]
        # check fed admin
        async with db.execute(
            "SELECT 1 FROM fed_admins WHERE fed_id=? AND user_id=?",
            (fed_id, update.effective_user.id)
        ) as cur:
            if not await cur.fetchone():
                if not await is_owner(update.effective_user.id, db):
                    continue
        await db.execute(
            "INSERT OR REPLACE INTO fed_bans (fed_id, user_id, reason, admin_id, created_at) VALUES (?,?,?,?,?)",
            (fed_id, uid, reason, update.effective_user.id, datetime.utcnow().isoformat())
        )
        # ban in all fed chats
        async with db.execute("SELECT chat_id FROM fed_chats WHERE fed_id=?", (fed_id,)) as cur:
            chats = await cur.fetchall()
        for c in chats:
            try:
                await context.bot.ban_chat_member(c["chat_id"], uid)
                banned_in += 1
            except Exception:
                pass
    await db.commit()
    await update.message.reply_text(f"{pe('ban','⛔️')} Fed-banned {uid} in {banned_in} group(s)\nReason: {reason}", parse_mode=ParseMode.HTML)

async def fedunban_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /fedunban USER_ID")
        return
    uid = int(context.args[0])
    db = context.bot_data["db"]
    await ensure_fed_tables(db)
    async with db.execute(
        "SELECT fed_id FROM fed_chats WHERE chat_id=?", (update.effective_chat.id,)
    ) as cur:
        feds = await cur.fetchall()
    for fed in feds:
        await db.execute("DELETE FROM fed_bans WHERE fed_id=? AND user_id=?", (fed["fed_id"], uid))
        async with db.execute("SELECT chat_id FROM fed_chats WHERE fed_id=?", (fed["fed_id"],)) as cur:
            chats = await cur.fetchall()
        for c in chats:
            try:
                await context.bot.unban_chat_member(c["chat_id"], uid, only_if_banned=True)
            except Exception:
                pass
    await db.commit()
    await update.message.reply_text(f"{pe('check','✅')} Fed-unbanned {uid}", parse_mode=ParseMode.HTML)

async def fedinfo_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = context.bot_data["db"]
    await ensure_fed_tables(db)
    async with db.execute(
        "SELECT fc.fed_id, f.name, f.owner_id FROM fed_chats fc JOIN federations f ON f.fed_id=fc.fed_id WHERE fc.chat_id=?",
        (update.effective_chat.id,)
    ) as cur:
        rows = await cur.fetchall()
    if not rows:
        await update.message.reply_text("Not in any federation.")
        return
    lines = [f"{pe('crown','👑')} Federations for this group:\n"]
    for r in rows:
        lines.append(f"• <b>{r['name']}</b>\n  ID: <code>{r['fed_id']}</code>")
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)

async def check_fed_ban(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Auto-ban fed-banned users on join/message."""
    if not update.message or not update.message.from_user:
        return False
    user = update.message.from_user
    db = context.bot_data["db"]
    try:
        await ensure_fed_tables(db)
        async with db.execute(
            "SELECT fb.reason FROM fed_bans fb JOIN fed_chats fc ON fc.fed_id=fb.fed_id WHERE fc.chat_id=? AND fb.user_id=?",
            (update.effective_chat.id, user.id)
        ) as cur:
            row = await cur.fetchone()
        if row:
            try:
                await context.bot.ban_chat_member(update.effective_chat.id, user.id)
                await update.message.reply_text(f"{pe('ban','⛔️')} {user.mention_html()} is federation-banned.\nReason: {row['reason']}", parse_mode=ParseMode.HTML)
            except Exception:
                pass
            return True
    except Exception:
        pass
    return False
