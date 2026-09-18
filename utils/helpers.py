"""Helpers — admin checks, time parse, text utils"""

import re
from datetime import datetime, timedelta
from telegram import ChatMember, Update
from telegram.ext import ContextTypes
from config import OWNER_IDS
from utils.db import is_sudo, is_owner_db

async def is_owner(user_id: int, db=None) -> bool:
    if user_id in OWNER_IDS:
        return True
    if db:
        return await is_owner_db(db, user_id)
    return False

async def is_authorized(user_id: int, db=None) -> bool:
    if await is_owner(user_id, db):
        return True
    if db:
        return await is_sudo(db, user_id)
    return False

async def is_group_admin(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int = None) -> bool:
    uid = user_id or update.effective_user.id
    if await is_owner(uid):
        return True
    chat = update.effective_chat
    if chat.type == "private":
        return False
    try:
        member = await context.bot.get_chat_member(chat.id, uid)
        return member.status in (ChatMember.ADMINISTRATOR, ChatMember.OWNER)
    except Exception:
        return False

async def bot_can_restrict(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    try:
        me = await context.bot.get_chat_member(update.effective_chat.id, context.bot.id)
        return me.can_restrict_members if me.status == ChatMember.ADMINISTRATOR else False
    except Exception:
        return False

async def bot_can_delete(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    try:
        me = await context.bot.get_chat_member(update.effective_chat.id, context.bot.id)
        return me.can_delete_messages if me.status == ChatMember.ADMINISTRATOR else False
    except Exception:
        return False

def parse_time(arg: str) -> timedelta | None:
    """Parse 1h 30m 2d 10s etc."""
    if not arg:
        return None
    total = 0
    for num, unit in re.findall(r"(\d+)([smhdw])", arg.lower()):
        n = int(num)
        if unit == "s":
            total += n
        elif unit == "m":
            total += n * 60
        elif unit == "h":
            total += n * 3600
        elif unit == "d":
            total += n * 86400
        elif unit == "w":
            total += n * 604800
    return timedelta(seconds=total) if total else None

def extract_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Get target user from reply or args."""
    if update.message.reply_to_message:
        u = update.message.reply_to_message.from_user
        return u.id, u.mention_html() if u else (None, None)
    if context.args:
        arg = context.args[0]
        if arg.isdigit():
            return int(arg), f"<code>{arg}</code>"
        return None, arg  # username — resolve later
    return None, None

URL_RE = re.compile(r"(https?://\S+|t\.me/\S+|www\.\S+|telegram\.me/\S+)", re.I)

def has_link(text: str) -> bool:
    return bool(text and URL_RE.search(text))
