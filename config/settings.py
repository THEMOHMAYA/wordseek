import os
from datetime import datetime, date
from typing import List, Optional
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from dotenv import load_dotenv

load_dotenv()

class Settings(BaseSettings):
    BOT_TOKEN: str = Field(default="", description="Telegram Bot Token from @BotFather")
    DATABASE_URL: str = Field(
        default="sqlite+aiosqlite:///wordseek.db", 
        description="Database URL (PostgreSQL or SQLite)"
    )
    ENVIRONMENT: str = Field(default="development", description="development or production")
    ADMIN_USERS_RAW: str = Field(default="", alias="ADMIN_USERS")
    REDIS_URI: str = Field(default="redis://127.0.0.1:6379")
    CUSTOM_API_ROOT: str = Field(default="https://api.telegram.org")
    LOGS_CHANNEL_RAW: Optional[str] = Field(default=None, alias="LOGS_CHANNEL")
    TIME_ZONE: str = Field(default="UTC")
    DAILY_WORDLE_START_DATE_STR: str = Field(default="2025-01-01", alias="DAILY_WORDLE_START_DATE")
    DAILY_WORDLE_SECRET: str = Field(default="wordseek-secret-key-2025")
    GEMINI_API_KEYS_RAW: str = Field(default="", alias="GEMINI_API_KEYS")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    @property
    def LOGS_CHANNEL(self) -> Optional[int]:
        if not self.LOGS_CHANNEL_RAW:
            return None
        clean = self.LOGS_CHANNEL_RAW.strip()
        if clean and (clean.isdigit() or clean.startswith("-") and clean[1:].isdigit()):
            return int(clean)
        return None

    @property
    def ADMIN_USERS(self) -> List[int]:
        if not self.ADMIN_USERS_RAW:
            return []
        ids = []
        for part in self.ADMIN_USERS_RAW.replace(" ", ",").split(","):
            part = part.strip()
            if part and (part.isdigit() or (part.startswith("-") and part[1:].isdigit())):
                ids.append(int(part))
        return ids

    @property
    def GEMINI_API_KEYS(self) -> List[str]:
        if not self.GEMINI_API_KEYS_RAW:
            return []
        return [k.strip() for k in self.GEMINI_API_KEYS_RAW.replace(",", " ").split(" ") if k.strip()]

    @property
    def DAILY_WORDLE_START_DATE(self) -> date:
        try:
            return datetime.strptime(self.DAILY_WORDLE_START_DATE_STR, "%Y-%m-%d").date()
        except Exception:
            return date(2025, 1, 1)

    @property
    def ASYNC_DATABASE_URL(self) -> str:
        url = self.DATABASE_URL
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql+asyncpg://", 1)
        elif url.startswith("postgresql://") and not url.startswith("postgresql+asyncpg://"):
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        elif url.startswith("sqlite://") and not url.startswith("sqlite+aiosqlite://"):
            url = url.replace("sqlite://", "sqlite+aiosqlite://", 1)
        return url

settings = Settings()
