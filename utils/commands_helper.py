from typing import List
from telegram import BotCommand
from telegram.ext import Application

BOT_COMMANDS = [
    BotCommand("start", "Start the bot"),
    BotCommand("help", "Get help and commands list"),
    BotCommand("new", "Start a new WordSeek game"),
    BotCommand("new4", "Start a 4-letter game"),
    BotCommand("new5", "Start a 5-letter game"),
    BotCommand("new6", "Start a 6-letter game"),
    BotCommand("end", "End the current game"),
    BotCommand("mafia", "Play Word Mafia (Imposter mode)"),
    BotCommand("daily", "Play WordSeek of the Day (DM only)"),
    BotCommand("pausedaily", "Pause Daily WordSeek game"),
    BotCommand("leaderboard", "View rankings and leaderboard"),
    BotCommand("score", "View your or user's score"),
    BotCommand("id", "Get message & user details"),
]

async def set_bot_commands(application: Application):
    try:
        await application.bot.set_my_commands(BOT_COMMANDS)
    except Exception as e:
        pass
