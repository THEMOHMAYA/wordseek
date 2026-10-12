import json
from telegram import Update
from telegram.ext import ContextTypes
from sqlalchemy import select, delete, update

from database.db import get_db
from database.models import ChatGameTopic
from utils.guards import run_guards, admin_only_guards

VALID_LENGTHS = [4, 5, 6]

async def set_game_topic_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    msg = update.effective_message
    if not chat or not msg:
        return

    if not getattr(chat, "is_forum", False):
        await msg.reply_text("This command can only be used in forum groups.")
        return

    guard = await run_guards(update, context, admin_only_guards)
    if not guard.ok:
        await msg.reply_text(guard.message)
        return

    topic_id = str(msg.message_thread_id) if msg.message_thread_id else "general"
    chat_id = str(chat.id)

    async with get_db() as db:
        existing = (await db.execute(
            select(ChatGameTopic).where(
                ChatGameTopic.chat_id == chat_id,
                ChatGameTopic.topic_id == topic_id
            )
        )).scalar_one_or_none()

        if existing:
            await msg.reply_text("Game has already been set for this topic.\nUse /unsetgametopic to unset it first.")
            return

        db.add(ChatGameTopic(
            chat_id=chat_id,
            topic_id=topic_id,
            allowed_lengths_json="[4, 5, 6]"
        ))

    bot_username = context.bot.username or "WordSeekBot"
    await msg.reply_text(f"@{bot_username} will now use this topic for the game.")

async def unset_game_topic_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    msg = update.effective_message
    if not chat or not msg:
        return

    if not getattr(chat, "is_forum", False):
        await msg.reply_text("This command can only be used in forum groups.")
        return

    guard = await run_guards(update, context, admin_only_guards)
    if not guard.ok:
        await msg.reply_text(guard.message)
        return

    topic_id = str(msg.message_thread_id) if msg.message_thread_id else "general"
    chat_id = str(chat.id)

    async with get_db() as db:
        stmt = delete(ChatGameTopic).where(
            ChatGameTopic.chat_id == chat_id,
            ChatGameTopic.topic_id == topic_id
        )
        res = await db.execute(stmt)
        if res.rowcount == 0:
            await msg.reply_text("This topic was not set as a game topic.")
            return

    bot_username = context.bot.username or "WordSeekBot"
    await msg.reply_text(f"@{bot_username} will no longer restrict games to this topic.")

async def allow_only_len_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    msg = update.effective_message
    if not chat or not msg:
        return

    if not getattr(chat, "is_forum", False):
        await msg.reply_text("This command can only be used in forum groups.")
        return

    guard = await run_guards(update, context, admin_only_guards)
    if not guard.ok:
        await msg.reply_text(guard.message)
        return

    topic_id = str(msg.message_thread_id) if msg.message_thread_id else "general"
    chat_id = str(chat.id)
    args = context.args or []

    if not args:
        await msg.reply_text("Usage: /allowonlylen 5 4 6")
        return

    lengths = [int(x) for x in args if x.isdigit() and int(x) in VALID_LENGTHS]
    if not lengths:
        await msg.reply_text("Allowed lengths are only: 4, 5, 6")
        return

    async with get_db() as db:
        existing = (await db.execute(
            select(ChatGameTopic).where(
                ChatGameTopic.chat_id == chat_id,
                ChatGameTopic.topic_id == topic_id
            )
        )).scalar_one_or_none()

        if not existing:
            await msg.reply_text("This topic is not set for the game.\nUse /setgametopic first.")
            return

        existing.allowed_lengths = lengths

    await msg.reply_text(
        f"Allowed word lengths updated.\nDefault length: {lengths[0]}\nAllowed: {', '.join(map(str, lengths))}"
    )

async def recreate_topic_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    msg = update.effective_message
    if not chat or not msg:
        return

    if not getattr(chat, "is_forum", False):
        await msg.reply_text("This command can only be used in forum groups.")
        return

    guard = await run_guards(update, context, admin_only_guards)
    if not guard.ok:
        await msg.reply_text(guard.message)
        return

    if not msg.message_thread_id:
        await msg.reply_text("General topics can't expire. So, you don't need to use this.")
        return

    topic_id = str(msg.message_thread_id)
    chat_id = str(chat.id)
    args = context.args or []
    action = args[0].lower() if args else ""

    if action not in ["on", "off"]:
        await msg.reply_text("Please specify 'on' or 'off'.\nUsage: /recreatetopic on or /recreatetopic off")
        return

    should_recreate = (action == "on")

    async with get_db() as db:
        existing = (await db.execute(
            select(ChatGameTopic).where(
                ChatGameTopic.chat_id == chat_id,
                ChatGameTopic.topic_id == topic_id
            )
        )).scalar_one_or_none()

        if not existing:
            await msg.reply_text("No game topic set for this topic.\nUse /setgametopic first.")
            return

        existing.should_recreate_on_expire = should_recreate

    await msg.reply_text(f"Topic recreation on expire has been turned {action.upper()}.")
