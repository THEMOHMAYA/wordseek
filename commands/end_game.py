import html
import json
import time
from telegram import Update
from telegram.ext import ContextTypes
from sqlalchemy import select, delete

from config.settings import settings
from database.db import get_db
from database.models import Game, Guess, AuthorizedUser
from utils.cache import cache
from utils.guards import run_guards, require_allowed_topic
from utils.keyboards import get_vote_end_keyboard

async def is_user_authorized(user_id: str, chat_id: str) -> bool:
    async with get_db() as db:
        stmt = select(AuthorizedUser).where(
            AuthorizedUser.user_id == user_id,
            AuthorizedUser.chat_id == chat_id
        ).limit(1)
        res = await db.execute(stmt)
        return bool(res.scalar_one_or_none())

async def end_active_game(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: str,
    topic_id: str,
    word: str,
    reason: str
):
    async with get_db() as db:
        # Find games and clean up their guesses
        games_res = await db.execute(select(Game.id).where(Game.active_chat == chat_id, Game.topic_id == topic_id))
        game_ids = games_res.scalars().all()
        for gid in game_ids:
            await db.execute(delete(Guess).where(Guess.game_id == gid))
        await db.execute(delete(Game).where(Game.active_chat == chat_id, Game.topic_id == topic_id))

    word_len = len(word)
    reason_line = f"👤 {reason}\n" if reason else ""
    message_text = (
        "🛑 <b>Game Terminated</b>\n\n"
        f"<blockquote>🔍 <b>The word was:</b> <b>{word.upper()}</b>\n"
        f"{reason_line}</blockquote>\n\n"
        f"<i>Ready for another round? Start with /new{word_len}</i>"
    )

    chat = update.effective_chat
    if chat:
        await context.bot.send_message(
            chat_id=chat.id,
            message_thread_id=int(topic_id) if topic_id.isdigit() else None,
            text=message_text,
            parse_mode="HTML"
        )

async def end_game_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    msg = update.effective_message
    if not user or not chat or not msg:
        return

    guard = await run_guards(update, context, [require_allowed_topic])
    if not guard.ok:
        await msg.reply_text(guard.message)
        return

    topic_id = str(msg.message_thread_id) if msg.message_thread_id else "general"
    chat_id = str(chat.id)
    user_id = str(user.id)

    async with get_db() as db:
        stmt = select(Game).where(Game.active_chat == chat_id, Game.topic_id == topic_id).limit(1)
        res = await db.execute(stmt)
        current_game = res.scalar_one_or_none()

    if not current_game:
        await msg.reply_text("There is no game in progress.")
        return

    is_private = (chat.type == "private")
    is_system_admin = (user.id in settings.ADMIN_USERS)
    is_game_starter = (current_game.started_by == user_id)
    is_authorized = await is_user_authorized(user_id, chat_id)

    is_admin = False
    if not is_private:
        try:
            member = await context.bot.get_chat_member(chat.id, user.id)
            is_admin = (member.status in ["administrator", "creator"])
        except Exception:
            pass

    is_permitted = (is_admin or is_system_admin or is_game_starter or is_authorized or is_private)

    user_name = html.escape(user.full_name)
    user_link = f'<a href="tg://user?id={user.id}">{user_name}</a>'

    if is_permitted:
        if is_private:
            reason = ""
        elif is_game_starter:
            reason = f"<b>Ended by game starter: </b>{user_link}"
        elif is_system_admin:
            reason = f"<b>Ended by system administrator: </b>{user_link}"
        elif is_admin:
            reason = f"<b>Ended by group administrator: </b>{user_link}"
        elif is_authorized:
            reason = f"<b>Ended by authorized user: </b>{user_link}"
        else:
            reason = f"<b>Ended by: </b>{user_link}"

        await end_active_game(update, context, chat_id, topic_id, current_game.word, reason)
        return

    # Voting flow for regular users in groups
    vote_key = f"vote:{chat_id}"
    existing_votes = await cache.get(vote_key)
    if existing_votes:
        await msg.reply_text("⏳ A vote to end the game is already in progress. Please wait for it to complete.")
        return

    vote_data = {
        "voters": [user_id],
        "initiatedAt": time.time(),
        "topicId": topic_id
    }
    await cache.setex(vote_key, 300, json.dumps(vote_data))

    vote_msg = (
        f"<b>🗳️ Vote to End Game</b>\n\n"
        f"{user_link} wants to end the game.\n\n"
        f"<b>Votes needed: 3 total</b>\n"
        f"<b>Current votes: 1/3</b>\n\n"
        f"React with the button below to vote for ending the game."
    )
    keyboard = get_vote_end_keyboard(chat_id, current_votes=1)
    await msg.reply_text(vote_msg, parse_mode="HTML", reply_markup=keyboard)
