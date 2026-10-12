import asyncio
import logging
import sys
from datetime import datetime, time as dtime
from zoneinfo import ZoneInfo

from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters
)

from config.settings import settings
from database.db import init_db
from utils.cache import cache
from utils.commands_helper import set_bot_commands
from services.daily_service import ensure_daily_word_exists, get_current_game_date

from commands.start import start_command
from commands.help import help_command
from commands.new_game import (
    new_game_command,
    new4_game_command,
    new5_game_command,
    new6_game_command
)
from commands.end_game import end_game_command
from commands.mafia import mafia_command
from commands.daily import daily_command, pause_daily_command
from commands.leaderboard import leaderboard_command
from commands.score import score_command, my_score_command
from commands.stats import stats_command
from commands.admin import (
    seek_auth_command,
    ban_command,
    unban_command,
    transfer_command
)
from commands.topics import (
    set_game_topic_command,
    unset_game_topic_command,
    allow_only_len_command,
    recreate_topic_command
)
from commands.broadcast import broadcast_command, broadcast_cancel_command
from commands.captcha import captcha_command
from commands.id import (
    id_command,
    track_command,
    untrack_command,
    tracklist_command
)
from handlers.message_handler import handle_text_message
from handlers.callback_handler import handle_callback_query
from handlers.error_handler import error_handler

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger("WordSeek")

async def daily_cron_worker():
    """Background task to ensure daily word exists and rolls over cleanly at 06:00 AM."""
    while True:
        try:
            target_date = get_current_game_date()
            await ensure_daily_word_exists(target_date)
        except Exception as e:
            logger.error(f"Daily cron worker error: {e}")
        await asyncio.sleep(300)  # Check every 5 minutes

async def on_startup(application):
    logger.info("Initializing database...")
    await init_db()

    logger.info("Initializing cache...")
    await cache.initialize()

    logger.info("Ensuring today's Daily Wordle...")
    await ensure_daily_word_exists()

    logger.info("Setting bot commands menu...")
    await set_bot_commands(application)

    # Start background daily worker
    asyncio.create_task(daily_cron_worker())
    logger.info("WordSeek Bot started successfully! 🚀")

def main():
    if not settings.BOT_TOKEN:
        logger.error("❌ BOT_TOKEN is missing! Please set BOT_TOKEN in your .env file.")
        print("\n[ERROR] BOT_TOKEN is missing! Please set your Telegram bot token in .env file.\n")
        sys.exit(1)

    app = ApplicationBuilder().token(settings.BOT_TOKEN).post_init(on_startup).build()

    # Register Command Handlers
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))

    app.add_handler(CommandHandler("new", new_game_command))
    app.add_handler(CommandHandler("new4", new4_game_command))
    app.add_handler(CommandHandler("new5", new5_game_command))
    app.add_handler(CommandHandler("new6", new6_game_command))
    app.add_handler(CommandHandler("startmatch", new_game_command))
    app.add_handler(CommandHandler("end", end_game_command))
    app.add_handler(CommandHandler("mafia", mafia_command))

    app.add_handler(CommandHandler("daily", daily_command))
    app.add_handler(CommandHandler("pausedaily", pause_daily_command))

    app.add_handler(CommandHandler("leaderboard", leaderboard_command))
    app.add_handler(CommandHandler("score", score_command))
    app.add_handler(CommandHandler("myscore", my_score_command))

    app.add_handler(CommandHandler("seekauth", seek_auth_command))
    app.add_handler(CommandHandler("ban", ban_command))
    app.add_handler(CommandHandler("unban", unban_command))
    app.add_handler(CommandHandler("transfer", transfer_command))

    app.add_handler(CommandHandler("setgametopic", set_game_topic_command))
    app.add_handler(CommandHandler("unsetgametopic", unset_game_topic_command))
    app.add_handler(CommandHandler("allowonlylen", allow_only_len_command))
    app.add_handler(CommandHandler("recreatetopic", recreate_topic_command))

    app.add_handler(CommandHandler("broadcast", broadcast_command))
    app.add_handler(CommandHandler("broadcast_cancel", broadcast_cancel_command))
    app.add_handler(CommandHandler("captcha", captcha_command))

    app.add_handler(CommandHandler("id", id_command))
    app.add_handler(CommandHandler("track", track_command))
    app.add_handler(CommandHandler("untrack", untrack_command))
    app.add_handler(CommandHandler("tracklist", tracklist_command))
    app.add_handler(CommandHandler("stats", stats_command))

    # Callback query handler
    app.add_handler(CallbackQueryHandler(handle_callback_query))

    # Text message handler (Guessing engine)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))

    # Error handler
    app.add_error_handler(error_handler)

    print("Starting WordSeek Bot...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
