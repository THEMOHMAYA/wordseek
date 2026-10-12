import json
import time
import asyncio
import logging
from telegram import Update
from telegram.ext import ContextTypes
from sqlalchemy import select, delete

from config.settings import settings
from database.db import get_db
from database.models import BroadcastChat
from utils.cache import cache

logger = logging.getLogger(__name__)

BROADCAST_KEY = "broadcast:state"
BROADCAST_LOCK_KEY = "broadcast:lock"

def format_duration(ms: float) -> str:
    seconds = int(ms / 1000)
    if seconds < 60:
        return f"{seconds}s"
    minutes = seconds // 60
    rem_sec = seconds % 60
    if minutes < 60:
        return f"{minutes}m {rem_sec}s"
    hours = minutes // 60
    rem_min = minutes % 60
    return f"{hours}h {rem_min}m"

async def save_broadcast_state(state: dict):
    await cache.setex(BROADCAST_KEY, 86400, json.dumps(state))

async def get_broadcast_state() -> dict:
    data = await cache.get(BROADCAST_KEY)
    if not data:
        return None
    try:
        return json.loads(data)
    except Exception:
        return None

async def clear_broadcast_state():
    await cache.delete(BROADCAST_KEY, BROADCAST_LOCK_KEY)

async def perform_broadcast(context: ContextTypes.DEFAULT_TYPE, chats: list, state: dict):
    start_idx = state["currentIndex"]

    for i in range(start_idx, len(chats)):
        # Check if cancelled
        cur_state = await get_broadcast_state()
        if not cur_state:
            break

        chat_id_str = chats[i]

        try:
            target_chat_id = int(chat_id_str)
            await context.bot.copy_message(
                chat_id=target_chat_id,
                from_chat_id=state["fromChatId"],
                message_id=state["messageId"]
            )
            state["successCount"] += 1
        except Exception as e:
            err_str = str(e).lower()
            if "blocked" in err_str or "kicked" in err_str or "chat not found" in err_str or "user is deactivated" in err_str:
                state["blockedCount"] += 1
            else:
                state["unknownErrorCount"] += 1

            # Remove invalid chat in background
            try:
                async with get_db() as db:
                    await db.execute(delete(BroadcastChat).where(BroadcastChat.id == chat_id_str))
                state["deletedCount"] += 1
            except Exception:
                pass

        state["currentIndex"] = i + 1
        await save_broadcast_state(state)

        # Update progress every 25 chats
        if (i + 1) % 25 == 0 or (i + 1) == len(chats):
            elapsed = (time.time() * 1000) - state["startTime"]
            estimated_total = (elapsed / (i + 1)) * len(chats)
            remaining = max(0, estimated_total - elapsed)

            try:
                await context.bot.edit_message_text(
                    chat_id=state["statusChatId"],
                    message_id=state["statusMessageId"],
                    text=(
                        "<blockquote>Broadcast in progress!</blockquote>\n\n"
                        f"Estimated time: <code>{format_duration(remaining)}</code>\n"
                        f"Progress: <code>{state['currentIndex']}/{len(chats)}</code>\n"
                        f"Success: <code>{state['successCount']}</code>\n"
                        f"Blocked: <code>{state['blockedCount']}</code>\n"
                        f"Deleted: <code>{state['deletedCount']}</code>"
                    ),
                    parse_mode="HTML"
                )
            except Exception:
                pass

            await asyncio.sleep(1.0)

    total_time = (time.time() * 1000) - state["startTime"]
    total_failed = state["blockedCount"] + state["unknownErrorCount"]

    try:
        await context.bot.edit_message_text(
            chat_id=state["statusChatId"],
            message_id=state["statusMessageId"],
            text=(
                "<blockquote>Broadcast completed!</blockquote>\n\n"
                f"Completed in: <code>{format_duration(total_time)}</code>\n"
                f"Total Users: <code>{len(chats)}</code>\n"
                f"Success: <code>{state['successCount']}</code>\n"
                f"Blocked: <code>{state['blockedCount']}</code>\n"
                f"Deleted: <code>{state['deletedCount']}</code>\n"
                f"Total Failed: <code>{total_failed}</code>"
            ),
            parse_mode="HTML"
        )
    except Exception:
        pass

    await clear_broadcast_state()

async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    msg = update.effective_message
    if not user or not chat or chat.type != "private" or user.id not in settings.ADMIN_USERS:
        return

    if not msg.reply_to_message:
        await msg.reply_text(
            "<blockquote>No message to broadcast!</blockquote>\n\nPlease reply to the message that you want to broadcast.",
            parse_mode="HTML"
        )
        return

    existing_state = await get_broadcast_state()
    if existing_state:
        await msg.reply_text(
            f"<blockquote>A broadcast is already in progress!</blockquote>\n\n"
            f"Progress: {existing_state['currentIndex']}/{existing_state['totalChats']}\n"
            f"Use /broadcast_cancel to cancel.",
            parse_mode="HTML"
        )
        return

    async with get_db() as db:
        chats_rows = (await db.execute(select(BroadcastChat.id))).scalars().all()

    if not chats_rows:
        await msg.reply_text("Not enough users or chats recorded yet!")
        return

    status_msg = await msg.reply_text(
        f"<blockquote>Broadcasting your message to {len(chats_rows)} members...</blockquote>",
        parse_mode="HTML"
    )

    initial_state = {
        "messageId": msg.reply_to_message.message_id,
        "fromChatId": chat.id,
        "totalChats": len(chats_rows),
        "currentIndex": 0,
        "successCount": 0,
        "blockedCount": 0,
        "deletedCount": 0,
        "unknownErrorCount": 0,
        "startTime": time.time() * 1000,
        "statusMessageId": status_msg.message_id,
        "statusChatId": chat.id
    }

    await save_broadcast_state(initial_state)
    asyncio.create_task(perform_broadcast(context, chats_rows, initial_state))

async def broadcast_cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    msg = update.effective_message
    if not user or not msg or user.id not in settings.ADMIN_USERS:
        return

    state = await get_broadcast_state()
    if not state:
        await msg.reply_text("<blockquote>No broadcast in progress</blockquote>", parse_mode="HTML")
        return

    await clear_broadcast_state()
    await msg.reply_text(f"<blockquote>Broadcast cancelled!</blockquote>\nCompleted: <code>{state['currentIndex']}/{state['totalChats']}</code>", parse_mode="HTML")
