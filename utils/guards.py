import json
from typing import Callable, Coroutine, List, Tuple, Any
from telegram import Update
from telegram.ext import ContextTypes
from config.settings import settings
from database.db import get_db
from database.models import ChatGameTopic, Game
from sqlalchemy import select
from utils.cache import cache

class GuardResult:
    def __init__(self, ok: bool, message: str = ""):
        self.ok = ok
        self.message = message

async def require_private_chat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> GuardResult:
    chat = update.effective_chat
    if not chat or chat.type != "private":
        return GuardResult(
            False,
            "WordSeek of the Day can only be played in private chat with the bot. Send me a message directly!"
        )
    return GuardResult(True)

async def require_no_active_daily_game(update: Update, context: ContextTypes.DEFAULT_TYPE) -> GuardResult:
    user = update.effective_user
    if not user:
        return GuardResult(True)
    user_id = str(user.id)
    daily_data = await cache.get(f"daily_wordle:{user_id}")
    if daily_data:
        try:
            parsed = json.loads(daily_data)
            if parsed.get("dailyWordId"):
                return GuardResult(
                    False,
                    "⚠️ You have an active WordSeek of the Day game in your private chat. Please finish or pause it before playing regular WordSeek."
                )
        except Exception:
            pass
    return GuardResult(True)

async def require_no_active_regular_game(update: Update, context: ContextTypes.DEFAULT_TYPE) -> GuardResult:
    user = update.effective_user
    if not user:
        return GuardResult(True)
    user_id = str(user.id)
    async with get_db() as db:
        stmt = select(Game).where(Game.active_chat == user_id).limit(1)
        res = await db.execute(stmt)
        if res.scalar_one_or_none():
            return GuardResult(
                False,
                "⚠️ You have an active regular WordSeek game. Please complete or end that game with /end before starting WordSeek of the Day."
            )
    return GuardResult(True)

async def require_allowed_topic(update: Update, context: ContextTypes.DEFAULT_TYPE) -> GuardResult:
    chat = update.effective_chat
    msg = update.effective_message
    if not chat or not msg or not getattr(chat, "is_forum", False):
        return GuardResult(True)

    chat_id = str(chat.id)
    current_topic_id = str(msg.message_thread_id) if msg.message_thread_id else "general"

    async with get_db() as db:
        stmt = select(ChatGameTopic).where(ChatGameTopic.chat_id == chat_id)
        res = await db.execute(stmt)
        topic_data = res.scalars().all()

        if topic_data:
            topic_ids = [t.topic_id for t in topic_data]
            if current_topic_id not in topic_ids:
                return GuardResult(
                    False,
                    "This topic is not set for the game. Please play the game in the designated topic."
                )
    return GuardResult(True)

async def require_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> GuardResult:
    chat = update.effective_chat
    user = update.effective_user
    if not chat or not user:
        return GuardResult(True)

    if chat.type == "private":
        return GuardResult(True)

    if user.id in settings.ADMIN_USERS:
        return GuardResult(True)

    try:
        member = await context.bot.get_chat_member(chat.id, user.id)
        if member.status in ["administrator", "creator"]:
            return GuardResult(True)
        return GuardResult(False, "Only admins can use this command.")
    except Exception:
        return GuardResult(
            False,
            "⚠️ I couldn't verify admin rights.\n👉 Please make sure I’m an admin in this group."
        )

async def run_guards(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    guards: List[Callable[[Update, ContextTypes.DEFAULT_TYPE], Coroutine[Any, Any, GuardResult]]]
) -> GuardResult:
    for guard in guards:
        result = await guard(update, context)
        if not result.ok:
            return result
    return GuardResult(True)

daily_game_guards = [require_private_chat, require_no_active_regular_game]
regular_game_guards = [require_allowed_topic, require_no_active_daily_game]
admin_only_guards = [require_admin]
