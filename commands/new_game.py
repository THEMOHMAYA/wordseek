import logging
from typing import Optional
from telegram import Update
from telegram.ext import ContextTypes
from sqlalchemy import select, delete
from sqlalchemy.exc import IntegrityError

from database.db import get_db
from database.models import Game, Guess, ChatGameTopic
from services.word_selector import word_selector
from utils.guards import run_guards, regular_game_guards

logger = logging.getLogger(__name__)
GLOBAL_VALID_LENGTHS = [5, 4, 6]

async def start_game(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    forced_length: Optional[int] = None
):
    user = update.effective_user
    chat = update.effective_chat
    msg = update.effective_message
    if not user or not chat or not msg:
        return

    topic_id = str(msg.message_thread_id) if msg.message_thread_id else "general"
    chat_id = str(chat.id)

    guard = await run_guards(update, context, regular_game_guards)
    if not guard.ok:
        await msg.reply_text(guard.message)
        return

    async with get_db() as db:
        # Check if game already running in this chat + topic
        existing_stmt = select(Game).where(Game.active_chat == chat_id, Game.topic_id == topic_id).limit(1)
        existing_game = (await db.execute(existing_stmt)).scalar_one_or_none()
        if existing_game:
            await msg.reply_text("There is already a game in progress in this chat. Use /end to end the current game.")
            return

        # Check allowed lengths for this topic
        topic_stmt = select(ChatGameTopic).where(
            ChatGameTopic.chat_id == chat_id,
            ChatGameTopic.topic_id == topic_id
        ).limit(1)
        topic_res = await db.execute(topic_stmt)
        topic_settings = topic_res.scalar_one_or_none()

        allowed_lengths = topic_settings.allowed_lengths if topic_settings else GLOBAL_VALID_LENGTHS
        default_length = allowed_lengths[0] if allowed_lengths else 5

        word_length = default_length

        if forced_length is not None:
            if forced_length not in allowed_lengths:
                await msg.reply_text(f"Only these lengths are allowed in this topic: {', '.join(map(str, allowed_lengths))}.")
                return
            word_length = forced_length
        else:
            args = context.args
            if args:
                raw_len = args[0].strip()
                if raw_len.isdigit() and int(raw_len) in GLOBAL_VALID_LENGTHS:
                    parsed_len = int(raw_len)
                    if parsed_len not in allowed_lengths:
                        await msg.reply_text(f"Only these lengths are allowed in this topic: {', '.join(map(str, allowed_lengths))}.")
                        return
                    word_length = parsed_len

        random_word = await word_selector.get_random_word(chat_id, word_length)

        # Ensure no lingering guesses for non-existent game in this chat/topic
        dangling_games = (await db.execute(select(Game.id).where(Game.active_chat == chat_id, Game.topic_id == topic_id))).scalars().all()
        for gid in dangling_games:
            await db.execute(delete(Guess).where(Guess.game_id == gid))

        new_game = Game(
            word=random_word,
            active_chat=chat_id,
            topic_id=topic_id,
            started_by=str(user.id)
        )
        db.add(new_game)
        try:
            await db.flush()
            start_msg = (
                "🎯 <b>Game Started!</b>\n\n"
                f"<blockquote><b>Mode:</b> {word_length}-Letter Wordle\n"
                "<b>Attempts:</b> Max 30 guesses\n"
                "<b>Hints:</b> 🟩 Right Spot • 🟨 Wrong Spot • 🟥 Absent</blockquote>\n\n"
                f"<i>💬 Type any {word_length}-letter word in chat to make a guess...</i>"
            )
            await msg.reply_text(start_msg, parse_mode="HTML")
        except IntegrityError:
            await msg.reply_text("There is already a game in progress in this chat. Use /end to end the current game.")
        except Exception as e:
            logger.error(f"Error starting game: {e}")
            await msg.reply_text("Something went wrong. Please try again.")

async def new_game_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start_game(update, context)

async def new4_game_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start_game(update, context, forced_length=4)

async def new5_game_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start_game(update, context, forced_length=5)

async def new6_game_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start_game(update, context, forced_length=6)
