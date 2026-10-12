import json
from datetime import datetime
from typing import List, Optional
from sqlalchemy import (
    Column,
    Integer,
    BigInteger,
    String,
    Text,
    Boolean,
    DateTime,
    Date,
    ForeignKey,
    Index,
    func
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

class User(Base):
    __tablename__ = "users"

    id = Column(String(64), primary_key=True)  # Telegram User ID string
    name = Column(String(255), nullable=False)
    username = Column(String(255), nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class AuthorizedUser(Base):
    __tablename__ = "authorized_users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(64), nullable=False, index=True)
    chat_id = Column(String(64), nullable=False, index=True)
    authorized_by = Column(String(64), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class BannedUser(Base):
    __tablename__ = "banned_users"

    user_id = Column(String(64), primary_key=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class BroadcastChat(Base):
    __tablename__ = "broadcast_chats"

    id = Column(String(64), primary_key=True)  # Chat ID string
    name = Column(String(255), nullable=True)
    username = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class ChatGameTopic(Base):
    __tablename__ = "chat_game_topics"

    id = Column(Integer, primary_key=True, autoincrement=True)
    chat_id = Column(String(64), nullable=False, index=True)
    topic_id = Column(String(64), nullable=False, index=True)
    name = Column(String(255), nullable=True)
    icon_custom_emoji_id = Column(String(255), nullable=True)
    allowed_lengths_json = Column(Text, default="[4, 5, 6]", nullable=False)
    should_recreate_on_expire = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    @property
    def allowed_lengths(self) -> List[int]:
        try:
            return json.loads(self.allowed_lengths_json)
        except Exception:
            return [4, 5, 6]

    @allowed_lengths.setter
    def allowed_lengths(self, val: List[int]):
        self.allowed_lengths_json = json.dumps(val)


class Game(Base):
    __tablename__ = "games"

    id = Column(Integer, primary_key=True, autoincrement=True)
    active_chat = Column(String(64), nullable=False, index=True)
    topic_id = Column(String(64), default="general", nullable=False, index=True)
    word = Column(String(16), nullable=False)
    started_by = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class Guess(Base):
    __tablename__ = "guesses"

    id = Column(Integer, primary_key=True, autoincrement=True)
    game_id = Column(Integer, ForeignKey("games.id", ondelete="CASCADE"), nullable=False, index=True)
    chat_id = Column(String(64), nullable=False, index=True)
    guess = Column(String(16), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class Leaderboard(Base):
    __tablename__ = "leaderboard"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(64), nullable=False, index=True)
    chat_id = Column(String(64), nullable=False, index=True)
    score = Column(Integer, nullable=False)
    word_length = Column(String(4), default="5", nullable=False, index=True)  # "4", "5", "6"
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class DailyWord(Base):
    __tablename__ = "daily_words"

    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(Date, nullable=False, unique=True, index=True)
    word = Column(String(16), nullable=False)
    day_number = Column(Integer, default=1, nullable=False)
    meaning = Column(Text, nullable=True)
    phonetic = Column(String(255), nullable=True)
    sentence = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class DailyGuess(Base):
    __tablename__ = "daily_guesses"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(64), nullable=False, index=True)
    daily_word_id = Column(Integer, ForeignKey("daily_words.id", ondelete="CASCADE"), nullable=False, index=True)
    guess = Column(String(16), nullable=False)
    attempt_number = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class UserStat(Base):
    __tablename__ = "user_stats"

    user_id = Column(String(64), primary_key=True)
    current_streak = Column(Integer, default=0, nullable=False)
    highest_streak = Column(Integer, default=0, nullable=False)
    last_guessed = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
