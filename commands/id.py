import html
from datetime import datetime
from telegram import Update
from telegram.ext import ContextTypes
from config.settings import settings
from utils.cache import cache

async def id_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    msg = update.effective_message
    if not chat or not user or not msg:
        return

    if chat.type != "private":
        try:
            member = await context.bot.get_chat_member(chat.id, user.id)
            if member.status not in ["administrator", "creator"] and user.id not in settings.ADMIN_USERS:
                return
        except Exception:
            return

    replied = msg.reply_to_message
    if not replied:
        await msg.reply_text("Please reply to a message to get its information.")
        return

    info = "<b>▸ Message Information</b>\n<blockquote>"
    info += f"<b>Message ID:</b> <code>{replied.message_id}</code>\n"
    info += f"<b>Date:</b> {replied.date.strftime('%Y-%m-%d %H:%M:%S')}"
    info += "</blockquote>\n\n"

    if replied.from_user:
        u = replied.from_user
        info += "<b>▸ User Information</b>\n<blockquote>"
        info += f"<b>User ID:</b> <code>{u.id}</code>\n"
        info += f"<b>First Name:</b> {html.escape(u.first_name)}\n"
        if u.last_name:
            info += f"<b>Last Name:</b> {html.escape(u.last_name)}\n"
        if u.username:
            info += f"<b>Username:</b> @{u.username}\n"
        info += f"<b>Is Bot:</b> {'Yes' if u.is_bot else 'No'}\n"
        if u.is_premium:
            info += "<b>Premium:</b> Yes\n"
        info += "</blockquote>\n\n"

    info += "<b>▸ Chat Information</b>\n<blockquote>"
    info += f"<b>Chat ID:</b> <code>{chat.id}</code>\n"
    info += f"<b>Chat Type:</b> {chat.type}"
    if chat.title:
        info += f"\n<b>Chat Title:</b> {html.escape(chat.title)}"
    if chat.username:
        info += f"\n<b>Chat Username:</b> @{chat.username}"
    info += "</blockquote>\n\n"

    if replied.photo:
        p = replied.photo[-1]
        info += "<b>▸ Photo</b>\n<blockquote>"
        info += f"<b>File ID:</b> <code>{p.file_id}</code>\n"
        info += f"<b>Dimensions:</b> {p.width}x{p.height}\n"
        if p.file_size:
            info += f"<b>File Size:</b> {p.file_size / 1024:.2f} KB"
        info += "</blockquote>\n\n"

    if replied.video:
        v = replied.video
        info += "<b>▸ Video</b>\n<blockquote>"
        info += f"<b>File ID:</b> <code>{v.file_id}</code>\n"
        info += f"<b>Dimensions:</b> {v.width}x{v.height}\n"
        info += f"<b>Duration:</b> {v.duration}s"
        info += "</blockquote>\n\n"

    if replied.document:
        d = replied.document
        info += "<b>▸ Document</b>\n<blockquote>"
        info += f"<b>File ID:</b> <code>{d.file_id}</code>\n"
        if d.file_name:
            info += f"<b>File Name:</b> {html.escape(d.file_name)}\n"
        if d.file_size:
            info += f"<b>File Size:</b> {d.file_size / (1024*1024):.2f} MB"
        info += "</blockquote>\n\n"

    if replied.text:
        info += f"<b>▸ Text Content</b>\n<blockquote><b>Length:</b> {len(replied.text)} characters</blockquote>\n\n"
    elif replied.caption:
        info += f"<b>▸ Caption</b>\n<blockquote><b>Length:</b> {len(replied.caption)} characters</blockquote>\n\n"

    await msg.reply_text(info.strip(), parse_mode="HTML")

async def track_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    msg = update.effective_message
    if not user or not msg or user.id not in settings.ADMIN_USERS:
        return

    args = context.args or []
    if not args:
        await msg.reply_text("Usage: /track <chat_id>")
        return

    target_chat_id = args[0].strip()
    await cache.sadd("tracked_chats", target_chat_id)
    await msg.reply_text(f"Started tracking messages in chat <code>{target_chat_id}</code>", parse_mode="HTML")

async def untrack_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    msg = update.effective_message
    if not user or not msg or user.id not in settings.ADMIN_USERS:
        return

    args = context.args or []
    if not args:
        await msg.reply_text("Usage: /untrack <chat_id>")
        return

    target_chat_id = args[0].strip()
    members = await cache.smembers("tracked_chats")
    if target_chat_id in members:
        members.remove(target_chat_id)
        await cache.delete("tracked_chats")
        if members:
            await cache.sadd("tracked_chats", *members)
        await msg.reply_text(f"Stopped tracking chat <code>{target_chat_id}</code>", parse_mode="HTML")
    else:
        await msg.reply_text("Chat was not being tracked.")

async def tracklist_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    msg = update.effective_message
    if not user or not msg or user.id not in settings.ADMIN_USERS:
        return

    members = await cache.smembers("tracked_chats")
    if not members:
        await msg.reply_text("No chats currently being tracked.")
        return

    list_text = "\n".join([f"• <code>{c}</code>" for c in members])
    await msg.reply_text(f"<b>Tracked Chats:</b>\n{list_text}", parse_mode="HTML")
