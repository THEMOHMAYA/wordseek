# WordSeek (Python Edition) 🎮

A feature-rich, competitive Wordle-style Telegram Game Bot completely rewritten in **Python**.
Play multiplayer Wordle in groups or private chats, track your global and group rankings on interactive leaderboards, enjoy daily challenges with custom-rendered Wordle images, and manage games with powerful group admin tools!

---

## 🌟 Key Features

- **Multiplayer Wordle (Group & Private)**:
  - Supports 4, 5, and 6 letter word guessing modes (`/new`, `/new4`, `/new5`, `/new6`).
  - High-precision dictionary validation for standard English words.
  - Stylish fancy feedback with colored emoji indicators (`🟩` Correct spot, `🟨` Wrong spot, `🟥` Not in word) and attempts count (`x/30`).
  - Automatic leaderboard scoring (`30 - total_attempts`) awarded to the winner.
  - Interactive `/end` command with immediate admin termination or 3-player voting threshold for group members.

- **Daily Wordle & Streaks (`/daily`)**:
  - Daily Wordle challenge in direct messages (6 attempts).
  - High-resolution Wordle grid image generation using Pillow.
  - Daily streaks tracking (Current streak, Highest streak).
  - AI-powered word meaning, IPA pronunciation phonetic, and example sentences.
  - Telegram inline share format (`WordSeek <day> <guesses>/6`).

- **Interactive Leaderboards & User Scores**:
  - `/leaderboard [global|group] [today|week|month|year|all] [4|5|6]`
  - `/score [@username|user_id] [scope] [period] [length]`
  - Real-time inline filter buttons with instant updates.

- **Forum Topic & Admin Tools**:
  - Restrict games to specific forum topics: `/setgametopic`, `/unsetgametopic`, `/recreatetopic`.
  - Allowed word lengths per topic: `/allowonlylen 4 5 6`.
  - Delegate game ending permission: `/seekauth @username`, `/seekauth list`, `/seekauth remove`.
  - Moderation & Stats: `/ban`, `/unban`, `/transfer`, `/stats`, `/broadcast`, `/captcha`, `/id`, `/track`.

---

## 🚀 Setup & Installation

### 1. Requirements
- Python 3.10+
- Telegram Bot Token (from [@BotFather](https://t.me/BotFather))

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Configure Environment
Create a `.env` file in the root folder:
```env
BOT_TOKEN=your_bot_token_from_botfather
ADMIN_USERS=123456789
DATABASE_URL=sqlite+aiosqlite:///wordseek.db
REDIS_URI=redis://127.0.0.1:6379
TIME_ZONE=UTC
DAILY_WORDLE_SECRET=your-daily-wordle-secret-key
```
*(Note: Redis is optional. If Redis is not running, the bot automatically switches to its high-speed in-memory cache!)*

### 4. Run the Bot
```bash
python run.py
```

---

## 📜 Bot Commands List

### Gameplay Commands
| Command | Description |
|---|---|
| `/start` | Welcome message and quick start links |
| `/help` | Interactive tabbed help guide |
| `/new` | Start a new 5-letter game |
| `/new4` | Start a new 4-letter game |
| `/new5` | Start a new 5-letter game |
| `/new6` | Start a new 6-letter game |
| `/end` | End the current active game |
| `/daily` | Play WordSeek of the Day (DM only) |
| `/pausedaily` | Pause daily mode to play regular games |

### Stats & Leaderboards
| Command | Description |
|---|---|
| `/leaderboard` | View rankings with scope/time/length filters |
| `/score` | View your personal or mentioned user's score |
| `/myscore` | Redirects to `/score` |

### Group Admin Commands
| Command | Description |
|---|---|
| `/seekauth` | Authorize members to end games without voting |
| `/setgametopic` | Restrict games to current forum topic |
| `/unsetgametopic` | Remove forum topic restriction |
| `/allowonlylen` | Restrict allowed word lengths in topic (e.g. `/allowonlylen 5 4`) |
| `/recreatetopic` | Toggle auto topic recreation on expire |

### Bot Owner Commands
| Command | Description |
|---|---|
| `/stats` | View VPS, CPU, RAM, and game statistics |
| `/ban` / `/unban` | Ban or unban users globally |
| `/transfer` | Transfer scores between users |
| `/broadcast` | Broadcast replied message to all users & chats |
| `/captcha` | Send slot-machine verification to a user |
| `/id` | Detailed message & user metadata |
| `/track` / `/untrack` | Monitor chat message activity |

---

## 📄 License
This project is open-source under the MIT License.
