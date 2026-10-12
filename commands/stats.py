import os
import sys
import time
import psutil
import platform
from telegram import Update
from telegram.ext import ContextTypes
from sqlalchemy import select, func, distinct

from config.settings import settings
from database.db import get_db
from database.models import User, Leaderboard, BroadcastChat

BOT_START_TIME = time.time()

def format_bytes(b: int) -> str:
    if not b:
        return "0 B"
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if b < 1024.0:
            return f"{b:.2f} {unit}"
        b /= 1024.0
    return f"{b:.2f} PB"

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    msg = update.effective_message
    if not user or not msg:
        return

    if user.id not in settings.ADMIN_USERS:
        return

    uptime_sec = int(time.time() - BOT_START_TIME)
    uptime_hours = uptime_sec // 3600
    uptime_minutes = (uptime_sec % 3600) // 60

    process = psutil.Process(os.getpid())
    process_mem = process.memory_info().rss
    sys_mem = psutil.virtual_memory()
    cpu_count = psutil.cpu_count()
    cpu_percent = psutil.cpu_percent(interval=None)

    async with get_db() as db:
        all_users = (await db.execute(select(func.count(User.id)))).scalar() or 0
        active_players = (await db.execute(
            select(func.count(distinct(Leaderboard.chat_id))).where(Leaderboard.chat_id.notlike("-1%"))
        )).scalar() or 0
        active_groups = (await db.execute(
            select(func.count(distinct(Leaderboard.chat_id))).where(Leaderboard.chat_id.like("-1%"))
        )).scalar() or 0
        total_groups = (await db.execute(
            select(func.count(BroadcastChat.id)).where(BroadcastChat.id.like("-1%"))
        )).scalar() or 0

    stats_msg = (
        "🤖 <b>Bot Statistics</b>\n\n"
        "<blockquote>📊 <b>Bot Overview</b>\n"
        f"├ Total Users: {all_users}\n"
        f"├ Active Players: {active_players}\n"
        f"├ Total Groups: {total_groups}\n"
        f"├ Active Groups: {active_groups}\n"
        f"├ Uptime: {uptime_hours}h {uptime_minutes}m\n"
        f"└ PID: {os.getpid()}</blockquote>\n\n"
        "<blockquote>🧠 <b>Bot Memory</b>\n"
        f"├ RSS: {format_bytes(process_mem)}\n"
        f"└ Memory %: {process.memory_percent():.2f}%</blockquote>\n\n"
        "<blockquote>💻 <b>VPS System</b>\n"
        f"├ OS: {platform.system()} {platform.release()}\n"
        f"├ Architecture: {platform.machine()}\n"
        f"├ CPUs: {cpu_count} Cores\n"
        f"└ Hostname: {platform.node()}</blockquote>\n\n"
        "<blockquote>💾 <b>VPS Memory</b>\n"
        f"├ Total: {format_bytes(sys_mem.total)}\n"
        f"├ Used: {format_bytes(sys_mem.used)} ({sys_mem.percent}%)\n"
        f"├ Free: {format_bytes(sys_mem.free)}\n"
        f"└ Available: {format_bytes(sys_mem.available)}</blockquote>\n\n"
        "<blockquote>📈 <b>Performance</b>\n"
        f"├ Python Version: {platform.python_version()}\n"
        f"├ CPU Usage: {cpu_percent}%\n"
        f"└ Platform: {sys.platform}</blockquote>"
    )

    await msg.reply_text(stats_msg, parse_mode="HTML")
