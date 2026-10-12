from telegram import Update
from telegram.ext import ContextTypes
from services.leaderboard_service import (
    get_leaderboard_scores,
    parse_leaderboard_filters,
    format_leaderboard_message
)
from utils.guards import run_guards, require_allowed_topic
from utils.keyboards import generate_leaderboard_keyboard

async def leaderboard_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    msg = update.effective_message
    if not chat or not msg:
        return

    guard = await run_guards(update, context, [require_allowed_topic])
    if not guard.ok:
        await msg.reply_text(guard.message)
        return

    chat_id = str(chat.id)
    raw_args = " ".join(context.args or [])
    default_scope = "global" if chat.type == "private" else "group"

    parsed = parse_leaderboard_filters(raw_args, default_search_key=default_scope, default_time_key="today")
    search_key = parsed["searchKey"]
    time_key = parsed["timeKey"]
    word_length = parsed["wordLength"]

    keyboard = generate_leaderboard_keyboard(search_key, time_key, word_length)
    member_scores = await get_leaderboard_scores(chat_id, search_key, time_key, word_length)

    await msg.reply_text(
        format_leaderboard_message(member_scores, search_key),
        parse_mode="HTML",
        reply_markup=keyboard,
        disable_web_page_preview=True
    )
