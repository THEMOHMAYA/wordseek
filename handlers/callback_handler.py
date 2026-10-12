import json
import html
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from sqlalchemy import select, delete

from config.settings import settings
from config.constants import (
    ALLOWED_CHAT_SEARCH_KEYS,
    ALLOWED_CHAT_TIME_KEYS,
    ALLOWED_WORD_LENGTHS
)
from database.db import get_db
from database.models import User, Game, Guess, AuthorizedUser
from services.leaderboard_service import (
    get_leaderboard_scores,
    get_user_scores,
    get_smart_defaults,
    format_leaderboard_message,
    format_user_score_message,
    format_no_scores_message
)
from utils.cache import cache
from utils.keyboards import (
    generate_leaderboard_keyboard,
    generate_user_selection_keyboard,
    get_main_help_keyboard,
    build_captcha_keyboard
)
from commands.help import (
    get_how_to_play_message,
    get_scores_message,
    get_group_settings_message,
    get_other_commands_message,
    get_admin_commands_message
)
from commands.captcha import build_captcha_message

logger = logging.getLogger(__name__)

async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query or not query.data:
        return

    data = query.data
    user = query.from_user
    chat = query.message.chat if query.message else None

    # 1. Leaderboard Callback
    if data.startswith("leaderboard"):
        parts = data.split()
        if len(parts) >= 4:
            _, search_key, time_key, raw_len = parts[:4]
            word_len = int(raw_len) if raw_len.isdigit() else 5

            if search_key in ALLOWED_CHAT_SEARCH_KEYS and time_key in ALLOWED_CHAT_TIME_KEYS and word_len in ALLOWED_WORD_LENGTHS:
                chat_id = str(chat.id) if chat else ""
                scores = await get_leaderboard_scores(chat_id, search_key, time_key, word_len)
                keyboard = generate_leaderboard_keyboard(search_key, time_key, word_len)

                try:
                    await query.edit_message_text(
                        text=format_leaderboard_message(scores, search_key),
                        parse_mode="HTML",
                        reply_markup=keyboard,
                        disable_web_page_preview=True
                    )
                except Exception:
                    pass
        await query.answer()
        return

    # 2. Score List (Multiple Users with same username)
    elif data.startswith("score_list"):
        parts = data.split()
        if len(parts) > 1:
            target_username = parts[1]
            async with get_db() as db:
                users_res = (await db.execute(
                    select(User).where(User.username.ilike(target_username))
                )).scalars().all()

            if not users_res:
                await query.answer("No users found with this username.", show_alert=True)
                return

            keyboard = generate_user_selection_keyboard(users_res, target_username)
            try:
                await query.edit_message_text(
                    f"⚠️ <b>Multiple Users Found</b>\n\n"
                    f"There are {len(users_res)} users with username @{target_username}.\n"
                    f"Please select the user you want to view:",
                    parse_mode="HTML",
                    reply_markup=keyboard
                )
            except Exception:
                pass
        await query.answer()
        return

    # 3. Score Select
    elif data.startswith("score_select"):
        parts = data.split()
        if len(parts) >= 2:
            target_user_id = parts[1]
            target_username = parts[2] if len(parts) > 2 else ""
            chat_id = str(chat.id) if chat else ""

            async with get_db() as db:
                user_info = (await db.execute(select(User).where(User.id == target_user_id))).scalar_one_or_none()

            if not user_info:
                await query.answer("User not found.", show_alert=True)
                return

            smart = await get_smart_defaults(
                user_id=target_user_id,
                chat_id=chat_id,
                chat_type=chat.type if chat else "group"
            )

            user_score = await get_user_scores(
                chat_id=chat_id,
                user_id=target_user_id,
                search_key=smart["searchKey"],
                time_key=smart["timeKey"],
                word_length=smart["wordLength"]
            )

            back_btn = {"text": "⬅️ Back to user list", "callback": f"score_list {target_username}"} if target_username else None
            keyboard = generate_leaderboard_keyboard(
                search_key=smart["searchKey"],
                time_key=smart["timeKey"],
                word_length=smart["wordLength"],
                callback_prefix=f"score {target_user_id}",
                back_button=back_btn
            )

            if not user_score:
                no_scores_text = format_no_scores_message(
                    is_own_score=False,
                    user_name=user_info.name,
                    search_key=smart["searchKey"],
                    time_key=smart["timeKey"],
                    was_time_key_explicit=False,
                    has_any_scores=smart["hasAnyScores"]
                )
                try:
                    await query.edit_message_text(no_scores_text, reply_markup=keyboard)
                except Exception:
                    pass
                await query.answer("No scores found for the current filter.")
                return

            try:
                await query.edit_message_text(
                    format_user_score_message(user_score, smart["searchKey"]),
                    parse_mode="HTML",
                    reply_markup=keyboard,
                    disable_web_page_preview=True
                )
            except Exception:
                pass
        await query.answer()
        return

    # 4. Score Filter Navigation
    elif data.startswith("score "):
        parts = data.split()
        if len(parts) >= 5:
            _, target_user_id, search_key, time_key, raw_len = parts[:5]
            word_len = int(raw_len) if raw_len.isdigit() else 5
            chat_id = str(chat.id) if chat else ""

            async with get_db() as db:
                user_info = (await db.execute(select(User).where(User.id == target_user_id))).scalar_one_or_none()

            if not user_info:
                await query.answer("User not found.", show_alert=True)
                return

            user_score = await get_user_scores(
                chat_id=chat_id,
                user_id=target_user_id,
                search_key=search_key,
                time_key=time_key,
                word_length=word_len
            )

            keyboard = generate_leaderboard_keyboard(
                search_key=search_key,
                time_key=time_key,
                word_length=word_len,
                callback_prefix=f"score {target_user_id}"
            )

            if not user_score:
                no_scores_text = format_no_scores_message(
                    is_own_score=(target_user_id == str(user.id)),
                    user_name=user_info.name,
                    search_key=search_key,
                    time_key=time_key,
                    was_time_key_explicit=True,
                    has_any_scores=True
                )
                try:
                    await query.edit_message_text(no_scores_text, reply_markup=keyboard)
                except Exception:
                    pass
                await query.answer("No scores found for this period.")
                return

            try:
                await query.edit_message_text(
                    format_user_score_message(user_score, search_key),
                    parse_mode="HTML",
                    reply_markup=keyboard,
                    disable_web_page_preview=True
                )
            except Exception:
                pass
        await query.answer()
        return

    # 5. Vote End Game Callback
    elif data.startswith("vote_end"):
        parts = data.split()
        if len(parts) < 2:
            return

        chat_id_str = parts[1]
        user_id_str = str(user.id)

        vote_key = f"vote:{chat_id_str}"
        vote_data_str = await cache.get(vote_key)
        if not vote_data_str:
            await query.answer("The voting session has expired.", show_alert=True)
            return

        vote_data = json.loads(vote_data_str)
        voters = vote_data.get("voters", [])

        if user_id_str in voters:
            await query.answer("You have already voted.")
            return

        topic_id = vote_data.get("topicId", "general")

        async with get_db() as db:
            game_stmt = select(Game).where(Game.active_chat == chat_id_str, Game.topic_id == topic_id)
            current_game = (await db.execute(game_stmt)).scalar_one_or_none()

        if not current_game:
            await query.answer("No active game found.", show_alert=True)
            return

        # Check if caller has admin/starter privileges to end immediately
        is_game_starter = (current_game.started_by == user_id_str)
        is_system_admin = (user.id in settings.ADMIN_USERS)

        is_admin = False
        if chat and chat.type != "private":
            try:
                member = await context.bot.get_chat_member(chat.id, user.id)
                is_admin = (member.status in ["administrator", "creator"])
            except Exception:
                pass

        async with get_db() as db:
            is_auth = bool((await db.execute(
                select(AuthorizedUser).where(AuthorizedUser.user_id == user_id_str, AuthorizedUser.chat_id == chat_id_str)
            )).scalar_one_or_none())

        user_name = html.escape(user.full_name)
        user_link = f'<a href="tg://user?id={user.id}">{user_name}</a>'

        if is_game_starter or is_system_admin or is_admin or is_auth:
            reason = f"<b>Ended by: </b>{user_link}"
            await cache.delete(vote_key)
            try:
                await query.message.delete()
            except Exception:
                pass

            async with get_db() as db:
                await db.execute(delete(Guess).where(Guess.game_id == current_game.id))
                await db.execute(delete(Game).where(Game.id == current_game.id))

            word_len = len(current_game.word)
            await context.bot.send_message(
                chat_id=int(chat_id_str),
                message_thread_id=int(topic_id) if topic_id.isdigit() else None,
                text=(
                    "🛑 <b>Game Terminated</b>\n\n"
                    f"<blockquote>🔍 <b>The word was:</b> <b>{current_game.word.upper()}</b>\n"
                    f"👤 {reason}</blockquote>\n\n"
                    f"<i>Ready for another round? Start with /new{word_len}</i>"
                ),
                parse_mode="HTML"
            )
            await query.answer("Game ended! 🎯")
            return

        # Add vote
        voters.append(user_id_str)
        vote_data["voters"] = voters

        if len(voters) >= 3:
            await cache.delete(vote_key)
            try:
                await query.message.delete()
            except Exception:
                pass

            async with get_db() as db:
                await db.execute(delete(Guess).where(Guess.game_id == current_game.id))
                await db.execute(delete(Game).where(Game.id == current_game.id))

            word_len = len(current_game.word)
            await context.bot.send_message(
                chat_id=int(chat_id_str),
                message_thread_id=int(topic_id) if topic_id.isdigit() else None,
                text=(
                    "🛑 <b>Game Terminated</b>\n\n"
                    f"<blockquote>🔍 <b>The word was:</b> <b>{current_game.word.upper()}</b>\n"
                    "🗳️ <b>Terminated by community vote (3/3 votes)</b></blockquote>\n\n"
                    f"<i>Ready for another round? Start with /new{word_len}</i>"
                ),
                parse_mode="HTML"
            )
            await query.answer("Game ended! Voting threshold reached. 🎯")
            return

        await cache.setex(vote_key, 300, json.dumps(vote_data))
        votes_left = 3 - len(voters)

        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton(f"✅ Vote to End ({len(voters)}/3)", callback_data=f"vote_end {chat_id_str}")
        ]])

        try:
            await query.edit_message_text(
                f"<b>🗳️ Vote to End Game</b>\n\n"
                f"Players are voting to end the game.\n\n"
                f"<b>Votes needed: 3 total</b>\n"
                f"<b>Current votes: {len(voters)}/3</b>\n\n"
                f"React with the button below to vote for ending the game.",
                parse_mode="HTML",
                reply_markup=keyboard
            )
        except Exception:
            pass

        await query.answer(f"Vote recorded! {votes_left} more votes needed.")
        return

    # 6. Help Menu Tabs
    elif data.startswith("help_"):
        section = data.replace("help_", "")
        should_show_admin = (user.id in settings.ADMIN_USERS) and (chat and chat.type == "private")

        if section == "admin" and not should_show_admin:
            await query.answer("You don't have permission to view this.", show_alert=True)
            return

        if section == "howto":
            text = get_how_to_play_message()
        elif section == "scores":
            text = get_scores_message()
        elif section == "group":
            text = get_group_settings_message()
        elif section == "other":
            text = get_other_commands_message()
        elif section == "admin":
            text = get_admin_commands_message()
        else:
            text = get_how_to_play_message()
            section = "howto"

        keyboard = get_main_help_keyboard(should_show_admin, active=section)

        try:
            await query.edit_message_text(
                text=text,
                parse_mode="HTML",
                reply_markup=keyboard,
                disable_web_page_preview=True
            )
        except Exception:
            pass
        await query.answer()
        return

    # 7. Captcha Interaction
    elif data.startswith("captcha_"):
        if not chat:
            return
        key = f"captcha:{chat.id}:{user.id}"
        raw = await cache.get(key)
        if not raw:
            await query.answer("Captcha expired or this captcha isn't for you.", show_alert=True)
            return

        session = json.loads(raw)
        progress = session.get("progress", [])

        if data == "captcha_clear":
            progress = []
        elif data == "captcha_back":
            if progress:
                progress.pop()
        elif data.startswith("captcha_pick"):
            symbol = data.split()[1] if len(data.split()) > 1 else ""
            if symbol and len(progress) < 3:
                progress.append(symbol)

        session["progress"] = progress

        mention = f"@{session['username']}" if session.get("username") else f'<a href="tg://user?id={user.id}">{html.escape(session.get("name", "User"))}</a>'

        if len(progress) == 3:
            if progress == session["answer"]:
                await cache.delete(key)
                try:
                    await context.bot.send_message(
                        chat_id=int(session["adminId"]),
                        text=f"✅ {mention} passed the captcha.",
                        parse_mode="HTML"
                    )
                except Exception:
                    pass

                await query.edit_message_text(
                    build_captcha_message(mention, progress, session.get("attempts", 0), 3, status="Verification successful ✅"),
                    parse_mode="HTML"
                )
                await query.answer("Verification successful! ✅")
                return

            # Failed Attempt
            attempts = session.get("attempts", 0) + 1
            session["attempts"] = attempts

            if attempts >= 3:
                await cache.delete(key)
                try:
                    await context.bot.send_message(
                        chat_id=int(session["adminId"]),
                        text=f"❌ {mention} failed the captcha.\nExpected: {' '.join(session['answer'])}\nGot: {' '.join(progress)}",
                        parse_mode="HTML"
                    )
                except Exception:
                    pass

                await query.edit_message_text(
                    build_captcha_message(mention, session["answer"], attempts, 3, status="Verification failed ❌"),
                    parse_mode="HTML"
                )
                await query.answer("Verification failed! ❌", show_alert=True)
                return

            session["progress"] = []
            await cache.set(key, json.dumps(session), keep_ttl=True)

            keyboard = build_captcha_keyboard([])
            await query.edit_message_text(
                build_captcha_message(mention, [], attempts, 3, status="Incorrect selection. Try again."),
                parse_mode="HTML",
                reply_markup=keyboard
            )
            await query.answer("Incorrect! Try again.")
            return

        await cache.set(key, json.dumps(session), keep_ttl=True)
        keyboard = build_captcha_keyboard(progress)
        try:
            await query.edit_message_text(
                build_captcha_message(mention, progress, session.get("attempts", 0), 3),
                parse_mode="HTML",
                reply_markup=keyboard
            )
        except Exception:
            pass
        await query.answer()

    # 8. Word Mafia Callbacks
    elif data.startswith("mafia_"):
        from commands.mafia import (
            handle_mafia_join,
            handle_mafia_leave,
            handle_mafia_cancel,
            handle_mafia_start,
            handle_mafia_vote
        )
        parts = data.split()
        action = parts[0]
        if action == "mafia_join" and len(parts) >= 3:
            await handle_mafia_join(update, context, parts[1], parts[2])
        elif action == "mafia_leave" and len(parts) >= 3:
            await handle_mafia_leave(update, context, parts[1], parts[2])
        elif action == "mafia_cancel" and len(parts) >= 3:
            await handle_mafia_cancel(update, context, parts[1], parts[2])
        elif action == "mafia_start" and len(parts) >= 3:
            await handle_mafia_start(update, context, parts[1], parts[2])
        elif action == "mafia_vote" and len(parts) >= 4:
            await handle_mafia_vote(update, context, parts[1], parts[2], parts[3])

