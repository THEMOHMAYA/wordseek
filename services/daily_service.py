import os
import json
import hmac
import hashlib
import struct
import logging
from datetime import datetime, date, timedelta
from typing import List, Optional, Tuple, Dict, Any
from zoneinfo import ZoneInfo
from sqlalchemy import select, update, or_
from sqlalchemy.ext.asyncio import AsyncSession

from config.settings import settings
from database.db import get_db
from database.models import DailyWord, DailyGuess, UserStat
from services.ai_service import ai_service

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def load_daily_words() -> List[str]:
    path = os.path.join(BASE_DIR, "data", "daily-word-lists.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return ["apple", "crane", "slate", "trace", "audio", "house"]

DAILY_WORDS_LIST = load_daily_words()

def seed_from_secret(secret: str) -> int:
    h = hmac.new(secret.encode("utf-8"), b"wotd-permutation-seed", hashlib.sha256).digest()
    return struct.unpack(">I", h[:4])[0]

def mulberry32(seed: int):
    t = seed & 0xFFFFFFFF
    def next_rand():
        nonlocal t
        t = (t + 0x6D2B79F5) & 0xFFFFFFFF
        r = (t ^ (t >> 15)) * (1 | t) & 0xFFFFFFFF
        r = (r + ((r ^ (r >> 7)) * 61 & 0xFFFFFFFF)) ^ r & 0xFFFFFFFF
        return ((r ^ (r >> 14)) & 0xFFFFFFFF) / 4294967296.0
    return next_rand

def deterministic_shuffle(seed: int) -> List[str]:
    arr = list(DAILY_WORDS_LIST)
    rnd = mulberry32(seed)
    for i in range(len(arr) - 1, 0, -1):
        j = int(rnd() * (i + 1))
        arr[i], arr[j] = arr[j], arr[i]
    return arr

def get_current_game_date() -> date:
    try:
        tz = ZoneInfo(settings.TIME_ZONE)
        now_tz = datetime.now(tz)
    except Exception:
        now_tz = datetime.utcnow()

    # Game date flips at 06:00 AM
    if now_tz.hour < 6:
        base_dt = now_tz - timedelta(days=1)
    else:
        base_dt = now_tz
    return base_dt.date()

def get_day_number(game_date: date) -> int:
    start_date = settings.DAILY_WORDLE_START_DATE
    diff = (game_date - start_date).days
    return max(1, diff + 1)

def get_word_of_the_day(shuffled: List[str], game_date: date) -> str:
    day_num = get_day_number(game_date)
    return shuffled[day_num % len(shuffled)]

def format_daily_word_details(daily_word: DailyWord) -> str:
    parts = []
    if daily_word.phonetic:
        parts.append(f"🗣️ <i>Pronunciation:</i> <code>{daily_word.phonetic}</code>")
    if daily_word.meaning:
        parts.append(f"📖 <i>Meaning:</i>\n{daily_word.meaning}")
    if daily_word.sentence:
        parts.append(f"💬 <i>Example:</i> <i>\"{daily_word.sentence}\"</i>")
    return "\n\n".join(parts)

def generate_wordle_share_text(day_number: int, guesses: List[str], solution: str) -> str:
    total_attempts = len(guesses)
    attempt_line = f"{day_number} {total_attempts}/6"
    sol_upper = solution.upper()

    lines = []
    for g in guesses:
        g_upper = g.upper()
        sol_count = {}
        for c in sol_upper:
            sol_count[c] = sol_count.get(c, 0) + 1

        result = ["⬛"] * len(g_upper)
        for i in range(len(g_upper)):
            if i < len(sol_upper) and g_upper[i] == sol_upper[i]:
                result[i] = "🟩"
                sol_count[g_upper[i]] -= 1

        for i in range(len(g_upper)):
            if result[i] != "🟩" and sol_count.get(g_upper[i], 0) > 0:
                result[i] = "🟨"
                sol_count[g_upper[i]] -= 1

        lines.append("".join(result))

    return f"WordSeek {attempt_line}\n\n" + "\n".join(lines) + "\n\nTry yourself by using /daily command."

async def reset_streaks_for_inactive_players(yesterday_date: date, db: Optional[AsyncSession] = None):
    yesterday_dt = datetime.combine(yesterday_date, datetime.min.time())
    stmt = (
        update(UserStat)
        .where(UserStat.current_streak > 0)
        .where(or_(UserStat.last_guessed == None, UserStat.last_guessed < yesterday_dt))
        .values(current_streak=0)
    )

    if db is not None:
        await db.execute(stmt)
    else:
        async with get_db() as session:
            await session.execute(stmt)

async def ensure_daily_word_exists(target_date: Optional[date] = None) -> DailyWord:
    if target_date is None:
        target_date = get_current_game_date()

    async with get_db() as db:
        stmt = select(DailyWord).where(DailyWord.date == target_date)
        res = await db.execute(stmt)
        existing = res.scalar_one_or_none()
        if existing:
            return existing

        seed = seed_from_secret(settings.DAILY_WORDLE_SECRET)
        shuffled = deterministic_shuffle(seed)
        word = get_word_of_the_day(shuffled, target_date).lower()
        day_number = get_day_number(target_date)

        details = await ai_service.get_word_details(word)

        new_daily = DailyWord(
            date=target_date,
            word=word,
            day_number=day_number,
            meaning=details.get("meaning"),
            phonetic=details.get("phonetic"),
            sentence=details.get("sentence")
        )
        db.add(new_daily)
        await db.flush()
        await db.refresh(new_daily)

        yesterday = target_date - timedelta(days=1)
        await reset_streaks_for_inactive_players(yesterday, db=db)

        logger.info(f"Generated daily word '{word}' for date {target_date}")
        return new_daily
