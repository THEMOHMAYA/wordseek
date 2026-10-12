import re
import json
import random
import logging
import html
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from sqlalchemy import select, delete

from config.settings import settings
from config.constants import MODE_LABELS
from database.db import get_db
from database.models import User, BroadcastChat, Game, Guess, Leaderboard, DailyWord, DailyGuess, UserStat
from services.word_selector import ALL_VALID_WORDS
from services.daily_service import (
    get_current_game_date,
    format_daily_word_details,
    generate_wordle_share_text
)
from services.image_generator import generate_wordle_image
from utils.cache import cache
from utils.fancy_text import to_fancy_text
from utils.guards import run_guards, require_allowed_topic

logger = logging.getLogger(__name__)

WIN_REACTIONS = ["🎉", "🏆", "🤩", "⚡", "🫡", "💯", "🔥", "🦄"]

def get_feedback(guesses: list, solution: str) -> str:
    lines = []
    sol_upper = solution.upper()

    for entry in guesses:
        g_upper = entry.guess.upper()
        sol_count = {}
        for char in sol_upper:
            sol_count[char] = sol_count.get(char, 0) + 1

        result = ["🟥"] * len(g_upper)

        for i in range(len(g_upper)):
            if i < len(sol_upper) and g_upper[i] == sol_upper[i]:
                result[i] = "🟩"
                sol_count[g_upper[i]] -= 1

        for i in range(len(g_upper)):
            if result[i] == "🟥" and sol_count.get(g_upper[i], 0) > 0:
                result[i] = "🟨"
                sol_count[g_upper[i]] -= 1

        feedback = " ".join(result)
        lines.append(f"{feedback} {g_upper}")

    return "\n".join(lines)

async def sync_user_and_chat(update: Update):
    user = update.effective_user
    chat = update.effective_chat
    if not user or not chat:
        return

    user_id = str(user.id)
    chat_id = str(chat.id)

    async with get_db() as db:
        # Sync User
        u = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
        if not u:
            db.add(User(id=user_id, name=user.full_name, username=user.username))
        else:
            u.name = user.full_name
            u.username = user.username

        # Sync BroadcastChat
        b = (await db.execute(select(BroadcastChat).where(BroadcastChat.id == chat_id))).scalar_one_or_none()
        if not b:
            chat_name = chat.title or user.full_name
            db.add(BroadcastChat(id=chat_id, name=chat_name, username=chat.username))

async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    user = update.effective_user
    chat = update.effective_chat
    if not msg or not user or not chat or not msg.text:
        return

    # Auto sync user & chat in database
    await sync_user_and_chat(update)

    text = msg.text.strip().lower()

    # Track messages if chat is being monitored
    tracked_chats = await cache.smembers("tracked_chats")
    if str(chat.id) in tracked_chats and settings.ADMIN_USERS:
        for admin_id in settings.ADMIN_USERS:
            try:
                await context.bot.send_message(
                    chat_id=admin_id,
                    text=f"📡 <b>Tracked [{chat.id}]</b> @{user.username or user.first_name}: {msg.text}",
                    parse_mode="HTML"
                )
            except Exception:
                pass

    # Check if text is a valid 4-6 letter word guess
    if text.startswith("/") or not re.match(r"^[a-z]{4,6}$", text):
        return

    user_id = str(user.id)
    chat_id = str(chat.id)

    # Check if private Daily Wordle is active
    if chat.type == "private":
        daily_session = await cache.get(f"daily_wordle:{user_id}")
        if daily_session:
            try:
                sess_data = json.loads(daily_session)
                today_str = str(get_current_game_date())
                if sess_data.get("date") != today_str:
                    await cache.delete(f"daily_wordle:{user_id}")
                    await msg.reply_text("Your previous game has expired. Please start today's WordSeek with /daily")
                    return
                return await handle_daily_wordle_guess(update, context, text)
            except Exception as e:
                logger.error(f"Daily session parse error: {e}")

    # Check if active Mafia Game in group
    topic_id = str(msg.message_thread_id) if msg.message_thread_id else "general"
    mafia_key = f"mafia:{chat_id}:{topic_id}"
    mafia_raw = await cache.get(mafia_key)
    if mafia_raw:
        try:
            mafia_session = json.loads(mafia_raw)
            if mafia_session.get("status") == "playing":
                from commands.mafia import handle_mafia_guess
                handled = await handle_mafia_guess(update, context, text, mafia_session, mafia_key)
                if handled:
                    return
        except Exception as e:
            logger.error(f"Mafia guess handling error: {e}")

    # Regular Game Handling (Group or Private)
    async with get_db() as db:
        stmt = select(Game).where(Game.active_chat == chat_id, Game.topic_id == topic_id).limit(1)
        res = await db.execute(stmt)
        current_game = res.scalar_one_or_none()

        if not current_game:
            return

        guard = await run_guards(update, context, [require_allowed_topic])
        if not guard.ok:
            return

        word_length = len(current_game.word)
        if len(text) != word_length:
            return

        valid_words = ALL_VALID_WORDS.get(word_length, [])
        if text not in valid_words:
            await msg.reply_text(f"{text} is not a valid {word_length}-letter word.")
            return

        # Check if already guessed in THIS current game only
        dup_stmt = select(Guess).where(
            Guess.game_id == current_game.id,
            Guess.guess == text
        ).limit(1)
        dup = (await db.execute(dup_stmt)).scalar_one_or_none()
        if dup:
            await msg.reply_text("Someone has already guessed your word. Please try another one!")
            return

        # Correct Guess!
        if text == current_game.word.lower():
            guesses_q = select(Guess).where(Guess.game_id == current_game.id)
            all_guesses = (await db.execute(guesses_q)).scalars().all()
            attempts_taken = len(all_guesses) + 1
            score = 30 - len(all_guesses)

            if not user.is_bot:
                db.add(Leaderboard(
                    chat_id=chat_id,
                    user_id=user_id,
                    score=score,
                    word_length=str(word_length)
                ))

            user_mention = f"@{user.username}" if user.username else f'<a href="tg://user?id={user.id}">{html.escape(user.full_name)}</a>'

            resp = (
                "🎉 <b>BULLSEYE! WE HAVE A WINNER!</b> 🏆\n\n"
                f"<blockquote>👤 <b>Guessed by:</b> {user_mention}\n"
                f"🎯 <b>Correct Word:</b> <b>{text.upper()}</b>\n"
                f"🪙 <b>Score:</b> +{score} Points (in {attempts_taken}/30 attempts)</blockquote>\n\n"
                f"<i>🔥 Ready for the next round? Start with /new{word_length}</i>"
            )

            await msg.reply_text(
                resp,
                parse_mode="HTML",
                reply_to_message_id=msg.message_id
            )

            # Random emoji reaction
            try:
                await msg.set_reaction(random.choice(WIN_REACTIONS))
            except Exception:
                pass

            # Explicitly clean up all guesses for this game
            await db.execute(delete(Guess).where(Guess.game_id == current_game.id))
            await db.execute(delete(Game).where(Game.id == current_game.id))
            return

        # Incorrect Guess
        db.add(Guess(
            game_id=current_game.id,
            chat_id=chat_id,
            guess=text
        ))
        await db.flush()

        guesses_q = select(Guess).where(Guess.game_id == current_game.id).order_by(Guess.created_at.asc())
        all_guesses = (await db.execute(guesses_q)).scalars().all()

        if len(all_guesses) >= 30:
            word_ans = current_game.word
            await db.execute(delete(Guess).where(Guess.game_id == current_game.id))
            await db.execute(delete(Game).where(Game.id == current_game.id))

            game_over_msg = (
                "💀 <b>GAME OVER!</b>\n\n"
                "<blockquote>Max attempts (30/30) reached! Nobody could crack the word.\n\n"
                f"🔍 <b>The Secret Word was:</b> <b>{word_ans.upper()}</b></blockquote>\n\n"
                f"<i>Don't give up! Start a fresh game with /new{word_length}</i>"
            )
            await msg.reply_text(game_over_msg, parse_mode="HTML")
            return

        mode_label = MODE_LABELS.get(word_length, f"{word_length}-letter mode")
        feedback_text = get_feedback(all_guesses, current_game.word)
        response_msg = f"<i>{mode_label} · {len(all_guesses)}/30</i>\n\n{to_fancy_text(feedback_text)}"

        await msg.reply_text(response_msg, parse_mode="HTML")

async def handle_daily_wordle_guess(update: Update, context: ContextTypes.DEFAULT_TYPE, guess: str):
    user = update.effective_user
    msg = update.effective_message
    if not user or not msg:
        return

    user_id = str(user.id)
    game_date = get_current_game_date()

    async with get_db() as db:
        daily_stmt = select(DailyWord).where(DailyWord.date == game_date)
        daily_word = (await db.execute(daily_stmt)).scalar_one_or_none()

        if not daily_word:
            await msg.reply_text("Today's WordSeek is not available. Please try again later.")
            return

        valid_words = ALL_VALID_WORDS.get(5, [])
        if guess not in valid_words:
            await msg.reply_text(f"{guess.upper()} is not a valid word.")
            return

        # Check existing guesses
        existing_stmt = select(DailyGuess).where(
            DailyGuess.user_id == user_id,
            DailyGuess.daily_word_id == daily_word.id
        ).order_by(DailyGuess.attempt_number.asc())
        existing_guesses = (await db.execute(existing_stmt)).scalars().all()

        if any(g.guess == guess for g in existing_guesses):
            await msg.reply_text("You've already guessed this word. Try a different one!")
            return

        attempt_num = len(existing_guesses) + 1
        db.add(DailyGuess(
            user_id=user_id,
            daily_word_id=daily_word.id,
            guess=guess,
            attempt_number=attempt_num
        ))
        await db.flush()

        all_guesses = (await db.execute(existing_stmt)).scalars().all()
        guess_words = [g.guess for g in all_guesses]

        # Check Win
        if guess == daily_word.word.lower():
            await cache.delete(f"daily_wordle:{user_id}")

            stat_stmt = select(UserStat).where(UserStat.user_id == user_id)
            stat = (await db.execute(stat_stmt)).scalar_one_or_none()
            if not stat:
                stat = UserStat(user_id=user_id, current_streak=0, highest_streak=0)
                db.add(stat)

            new_streak = 1
            if stat.last_guessed:
                diff_days = (game_date - stat.last_guessed.date()).days
                if diff_days == 1:
                    new_streak = stat.current_streak + 1
                elif diff_days == 0:
                    new_streak = stat.current_streak

            stat.current_streak = new_streak
            stat.highest_streak = max(new_streak, stat.highest_streak)
            stat.last_guessed = datetime.utcnow()

            img_bytes = generate_wordle_image(guess_words, daily_word.word)
            share_text = generate_wordle_share_text(daily_word.day_number, guess_words, daily_word.word)

            share_keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton("📤 Share", switch_inline_query=share_text)
            ]])

            tries_label = "try" if len(guess_words) == 1 else "tries"
            caption = (
                f"🎉 Congratulations! You guessed it in {len(guess_words)} {tries_label}!\n\n"
                f"🔥 Current Streak: {new_streak}\n"
                f"⭐ Highest Streak: {stat.highest_streak}\n\n"
                f"{format_daily_word_details(daily_word)}"
            )

            await msg.reply_photo(
                photo=img_bytes,
                caption=caption,
                parse_mode="HTML",
                reply_markup=share_keyboard
            )
            return

        # Check Loss
        if len(guess_words) >= 6:
            await cache.delete(f"daily_wordle:{user_id}")

            stat_stmt = select(UserStat).where(UserStat.user_id == user_id)
            stat = (await db.execute(stat_stmt)).scalar_one_or_none()
            if stat:
                stat.current_streak = 0
                stat.last_guessed = datetime.utcnow()

            img_bytes = generate_wordle_image(guess_words, daily_word.word)
            share_text = generate_wordle_share_text(daily_word.day_number, guess_words, daily_word.word)

            share_keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton("📤 Share", switch_inline_query=share_text)
            ]])

            caption = (
                f"Game Over! The word was: {daily_word.word.upper()}\n\n"
                f"💔 Streak reset to 0\n\n"
                f"{format_daily_word_details(daily_word)}\n\n"
                f"Come back tomorrow for a new challenge!"
            )

            await msg.reply_photo(
                photo=img_bytes,
                caption=caption,
                parse_mode="HTML",
                reply_markup=share_keyboard
            )
            return

        # Continue Game
        img_bytes = generate_wordle_image(guess_words, daily_word.word)
        attempts_left = 6 - len(guess_words)
        att_label = "attempt" if attempts_left == 1 else "attempts"
        await msg.reply_photo(
            photo=img_bytes,
            caption=f"{attempts_left} {att_label} remaining"
        )
