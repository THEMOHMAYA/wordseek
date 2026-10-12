import json
import os
import random
import logging
from typing import Dict, List, Optional
from utils.cache import cache

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def load_json_data(filename: str) -> List[str]:
    path = os.path.join(BASE_DIR, "data", filename)
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error loading {path}: {e}")
        return []

ALL_FOUR = load_json_data("all-four.json")
ALL_FIVE = load_json_data("all-five.json")
ALL_SIX = load_json_data("all-six.json")

COMMON_FOUR = load_json_data("common-four.json")
COMMON_FIVE = load_json_data("common-five.json")
COMMON_SIX = load_json_data("common-six.json")

ALL_VALID_WORDS: Dict[int, List[str]] = {
    4: ALL_FOUR,
    5: ALL_FIVE,
    6: ALL_SIX,
}

COMMON_WORDS: Dict[int, List[str]] = {
    4: COMMON_FOUR,
    5: COMMON_FIVE,
    6: COMMON_SIX,
}

class WordSelector:
    def __init__(self, history_size: int = 50, reset_threshold: int = 10, ttl_seconds: int = 7 * 24 * 3600):
        self.history_size = history_size
        self.reset_threshold = reset_threshold
        self.ttl_seconds = ttl_seconds

    def _history_key(self, chat_id: str, word_length: int) -> str:
        return f"h:{chat_id}:{word_length}"

    async def get_random_word(self, chat_id: str, word_length: int = 5) -> str:
        word_list = COMMON_WORDS.get(word_length, COMMON_FIVE)
        if not word_list:
            word_list = ALL_VALID_WORDS.get(word_length, ALL_FIVE)
            if not word_list:
                return "apple" if word_length == 5 else ("test" if word_length == 4 else "orange")

        history_key = self._history_key(chat_id, word_length)

        try:
            used_words_raw = await cache.smembers(history_key)
            used_words = {w.lower() for w in used_words_raw}
            set_size = len(used_words)

            available_words = [w for w in word_list if w.lower() not in used_words]

            if len(available_words) < self.reset_threshold:
                recent_words = list(used_words)[-max(1, self.reset_threshold // 2):]
                await cache.delete(history_key)
                if recent_words:
                    await cache.sadd(history_key, *recent_words)
                return await self.get_random_word(chat_id, word_length)

            selected = random.choice(available_words).lower()

            await cache.sadd(history_key, selected)
            await cache.expire(history_key, self.ttl_seconds)

            if set_size >= self.history_size:
                trim_count = max(1, int(self.history_size * 0.2))
                await cache.spop(history_key, trim_count)

            return selected
        except Exception as e:
            logger.error(f"Error selecting word, using fallback: {e}")
            return random.choice(word_list).lower()

    async def reset_chat(self, chat_id: str, word_length: int = 5):
        await cache.delete(self._history_key(chat_id, word_length))

word_selector = WordSelector()
