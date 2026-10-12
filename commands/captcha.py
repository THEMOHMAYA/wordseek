import json
import time
import html
from telegram import Update
from telegram.ext import ContextTypes
from sqlalchemy import select

from config.settings import settings
from config.constants import SLOT_SYMBOLS
from database.db import get_db
from database.models import User
from utils.cache import cache
from utils.keyboards import build_captcha_keyboard

def decode_slot(value: int) -> list:
    n = value - 1
    return [
        SLOT_SYMBOLS[n & 3],
        SLOT_SYMBOLS[(n >> 2) & 3],
        SLOT_SYMBOLS[(n >> 4) & 3],
    ]

def build_captcha_message(mention: str, progress: list, attempts: int, max_attempts: int = 3, status: str = "Waiting for input") -> str:
    filled = list(progress)
    while len(filled) < 3:
        filled.append("⬜")

    return (
        "<blockquote>🎰 <strong>Verification Required</strong></blockquote>\n"
        "<blockquote>"
        f"{mention}, please prove that you are not a robot.\n"
        f"├ Result: {' '.join(filled)}\n"
        f"├ Attempts: {attempts}/{max_attempts}\n"
        f"├ Status: {status}\n"
        "└ Instruction: Select the symbols in the exact order shown above."
        "</blockquote>"
    )

async def captcha_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    msg = update.effective_message
    if not user or not chat or chat.type != "private" or user.id not in settings.ADMIN_USERS:
        return

    args = context.args or []
    if len(args) < 2:
        await msg.reply_text("Usage: /captcha <chat_id> <user_id>")
        return

    target_chat_id, target_user_id = args[0], args[1]
    key = f"captcha:{target_chat_id}:{target_user_id}"

    existing = await cache.get(key)
    if existing:
        sess = json.loads(existing)
        await msg.reply_text(
            f"⚠️ A captcha is already active for this user.\nAttempts: {sess.get('attempts', 0)}/3"
        )
        return

    async with get_db() as db:
        user_row = (await db.execute(select(User).where(User.id == target_user_id))).scalar_one_or_none()

    if user_row and user_row.username:
        mention = f"@{user_row.username}"
    elif user_row:
        mention = f'<a href="tg://user?id={target_user_id}">{html.escape(user_row.name)}</a>'
    else:
        mention = f'<a href="tg://user?id={target_user_id}">User</a>'

    try:
        dice_msg = await context.bot.send_dice(chat_id=int(target_chat_id), emoji="🎰")
        dice_val = dice_msg.dice.value
        answer = decode_slot(dice_val)

        keyboard = build_captcha_keyboard([])
        captcha_msg = await context.bot.send_message(
            chat_id=int(target_chat_id),
            text=build_captcha_message(mention, [], 0, 3),
            parse_mode="HTML",
            reply_markup=keyboard,
            reply_to_message_id=dice_msg.message_id
        )

        session_data = {
            "chatId": target_chat_id,
            "userId": target_user_id,
            "adminId": str(user.id),
            "messageId": captcha_msg.message_id,
            "answer": answer,
            "progress": [],
            "attempts": 0,
            "createdAt": time.time(),
            "name": user_row.name if user_row else "User",
            "username": user_row.username if user_row else None
        }

        await cache.setex(key, 90, json.dumps(session_data))
        await msg.reply_text(f"✅ Captcha sent for {mention}.", parse_mode="HTML")
    except Exception as e:
        await msg.reply_text(f"❌ Failed to send captcha: {e}")
