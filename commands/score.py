from typing import Optional, Dict, Any
from telegram import Update
from telegram.ext import ContextTypes
from sqlalchemy import select, func

from database.db import get_db
from database.models import User
from services.leaderboard_service import (
    get_user_scores,
    get_smart_defaults,
    parse_score_input,
    format_user_score_message,
    format_no_scores_message
)
from utils.guards import run_guards, require_allowed_topic
from utils.keyboards import generate_leaderboard_keyboard

async def resolve_target_user(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    identifier: Optional[str] = None,
    fallback: bool = True
) -> Optional[Dict[str, str]]:
    msg = update.effective_message
    user = update.effective_user

    if msg and msg.reply_to_message and msg.reply_to_message.from_user:
        replied = msg.reply_to_message.from_user
        if not replied.is_bot:
            return {
                "id": str(replied.id),
                "name": replied.full_name,
                "username": replied.username
            }

    if identifier:
        clean_id = identifier.lstrip("@").strip()
        async with get_db() as db:
            if clean_id.isdigit():
                stmt = select(User).where(User.id == clean_id)
            else:
                stmt = select(User).where(func.lower(User.username) == clean_id.lower())
            res = await db.execute(stmt)
            found_user = res.scalar_one_or_none()
            if found_user:
                return {
                    "id": found_user.id,
                    "name": found_user.name,
                    "username": found_user.username
                }

    if fallback and user:
        return {
            "id": str(user.id),
            "name": user.full_name,
            "username": user.username
        }

    return None

async def score_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    parsed = parse_score_input(raw_args)

    target_identifier = parsed["target"]
    target_user = await resolve_target_user(update, context, target_identifier, fallback=True)

    if not target_user:
        await msg.reply_text("User not found.")
        return

    is_own_score = not target_identifier
    target_name = target_user["username"] or target_user["name"]

    smart = await get_smart_defaults(
        user_id=target_user["id"],
        chat_id=chat_id,
        requested_search_key=parsed["searchKey"],
        requested_time_key=parsed["timeKey"],
        requested_word_length=parsed["wordLength"],
        chat_type=chat.type
    )

    search_key = smart["searchKey"]
    time_key = smart["timeKey"]
    word_length = smart["wordLength"]
    has_any_scores = smart["hasAnyScores"]

    keyboard = generate_leaderboard_keyboard(
        search_key=search_key,
        time_key=time_key,
        word_length=word_length,
        callback_prefix=f"score {target_user['id']}"
    )

    user_score = await get_user_scores(
        chat_id=chat_id,
        user_id=target_user["id"],
        search_key=search_key,
        time_key=time_key,
        word_length=word_length
    )

    if not user_score:
        no_scores_text = format_no_scores_message(
            is_own_score=is_own_score,
            user_name=target_name,
            search_key=search_key,
            time_key=time_key,
            was_time_key_explicit=bool(parsed["timeKey"]),
            has_any_scores=has_any_scores
        )
        await msg.reply_text(no_scores_text, reply_markup=keyboard)
        return

    formatted_msg = format_user_score_message(user_score, search_key)
    await msg.reply_text(
        formatted_msg,
        parse_mode="HTML",
        reply_markup=keyboard,
        disable_web_page_preview=True
    )

async def my_score_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if msg:
        await msg.reply_text("Please switch to /score command. It's a replacement for /myscore command.")
