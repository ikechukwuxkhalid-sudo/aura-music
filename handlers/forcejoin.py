"""Force join channels / groups"""

import json
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatMember
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from utils.emoji import pe
from utils.helpers import is_group_admin
from utils.db import ensure_group, get_group

async def forcejoin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_group_admin(update, context):
        return
    if not context.args:
        row = await get_group(context.bot_data["db"], update.effective_chat.id)
        fj = json.loads(row["force_join"] or "[]") if row else []
        text = f"{pe('lock','🔒')} Force-join list:\n" + ("\n".join(f"• {x}" for x in fj) if fj else "Empty")
        text += "\n\n/forcejoin add @channel\n/forcejoin del @channel\n/forcejoin clear"
        await update.message.reply_text(text, parse_mode=ParseMode.HTML)
        return
    action = context.args[0].lower()
    db = context.bot_data["db"]
    await ensure_group(db, update.effective_chat.id, update.effective_chat.title or "")
    row = await get_group(db, update.effective_chat.id)
    fj = json.loads(row["force_join"] or "[]") if row else []

    if action == "add" and len(context.args) > 1:
        ch = context.args[1]
        if ch not in fj:
            fj.append(ch)
        await db.execute("UPDATE groups SET force_join=? WHERE chat_id=?", (json.dumps(fj), update.effective_chat.id))
        await db.commit()
        await update.message.reply_text(f"{pe('check','✅')} Added {ch}", parse_mode=ParseMode.HTML)
    elif action == "del" and len(context.args) > 1:
        ch = context.args[1]
        fj = [x for x in fj if x != ch]
        await db.execute("UPDATE groups SET force_join=? WHERE chat_id=?", (json.dumps(fj), update.effective_chat.id))
        await db.commit()
        await update.message.reply_text(f"Removed {ch}")
    elif action == "clear":
        await db.execute("UPDATE groups SET force_join=? WHERE chat_id=?", ("[]", update.effective_chat.id))
        await db.commit()
        await update.message.reply_text("Force-join list cleared.")
    else:
        await update.message.reply_text("Usage: /forcejoin add|del|clear @channel")

async def check_force_join(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Returns True if user is blocked (not joined required channels)."""
    if not update.message or not update.message.from_user:
        return False
    if update.effective_chat.type == "private":
        return False
    user = update.message.from_user
    if user.is_bot:
        return False
    db = context.bot_data["db"]
    row = await get_group(db, update.effective_chat.id)
    if not row:
        return False
    fj = json.loads(row["force_join"] or "[]")
    if not fj:
        return False
    # admins bypass
    try:
        mem = await context.bot.get_chat_member(update.effective_chat.id, user.id)
        if mem.status in (ChatMember.ADMINISTRATOR, ChatMember.OWNER):
            return False
    except Exception:
        pass

    missing = []
    for ch in fj:
        try:
            m = await context.bot.get_chat_member(ch, user.id)
            if m.status in ("left", "kicked"):
                missing.append(ch)
        except Exception:
            missing.append(ch)
    if not missing:
        return False

    buttons = []
    for ch in missing:
        url = ch if ch.startswith("http") else f"https://t.me/{ch.lstrip('@')}"
        buttons.append([InlineKeyboardButton(f"Join {ch}", url=url)])
    buttons.append([InlineKeyboardButton("✅ I joined", callback_data=f"fj_check:{update.effective_chat.id}")])
    try:
        await update.message.delete()
    except Exception:
        pass
    try:
        await context.bot.send_message(
            update.effective_chat.id,
            f"{pe('lock','🔒')} {user.mention_html()}, join the required channels first:",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(buttons)
        )
    except Exception:
        pass
    return True

async def fj_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not q.data.startswith("fj_check:"):
        return
    chat_id = int(q.data.split(":")[1])
    user = q.from_user
    db = context.bot_data["db"]
    row = await get_group(db, chat_id)
    fj = json.loads(row["force_join"] or "[]") if row else []
    missing = []
    for ch in fj:
        try:
            m = await context.bot.get_chat_member(ch, user.id)
            if m.status in ("left", "kicked"):
                missing.append(ch)
        except Exception:
            missing.append(ch)
    if missing:
        await q.answer("Still missing channels!", show_alert=True)
    else:
        await q.edit_message_text(f"{pe('check','✅')} Verified. Welcome!", parse_mode=ParseMode.HTML)
