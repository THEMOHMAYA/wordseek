import json
import re
import logging
import httpx
from typing import Optional, Dict, Any
from config.settings import settings
from config.constants import SYSTEM_PROMPT

logger = logging.getLogger(__name__)

ALLOWED_TAGS = ["b", "i", "u"]

def sanitize_meaning(text: str) -> str:
    def replace_tag(match):
        tag_name = match.group(1).lower()
        if tag_name in ALLOWED_TAGS:
            return f"<{match.group(1)}>" if not match.group(0).startswith("</") else f"</{match.group(1)}>"
        return ""
    return re.sub(r"</?([a-zA-Z0-9]+)([^>]*)>", replace_tag, text)

class AIService:
    def __init__(self):
        self.api_keys = list(settings.GEMINI_API_KEYS)
        self.models = [
            "gemini-2.5-flash",
            "gemini-2.0-flash",
            "gemini-1.5-flash",
        ]

    async def get_word_details(self, word: str) -> Dict[str, str]:
        """Fetches meaning, phonetic IPA, and example sentence for the given word."""
        if not self.api_keys:
            return self._get_fallback_details(word)

        prompt = f"{SYSTEM_PROMPT}\n\n**THE WORD TO CREATE HINTS FOR:** {word}"

        for key in self.api_keys:
            for model in self.models:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
                payload = {
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {"temperature": 0.3}
                }
                try:
                    async with httpx.AsyncClient(timeout=10.0) as client:
                        resp = await client.post(url, json=payload)
                        if resp.status_code == 200:
                            data = resp.json()
                            candidate = data.get("candidates", [{}])[0]
                            content_text = candidate.get("content", {}).get("parts", [{}])[0].get("text", "")
                            cleaned = re.sub(r"```(?:json)?|```", "", content_text).strip()
                            parsed = json.loads(cleaned)
                            return {
                                "word": parsed.get("word", word).lower(),
                                "phonetic": parsed.get("phonetic", ""),
                                "meaning": sanitize_meaning(parsed.get("meaning", f"An English word: {word}")),
                                "sentence": parsed.get("sentence", f"The word '{word}' was used in a sentence.")
                            }
                except Exception as e:
                    logger.debug(f"Gemini API attempt failed with model {model}: {e}")
                    continue

        return self._get_fallback_details(word)

    def _get_fallback_details(self, word: str) -> Dict[str, str]:
        return {
            "word": word.lower(),
            "phonetic": f"/{word.lower()}/",
            "meaning": f"<b>{word.capitalize()}</b> is a standard English dictionary word.",
            "sentence": f"She learned the word '{word}' while playing WordSeek."
        }

ai_service = AIService()
