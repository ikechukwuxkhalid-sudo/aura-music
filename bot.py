#!/usr/bin/env python3
"""
DR AURA — Full Group Management Bot
Owner: King Khalid (8333953794)
"""

import asyncio
import json
import logging
import re
from datetime import datetime, timedelta
from functools import wraps

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatPermissions,
    ChatMember, MessageEntity
)
from telegram.constants import ParseMode, ChatType
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ChatMemberHandler, ContextTypes, filters
)
from telegram.error import BadRequest, Forbidden

from config import (
    BOT_TOKEN, OWNER_IDS, BOT_NAME, VERSION, SUPPORT_LINK,
    DEFAULT_WARN_LIMIT, MAINTENANCE_MODE
)
from utils.db import (
    get_db, ensure_group, get_group, set_group_setting, get_setting,
    add_warn, reset_warns, get_warn_count, log_action,
    is_sudo, add_sudo, del_sudo, list_sudos, set_global, get_global
)
from utils.emoji import pe, set_enabled, is_enabled, set_emoji, save_map
from utils.helpers import (
    is_owner, is_authorized, is_group_admin, bot_can_restrict, bot_can_delete,
    bot_can_promote, parse_time, extract_user, resolve_user, has_link
)
from handlers.filters_mod import filter_cmd, stop_filter_cmd, filters_list_cmd, check_filters
from handlers.forcejoin import forcejoin_cmd, check_force_join, fj_callback
from handlers.federation import (
    newfed_cmd, joinfed_cmd, leavefed_cmd, fedban_cmd, fedunban_cmd, fedinfo_cmd, check_fed_ban
)
from handlers.owner_extra import (
    backup_cmd, maintenance_cmd, uptime_cmd, health_cmd, gbroadcast_cmd,
    banuser_bot_cmd, unbanuser_bot_cmd
)

logging.basicConfig(format="%(asctime)s | %(levelname)s | %(message)s", level=logging.INFO)
log = logging.getLogger("AURA")

# Flood tracker: chat_id -> {user_id: [timestamps]}
flood_cache: dict = {}

# ==================== DECORATORS ====================
def owner_only(func):
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await is_owner(update.effective_user.id, context.bot_data.get("db")):
            return
        return await func(update, context)
    return wrapper

def admin_only(func):
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await is_group_admin(update, context):
            await update.message.reply_text(f"{pe('ban','⛔️')} Admins only.")
            return
        return await func(update, context)
    return wrapper

def group_only(func):
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_chat.type == ChatType.PRIVATE:
            await update.message.reply_text("This command works only in groups.")
            return
        return await func(update, context)
    return wrapper

# ==================== START / HELP ====================
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db = context.bot_data["db"]
    await db.execute(
        "INSERT OR REPLACE INTO users (user_id, username, full_name, last_seen) VALUES (?,?,?,?)",
        (user.id, user.username or "", user.full_name, datetime.utcnow().isoformat())
    )
    await db.commit()

    text = (
        f"{pe('crown','👑')} <b>{BOT_NAME}</b> v{VERSION}\n\n"
        f"Advanced group management bot.\n"
        f"Add me to a group and promote me as admin.\n\n"
        f"{pe('shield','🛡')} Moderation • Warnings • Locks\n"
        f"{pe('wave','👋')} Welcome / Goodbye • Rules • Notes\n"
        f"{pe('lock','🔒')} Anti-spam • Anti-link • Anti-delete\n"
        f"{pe('zap','⚡')} Filters • Force Join • Federation\n\n"
        f"Commands: /help\n"
        f"Support: {SUPPORT_LINK}"
    )
    kb = [[InlineKeyboardButton("➕ Add to Group", url=f"https://t.me/{context.bot.username}?startgroup=true")]]
    await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(kb))

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        f"{pe('robot','🤖')} <b>{BOT_NAME} Help</b>\n\n"
        f"<b>Moderation</b>\n"
        f"/ban /tban /unban /kick /mute /tmute /unmute\n"
        f"/warn /unwarn /warns /resetwarns\n\n"
        f"<b>Locks</b>\n"
        f"/lock [type] • /unlock [type] • /locks\n"
        f"types: all media url gif photo video audio document sticker emoji forward bot command text\n\n"
        f"<b>Anti</b>\n"
        f"/antilink [off|del|kick|ban|mute]\n"
        f"/antidelete [on|off] — resend deleted messages\n"
        f"/antiflood [limit]\n\n"
        f"<b>Welcome / Rules</b>\n"
        f"/setwelcome • /setgoodbye • /setrules • /rules\n\n"
        f"<b>Notes / Filters</b>\n"
        f"/save • /get • /notes • /clear\n"
        f"/filter • /stop • /filters\n\n"
        f"<b>Force Join</b>\n"
        f"/forcejoin add|del|clear @channel\n\n"
        f"<b>Federation</b>\n"
        f"/newfed • /joinfed • /leavefed • /fedban • /fedunban • /fedinfo\n\n"
        f"<b>Info</b>\n"
        f"/id • /adminlist\n\n"
        f"<b>Owner</b>\n"
        f"/owner • /stats • /broadcast • /gbroadcast\n"
        f"/setemo • /emojitoggle • /backup • /maintenance\n"
        f"/health • /uptime • /banuser • /unbanuser"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)

# ==================== MODERATION ====================
@group_only
@admin_only
async def ban_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await bot_can_restrict(update, context):
        await update.message.reply_text("❌ I need Restrict Members permission. Promote me properly.")
        return
    uid, mention, _ = await resolve_user(update, context)
    if not uid:
        await update.message.reply_text("Reply to a user, or use /ban @username or /ban USER_ID")
        return
    # don't ban admins / owner / self
    if await is_group_admin(update, context, uid) or await is_owner(uid):
        await update.message.reply_text("❌ Can't ban an admin/owner.")
        return
    reason = "No reason"
    if context.args:
        # if first arg is id/username skip it for reason
        start = 1 if (context.args[0].isdigit() or context.args[0].startswith("@")) else 0
        if update.message.reply_to_message:
            start = 0
        reason = " ".join(context.args[start:]) or "No reason"
    try:
        await context.bot.ban_chat_member(update.effective_chat.id, uid)
        await log_action(context.bot_data["db"], update.effective_chat.id, "ban", update.effective_user.id, uid, reason)
        await update.message.reply_text(f"⛔️ Banned {mention}\nReason: {reason}", parse_mode=ParseMode.HTML)
    except Exception as e:
        await update.message.reply_text(f"❌ Ban failed: {e}")

@group_only
@admin_only
async def tban_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await bot_can_restrict(update, context):
        return
    if not context.args:
        await update.message.reply_text("Usage: /tban [time] (reply or id)  e.g. /tban 1h")
        return
    t = parse_time(context.args[0])
    if not t:
        await update.message.reply_text("Invalid time. Use 1h 30m 2d etc.")
        return
    uid, mention, _ = await resolve_user(update, context)
    if not uid:
        await update.message.reply_text("Reply to a user or pass @username / USER_ID")
        return
    until = datetime.utcnow() + t
    try:
        await context.bot.ban_chat_member(update.effective_chat.id, uid, until_date=until)
        await update.message.reply_text(f"{pe('ban','⛔️')} Temp banned {mention} for {context.args[0]}", parse_mode=ParseMode.HTML)
    except Exception as e:
        await update.message.reply_text(f"❌ {e}")

@group_only
@admin_only
async def unban_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid, mention, _ = await resolve_user(update, context)
    if not uid:
        await update.message.reply_text("Give user id or reply.")
        return
    try:
        await context.bot.unban_chat_member(update.effective_chat.id, uid, only_if_banned=True)
        await update.message.reply_text(f"{pe('check','✅')} Unbanned {mention}", parse_mode=ParseMode.HTML)
    except Exception as e:
        await update.message.reply_text(f"❌ {e}")

@group_only
@admin_only
async def kick_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await bot_can_restrict(update, context):
        await update.message.reply_text("❌ I need Restrict Members permission.")
        return
    uid, mention, _ = await resolve_user(update, context)
    if not uid:
        await update.message.reply_text("Reply to a user or /kick @user or /kick USER_ID")
        return
    if await is_group_admin(update, context, uid) or await is_owner(uid):
        await update.message.reply_text("❌ Can't kick an admin/owner.")
        return
    try:
        await context.bot.ban_chat_member(update.effective_chat.id, uid)
        await context.bot.unban_chat_member(update.effective_chat.id, uid)
        await log_action(context.bot_data["db"], update.effective_chat.id, "kick", update.effective_user.id, uid, "")
        await update.message.reply_text(f"👢 Kicked {mention}", parse_mode=ParseMode.HTML)
    except Exception as e:
        await update.message.reply_text(f"❌ Kick failed: {e}")


@group_only
@admin_only
async def mute_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await bot_can_restrict(update, context):
        await update.message.reply_text("❌ I need Restrict Members permission.")
        return
    uid, mention, _ = await resolve_user(update, context)
    if not uid:
        await update.message.reply_text("Reply to a user or /mute @user")
        return
    if await is_group_admin(update, context, uid) or await is_owner(uid):
        await update.message.reply_text("❌ Can't mute an admin/owner.")
        return
    perms = ChatPermissions(can_send_messages=False)
    try:
        await context.bot.restrict_chat_member(update.effective_chat.id, uid, permissions=perms)
        await log_action(context.bot_data["db"], update.effective_chat.id, "mute", update.effective_user.id, uid, "")
        await update.message.reply_text(f"🔇 Muted {mention}", parse_mode=ParseMode.HTML)
    except Exception as e:
        await update.message.reply_text(f"❌ Mute failed: {e}")


@group_only
@admin_only
async def tmute_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await bot_can_restrict(update, context):
        return
    if not context.args:
        await update.message.reply_text("Usage: /tmute 1h (reply)")
        return
    t = parse_time(context.args[0])
    if not t:
        await update.message.reply_text("Invalid time.")
        return
    uid, mention, _ = await resolve_user(update, context)
    if not uid:
        await update.message.reply_text("Reply to a user or pass @username / USER_ID")
        return
    perms = ChatPermissions(can_send_messages=False)
    until = datetime.utcnow() + t
    try:
        await context.bot.restrict_chat_member(update.effective_chat.id, uid, permissions=perms, until_date=until)
        await update.message.reply_text(f"{pe('mute','🔇')} Temp muted {mention} for {context.args[0]}", parse_mode=ParseMode.HTML)
    except Exception as e:
        await update.message.reply_text(f"❌ {e}")

@group_only
@admin_only
async def unmute_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid, mention, _ = await resolve_user(update, context)
    if not uid:
        await update.message.reply_text("Reply to a user or /unmute @user")
        return
    perms = ChatPermissions(
        can_send_messages=True, can_send_audios=True, can_send_documents=True,
        can_send_photos=True, can_send_videos=True, can_send_video_notes=True,
        can_send_voice_notes=True, can_send_polls=True, can_send_other_messages=True,
        can_add_web_page_previews=True
    )
    try:
        await context.bot.restrict_chat_member(update.effective_chat.id, uid, permissions=perms)
        await update.message.reply_text(f"✅ Unmuted {mention}", parse_mode=ParseMode.HTML)
    except Exception as e:
        await update.message.reply_text(f"❌ {e}")



@group_only
@admin_only
async def promote_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await bot_can_promote(update, context):
        await update.message.reply_text("❌ I need Promote Members permission.")
        return
    uid, mention, _ = await resolve_user(update, context)
    if not uid:
        await update.message.reply_text("Reply to a user or /promote @user")
        return
    try:
        await context.bot.promote_chat_member(
            update.effective_chat.id, uid,
            can_delete_messages=True,
            can_restrict_members=True,
            can_invite_users=True,
            can_pin_messages=True,
            can_manage_chat=True,
        )
        await update.message.reply_text(f"⬆️ Promoted {mention}", parse_mode=ParseMode.HTML)
    except Exception as e:
        await update.message.reply_text(f"❌ Promote failed: {e}")

@group_only
@admin_only
async def demote_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await bot_can_promote(update, context):
        await update.message.reply_text("❌ I need Promote Members permission.")
        return
    uid, mention, _ = await resolve_user(update, context)
    if not uid:
        await update.message.reply_text("Reply to a user or /demote @user")
        return
    try:
        await context.bot.promote_chat_member(
            update.effective_chat.id, uid,
            is_anonymous=False,
            can_manage_chat=False,
            can_delete_messages=False,
            can_manage_video_chats=False,
            can_restrict_members=False,
            can_promote_members=False,
            can_change_info=False,
            can_invite_users=False,
            can_pin_messages=False,
        )
        await update.message.reply_text(f"⬇️ Demoted {mention}", parse_mode=ParseMode.HTML)
    except Exception as e:
        await update.message.reply_text(f"❌ Demote failed: {e}")

@group_only
async def panel_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cool admin panel menu"""
    kb = [
        [
            InlineKeyboardButton("⛔️ Ban", callback_data="help_ban"),
            InlineKeyboardButton("👢 Kick", callback_data="help_kick"),
            InlineKeyboardButton("🔇 Mute", callback_data="help_mute"),
        ],
        [
            InlineKeyboardButton("⚠️ Warn", callback_data="help_warn"),
            InlineKeyboardButton("⬆️ Promote", callback_data="help_promote"),
            InlineKeyboardButton("⬇️ Demote", callback_data="help_demote"),
        ],
        [
            InlineKeyboardButton("🔒 Locks", callback_data="help_locks"),
            InlineKeyboardButton("🔗 Anti-link", callback_data="help_antilink"),
            InlineKeyboardButton("👀 Anti-delete", callback_data="help_antidelete"),
        ],
        [
            InlineKeyboardButton("👋 Welcome", callback_data="help_welcome"),
            InlineKeyboardButton("📝 Notes", callback_data="help_notes"),
            InlineKeyboardButton("⚡ Filters", callback_data="help_filters"),
        ],
        [
            InlineKeyboardButton("📢 Force Join", callback_data="help_forcejoin"),
            InlineKeyboardButton("👑 Federation", callback_data="help_fed"),
            InlineKeyboardButton("ℹ️ Help", callback_data="help_full"),
        ],
    ]
    await update.message.reply_text(
        f"🛡 <b>Dr Aura Control Panel</b>\n\n"
        f"Group: <b>{update.effective_chat.title}</b>\n"
        f"Choose a category:",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(kb)
    )

async def panel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data or ""
    guides = {
        "help_ban": "⛔️ <b>Ban</b>\n/ban (reply) [reason]\n/ban @user [reason]\n/ban USER_ID [reason]\n/tban 1h (reply)\n/unban USER_ID",
        "help_kick": "👢 <b>Kick</b>\n/kick (reply)\n/kick @user\n/kick USER_ID",
        "help_mute": "🔇 <b>Mute</b>\n/mute (reply)\n/tmute 1h (reply)\n/unmute (reply)",
        "help_warn": "⚠️ <b>Warn</b>\n/warn (reply) [reason]\n/unwarn (reply)\n/warns (reply)",
        "help_promote": "⬆️ <b>Promote</b>\n/promote (reply)\n/promote @user\n\n⬇️ <b>Demote</b>\n/demote (reply)",
        "help_demote": "⬇️ <b>Demote</b>\n/demote (reply)\n/demote @user",
        "help_locks": "🔒 <b>Locks</b>\n/lock url|media|photo|video|sticker|gif|forward|command|text|all\n/unlock TYPE\n/locks",
        "help_antilink": "🔗 <b>Anti-link</b>\n/antilink off — disable\n/antilink del — delete links\n/antilink kick|ban|mute — delete + action",
        "help_antidelete": "👀 <b>Anti-delete</b>\n/antidelete on — watch messages\n/antidelete off\nWhen someone deletes a message, bot reports who deleted + content (from cache).",
        "help_welcome": "👋 <b>Welcome</b>\n/setwelcome Hello {mention} in {group}\n/setgoodbye Bye {name}\n/setrules rules text\n/rules",
        "help_notes": "📝 <b>Notes</b>\n/save name (reply to media/text)\n/get name  or  #name\n/notes  /clear name",
        "help_filters": "⚡ <b>Filters</b>\n/filter keyword reply text\n/stop keyword\n/filters",
        "help_forcejoin": "📢 <b>Force Join</b>\n/forcejoin add @channel\n/forcejoin del @channel\n/forcejoin clear",
        "help_fed": "👑 <b>Federation</b>\n/newfed Name\n/joinfed FED_ID\n/fedban (reply)\n/fedunban USER_ID\n/fedinfo",
        "help_full": "Use /help for full command list.",
    }
    text = guides.get(data, "Unknown")
    kb = [[InlineKeyboardButton("🔙 Back", callback_data="help_back")]]
    if data == "help_back":
        # re-show panel - edit
        kb = [
            [InlineKeyboardButton("⛔️ Ban", callback_data="help_ban"), InlineKeyboardButton("👢 Kick", callback_data="help_kick"), InlineKeyboardButton("🔇 Mute", callback_data="help_mute")],
            [InlineKeyboardButton("⚠️ Warn", callback_data="help_warn"), InlineKeyboardButton("⬆️ Promote", callback_data="help_promote"), InlineKeyboardButton("⬇️ Demote", callback_data="help_demote")],
            [InlineKeyboardButton("🔒 Locks", callback_data="help_locks"), InlineKeyboardButton("🔗 Anti-link", callback_data="help_antilink"), InlineKeyboardButton("👀 Anti-delete", callback_data="help_antidelete")],
            [InlineKeyboardButton("👋 Welcome", callback_data="help_welcome"), InlineKeyboardButton("📝 Notes", callback_data="help_notes"), InlineKeyboardButton("⚡ Filters", callback_data="help_filters")],
            [InlineKeyboardButton("📢 Force Join", callback_data="help_forcejoin"), InlineKeyboardButton("👑 Federation", callback_data="help_fed")],
        ]
        text = f"🛡 <b>Dr Aura Control Panel</b>\n\nChoose a category:"
    await q.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(kb))


# ==================== WARNINGS ====================
@group_only
@admin_only
async def warn_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid, mention, _ = await resolve_user(update, context)
    if not uid:
        await update.message.reply_text("Reply to a user or /warn @user")
        return
    reason = "No reason"
    if context.args:
        start = 1 if (context.args[0].isdigit() or context.args[0].startswith("@")) and not update.message.reply_to_message else 0
        reason = " ".join(context.args[start:]) or "No reason"
    db = context.bot_data["db"]
    count = await add_warn(db, update.effective_chat.id, uid, reason, update.effective_user.id)
    row = await get_group(db, update.effective_chat.id)
    limit = row["warn_limit"] if row else DEFAULT_WARN_LIMIT
    await update.message.reply_text(
        f"{pe('warn','⚠️')} Warned {mention}\nReason: {reason}\nWarns: {count}/{limit}",
        parse_mode=ParseMode.HTML
    )
    if count >= limit:
        try:
            await context.bot.ban_chat_member(update.effective_chat.id, uid)
            await reset_warns(db, update.effective_chat.id, uid)
            await update.message.reply_text(f"{pe('ban','⛔️')} Ban limit reached — user banned.")
        except Exception:
            pass

@group_only
@admin_only
async def unwarn_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid, mention, _ = await resolve_user(update, context)
    if not uid:
        await update.message.reply_text("Reply to a user or pass @username / USER_ID")
        return
    db = context.bot_data["db"]
    await reset_warns(db, update.effective_chat.id, uid)
    await update.message.reply_text(f"{pe('check','✅')} Warnings cleared for {mention}", parse_mode=ParseMode.HTML)

@group_only
async def warns_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid, mention, _ = await resolve_user(update, context)
    if not uid:
        uid = update.effective_user.id
        mention = update.effective_user.mention_html()
    count = await get_warn_count(context.bot_data["db"], update.effective_chat.id, uid)
    await update.message.reply_text(f"{pe('warn','⚠️')} {mention} has {count} warn(s)", parse_mode=ParseMode.HTML)

# ==================== LOCKS ====================
LOCK_TYPES = {
    "all": "all", "media": "media", "url": "url", "gif": "gif", "photo": "photo",
    "video": "video", "audio": "audio", "document": "document", "sticker": "sticker",
    "emoji": "emoji", "forward": "forward", "bot": "bot", "command": "command", "text": "text"
}

@group_only
@admin_only
async def lock_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /lock [type]\nTypes: " + ", ".join(LOCK_TYPES))
        return
    t = context.args[0].lower()
    if t not in LOCK_TYPES:
        await update.message.reply_text("Unknown type.")
        return
    db = context.bot_data["db"]
    await ensure_group(db, update.effective_chat.id, update.effective_chat.title or "")
    row = await get_group(db, update.effective_chat.id)
    locks = json.loads(row["locks"] or "{}") if row else {}
    locks[t] = True
    await db.execute("UPDATE groups SET locks=? WHERE chat_id=?", (json.dumps(locks), update.effective_chat.id))
    await db.commit()
    await update.message.reply_text(f"{pe('lock','🔒')} Locked: <b>{t}</b>", parse_mode=ParseMode.HTML)

@group_only
@admin_only
async def unlock_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /unlock [type]")
        return
    t = context.args[0].lower()
    db = context.bot_data["db"]
    row = await get_group(db, update.effective_chat.id)
    locks = json.loads(row["locks"] or "{}") if row else {}
    locks[t] = False
    await db.execute("UPDATE groups SET locks=? WHERE chat_id=?", (json.dumps(locks), update.effective_chat.id))
    await db.commit()
    await update.message.reply_text(f"{pe('unlock','🔓')} Unlocked: <b>{t}</b>", parse_mode=ParseMode.HTML)

@group_only
async def locks_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    row = await get_group(context.bot_data["db"], update.effective_chat.id)
    locks = json.loads(row["locks"] or "{}") if row else {}
    active = [k for k, v in locks.items() if v]
    text = f"{pe('lock','🔒')} Active locks:\n" + ("\n".join(f"• {x}" for x in active) if active else "None")
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)

# ==================== ANTILINK ====================
@group_only
@admin_only
async def antilink_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        row = await get_group(context.bot_data["db"], update.effective_chat.id)
        mode = row["antilink"] if row else "off"
        await update.message.reply_text(f"Anti-link mode: <b>{mode}</b>\n/antilink off|del|kick|ban|mute", parse_mode=ParseMode.HTML)
        return
    mode = context.args[0].lower()
    if mode not in ("off", "del", "kick", "ban", "mute"):
        await update.message.reply_text("Use: off | del | kick | ban | mute")
        return
    db = context.bot_data["db"]
    await ensure_group(db, update.effective_chat.id, update.effective_chat.title or "")
    await db.execute("UPDATE groups SET antilink=? WHERE chat_id=?", (mode, update.effective_chat.id))
    await db.commit()
    await update.message.reply_text(f"{pe('link','🔗')} Anti-link set to <b>{mode}</b>", parse_mode=ParseMode.HTML)

# ==================== ANTIDELETE ====================
@group_only
@admin_only
async def antidelete_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args or context.args[0].lower() not in ("on", "off"):
        row = await get_group(context.bot_data["db"], update.effective_chat.id)
        state = "ON" if (row and row["antidelete"]) else "OFF"
        await update.message.reply_text(f"Anti-delete: <b>{state}</b>\n/antidelete on|off", parse_mode=ParseMode.HTML)
        return
    val = 1 if context.args[0].lower() == "on" else 0
    db = context.bot_data["db"]
    await ensure_group(db, update.effective_chat.id, update.effective_chat.title or "")
    await db.execute("UPDATE groups SET antidelete=? WHERE chat_id=?", (val, update.effective_chat.id))
    await db.commit()
    await update.message.reply_text(f"{pe('eyes','👀')} Anti-delete {'enabled' if val else 'disabled'}")

# ==================== WELCOME / RULES ====================
@group_only
@admin_only
async def setwelcome_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args and not update.message.reply_to_message:
        await update.message.reply_text("Usage: /setwelcome Your message here\nPlaceholders: {name} {mention} {id} {group}")
        return
    text = " ".join(context.args) if context.args else (update.message.reply_to_message.text or "")
    db = context.bot_data["db"]
    await ensure_group(db, update.effective_chat.id, update.effective_chat.title or "")
    await db.execute("UPDATE groups SET welcome=? WHERE chat_id=?", (text, update.effective_chat.id))
    await db.commit()
    await update.message.reply_text(f"{pe('wave','👋')} Welcome message set.")

@group_only
@admin_only
async def setgoodbye_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = " ".join(context.args) if context.args else ""
    if not text:
        await update.message.reply_text("Usage: /setgoodbye Bye {name}")
        return
    db = context.bot_data["db"]
    await ensure_group(db, update.effective_chat.id, update.effective_chat.title or "")
    await db.execute("UPDATE groups SET goodbye=? WHERE chat_id=?", (text, update.effective_chat.id))
    await db.commit()
    await update.message.reply_text(f"{pe('wave','👋')} Goodbye message set.")

@group_only
@admin_only
async def setrules_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = " ".join(context.args) if context.args else ""
    if not text:
        await update.message.reply_text("Usage: /setrules rules text...")
        return
    db = context.bot_data["db"]
    await ensure_group(db, update.effective_chat.id, update.effective_chat.title or "")
    await db.execute("UPDATE groups SET rules=? WHERE chat_id=?", (text, update.effective_chat.id))
    await db.commit()
    await update.message.reply_text(f"{pe('note','📝')} Rules set.")

@group_only
async def rules_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    row = await get_group(context.bot_data["db"], update.effective_chat.id)
    rules = row["rules"] if row and row["rules"] else "No rules set."
    await update.message.reply_text(f"{pe('note','📝')} <b>Group Rules</b>\n\n{rules}", parse_mode=ParseMode.HTML)

# ==================== NOTES ====================
@group_only
@admin_only
async def save_note_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /save name content  OR reply with /save name")
        return
    name = context.args[0].lower()
    content = " ".join(context.args[1:]) if len(context.args) > 1 else ""
    media_type, media_id = None, None
    if update.message.reply_to_message:
        r = update.message.reply_to_message
        if r.photo:
            media_type, media_id = "photo", r.photo[-1].file_id
        elif r.document:
            media_type, media_id = "document", r.document.file_id
        elif r.sticker:
            media_type, media_id = "sticker", r.sticker.file_id
        elif r.video:
            media_type, media_id = "video", r.video.file_id
        elif r.audio:
            media_type, media_id = "audio", r.audio.file_id
        elif r.voice:
            media_type, media_id = "voice", r.voice.file_id
        if r.text or r.caption:
            content = r.text or r.caption
    if not content and not media_id:
        await update.message.reply_text("Nothing to save.")
        return
    db = context.bot_data["db"]
    await db.execute(
        "INSERT OR REPLACE INTO notes (chat_id, name, content, media_type, media_id) VALUES (?,?,?,?,?)",
        (update.effective_chat.id, name, content or "", media_type, media_id)
    )
    await db.commit()
    await update.message.reply_text(f"{pe('check','✅')} Note <b>#{name}</b> saved.", parse_mode=ParseMode.HTML)

@group_only
async def get_note_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        return
    name = context.args[0].lower().lstrip("#")
    db = context.bot_data["db"]
    async with db.execute(
        "SELECT * FROM notes WHERE chat_id=? AND name=?",
        (update.effective_chat.id, name)
    ) as cur:
        row = await cur.fetchone()
    if not row:
        await update.message.reply_text("Note not found.")
        return
    if row["media_type"] == "photo":
        await update.message.reply_photo(row["media_id"], caption=row["content"] or None)
    elif row["media_type"] == "sticker":
        await update.message.reply_sticker(row["media_id"])
    elif row["media_type"] == "document":
        await update.message.reply_document(row["media_id"], caption=row["content"] or None)
    elif row["media_type"] == "video":
        await update.message.reply_video(row["media_id"], caption=row["content"] or None)
    elif row["media_type"] == "audio":
        await update.message.reply_audio(row["media_id"], caption=row["content"] or None)
    elif row["media_type"] == "voice":
        await update.message.reply_voice(row["media_id"])
    else:
        await update.message.reply_text(row["content"] or "")

@group_only
async def notes_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = context.bot_data["db"]
    async with db.execute("SELECT name FROM notes WHERE chat_id=?", (update.effective_chat.id,)) as cur:
        rows = await cur.fetchall()
    if not rows:
        await update.message.reply_text("No notes.")
        return
    names = ", ".join(f"#{r['name']}" for r in rows)
    await update.message.reply_text(f"{pe('note','📝')} Notes:\n{names}", parse_mode=ParseMode.HTML)

@group_only
@admin_only
async def clear_note_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        return
    name = context.args[0].lower().lstrip("#")
    await context.bot_data["db"].execute(
        "DELETE FROM notes WHERE chat_id=? AND name=?",
        (update.effective_chat.id, name)
    )
    await context.bot_data["db"].commit()
    await update.message.reply_text(f"Deleted note #{name}")

# ==================== INFO ====================
async def id_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    text = f"User ID: <code>{user.id}</code>\nChat ID: <code>{chat.id}</code>"
    if update.message.reply_to_message:
        text += f"\nReplied user: <code>{update.message.reply_to_message.from_user.id}</code>"
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)

@group_only
async def adminlist_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    admins = await context.bot.get_chat_administrators(update.effective_chat.id)
    lines = [f"{pe('crown','👑')} <b>Admins</b>\n"]
    for a in admins:
        u = a.user
        lines.append(f"• {u.mention_html()} (<code>{u.id}</code>)")
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)

# ==================== OWNER ====================
@owner_only
async def owner_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        f"{pe('crown','👑')} <b>Owner Panel</b>\n\n"
        f"/stats — bot stats\n"
        f"/broadcast — broadcast message\n"
        f"/addsudo /delsudo /sudolist\n"
        f"/emojitoggle — on/off premium emoji\n"
        f"/setemo KEY EMOJI_ID FALLBACK\n"
        f"/ping /uptime /version"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)

@owner_only
async def stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = context.bot_data["db"]
    async with db.execute("SELECT COUNT(*) as c FROM users") as cur:
        users = (await cur.fetchone())["c"]
    async with db.execute("SELECT COUNT(*) as c FROM groups") as cur:
        groups = (await cur.fetchone())["c"]
    await update.message.reply_text(
        f"{pe('chart','📊')} <b>Stats</b>\nUsers: {users}\nGroups: {groups}\nVersion: {VERSION}",
        parse_mode=ParseMode.HTML
    )

@owner_only
async def broadcast_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args and not update.message.reply_to_message:
        await update.message.reply_text("Usage: /broadcast message  or reply")
        return
    text = " ".join(context.args) if context.args else (update.message.reply_to_message.text or "")
    db = context.bot_data["db"]
    async with db.execute("SELECT user_id FROM users WHERE is_banned=0") as cur:
        rows = await cur.fetchall()
    ok = fail = 0
    status = await update.message.reply_text(f"Broadcasting to {len(rows)} users...")
    for r in rows:
        try:
            await context.bot.send_message(r["user_id"], text, parse_mode=ParseMode.HTML)
            ok += 1
        except Exception:
            fail += 1
        await asyncio.sleep(0.05)
    await status.edit_text(f"Done. OK: {ok} | Fail: {fail}")

@owner_only
async def addsudo_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /addsudo USER_ID")
        return
    uid = int(context.args[0])
    await add_sudo(context.bot_data["db"], uid)
    await update.message.reply_text(f"{pe('check','✅')} Sudo added: {uid}", parse_mode=ParseMode.HTML)

@owner_only
async def delsudo_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        return
    uid = int(context.args[0])
    await del_sudo(context.bot_data["db"], uid)
    await update.message.reply_text(f"Removed sudo: {uid}")

@owner_only
async def sudolist_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sudos = await list_sudos(context.bot_data["db"])
    await update.message.reply_text("Sudos:\n" + ("\n".join(str(s) for s in sudos) or "None"))

@owner_only
async def emojitoggle_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    set_enabled(not is_enabled())
    await set_global(context.bot_data["db"], "premium_emoji", "1" if is_enabled() else "0")
    await update.message.reply_text(f"Premium emoji: {'ON' if is_enabled() else 'OFF'}")

@owner_only
async def setemo_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /setemo KEY EMOJI_ID [FALLBACK]\nExample: /setemo fire 5289722755871162900 🔥")
        return
    key = context.args[0].lower()
    eid = context.args[1]
    fb = context.args[2] if len(context.args) > 2 else "⭐"
    set_emoji(key, eid, fb)
    await update.message.reply_text(f"Set {key} → {eid} ({fb})")

@owner_only
async def ping_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"{pe('zap','⚡')} Pong!", parse_mode=ParseMode.HTML)

async def version_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"{BOT_NAME} v{VERSION}")

# ==================== MESSAGE HANDLERS ====================
async def on_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.new_chat_members:
        return
    db = context.bot_data["db"]
    chat = update.effective_chat
    await ensure_group(db, chat.id, chat.title or "")
    row = await get_group(db, chat.id)
    welcome = row["welcome"] if row and row["welcome"] else None
    for m in update.message.new_chat_members:
        if m.id == context.bot.id:
            await update.message.reply_text(f"{pe('wave','👋')} Thanks for adding me! Promote me as admin for full power.")
            continue
        if welcome:
            msg = welcome.format(
                name=m.first_name or "User",
                mention=m.mention_html(),
                id=m.id,
                group=chat.title or ""
            )
            try:
                await update.message.reply_text(msg, parse_mode=ParseMode.HTML)
            except Exception:
                await update.message.reply_text(msg)

async def on_left_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.left_chat_member:
        return
    db = context.bot_data["db"]
    row = await get_group(db, update.effective_chat.id)
    goodbye = row["goodbye"] if row and row["goodbye"] else None
    if goodbye:
        m = update.message.left_chat_member
        msg = goodbye.format(name=m.first_name or "User", mention=m.mention_html(), id=m.id)
        try:
            await update.message.reply_text(msg, parse_mode=ParseMode.HTML)
        except Exception:
            pass

async def message_guard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Anti-link, locks, flood, antidelete cache, force-join, fed-ban, filters"""
    if not update.message or update.effective_chat.type == ChatType.PRIVATE:
        return
    msg = update.message
    user = msg.from_user
    if not user or user.is_bot:
        return

    # Federation ban check
    if await check_fed_ban(update, context):
        return

    # Force join check
    if await check_force_join(update, context):
        return

    if await is_group_admin(update, context, user.id):
        # still allow filters for everyone including admins
        await check_filters(update, context)
        return  # admins bypass locks/antilink

    db = context.bot_data["db"]
    chat_id = update.effective_chat.id
    await ensure_group(db, chat_id, update.effective_chat.title or "")
    row = await get_group(db, chat_id)
    if not row:
        return

    # --- Anti-delete cache (store recent messages) ---
    if row["antidelete"]:
        try:
            data = {
                "from_id": user.id,
                "from_name": user.full_name,
                "text": msg.text or msg.caption or "",
                "type": "text",
                "file_id": None,
            }
            if msg.photo:
                data["type"] = "photo"
                data["file_id"] = msg.photo[-1].file_id
            elif msg.sticker:
                data["type"] = "sticker"
                data["file_id"] = msg.sticker.file_id
            elif msg.document:
                data["type"] = "document"
                data["file_id"] = msg.document.file_id
            elif msg.video:
                data["type"] = "video"
                data["file_id"] = msg.video.file_id
            elif msg.audio:
                data["type"] = "audio"
                data["file_id"] = msg.audio.file_id
            elif msg.voice:
                data["type"] = "voice"
                data["file_id"] = msg.voice.file_id
            elif msg.animation:
                data["type"] = "animation"
                data["file_id"] = msg.animation.file_id
            await db.execute(
                "INSERT OR REPLACE INTO antidelete_cache (chat_id, message_id, data) VALUES (?,?,?)",
                (chat_id, msg.message_id, json.dumps(data))
            )
            await db.commit()
        except Exception:
            pass

    # --- Anti-link ---
    antilink = (row["antilink"] or "off") if row else "off"
    text_check = msg.text or msg.caption or ""
    # also detect link previews / entities
    has_url_entity = False
    if msg.entities:
        for ent in msg.entities:
            if ent.type in ("url", "text_link"):
                has_url_entity = True
                break
    if msg.caption_entities:
        for ent in msg.caption_entities:
            if ent.type in ("url", "text_link"):
                has_url_entity = True
                break
    if antilink != "off" and (has_link(text_check) or has_url_entity):
        try:
            await msg.delete()
        except Exception as e:
            log.warning(f"antilink delete fail: {e}")
        action_note = ""
        if antilink == "kick":
            try:
                await context.bot.ban_chat_member(chat_id, user.id)
                await context.bot.unban_chat_member(chat_id, user.id)
                action_note = " + kicked"
            except Exception:
                pass
        elif antilink == "ban":
            try:
                await context.bot.ban_chat_member(chat_id, user.id)
                action_note = " + banned"
            except Exception:
                pass
        elif antilink == "mute":
            try:
                await context.bot.restrict_chat_member(
                    chat_id, user.id, permissions=ChatPermissions(can_send_messages=False)
                )
                action_note = " + muted"
            except Exception:
                pass
        try:
            warn = await context.bot.send_message(
                chat_id,
                f"🔗 Link removed from {user.mention_html()}{action_note}",
                parse_mode=ParseMode.HTML
            )
            # auto delete warning after 5s
            
        except Exception:
            pass
        return

    # --- Locks ---
    locks = json.loads(row["locks"] or "{}")
    violated = False
    if locks.get("text") and msg.text:
        violated = True
    if locks.get("url") and msg.text and has_link(msg.text):
        violated = True
    if locks.get("photo") and msg.photo:
        violated = True
    if locks.get("video") and msg.video:
        violated = True
    if locks.get("audio") and (msg.audio or msg.voice):
        violated = True
    if locks.get("document") and msg.document:
        violated = True
    if locks.get("sticker") and msg.sticker:
        violated = True
    if locks.get("gif") and msg.animation:
        violated = True
    if locks.get("forward") and msg.forward_origin:
        violated = True
    if locks.get("media") and (msg.photo or msg.video or msg.audio or msg.document or msg.sticker or msg.animation):
        violated = True
    if locks.get("command") and msg.text and msg.text.startswith("/"):
        violated = True
    if locks.get("all"):
        violated = True

    if violated:
        try:
            await msg.delete()
        except Exception:
            pass
        return

    # --- Filters ---
    await check_filters(update, context)

    # --- Note trigger (#name) ---
    if msg.text and msg.text.startswith("#"):
        name = msg.text[1:].split()[0].lower()
        async with db.execute(
            "SELECT * FROM notes WHERE chat_id=? AND name=?", (chat_id, name)
        ) as cur:
            note = await cur.fetchone()
        if note:
            context.args = [name]
            await get_note_cmd(update, context)

async def on_deleted_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Resend deleted messages when antidelete is on (via chat_member or service — limited).
    Telegram Bot API does not give full deleted message content for all cases.
    We use our cache from message_guard.
    """
    # Bot API doesn't push "message deleted" events with content.
    # Anti-delete works by caching messages as they arrive; a separate
    # /checkdelete or periodic cleanup can surface them.
    # Full real-time resend requires MTProto userbot; here we support cache export.
    pass

# ==================== MAIN ====================
async def post_init(app: Application):
    db = await get_db()
    app.bot_data["db"] = db
    # seed owner
    for oid in OWNER_IDS:
        await db.execute("INSERT OR IGNORE INTO owners (user_id) VALUES (?)", (oid,))
    await db.commit()
    pe_state = await get_global(db, "premium_emoji", "0")
    set_enabled(pe_state == "1")
    log.info(f"{BOT_NAME} v{VERSION} ready | premium emoji={is_enabled()}")

def main():
    import asyncio
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            raise RuntimeError
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    # Commands
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("ban", ban_cmd))
    app.add_handler(CommandHandler("tban", tban_cmd))
    app.add_handler(CommandHandler("unban", unban_cmd))
    app.add_handler(CommandHandler("kick", kick_cmd))
    app.add_handler(CommandHandler("mute", mute_cmd))
    app.add_handler(CommandHandler("tmute", tmute_cmd))
    app.add_handler(CommandHandler("unmute", unmute_cmd))
    app.add_handler(CommandHandler("promote", promote_cmd))
    app.add_handler(CommandHandler("demote", demote_cmd))
    app.add_handler(CommandHandler("panel", panel_cmd))
    app.add_handler(CommandHandler("menu", panel_cmd))
    app.add_handler(CallbackQueryHandler(panel_callback, pattern=r"^help_"))
    app.add_handler(CommandHandler("warn", warn_cmd))
    app.add_handler(CommandHandler("unwarn", unwarn_cmd))
    app.add_handler(CommandHandler("resetwarns", unwarn_cmd))
    app.add_handler(CommandHandler("warns", warns_cmd))
    app.add_handler(CommandHandler("lock", lock_cmd))
    app.add_handler(CommandHandler("unlock", unlock_cmd))
    app.add_handler(CommandHandler("locks", locks_cmd))
    app.add_handler(CommandHandler("antilink", antilink_cmd))
    app.add_handler(CommandHandler("antidelete", antidelete_cmd))
    app.add_handler(CommandHandler("setwelcome", setwelcome_cmd))
    app.add_handler(CommandHandler("setgoodbye", setgoodbye_cmd))
    app.add_handler(CommandHandler("setrules", setrules_cmd))
    app.add_handler(CommandHandler("rules", rules_cmd))
    app.add_handler(CommandHandler("save", save_note_cmd))
    app.add_handler(CommandHandler("get", get_note_cmd))
    app.add_handler(CommandHandler("notes", notes_cmd))
    app.add_handler(CommandHandler("clear", clear_note_cmd))
    app.add_handler(CommandHandler("id", id_cmd))
    app.add_handler(CommandHandler("adminlist", adminlist_cmd))
    app.add_handler(CommandHandler("owner", owner_cmd))
    app.add_handler(CommandHandler("stats", stats_cmd))
    app.add_handler(CommandHandler("broadcast", broadcast_cmd))
    app.add_handler(CommandHandler("addsudo", addsudo_cmd))
    app.add_handler(CommandHandler("delsudo", delsudo_cmd))
    app.add_handler(CommandHandler("sudolist", sudolist_cmd))
    app.add_handler(CommandHandler("emojitoggle", emojitoggle_cmd))
    app.add_handler(CommandHandler("setemo", setemo_cmd))
    app.add_handler(CommandHandler("ping", ping_cmd))
    app.add_handler(CommandHandler("version", version_cmd))

    # Filters
    app.add_handler(CommandHandler("filter", filter_cmd))
    app.add_handler(CommandHandler("stop", stop_filter_cmd))
    app.add_handler(CommandHandler("filters", filters_list_cmd))

    # Force join
    app.add_handler(CommandHandler("forcejoin", forcejoin_cmd))
    app.add_handler(CallbackQueryHandler(fj_callback, pattern=r"^fj_check:"))

    # Federation
    app.add_handler(CommandHandler("newfed", newfed_cmd))
    app.add_handler(CommandHandler("joinfed", joinfed_cmd))
    app.add_handler(CommandHandler("leavefed", leavefed_cmd))
    app.add_handler(CommandHandler("fedban", fedban_cmd))
    app.add_handler(CommandHandler("fedunban", fedunban_cmd))
    app.add_handler(CommandHandler("fedinfo", fedinfo_cmd))

    # Owner extra
    app.add_handler(CommandHandler("backup", backup_cmd))
    app.add_handler(CommandHandler("maintenance", maintenance_cmd))
    app.add_handler(CommandHandler("uptime", uptime_cmd))
    app.add_handler(CommandHandler("health", health_cmd))
    app.add_handler(CommandHandler("gbroadcast", gbroadcast_cmd))
    app.add_handler(CommandHandler("banuser", banuser_bot_cmd))
    app.add_handler(CommandHandler("unbanuser", unbanuser_bot_cmd))

    # Messages
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, on_new_member))
    app.add_handler(MessageHandler(filters.StatusUpdate.LEFT_CHAT_MEMBER, on_left_member))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND & filters.ChatType.GROUPS, message_guard))

    log.info("Starting Dr Aura...")
    app.run_polling(drop_pending_updates=True, close_loop=False)

if __name__ == "__main__":
    main()
