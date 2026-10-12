from telegram import Update
from telegram.ext import ContextTypes
from config.settings import settings
from utils.keyboards import get_main_help_keyboard

def get_how_to_play_message() -> str:
    tz = settings.TIME_ZONE
    return (
        "<b>▸ How to Play WordSeek</b>\n\n"
        "<blockquote>1. Start a game using /new, /new4, /new5, or /new6\n"
        "2. Guess the hidden word\n"
        "3. After each guess, you'll get color hints:\n"
        "   🟩 Correct letter in the right spot\n"
        "   🟨 Correct letter in the wrong spot\n"
        "   🟥 Letter not in the word\n"
        "4. First person to guess correctly wins!\n"
        "5. Maximum 30 guesses per game</blockquote>\n\n"
        "<b>Word Length Modes:</b>\n"
        "<blockquote>• /new → Start default 5-letter game\n"
        "• /new 4 → Start specific length (4, 5, or 6)\n"
        "• /new4 → Start 4-letter game\n"
        "• /new5 → Start 5-letter game\n"
        "• /new6 → Start 6-letter game</blockquote>\n\n"
        "<b>Basic Commands:</b>\n"
        "• /new - Start a new game (default 5 letters)\n"
        "• /new4 - Start a 4-letter game\n"
        "• /new5 - Start a 5-letter game\n"
        "• /new6 - Start a 6-letter game\n"
        "• /mafia - Start Word Mafia (Imposter Mode in groups)\n"
        "• /end - End current game (voting or admin only)\n"
        "• /help - Show this help menu\n"
        "• /daily - Play Daily WordSeek (private chat only)\n"
        "• /pausedaily - Pause Daily mode and go back to normal games\n\n"
        "<b>🕵️ Word Mafia (Imposter Mode):</b>\n"
        "<blockquote>• Start with /mafia in any group (min 3 players)\n"
        "• Detectives must solve the 5-letter word\n"
        "• 1 secret Imposter knows the word and tries to mislead the group\n"
        "• After the round, vote on who you think the Imposter was!</blockquote>\n\n"
        "<b>Daily Mode (Private Chat Only):</b>\n"
        "<blockquote>• Start a daily game using /daily command\n"
        "• Works like New York Times Wordle: one fixed word per day\n"
        "• You only get 6 guesses per daily puzzle\n"
        f"• A new puzzle unlocks every day at 06:00 in <code>{tz}</code>\n"
        "• You build a streak by solving the daily puzzle without failing\n"
        "• You cannot play normal WordSeek and Daily at the same time:\n"
        "  - If a normal game is running, end it before using /daily\n"
        "  - If Daily is active, use /pausedaily to play normal WordSeek again</blockquote>"
    )

def get_scores_message() -> str:
    return (
        "<b>▸ Leaderboard & Scores</b>\n\n"
        "<b>Quick Examples:</b>\n"
        "<blockquote><code>/leaderboard</code> - Group, today (default 5-letter)\n"
        "<code>/leaderboard 4</code> - 4-letter leaderboard (group, today)\n"
        "<code>/leaderboard global week 6</code> - Global rankings this week (6-letter mode)\n"
        "<code>/leaderboard month</code> - This group's monthly leaderboard\n\n"
        "<code>/score</code> - Your score (group, today, 5-letter by default)\n"
        "<code>/score 6</code> - Your 6-letter stats\n"
        "<code>/score @username global all 4</code> - Full 4-letter global history for a user\n"
        "<code>/score 123456789 month</code> - Monthly stats for a user</blockquote>\n\n"
        "<b>Leaderboard Command</b>\n"
        "<blockquote><b>Syntax:</b> <code>/leaderboard [scope] [period] [length]</code>\n\n"
        "All parameters are optional and can be used in any order.\n\n"
        "<b>Scope:</b>\n"
        "• <code>group</code> (default) - Current group only\n"
        "• <code>global</code> - All groups combined\n\n"
        "<b>Period:</b>\n"
        "• <code>today</code> (default)\n"
        "• <code>week</code>\n"
        "• <code>month</code>\n"
        "• <code>year</code>\n"
        "• <code>all</code>\n\n"
        "<b>Length:</b>\n"
        "• <code>4</code> - 4-letter mode\n"
        "• <code>5</code> - 5-letter mode (default)\n"
        "• <code>6</code> - 6-letter mode</blockquote>\n\n"
        "<b>Score Command</b>\n"
        "<blockquote><b>Syntax:</b> <code>/score [target] [scope] [period] [length]</code>\n\n"
        "All parameters are optional and can be used in any order.\n\n"
        "<b>Target (optional):</b>\n"
        "• Leave empty for your own score\n"
        "• <code>@username</code> - Look up by username\n"
        "• <code>user_id</code> - Look up by Telegram user ID\n\n"
        "<b>Scope, period & length:</b>\n"
        "Same as <code>/leaderboard</code></blockquote>"
    )

def get_group_settings_message() -> str:
    return (
        "<b>▸ Group Settings (Admin Only)</b>\n\n"
        "<b>Authorized Users</b>\n"
        "<blockquote><b>/seekauth</b> – Manage users who can end games without a vote.\n\n"
        "<b>Usage:</b>\n"
        "• <code>/seekauth @username</code> – Authorize a user\n"
        "• <code>/seekauth remove @username</code> – Remove authorization\n"
        "• <code>/seekauth list</code> – List all authorized users\n\n"
        "You can also use a user ID or reply to a message instead of @username.</blockquote>\n\n"
        "<b>Game Topic (Forum Groups)</b>\n"
        "<blockquote><b>/setgametopic</b> – Restrict games to one or more topics\n"
        "Run this command <i>inside the topic</i> where you want games to be played.\n"
        "After setting, the bot will only run games in that topic.\n\n"
        "<b>/unsetgametopic</b> – Remove topic restriction\n"
        "Usage: <code>/unsetgametopic</code>\n"
        "After unsetting, the bot can run games in any topic in the group again.\n\n"
        "<b>/allowonlylen</b> – Restrict allowed word lengths in this topic\n"
        "Usage: <code>/allowonlylen 4</code> or <code>/allowonlylen 5 6</code>\n"
        "Run this inside a game topic.\n\n"
        "<b>/recreatetopic</b> – Auto-recreate topic when it expires\n"
        "Usage: <code>/recreatetopic on</code> or <code>/recreatetopic off</code></blockquote>"
    )

def get_other_commands_message() -> str:
    return (
        "<b>▸ Other Commands</b>\n\n"
        "<blockquote><b>/id</b> - Get message & user information\n"
        "Reply to any message to see:\n"
        "• Message ID and date\n"
        "• User information (Name, ID, Username)\n"
        "• Chat information\n"
        "• Forward information (if forwarded)\n"
        "• Media File IDs\n\n"
        "<b>Only admins can use in case of a group</b></blockquote>"
    )

def get_admin_commands_message() -> str:
    return (
        "<b>▸ Admin Commands (Bot Owner Only)</b>\n\n"
        "<blockquote><b>/ban [user_id]</b>\n"
        "Ban a user from using the bot globally\n\n"
        "<b>/unban [user_id]</b>\n"
        "Unban a previously banned user\n\n"
        "<b>/stats</b>\n"
        "View bot statistics including RAM, CPU, Users and Games count\n\n"
        "<b>/transfer &lt;from_user&gt; &lt;to_user&gt;</b>\n"
        "Transfer scores between users\n\n"
        "<b>/broadcast</b>\n"
        "Broadcast a message to all users & groups (Reply to message)\n\n"
        "<b>/track &lt;chat_id&gt;</b>\n"
        "Start tracking a chat to detect cheaters\n\n"
        "<b>/untrack &lt;chat_id&gt;</b>\n"
        "Stop tracking a chat</blockquote>"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    if not user:
        return

    should_show_admin = (user.id in settings.ADMIN_USERS) and (chat and chat.type == "private")
    keyboard = get_main_help_keyboard(should_show_admin, active="howto")

    await update.message.reply_text(
        get_how_to_play_message(),
        parse_mode="HTML",
        reply_markup=keyboard
    )
