import json
import html
import random
import logging
from typing import Dict, Any, List, Optional
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from sqlalchemy import select

from config.settings import settings
from config.constants import (
    MAFIA_MIN_PLAYERS,
    MAFIA_MAX_PLAYERS,
    MAFIA_MAX_GUESSES,
    MAFIA_VOTE_TIMEOUT
)
from database.db import get_db
from database.models import Game, Leaderboard
from services.word_selector import word_selector, ALL_VALID_WORDS
from utils.cache import cache
from utils.fancy_text import to_fancy_text
from utils.keyboards import get_mafia_lobby_keyboard, get_mafia_voting_keyboard

logger = logging.getLogger(__name__)

def get_mafia_key(chat_id: str, topic_id: str) -> str:
    return f"mafia:{chat_id}:{topic_id}"

def format_lobby_message(session: Dict[str, Any]) -> str:
    players = session.get("players", [])
    count = len(players)
    host_id = session.get("host_id")

    player_list_lines = []
    for idx, p in enumerate(players, 1):
        name = html.escape(p.get("name", "Player"))
        crown = " 👑" if str(p.get("id")) == str(host_id) else ""
        player_list_lines.append(f"{idx}. <b>{name}</b>{crown}")

    players_text = "\n".join(player_list_lines) if player_list_lines else "<i>No players yet</i>"
    need_more = max(0, MAFIA_MIN_PLAYERS - count)

    status_note = (
        f"<i>Ready to start! (Host can start now)</i>"
        if count >= MAFIA_MIN_PLAYERS
        else f"<i>Waiting for {need_more} more player{'s' if need_more > 1 else ''} to start...</i>"
    )

    return (
        "🕵️ <b>WORD MAFIA: SECRET IMPOSTER LOBBY</b> 🕵️\n\n"
        "<blockquote>Detectives must crack the secret word, while 1 secret Imposter (who knows the word in advance) tries to mislead everyone!</blockquote>\n\n"
        f"<b>👥 Players ({count}/{MAFIA_MAX_PLAYERS}):</b>\n"
        f"{players_text}\n\n"
        f"{status_note}"
    )

async def check_user_can_receive_pm(bot, user_id: int) -> bool:
    try:
        await bot.send_chat_action(chat_id=user_id, action="typing")
        return True
    except Exception:
        return False

async def mafia_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    msg = update.effective_message
    if not chat or not user or not msg:
        return

    if chat.type == "private":
        bot_username = context.bot.username or "WordSeekBot"
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("➕ Add to Group", url=f"https://t.me/{bot_username}?startgroup=true")
        ]])
        await msg.reply_text(
            "🕵️ <b>Word Mafia is a multiplayer game for groups!</b>\n\n"
            "Add me to a group chat to play with your friends.",
            parse_mode="HTML",
            reply_markup=keyboard
        )
        return

    topic_id = str(msg.message_thread_id) if msg.message_thread_id else "general"
    chat_id = str(chat.id)
    key = get_mafia_key(chat_id, topic_id)

    # Check if a standard game is already running
    async with get_db() as db:
        std_game = (await db.execute(
            select(Game).where(Game.active_chat == chat_id, Game.topic_id == topic_id).limit(1)
        )).scalar_one_or_none()
        if std_game:
            await msg.reply_text("There is already a standard game in progress. End it first with /end before starting Mafia.")
            return

    # Check if a mafia game is already active
    existing_session_raw = await cache.get(key)
    if existing_session_raw:
        await msg.reply_text("A Word Mafia match or lobby is already active in this chat. Use the buttons above or cancel the lobby.")
        return

    # Check if host has started the bot in PM
    can_pm = await check_user_can_receive_pm(context.bot, user.id)
    if not can_pm:
        bot_username = context.bot.username or "WordSeekBot"
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("▶️ Start Bot in PM", url=f"https://t.me/{bot_username}?start=mafia")
        ]])
        user_name = html.escape(user.full_name)
        await msg.reply_text(
            f"👋 <b>Hey {user_name}!</b>\n\n"
            "<blockquote>To play <b>Word Mafia</b>, the bot needs to send your secret role and instructions in private messages (PM).\n\n"
            "Please tap the button below to start the bot in PM, then you can create or join the game!</blockquote>",
            parse_mode="HTML",
            reply_markup=keyboard
        )
        return

    session = {
        "chat_id": chat_id,
        "topic_id": topic_id,
        "host_id": str(user.id),
        "status": "lobby",
        "players": [{
            "id": str(user.id),
            "name": user.full_name,
            "username": user.username
        }],
        "imposter_id": None,
        "word": None,
        "guesses": [],
        "votes": {},
        "word_guessed": False
    }

    keyboard = get_mafia_lobby_keyboard(chat_id, topic_id, player_count=1, can_start=False)
    sent_msg = await msg.reply_text(
        format_lobby_message(session),
        parse_mode="HTML",
        reply_markup=keyboard
    )
    session["lobby_msg_id"] = sent_msg.message_id
    await cache.setex(key, 900, json.dumps(session))

async def handle_mafia_join(update: Update, context: ContextTypes.DEFAULT_TYPE, chat_id: str, topic_id: str):
    query = update.callback_query
    user = update.effective_user
    if not query or not user:
        return

    key = get_mafia_key(chat_id, topic_id)
    raw = await cache.get(key)
    if not raw:
        await query.answer("This lobby has expired.", show_alert=True)
        return

    session = json.loads(raw)
    if session.get("status") != "lobby":
        await query.answer("Game has already started!", show_alert=True)
        return

    players = session.get("players", [])
    user_id_str = str(user.id)

    if any(p["id"] == user_id_str for p in players):
        await query.answer("You are already in this lobby! 👍")
        return

    if len(players) >= MAFIA_MAX_PLAYERS:
        await query.answer(f"Lobby is full! (Max {MAFIA_MAX_PLAYERS} players)", show_alert=True)
        return

    # Verify user can receive PM before joining
    can_pm = await check_user_can_receive_pm(context.bot, user.id)
    if not can_pm:
        bot_username = context.bot.username or "WordSeekBot"
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("▶️ Start Bot in PM", url=f"https://t.me/{bot_username}?start=mafia")
        ]])
        user_name = html.escape(user.full_name)
        user_mention = f'<a href="tg://user?id={user.id}">{user_name}</a>'
        
        await query.answer("⚠️ Please start the bot in PM first so we can send your secret role!", show_alert=True)
        try:
            await context.bot.send_message(
                chat_id=int(chat_id),
                message_thread_id=int(topic_id) if topic_id.isdigit() else None,
                text=(
                    f"👋 <b>Hey {user_mention}!</b>\n\n"
                    "<blockquote>To receive your secret role for <b>Word Mafia</b>, please start the bot in private messages first!</blockquote>"
                ),
                parse_mode="HTML",
                reply_markup=keyboard
            )
        except Exception:
            pass
        return

    players.append({
        "id": user_id_str,
        "name": user.full_name,
        "username": user.username
    })
    session["players"] = players
    await cache.set(key, json.dumps(session), keep_ttl=True)

    can_start = len(players) >= MAFIA_MIN_PLAYERS
    keyboard = get_mafia_lobby_keyboard(chat_id, topic_id, len(players), can_start=can_start)

    try:
        await query.edit_message_text(
            format_lobby_message(session),
            parse_mode="HTML",
            reply_markup=keyboard
        )
    except Exception:
        pass
    await query.answer("You joined the lobby! 🎯")

async def handle_mafia_leave(update: Update, context: ContextTypes.DEFAULT_TYPE, chat_id: str, topic_id: str):
    query = update.callback_query
    user = update.effective_user
    if not query or not user:
        return

    key = get_mafia_key(chat_id, topic_id)
    raw = await cache.get(key)
    if not raw:
        await query.answer("Lobby expired.")
        return

    session = json.loads(raw)
    if session.get("status") != "lobby":
        await query.answer("Game already started.")
        return

    user_id_str = str(user.id)
    players = session.get("players", [])

    if not any(p["id"] == user_id_str for p in players):
        await query.answer("You are not in this lobby.")
        return

    # If host leaves and is only player -> cancel
    if user_id_str == session.get("host_id") and len(players) <= 1:
        await cache.delete(key)
        try:
            await query.edit_message_text("🛑 <b>Word Mafia lobby cancelled.</b>", parse_mode="HTML")
        except Exception:
            pass
        await query.answer("Lobby cancelled.")
        return

    # Remove player
    players = [p for p in players if p["id"] != user_id_str]
    session["players"] = players

    # Reassign host if host left
    if user_id_str == session.get("host_id") and players:
        session["host_id"] = players[0]["id"]

    await cache.set(key, json.dumps(session), keep_ttl=True)
    can_start = len(players) >= MAFIA_MIN_PLAYERS
    keyboard = get_mafia_lobby_keyboard(chat_id, topic_id, len(players), can_start=can_start)

    try:
        await query.edit_message_text(
            format_lobby_message(session),
            parse_mode="HTML",
            reply_markup=keyboard
        )
    except Exception:
        pass
    await query.answer("You left the lobby.")

async def handle_mafia_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE, chat_id: str, topic_id: str):
    query = update.callback_query
    user = update.effective_user
    chat = update.effective_chat
    if not query or not user:
        return

    key = get_mafia_key(chat_id, topic_id)
    raw = await cache.get(key)
    if not raw:
        await query.answer("No active lobby.")
        return

    session = json.loads(raw)
    user_id_str = str(user.id)

    is_host = (user_id_str == session.get("host_id"))
    is_sys_admin = (user.id in settings.ADMIN_USERS)

    if not (is_host or is_sys_admin):
        await query.answer("Only the lobby host can cancel this game.", show_alert=True)
        return

    await cache.delete(key)
    try:
        await query.edit_message_text("🛑 <b>Word Mafia lobby has been cancelled.</b>", parse_mode="HTML")
    except Exception:
        pass
    await query.answer("Lobby cancelled.")

async def handle_mafia_start(update: Update, context: ContextTypes.DEFAULT_TYPE, chat_id: str, topic_id: str):
    query = update.callback_query
    user = update.effective_user
    if not query or not user:
        return

    key = get_mafia_key(chat_id, topic_id)
    raw = await cache.get(key)
    if not raw:
        await query.answer("Lobby expired.", show_alert=True)
        return

    session = json.loads(raw)
    if session.get("status") != "lobby":
        await query.answer("Game already running.", show_alert=True)
        return

    user_id_str = str(user.id)
    if user_id_str != session.get("host_id") and user.id not in settings.ADMIN_USERS:
        await query.answer("Only the lobby host can start the game.", show_alert=True)
        return

    players = session.get("players", [])
    if len(players) < MAFIA_MIN_PLAYERS:
        await query.answer(f"Need at least {MAFIA_MIN_PLAYERS} players to start!", show_alert=True)
        return

    # Select random 5-letter word
    secret_word = await word_selector.get_random_word(chat_id, 5)
    secret_word = secret_word.upper()

    # Pick 1 random imposter
    imposter = random.choice(players)
    imposter_id = str(imposter["id"])

    session["status"] = "playing"
    session["word"] = secret_word
    session["imposter_id"] = imposter_id
    session["guesses"] = []
    session["votes"] = {}
    session["word_guessed"] = False

    await cache.setex(key, 1200, json.dumps(session))

    # Send PM secret roles to all players
    for p in players:
        p_id = int(p["id"])
        if str(p_id) == imposter_id:
            imposter_pm = (
                "🤫 <b>YOUR ROLE: IMPOSTER / SPY</b>\n\n"
                f"<blockquote>🎯 <b>Secret Word:</b> <b>{secret_word}</b>\n\n"
                "<b>Your Mission:</b>\n"
                "• You know the secret word in advance!\n"
                "• Mislead the Detectives by making clever guesses that waste attempts.\n"
                "• Act innocent and avoid getting voted out in the final round!</blockquote>"
            )
            try:
                await context.bot.send_message(chat_id=p_id, text=imposter_pm, parse_mode="HTML")
            except Exception as e:
                logger.warning(f"Could not send PM to imposter {p_id}: {e}")
        else:
            detective_pm = (
                "🔍 <b>YOUR ROLE: DETECTIVE</b>\n\n"
                "<blockquote><b>Your Mission:</b>\n"
                "• Work with your team in the group to guess the secret 5-letter word.\n"
                "• ⚠️ <b>Beware:</b> One player is an <b>Imposter</b> who knows the secret word and will try to mislead you!</blockquote>"
            )
            try:
                await context.bot.send_message(chat_id=p_id, text=detective_pm, parse_mode="HTML")
            except Exception as e:
                logger.warning(f"Could not send PM to detective {p_id}: {e}")

    player_mentions = ", ".join([f"@{p.get('username')}" if p.get('username') else html.escape(p.get('name', 'Player')) for p in players])

    start_text = (
        "🎲 <b>WORD MAFIA: MATCH STARTED!</b> 🕵️\n\n"
        f"<blockquote><b>Mode:</b> 5-Letter Wordle\n"
        f"<b>Attempts:</b> Max {MAFIA_MAX_GUESSES} guesses\n"
        f"<b>Active Players:</b> {player_mentions}</blockquote>\n\n"
        "<i>💬 Joined players, take turns guessing 5-letter words in chat!\n"
        "⚠️ Detectives, watch out for suspicious guesses!</i>"
    )

    try:
        await query.edit_message_text(start_text, parse_mode="HTML")
    except Exception:
        pass
    await query.answer("Match started! 🚀")

def get_mafia_feedback(guesses: list, solution: str) -> str:
    lines = []
    sol_upper = solution.upper()

    for g_entry in guesses:
        g_upper = g_entry.upper()
        sol_count = {}
        for char in sol_upper:
            sol_count[char] = sol_count.get(char, 0) + 1

        result = ["🟥"] * len(g_upper)

        for i in range(len(g_upper)):
            if i < len(sol_upper) and g_upper[i] == sol_upper[i]:
                result[i] = "🟩"
                sol_count[g_upper[i]] -= 1

        for i in range(len(g_upper)):
            if result[i] == "🟥" and sol_count.get(g_upper[i], 0) > 0:
                result[i] = "🟨"
                sol_count[g_upper[i]] -= 1

        feedback = " ".join(result)
        lines.append(f"{feedback} {g_upper}")

    return "\n".join(lines)

async def handle_mafia_guess(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
    session: Dict[str, Any],
    key: str
) -> bool:
    msg = update.effective_message
    user = update.effective_user
    chat = update.effective_chat
    if not msg or not user or not chat:
        return False

    user_id_str = str(user.id)
    players = session.get("players", [])

    # Only joined lobby players can make guesses
    if not any(p["id"] == user_id_str for p in players):
        await msg.reply_text("⚠️ Only players who joined this Word Mafia lobby can make guesses.")
        return True

    word_length = 5
    if len(text) != word_length:
        return False

    valid_words = ALL_VALID_WORDS.get(5, [])
    if text not in valid_words:
        await msg.reply_text(f"{text} is not a valid 5-letter word.")
        return True

    guesses = session.get("guesses", [])
    if text.upper() in [g.upper() for g in guesses]:
        await msg.reply_text("Someone has already guessed that word. Try another one!")
        return True

    guesses.append(text.upper())
    session["guesses"] = guesses
    secret_word = session.get("word", "").upper()

    # Check if Correct Guess
    if text.upper() == secret_word:
        session["word_guessed"] = True
        session["status"] = "voting"
        await cache.setex(key, 600, json.dumps(session))

        user_name = html.escape(user.full_name)
        user_mention = f"@{user.username}" if user.username else f'<a href="tg://user?id={user.id}">{user_name}</a>'

        win_msg = (
            "🎉 <b>WORD CRACKED!</b> 🎯\n\n"
            f"<blockquote>👤 <b>Guessed by:</b> {user_mention}\n"
            f"🎯 <b>Secret Word:</b> <b>{secret_word}</b> (in {len(guesses)}/{MAFIA_MAX_GUESSES} attempts)</blockquote>\n\n"
            "🚨 <b>EMERGENCY VOTING INITIATED!</b>\n"
            "Now it's time to identify the Imposter among you!"
        )
        await msg.reply_text(win_msg, parse_mode="HTML")
        await trigger_mafia_voting(context, str(chat.id), session.get("topic_id", "general"), session, key)
        return True

    # Check if Max Attempts Reached
    if len(guesses) >= MAFIA_MAX_GUESSES:
        session["word_guessed"] = False
        session["status"] = "voting"
        await cache.setex(key, 600, json.dumps(session))

        over_msg = (
            "💀 <b>MAX ATTEMPTS REACHED! (15/15)</b>\n\n"
            "<blockquote>The group could not crack the word!\n"
            f"🔍 <b>Secret Word:</b> <b>{secret_word}</b></blockquote>\n\n"
            "🚨 <b>EMERGENCY VOTING INITIATED!</b>\n"
            "Can you still catch the Imposter who sabotaged you?"
        )
        await msg.reply_text(over_msg, parse_mode="HTML")
        await trigger_mafia_voting(context, str(chat.id), session.get("topic_id", "general"), session, key)
        return True

    # Normal Guess Feedback
    await cache.set(key, json.dumps(session), keep_ttl=True)
    feedback_text = get_mafia_feedback(guesses, secret_word)
    response_msg = f"<i>Word Mafia · {len(guesses)}/{MAFIA_MAX_GUESSES}</i>\n\n{to_fancy_text(feedback_text)}"
    await msg.reply_text(response_msg, parse_mode="HTML")
    return True

async def trigger_mafia_voting(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: str,
    topic_id: str,
    session: Dict[str, Any],
    key: str
):
    players = session.get("players", [])
    votes = session.get("votes", {})

    keyboard = get_mafia_voting_keyboard(chat_id, topic_id, players, votes)

    voting_msg = (
        "🚨 <b>EMERGENCY VOTING: WHO IS THE IMPOSTER?</b> 🚨\n\n"
        "<blockquote>Detectives, discuss the guesses and vote for the player you suspect was the Imposter!\n\n"
        f"⏱️ <b>Voting window: {MAFIA_VOTE_TIMEOUT} seconds</b></blockquote>\n\n"
        "<i>Tap the button with the player's name below to cast your secret vote:</i>"
    )

    sent = await context.bot.send_message(
        chat_id=int(chat_id),
        message_thread_id=int(topic_id) if topic_id.isdigit() else None,
        text=voting_msg,
        parse_mode="HTML",
        reply_markup=keyboard
    )
    session["voting_msg_id"] = sent.message_id
    await cache.setex(key, MAFIA_VOTE_TIMEOUT + 30, json.dumps(session))

async def handle_mafia_vote(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: str,
    topic_id: str,
    target_id: str
):
    query = update.callback_query
    user = update.effective_user
    if not query or not user:
        return

    key = get_mafia_key(chat_id, topic_id)
    raw = await cache.get(key)
    if not raw:
        await query.answer("Voting session has expired.", show_alert=True)
        return

    session = json.loads(raw)
    if session.get("status") != "voting":
        await query.answer("Voting is not active.", show_alert=True)
        return

    user_id_str = str(user.id)
    players = session.get("players", [])

    if not any(p["id"] == user_id_str for p in players):
        await query.answer("Only lobby participants can vote!", show_alert=True)
        return

    votes = session.get("votes", {})
    votes[user_id_str] = target_id
    session["votes"] = votes

    await cache.set(key, json.dumps(session), keep_ttl=True)

    # If all players voted, finalize immediately
    if len(votes) >= len(players):
        await query.answer("All votes received! Calculating verdict...")
        await finalize_mafia_verdict(context, chat_id, topic_id, session, key)
        return

    keyboard = get_mafia_voting_keyboard(chat_id, topic_id, players, votes)
    try:
        await query.edit_message_reply_markup(reply_markup=keyboard)
    except Exception:
        pass

    target_name = next((p["name"] for p in players if p["id"] == target_id), "Player")
    await query.answer(f"Voted for {target_name}! ({len(votes)}/{len(players)} votes recorded)")

async def finalize_mafia_verdict(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: str,
    topic_id: str,
    session: Dict[str, Any],
    key: str
):
    # Ensure not executed twice
    await cache.delete(key)

    players = session.get("players", [])
    votes = session.get("votes", {})
    imposter_id = session.get("imposter_id")
    secret_word = session.get("word", "")
    word_guessed = session.get("word_guessed", False)

    # Tally votes
    tally: Dict[str, int] = {}
    for target_id in votes.values():
        tally[target_id] = tally.get(target_id, 0) + 1

    most_voted_id = None
    max_votes = 0
    for pid, count in tally.items():
        if count > max_votes:
            max_votes = count
            most_voted_id = pid

    imposter_info = next((p for p in players if p["id"] == imposter_id), None)
    imposter_name = html.escape(imposter_info["name"]) if imposter_info else "Imposter"
    imposter_mention = f"@{imposter_info['username']}" if (imposter_info and imposter_info.get('username')) else f'<a href="tg://user?id={imposter_id}">{imposter_name}</a>'

    voted_info = next((p for p in players if p["id"] == most_voted_id), None)
    voted_name = html.escape(voted_info["name"]) if voted_info else "Nobody"
    voted_mention = f"@{voted_info['username']}" if (voted_info and voted_info.get('username')) else (f'<a href="tg://user?id={most_voted_id}">{voted_name}</a>' if most_voted_id else "Nobody")

    imposter_caught = (most_voted_id == imposter_id)

    # Determine Points & Narrative
    async with get_db() as db:
        if word_guessed and imposter_caught:
            outcome_title = "🏆 <b>MAJOR DETECTIVE VICTORY!</b> 🎉"
            outcome_body = (
                f"• Detectives cracked the word <b>{secret_word}</b>\n"
                f"• AND successfully caught the Imposter: {imposter_mention}!\n\n"
                "🪙 <b>Score:</b> +50 Points awarded to all Detectives!"
            )
            for p in players:
                if p["id"] != imposter_id:
                    db.add(Leaderboard(chat_id=chat_id, user_id=p["id"], score=50, word_length="5"))

        elif word_guessed and not imposter_caught:
            outcome_title = "🎭 <b>PARTIAL VICTORY & MASTER OF DECEPTION!</b> 🎭"
            outcome_body = (
                f"• Detectives cracked the word <b>{secret_word}</b>\n"
                f"• But {imposter_mention} framed {voted_mention} and escaped untouched!\n\n"
                "🪙 <b>Score:</b> +20 Points to Detectives • +40 Points to Imposter!"
            )
            for p in players:
                if p["id"] != imposter_id:
                    db.add(Leaderboard(chat_id=chat_id, user_id=p["id"], score=20, word_length="5"))
                else:
                    db.add(Leaderboard(chat_id=chat_id, user_id=p["id"], score=40, word_length="5"))

        elif not word_guessed and not imposter_caught:
            outcome_title = "👑 <b>FLAWLESS IMPOSTER VICTORY!</b> 🤫"
            outcome_body = (
                f"• The group failed to crack the word.\n"
                f"• {imposter_mention} completely fooled the group!\n\n"
                f"🪙 <b>Score:</b> +100 Points awarded to Imposter {imposter_mention}!"
            )
            db.add(Leaderboard(chat_id=chat_id, user_id=imposter_id, score=100, word_length="5"))

        else: # not word_guessed but imposter caught
            outcome_title = "⚖️ <b>MUTUAL DRAW / DETECTIVES REVENGE!</b> ⚖️"
            outcome_body = (
                f"• The word was not cracked, but Detectives saw through the sabotage and executed {imposter_mention}!\n\n"
                "🪙 <b>Score:</b> +30 Points to Detectives."
            )
            for p in players:
                if p["id"] != imposter_id:
                    db.add(Leaderboard(chat_id=chat_id, user_id=p["id"], score=30, word_length="5"))

    verdict_text = (
        "⚖️ <b>THE VERDICT IS IN!</b> ⚖️\n\n"
        f"<blockquote>🎯 <b>Secret Word:</b> <b>{secret_word}</b>\n"
        f"🤫 <b>The Imposter Was:</b> {imposter_mention}\n"
        f"🗳️ <b>Most Voted:</b> {voted_mention} ({max_votes} votes)</blockquote>\n\n"
        f"{outcome_title}\n"
        f"<blockquote>{outcome_body}</blockquote>\n\n"
        "<i>🔥 Start a new match anytime with /mafia</i>"
    )

    try:
        await context.bot.send_message(
            chat_id=int(chat_id),
            message_thread_id=int(topic_id) if topic_id.isdigit() else None,
            text=verdict_text,
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Error sending verdict message: {e}")
