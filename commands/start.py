import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from config.constants import UPDATES_CHANNEL, DISCUSSION_GROUP

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BANNER_PATH = os.path.join(BASE_DIR, "data", "banner.png")

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bot_username = context.bot.username or "WordSeekBot"

    # Deep-link handler when user connects PM for Word Mafia
    if context.args and "mafia" in context.args[0]:
        await update.message.reply_text(
            "🕵️ <b>Word Mafia Access Enabled!</b>\n\n"
            "<blockquote>You're all set! Your private chat is now connected.\n\n"
            "You will now receive your secret role and instructions right here whenever a match begins.\n"
            "Head back to your group and tap <b>[➕ Join Game]</b> to play!</blockquote>",
            parse_mode="HTML"
        )
        return
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Add me to your Group", url=f"https://t.me/{bot_username}?startgroup=true")],
        [
            InlineKeyboardButton("📢 Updates", url=UPDATES_CHANNEL),
            InlineKeyboardButton("💬 Support", url=DISCUSSION_GROUP),
        ],
        [InlineKeyboardButton("❓ Help & Rules", callback_data="help_howto")],
    ])

    caption = (
        "✨ <b>Welcome to WordSeek!</b> 🎮\n"
        "A fast-paced, competitive Wordle game for Telegram groups & private chats.\n\n"
        "<blockquote><b>⚡ Quick Start:</b>\n"
        "• /new — Start a 5-letter game\n"
        "• /new4 or /new6 — Play 4 or 6-letter modes\n"
        "• /mafia — Play Word Mafia (Imposter Mode)\n"
        "• /daily — Play today's Daily Puzzle</blockquote>\n\n"
        "<blockquote><b>👥 Multiplayer Fun:</b>\n"
        "Add me to your group and challenge your friends on the leaderboard!</blockquote>"
    )

    if os.path.exists(BANNER_PATH):
        with open(BANNER_PATH, "rb") as banner:
            await update.message.reply_photo(
                photo=banner,
                caption=caption,
                parse_mode="HTML",
                reply_markup=keyboard
            )
            return

    await update.message.reply_text(
        caption,
        parse_mode="HTML",
        reply_markup=keyboard
    )

