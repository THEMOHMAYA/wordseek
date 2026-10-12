import html
from datetime import datetime, date, timedelta
from typing import Optional, List, Dict, Any, Tuple
from sqlalchemy import select, func, desc, and_, not_, exists
from config.constants import (
    ALLOWED_CHAT_SEARCH_KEYS,
    ALLOWED_CHAT_TIME_KEYS,
    ALLOWED_WORD_LENGTHS
)
from database.db import get_db
from database.models import Leaderboard, User, BannedUser, UserStat

def escape_html(text: str) -> str:
    return html.escape(text or "")

def get_time_boundary(time_key: str) -> Optional[datetime]:
    now = datetime.utcnow()
    if time_key == "today":
        return datetime(now.year, now.month, now.day)
    elif time_key == "week":
        start_of_week = now - timedelta(days=now.weekday())
        return datetime(start_of_week.year, start_of_week.month, start_of_week.day)
    elif time_key == "month":
        return datetime(now.year, now.month, 1)
    elif time_key == "year":
        return datetime(now.year, 1, 1)
    return None

async def get_leaderboard_scores(
    chat_id: str,
    search_key: str = "group",
    time_key: str = "today",
    word_length: int = 5
) -> List[Dict[str, Any]]:
    async with get_db() as db:
        banned_subquery = select(BannedUser.user_id).where(BannedUser.user_id == Leaderboard.user_id)

        conditions = [
            not_(exists(banned_subquery)),
            Leaderboard.word_length == str(word_length)
        ]

        if search_key == "group":
            conditions.append(Leaderboard.chat_id == chat_id)

        time_boundary = get_time_boundary(time_key)
        if time_boundary:
            conditions.append(Leaderboard.created_at >= time_boundary)

        stmt = (
            select(
                User.id.label("user_id"),
                User.name.label("name"),
                User.username.label("username"),
                func.sum(Leaderboard.score).label("total_score")
            )
            .join(User, User.id == Leaderboard.user_id)
            .where(and_(*conditions))
            .group_by(User.id, User.name, User.username)
            .order_by(desc(func.sum(Leaderboard.score)))
            .limit(20)
        )

        result = await db.execute(stmt)
        rows = result.all()

        return [
            {
                "userId": r.user_id,
                "name": r.name,
                "username": r.username,
                "totalScore": int(r.total_score or 0)
            }
            for r in rows
        ]

async def get_user_scores(
    chat_id: str,
    user_id: str,
    search_key: str = "group",
    time_key: str = "all",
    word_length: int = 5
) -> Optional[Dict[str, Any]]:
    async with get_db() as db:
        # Check user info first
        user_stmt = select(User).where(User.id == user_id)
        user_res = await db.execute(user_stmt)
        user = user_res.scalar_one_or_none()
        if not user:
            return None

        # Build subquery for ranking
        banned_subquery = select(BannedUser.user_id).where(BannedUser.user_id == Leaderboard.user_id)
        conditions = [
            not_(exists(banned_subquery)),
            Leaderboard.word_length == str(word_length)
        ]

        if search_key == "group":
            conditions.append(Leaderboard.chat_id == chat_id)

        time_boundary = get_time_boundary(time_key)
        if time_boundary:
            conditions.append(Leaderboard.created_at >= time_boundary)

        # Get total score & rank
        sub_stmt = (
            select(
                Leaderboard.user_id,
                func.sum(Leaderboard.score).label("score_sum")
            )
            .where(and_(*conditions))
            .group_by(Leaderboard.user_id)
            .order_by(desc(func.sum(Leaderboard.score)))
        )
        ranked_res = (await db.execute(sub_stmt)).all()

        total_score = 0
        rank = 0
        for idx, row in enumerate(ranked_res, start=1):
            if row.user_id == user_id:
                total_score = int(row.score_sum or 0)
                rank = idx
                break

        if rank == 0:
            return None

        # Get user streaks
        stat_stmt = select(UserStat).where(UserStat.user_id == user_id)
        stat_res = await db.execute(stat_stmt)
        stat = stat_res.scalar_one_or_none()

        return {
            "userId": user.id,
            "name": user.name,
            "username": user.username,
            "totalScore": total_score,
            "rank": rank,
            "currentStreak": stat.current_streak if stat else 0,
            "highestStreak": stat.highest_streak if stat else 0
        }

async def get_smart_defaults(
    user_id: str,
    chat_id: str,
    requested_search_key: Optional[str] = None,
    requested_time_key: Optional[str] = None,
    requested_word_length: Optional[int] = None,
    chat_type: str = "group"
) -> Dict[str, Any]:
    search_key = requested_search_key or ("global" if chat_type == "private" else "group")

    async with get_db() as db:
        if search_key == "group" and chat_type != "private":
            check_stmt = select(Leaderboard.user_id).where(
                and_(Leaderboard.user_id == user_id, Leaderboard.chat_id == chat_id)
            ).limit(1)
            res = await db.execute(check_stmt)
            if not res.scalar_one_or_none():
                search_key = "global"

        # Determine word length
        word_length = requested_word_length or 5
        if not requested_word_length:
            for length in [5, 4, 6]:
                q = select(Leaderboard.user_id).where(
                    and_(Leaderboard.user_id == user_id, Leaderboard.word_length == str(length))
                )
                if search_key == "group":
                    q = q.where(Leaderboard.chat_id == chat_id)
                q = q.limit(1)
                if (await db.execute(q)).scalar_one_or_none():
                    word_length = length
                    break

        time_key = requested_time_key or "all"

        # Check if user has any scores
        has_scores_q = select(Leaderboard.user_id).where(
            and_(Leaderboard.user_id == user_id, Leaderboard.word_length == str(word_length))
        )
        if search_key == "group":
            has_scores_q = has_scores_q.where(Leaderboard.chat_id == chat_id)
        has_scores_q = has_scores_q.limit(1)
        has_any_scores = bool((await db.execute(has_scores_q)).scalar_one_or_none())

    return {
        "searchKey": search_key,
        "timeKey": time_key,
        "wordLength": word_length,
        "hasAnyScores": has_any_scores
    }

def parse_leaderboard_filters(
    input_text: str,
    default_search_key: str = "group",
    default_time_key: str = "today"
) -> Dict[str, Any]:
    parts = input_text.lower().strip().split()
    search_key = default_search_key
    time_key = default_time_key
    word_length = 5

    for part in parts:
        if part in ALLOWED_CHAT_SEARCH_KEYS:
            search_key = part
        elif part in ALLOWED_CHAT_TIME_KEYS:
            time_key = part
        elif part.isdigit() and int(part) in ALLOWED_WORD_LENGTHS:
            word_length = int(part)

    return {
        "searchKey": search_key,
        "timeKey": time_key,
        "wordLength": word_length
    }

def parse_score_input(input_text: str) -> Dict[str, Any]:
    parts = input_text.lower().strip().split()
    target = None
    search_key = None
    time_key = None
    word_length = None

    for part in parts:
        if part in ALLOWED_CHAT_SEARCH_KEYS:
            search_key = part
        elif part in ALLOWED_CHAT_TIME_KEYS:
            time_key = part
        elif part.isdigit() and int(part) in ALLOWED_WORD_LENGTHS:
            word_length = int(part)
        elif part.startswith("@") or part.isdigit():
            target = part
        elif not target:
            target = part

    return {
        "target": target,
        "searchKey": search_key,
        "timeKey": time_key,
        "wordLength": word_length
    }

def format_leaderboard_message(data: List[Dict[str, Any]], search_key: str) -> str:
    if not data:
        scope = "Global" if search_key == "global" else "Group"
        return f"<blockquote>🏆 <b>{scope} Leaderboard</b> 🏆</blockquote>\n\n<blockquote>No scores recorded yet for this period.</blockquote>"

    blocks = []
    current_block = []

    for index, entry in enumerate(data):
        rank_icon = ["🥇", "🥈", "🥉"][index] if index < 3 else "🔅"
        safe_name = escape_html(entry["name"])
        username = entry.get("username")
        if username:
            user_link = f'<a href="https://t.me/{username}">{safe_name}</a>'
        else:
            user_link = safe_name

        score_formatted = f"{entry['totalScore']:,}"
        line = f"{rank_icon} {user_link} - {score_formatted} pts"

        if index == 0 or index == 3 or (index > 3 and (index - 3) % 10 == 0):
            if current_block:
                blocks.append(current_block)
            current_block = []

        current_block.append(line)

    if current_block:
        blocks.append(current_block)

    formatted_entries = "\n".join([f"<blockquote>{chr(10).join(b)}</blockquote>" for b in blocks])
    scope = "Global" if search_key == "global" else "Group"
    return f"<blockquote>🏆 <b>{scope} Leaderboard</b> 🏆</blockquote>\n\n{formatted_entries}"

def format_user_score_message(data: Dict[str, Any], search_key: str) -> str:
    safe_name = escape_html(data["name"])
    username = data.get("username")
    if username:
        mention = f'<a href="https://t.me/{username}">{safe_name}</a>'
    else:
        mention = safe_name

    scope_text = "globally" if search_key == "global" else "in this chat"
    total_score = f"{data['totalScore']:,}"
    rank = f"{data['rank']:,}"
    current_streak = data.get("currentStreak", 0)
    highest_streak = data.get("highestStreak", 0)

    return (
        f"<blockquote><strong>🏆 Regular WordSeek Scores</strong></blockquote>\n"
        f"<b>{mention}</b> has a total score of <b>{total_score}</b> {scope_text}.\n"
        f"Their rank is <b>#{rank}</b>.\n\n"
        f"<blockquote><strong>🔥 Daily WordSeek Stats</strong></blockquote>\n"
        f"<b>Current Streak:</b> {current_streak} days\n"
        f"<b>Highest Streak:</b> {highest_streak} days"
    )

def format_no_scores_message(
    is_own_score: bool,
    user_name: str,
    search_key: str,
    time_key: str,
    was_time_key_explicit: bool,
    has_any_scores: bool
) -> str:
    subject = "You" if is_own_score else (user_name or "This user")
    verb = "have" if is_own_score else "has"
    verb_have = "haven't" if is_own_score else "hasn't"
    scope_text = "globally" if search_key == "global" else "in this chat"

    time_map = {
        "today": "today",
        "week": "this week",
        "month": "this month",
        "year": "this year",
        "all": "yet",
    }

    if not has_any_scores:
        if search_key == "group":
            return f"{subject} {verb} no scores recorded in this chat. Try switching to \"Global\" to see overall scores."
        return f"{subject} {verb} no scores recorded yet." + (" Start playing to earn some points! 🎮" if is_own_score else "")

    if was_time_key_explicit:
        if time_key == "all":
            return f"{subject} {verb} no scores recorded {scope_text}."
        t_text = time_map.get(time_key, "this period")
        return f"{subject} {verb_have} played {t_text} {scope_text}. Try selecting a different time period to see scores."

    return f"{subject} {verb} no scores recorded {scope_text}. Try switching to \"Global\" or selecting a different time period."
