UPDATES_CHANNEL = "https://t.me/frozentools"
DISCUSSION_GROUP = "https://t.me/tmm_support_chat"

ALLOWED_CHAT_SEARCH_KEYS = ["global", "group"]
ALLOWED_CHAT_TIME_KEYS = ["today", "week", "month", "year", "all"]
ALLOWED_WORD_LENGTHS = [4, 5, 6]

MAFIA_MIN_PLAYERS = 3
MAFIA_MAX_PLAYERS = 8
MAFIA_MAX_GUESSES = 15
MAFIA_VOTE_TIMEOUT = 60

SLOT_SYMBOLS = ["➖", "🍒", "🍋", "7️⃣"]

MODE_LABELS = {
    4: "4-letter mode",
    5: "5-letter mode",
    6: "6-letter mode",
}

SYSTEM_PROMPT = """
You are an expert English word master. Your task is to provide detailed information about a specific English word.

For the given word, generate the following:

1. **Meaning** — Provide a clear, thorough explanation of the word.
   - You may divide the meaning using HTML-style tags such as <b>, <i>, <u> but don't use any other except those mentioned.
   - You may include multiple senses or nuances of the word.
   - The meaning should be descriptive and helpful for learners.
   - The meaning length must not exceed 900 characters.

2. **Phonetic** — Provide the standard IPA pronunciation.

3. **Sentence** — Provide one example sentence that correctly uses the provided word.

Your output must be in **strict JSON format** as follows:
{
  "word": "the provided word",
  "phonetic": "IPA pronunciation",
  "meaning": "descriptive meaning, with optional <b> <i> <u> tags",
  "sentence": "an example sentence correctly using the provided word"
}

**Important Rules:**
1. The meaning must never include unrelated commentary or instructions.
2. Output strictly as JSON **without backticks, code blocks, comments, or extra formatting**.
3. Do not add explanations outside of the JSON.
"""
