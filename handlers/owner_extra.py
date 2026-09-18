"""Extra owner tools — backup, maintenance, logs, health"""

import os
import shutil
import zipfile
from datetime import datetime
from pathlib import Path
from telegram import Update, InputFile
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from config import DB_PATH, BACKUP_DIR, LOG_DIR, VERSION, BOT_NAME, MAINTENANCE_MODE
from utils.emoji import pe
from utils.helpers import is_owner
from utils.db import set_global, get_global

START_TIME = datetime.utcnow()

async def backup_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_owner(update.effective_user.id, context.bot_data.get("db")):
        return
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    zip_path = BACKUP_DIR / f"aura_backup_{ts}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        if DB_PATH.exists():
            z.write(DB_PATH, "aura.db")
        data_dir = DB_PATH.parent
        for f in data_dir.glob("*.json"):
            z.write(f, f.name)
    await update.message.reply_document(
        document=InputFile(zip_path.open("rb"), filename=zip_path.name),
        caption=f"{pe('check','✅')} Backup created"
    )

async def maintenance_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_owner(update.effective_user.id, context.bot_data.get("db")):
        return
    db = context.bot_data["db"]
    cur = await get_global(db, "maintenance", "0")
    new = "0" if cur == "1" else "1"
    await set_global(db, "maintenance", new)
    await update.message.reply_text(f"Maintenance mode: {'ON' if new == '1' else 'OFF'}")

async def uptime_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    delta = datetime.utcnow() - START_TIME
    hours, rem = divmod(int(delta.total_seconds()), 3600)
    mins, secs = divmod(rem, 60)
    await update.message.reply_text(f"{pe('zap','⚡')} Uptime: {hours}h {mins}m {secs}s", parse_mode=ParseMode.HTML)

async def health_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_owner(update.effective_user.id, context.bot_data.get("db")):
        return
    db = context.bot_data["db"]
    async with db.execute("SELECT COUNT(*) as c FROM users") as cur:
        users = (await cur.fetchone())["c"]
    async with db.execute("SELECT COUNT(*) as c FROM groups") as cur:
        groups = (await cur.fetchone())["c"]
    await update.message.reply_text(
        f"{pe('chart','📊')} <b>Health</b>\n"
        f"Version: {VERSION}\n"
        f"Users: {users}\n"
        f"Groups: {groups}\n"
        f"DB: {DB_PATH.exists()}\n"
        f"Uptime: {(datetime.utcnow() - START_TIME)}",
        parse_mode=ParseMode.HTML
    )

async def gbroadcast_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_owner(update.effective_user.id, context.bot_data.get("db")):
        return
    if not context.args and not update.message.reply_to_message:
        await update.message.reply_text("Usage: /gbroadcast message")
        return
    text = " ".join(context.args) if context.args else (update.message.reply_to_message.text or "")
    db = context.bot_data["db"]
    async with db.execute("SELECT chat_id FROM groups") as cur:
        rows = await cur.fetchall()
    ok = fail = 0
    status = await update.message.reply_text(f"Group broadcast to {len(rows)}...")
    for r in rows:
        try:
            await context.bot.send_message(r["chat_id"], text, parse_mode=ParseMode.HTML)
            ok += 1
        except Exception:
            fail += 1
    await status.edit_text(f"Done. OK: {ok} | Fail: {fail}")

async def banuser_bot_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ban user from using the bot globally."""
    if not await is_owner(update.effective_user.id, context.bot_data.get("db")):
        return
    if not context.args:
        await update.message.reply_text("Usage: /banuser USER_ID")
        return
    uid = int(context.args[0])
    await context.bot_data["db"].execute("UPDATE users SET is_banned=1 WHERE user_id=?", (uid,))
    await context.bot_data["db"].commit()
    await update.message.reply_text(f"Bot-banned {uid}")

async def unbanuser_bot_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_owner(update.effective_user.id, context.bot_data.get("db")):
        return
    if not context.args:
        return
    uid = int(context.args[0])
    await context.bot_data["db"].execute("UPDATE users SET is_banned=0 WHERE user_id=?", (uid,))
    await context.bot_data["db"].commit()
    await update.message.reply_text(f"Unbanned {uid} from bot")
