import json
import logging
from datetime import datetime
from telegram import Update
from telegram.ext import ContextTypes
from sqlalchemy import select

from database.db import get_db
from database.models import UserStat, DailyGuess, DailyWord
from services.daily_service import ensure_daily_word_exists, get_current_game_date
from services.image_generator import generate_wordle_image
from utils.cache import cache
from utils.guards import run_guards, daily_game_guards

logger = logging.getLogger(__name__)

async def daily_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    msg = update.effective_message
    if not user or not msg:
        return

    try:
        guard = await run_guards(update, context, daily_game_guards)
        if not guard.ok:
            await msg.reply_text(guard.message)
            return

        user_id = str(user.id)
        game_date = get_current_game_date()
        daily_word = await ensure_daily_word_exists(game_date)

        if not daily_word:
            await msg.reply_text("Today's WordSeek is not ready yet due to a server issue. Please try again in a few moments!")
            return

        async with get_db() as db:
            # Ensure UserStat exists
            stat_stmt = select(UserStat).where(UserStat.user_id == user_id)
            stat = (await db.execute(stat_stmt)).scalar_one_or_none()
            if not stat:
                new_stat = UserStat(
                    user_id=user_id,
                    current_streak=0,
                    highest_streak=0,
                    last_guessed=None
                )
                db.add(new_stat)
                await db.flush()

            # Check existing guesses
            guesses_stmt = (
                select(DailyGuess)
                .where(DailyGuess.user_id == user_id, DailyGuess.daily_word_id == daily_word.id)
                .order_by(DailyGuess.attempt_number.asc())
            )
            existing_guesses = (await db.execute(guesses_stmt)).scalars().all()

        if existing_guesses:
            last_guess = existing_guesses[-1]
            if last_guess.guess.lower() == daily_word.word.lower():
                tries_str = "try" if len(existing_guesses) == 1 else "tries"
                await msg.reply_text(
                    f"You've already completed today's WordSeek! You got it in {len(existing_guesses)} {tries_str}. Come back after 6:00 AM tomorrow for a new challenge!"
                )
                return

            if len(existing_guesses) >= 6:
                await msg.reply_text(
                    f"You've already used all 6 attempts for today's WordSeek. The word was: {daily_word.word.upper()}\n\nCome back after 6:00 AM tomorrow for a new challenge!"
                )
                return

        # Store session in cache
        session_data = {
            "dailyWordId": daily_word.id,
            "date": str(game_date),
            "startedAt": datetime.utcnow().isoformat()
        }
        await cache.setex(f"daily_wordle:{user_id}", 86400, json.dumps(session_data))

        attempts_used = len(existing_guesses)
        attempts_left = 6 - attempts_used

        if attempts_used > 0:
            guess_words = [g.guess for g in existing_guesses]
            img_bytes = generate_wordle_image(guess_words, daily_word.word)
            att_word = "attempt" if attempts_left == 1 else "attempts"
            await msg.reply_photo(
                photo=img_bytes,
                caption=f"Welcome back! You have {attempts_left} {att_word} left for today's WordSeek. Keep guessing!"
            )
            return

        await msg.reply_text("🎯 WordSeek of the Day started! Guess the 5-letter word. You have 6 attempts. Good luck!")
    except Exception as e:
        logger.error(f"Error starting daily wordle: {e}")
        await msg.reply_text("Something went wrong. Please try again.")

async def pause_daily_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    msg = update.effective_message
    if not user or not msg:
        return

    try:
        user_id = str(user.id)
        daily_game_data = await cache.get(f"daily_wordle:{user_id}")

        if not daily_game_data:
            await msg.reply_text("You don't have an active WordSeek of the Day game to pause.")
            return

        await cache.delete(f"daily_wordle:{user_id}")
        await msg.reply_text(
            "✅ Your WordSeek of the Day game has been paused. You can now play regular WordSeek.\n\n"
            "To play today's WordSeek again, use /daily (your previous attempts will still count)."
        )
    except Exception as e:
        logger.error(f"Error pausing daily wordle: {e}")
        await msg.reply_text("Something went wrong. Please try again.")
