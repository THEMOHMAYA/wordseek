from typing import Optional, List, Dict, Any, Union
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from config.constants import (
    ALLOWED_CHAT_SEARCH_KEYS,
    ALLOWED_CHAT_TIME_KEYS,
    ALLOWED_WORD_LENGTHS,
    UPDATES_CHANNEL,
    DISCUSSION_GROUP,
    SLOT_SYMBOLS
)

def format_active_button(label: str, active: bool) -> str:
    return f"« {label} »" if active else label

def generate_leaderboard_keyboard(
    search_key: str = "group",
    time_key: str = "today",
    word_length: int = 5,
    callback_prefix: str = "leaderboard",
    back_button: Optional[Dict[str, str]] = None
) -> InlineKeyboardMarkup:
    keyboard: List[List[InlineKeyboardButton]] = []

    # Row 1: Search Scope (Group / Global) + Refresh
    row1: List[InlineKeyboardButton] = []
    mid = len(ALLOWED_CHAT_SEARCH_KEYS) // 2
    for idx, key in enumerate(ALLOWED_CHAT_SEARCH_KEYS):
        if idx == mid:
            row1.append(
                InlineKeyboardButton(
                    "🔄",
                    callback_data=f"{callback_prefix} {search_key} {time_key} {word_length}"
                )
            )
        label = "This chat" if key == "group" else "Global"
        row1.append(
            InlineKeyboardButton(
                format_active_button(label, search_key == key),
                callback_data=f"{callback_prefix} {key} {time_key} {word_length}"
            )
        )
    keyboard.append(row1)

    # Row 2 & 3: Time Filters (Today, Week, Month, Year, All)
    time_buttons: List[InlineKeyboardButton] = []
    for key in ALLOWED_CHAT_TIME_KEYS:
        if key == "all":
            label = "All time"
        elif key == "today":
            label = "Today"
        else:
            label = f"This {key}"
        time_buttons.append(
            InlineKeyboardButton(
                format_active_button(label, time_key == key),
                callback_data=f"{callback_prefix} {search_key} {key} {word_length}"
            )
        )
    keyboard.append(time_buttons[:3])
    if len(time_buttons) > 3:
        keyboard.append(time_buttons[3:])

    # Row 4: Word Lengths (4 letters, 5 letters, 6 letters)
    length_row: List[InlineKeyboardButton] = []
    for length in ALLOWED_WORD_LENGTHS:
        length_row.append(
            InlineKeyboardButton(
                format_active_button(f"{length} letters", word_length == length),
                callback_data=f"{callback_prefix} {search_key} {time_key} {length}"
            )
        )
    keyboard.append(length_row)

    # Row 5: External Links (Updates & Support)
    links_row = [
        InlineKeyboardButton("📢 Updates", url=UPDATES_CHANNEL),
        InlineKeyboardButton("💬 Support", url=DISCUSSION_GROUP),
    ]
    keyboard.append(links_row)

    # Optional Back Button
    if back_button:
        keyboard.append([
            InlineKeyboardButton(back_button["text"], callback_data=back_button["callback"])
        ])

    return InlineKeyboardMarkup(keyboard)

def generate_user_selection_keyboard(users: List[Any], username: str) -> InlineKeyboardMarkup:
    keyboard: List[List[InlineKeyboardButton]] = []
    for user in users:
        label = f"{user.name} (ID: {user.id})"
        keyboard.append([
            InlineKeyboardButton(label, callback_data=f"score_select {user.id} {username}")
        ])
    return InlineKeyboardMarkup(keyboard)

def get_main_help_keyboard(should_show_admin: bool = False, active: str = "howto") -> InlineKeyboardMarkup:
    keyboard: List[List[InlineKeyboardButton]] = []

    row1 = [
        InlineKeyboardButton(format_active_button("How to Play", active == "howto"), callback_data="help_howto"),
        InlineKeyboardButton(format_active_button("Leaderboard & Scores", active == "scores"), callback_data="help_scores"),
    ]
    row2 = [
        InlineKeyboardButton(format_active_button("Group Settings", active == "group"), callback_data="help_group"),
        InlineKeyboardButton(format_active_button("Other Commands", active == "other"), callback_data="help_other"),
    ]
    keyboard.append(row1)
    keyboard.append(row2)

    if should_show_admin:
        keyboard.append([
            InlineKeyboardButton(format_active_button("👑 Admin Commands", active == "admin"), callback_data="help_admin")
        ])

    keyboard.append([
        InlineKeyboardButton("📢 Updates", url=UPDATES_CHANNEL),
        InlineKeyboardButton("💬 Support", url=DISCUSSION_GROUP),
    ])

    return InlineKeyboardMarkup(keyboard)

def build_captcha_keyboard(progress: List[str]) -> InlineKeyboardMarkup:
    keyboard: List[List[InlineKeyboardButton]] = []

    row1 = [InlineKeyboardButton(sym, callback_data=f"captcha_pick {sym}") for sym in SLOT_SYMBOLS]
    keyboard.append(row1)

    row2 = [
        InlineKeyboardButton("🗑️ Clear", callback_data="captcha_clear"),
        InlineKeyboardButton("⌫ Back", callback_data="captcha_back"),
    ]
    keyboard.append(row2)

    return InlineKeyboardMarkup(keyboard)

def get_vote_end_keyboard(chat_id: Union[str, int], current_votes: int = 1) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(f"✅ Vote to End ({current_votes}/3)", callback_data=f"vote_end {chat_id}")
    ]])

def get_mafia_lobby_keyboard(chat_id: str, topic_id: str, player_count: int, can_start: bool = False) -> InlineKeyboardMarkup:
    start_label = f"▶️ Start Game ({player_count} Players)" if can_start else f"⏳ Need {3 - player_count} More to Start"
    keyboard = [
        [
            InlineKeyboardButton("➕ Join Game", callback_data=f"mafia_join {chat_id} {topic_id}"),
            InlineKeyboardButton("❌ Leave", callback_data=f"mafia_leave {chat_id} {topic_id}"),
        ],
        [
            InlineKeyboardButton(start_label, callback_data=f"mafia_start {chat_id} {topic_id}")
        ],
        [
            InlineKeyboardButton("🛑 Cancel Lobby", callback_data=f"mafia_cancel {chat_id} {topic_id}")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_mafia_voting_keyboard(chat_id: str, topic_id: str, players: List[Dict[str, Any]], votes: Dict[str, str]) -> InlineKeyboardMarkup:
    keyboard: List[List[InlineKeyboardButton]] = []
    # Count votes per player
    vote_counts: Dict[str, int] = {}
    for target_id in votes.values():
        vote_counts[target_id] = vote_counts.get(target_id, 0) + 1

    # Pair players in 2 per row
    row: List[InlineKeyboardButton] = []
    for p in players:
        p_id = str(p["id"])
        name = p.get("name", "Player")[:12]
        cnt = vote_counts.get(p_id, 0)
        btn_text = f"🎯 {name} ({cnt})"
        row.append(InlineKeyboardButton(btn_text, callback_data=f"mafia_vote {chat_id} {topic_id} {p_id}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)

    return InlineKeyboardMarkup(keyboard)

