"""Filters system"""

from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from utils.emoji import pe
from utils.helpers import is_group_admin

async def filter_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_group_admin(update, context):
        return
    if len(context.args) < 2 and not update.message.reply_to_message:
        await update.message.reply_text("Usage: /filter keyword reply text\nOr reply to a message: /filter keyword")
        return
    keyword = context.args[0].lower()
    reply = " ".join(context.args[1:]) if len(context.args) > 1 else ""
    media_type = media_id = None
    if update.message.reply_to_message:
        r = update.message.reply_to_message
        reply = reply or r.text or r.caption or ""
        if r.photo:
            media_type, media_id = "photo", r.photo[-1].file_id
        elif r.sticker:
            media_type, media_id = "sticker", r.sticker.file_id
        elif r.document:
            media_type, media_id = "document", r.document.file_id
        elif r.video:
            media_type, media_id = "video", r.video.file_id
    db = context.bot_data["db"]
    await db.execute(
        "INSERT INTO filters (chat_id, keyword, reply, media_type, media_id, exact) VALUES (?,?,?,?,?,0)",
        (update.effective_chat.id, keyword, reply, media_type, media_id)
    )
    await db.commit()
    await update.message.reply_text(f"{pe('check','✅')} Filter for <b>{keyword}</b> saved.", parse_mode=ParseMode.HTML)

async def stop_filter_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_group_admin(update, context):
        return
    if not context.args:
        await update.message.reply_text("Usage: /stop keyword")
        return
    keyword = context.args[0].lower()
    await context.bot_data["db"].execute(
        "DELETE FROM filters WHERE chat_id=? AND keyword=?",
        (update.effective_chat.id, keyword)
    )
    await context.bot_data["db"].commit()
    await update.message.reply_text(f"Filter <b>{keyword}</b> removed.", parse_mode=ParseMode.HTML)

async def filters_list_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = context.bot_data["db"]
    async with db.execute(
        "SELECT keyword FROM filters WHERE chat_id=?", (update.effective_chat.id,)
    ) as cur:
        rows = await cur.fetchall()
    if not rows:
        await update.message.reply_text("No filters.")
        return
    await update.message.reply_text(
        f"{pe('zap','⚡')} Filters:\n" + "\n".join(f"• {r['keyword']}" for r in rows),
        parse_mode=ParseMode.HTML
    )

async def check_filters(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    if update.effective_chat.type == "private":
        return
    text = update.message.text.lower()
    db = context.bot_data["db"]
    async with db.execute(
        "SELECT * FROM filters WHERE chat_id=?", (update.effective_chat.id,)
    ) as cur:
        rows = await cur.fetchall()
    for r in rows:
        kw = r["keyword"]
        if kw in text:
            if r["media_type"] == "photo":
                await update.message.reply_photo(r["media_id"], caption=r["reply"] or None)
            elif r["media_type"] == "sticker":
                await update.message.reply_sticker(r["media_id"])
            elif r["media_type"] == "document":
                await update.message.reply_document(r["media_id"], caption=r["reply"] or None)
            elif r["media_type"] == "video":
                await update.message.reply_video(r["media_id"], caption=r["reply"] or None)
            elif r["reply"]:
                await update.message.reply_text(r["reply"])
            break
