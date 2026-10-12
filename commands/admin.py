import html
from telegram import Update
from telegram.ext import ContextTypes
from sqlalchemy import select, delete, update, func

from config.settings import settings
from database.db import get_db
from database.models import User, AuthorizedUser, BannedUser, Leaderboard
from commands.score import resolve_target_user

async def is_chat_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    user = update.effective_user
    chat = update.effective_chat
    if not user or not chat:
        return False
    if chat.type == "private":
        return True
    if user.id in settings.ADMIN_USERS:
        return True
    try:
        member = await context.bot.get_chat_member(chat.id, user.id)
        return member.status in ["administrator", "creator"]
    except Exception:
        return False

async def seek_auth_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    msg = update.effective_message
    if not chat or not user or not msg:
        return

    if not await is_chat_admin(update, context):
        await msg.reply_text("❌ You don't have permission to use this command. Only administrators can manage authorized users.")
        return

    chat_id = str(chat.id)
    args = context.args or []

    if not args:
        # Check if reply to message
        if msg.reply_to_message:
            target_user = await resolve_target_user(update, context, fallback=False)
            if target_user:
                return await _authorize_user(msg, chat_id, str(user.id), target_user)
        await msg.reply_text("Usage:\n• /seekauth @username\n• /seekauth remove @username\n• /seekauth list")
        return

    action = args[0].lower()

    if action == "list":
        async with get_db() as db:
            stmt = (
                select(User.id, User.name, User.username)
                .join(AuthorizedUser, AuthorizedUser.user_id == User.id)
                .where(AuthorizedUser.chat_id == chat_id)
            )
            auth_users = (await db.execute(stmt)).all()

        if not auth_users:
            await msg.reply_text("📋 No authorized users in this chat.")
            return

        lines = []
        for u in auth_users:
            safe_name = html.escape(u.name)
            handle = f" (@{u.username})" if u.username else ""
            lines.append(f'• <a href="tg://user?id={u.id}">{safe_name}</a>{handle}')

        await msg.reply_text(
            f"<b>🔐 Authorized Users for WordSeek Game</b>\n\n" + "\n".join(lines),
            parse_mode="HTML"
        )
        return

    if action == "remove":
        target_id = args[1] if len(args) > 1 else None
        target_user = await resolve_target_user(update, context, target_id, fallback=False)
        if not target_user:
            await msg.reply_text("❌ User not found.")
            return

        async with get_db() as db:
            stmt = delete(AuthorizedUser).where(
                AuthorizedUser.chat_id == chat_id,
                AuthorizedUser.user_id == target_user["id"]
            )
            res = await db.execute(stmt)
            if res.rowcount == 0:
                await msg.reply_text("❌ This user is not authorized.")
                return

        u_name = f"@{target_user['username']} ({target_user['name']})" if target_user["username"] else target_user["name"]
        await msg.reply_text(f"✅ <b>{html.escape(u_name)}</b> is no longer authorized to end the game.", parse_mode="HTML")
        return

    # Authorize user
    target_user = await resolve_target_user(update, context, action, fallback=False)
    if not target_user:
        await msg.reply_text("❌ Could not identify the user. Please mention with @username, provide user ID, or reply to their message.")
        return

    await _authorize_user(msg, chat_id, str(user.id), target_user)

async def _authorize_user(msg, chat_id: str, admin_user_id: str, target_user: dict):
    async with get_db() as db:
        existing = (await db.execute(
            select(AuthorizedUser).where(
                AuthorizedUser.chat_id == chat_id,
                AuthorizedUser.user_id == target_user["id"]
            )
        )).scalar_one_or_none()

        if existing:
            await msg.reply_text(f"⚠️ <b>{html.escape(target_user['name'])}</b> is already authorized to end the game in this chat.", parse_mode="HTML")
            return

        db.add(AuthorizedUser(
            chat_id=chat_id,
            user_id=target_user["id"],
            authorized_by=admin_user_id
        ))

    u_name = f"@{target_user['username']} ({target_user['name']})" if target_user["username"] else target_user["name"]
    await msg.reply_text(f"✅ <b>{html.escape(u_name)}</b> is now authorized to end the game without voting!", parse_mode="HTML")

async def ban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    msg = update.effective_message
    if not user or not msg or user.id not in settings.ADMIN_USERS:
        return

    args = context.args or []
    target_identifier = args[0] if args else None
    target_user = await resolve_target_user(update, context, target_identifier, fallback=False)

    if not target_user:
        await msg.reply_text("Can't find the user")
        return

    async with get_db() as db:
        existing = (await db.execute(
            select(BannedUser).where(BannedUser.user_id == target_user["id"])
        )).scalar_one_or_none()

        if existing:
            await msg.reply_text(f"⚠️ {target_user['name']} is already banned")
            return

        db.add(BannedUser(user_id=target_user["id"]))

    await msg.reply_text(f"Banned {target_user['name']} from the bot")

async def unban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    msg = update.effective_message
    if not user or not msg or user.id not in settings.ADMIN_USERS:
        return

    args = context.args or []
    target_identifier = args[0] if args else None
    target_user = await resolve_target_user(update, context, target_identifier, fallback=False)

    if not target_user:
        await msg.reply_text("Can't find the user")
        return

    async with get_db() as db:
        stmt = delete(BannedUser).where(BannedUser.user_id == target_user["id"])
        res = await db.execute(stmt)
        if res.rowcount == 0:
            await msg.reply_text(f"{target_user['name']} is not banned")
            return

    await msg.reply_text(f"Unbanned {target_user['name']} successfully")

async def transfer_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    msg = update.effective_message
    if not user or not msg or user.id not in settings.ADMIN_USERS:
        return

    args = context.args or []
    if len(args) != 2:
        await msg.reply_text("Usage: /transfer <from_user> <to_user>\nExample: /transfer @user1 @user2\nOr: /transfer 12345 67890")
        return

    from_ident, to_ident = args[0], args[1]

    async def find_user(ident: str):
        clean = ident.lstrip("@")
        async with get_db() as db:
            if clean.isdigit():
                stmt = select(User).where(User.id == clean)
            else:
                stmt = select(User).where(func.lower(User.username) == clean.lower())
            return (await db.execute(stmt)).scalar_one_or_none()

    from_user = await find_user(from_ident)
    to_user = await find_user(to_ident)

    if not from_user:
        await msg.reply_text(f"❌ Source user not found: {from_ident}")
        return
    if not to_user:
        await msg.reply_text(f"❌ Destination user not found: {to_ident}")
        return
    if from_user.id == to_user.id:
        await msg.reply_text("❌ Cannot transfer to the same user")
        return

    async with get_db() as db:
        entries = (await db.execute(
            select(Leaderboard).where(Leaderboard.user_id == from_user.id)
        )).scalars().all()

        if not entries:
            await msg.reply_text(f"ℹ️ {from_user.name} has no leaderboard entries to transfer")
            return

        total_score = sum(e.score for e in entries)
        await db.execute(
            update(Leaderboard).where(Leaderboard.user_id == from_user.id).values(user_id=to_user.id)
        )

    await msg.reply_text(
        f"✅ Successfully transferred leaderboard data:\n\n"
        f"From: {from_user.name} ({from_user.id})\n"
        f"To: {to_user.name} ({to_user.id})\n\n"
        f"Entries transferred: {len(entries)}\n"
        f"Total score transferred: {total_score:,}"
    )
