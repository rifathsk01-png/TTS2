import os
import json
import html
import logging
import asyncio
from pathlib import Path
from datetime import datetime, timezone
from collections import Counter
from tempfile import NamedTemporaryFile
from typing import Dict, Any, Optional

from gtts import gTTS
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.constants import ChatAction, ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# =========================
# Config
# =========================

BOT_TOKEN = os.getenv("BOTTOKEN")
ADMIN_USERNAME = "Sefuax"

BASE_DIR = Path(__file__).resolve().parent
USERS_FILE = BASE_DIR / "users.json"
VOICE_DIR = BASE_DIR / "voices"

DEFAULT_DAILY_LIMIT = 20
MAX_TEXT_LENGTH = 500
HISTORY_LIMIT = 20

LANGUAGE_OPTIONS = {
    "bn": "Bangla",
    "en": "English",
}

GENDER_OPTIONS = {
    "male": "Male",
    "female": "Female",
}

GTTS_LANG_MAP = {
    "bn": "bn",
    "en": "en",
}

# =========================
# Logging
# =========================

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger(__name__)

# =========================
# File Lock
# =========================

users_lock = asyncio.Lock()


# =========================
# Storage Helpers
# =========================

def today_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def ensure_files() -> None:
    VOICE_DIR.mkdir(parents=True, exist_ok=True)

    if not USERS_FILE.exists():
        USERS_FILE.write_text("{}", encoding="utf-8")


def load_users_sync() -> Dict[str, Any]:
    ensure_files()

    try:
        with USERS_FILE.open("r", encoding="utf-8") as file:
            data = json.load(file)

        if isinstance(data, dict):
            return data

        return {}

    except (json.JSONDecodeError, OSError):
        logger.exception("Failed to load users.json")
        return {}


def save_users_sync(users: Dict[str, Any]) -> None:
    ensure_files()

    temp_file = USERS_FILE.with_suffix(".json.tmp")

    with temp_file.open("w", encoding="utf-8") as file:
        json.dump(users, file, ensure_ascii=False, indent=2)

    temp_file.replace(USERS_FILE)


async def load_users() -> Dict[str, Any]:
    async with users_lock:
        return await asyncio.to_thread(load_users_sync)


async def save_users(users: Dict[str, Any]) -> None:
    async with users_lock:
        await asyncio.to_thread(save_users_sync, users)


async def update_users(mutator):
    async with users_lock:
        users = await asyncio.to_thread(load_users_sync)
        result = mutator(users)
        await asyncio.to_thread(save_users_sync, users)
        return result


def is_admin_user(update: Update) -> bool:
    user = update.effective_user
    if not user or not user.username:
        return False

    return user.username.lower() == ADMIN_USERNAME.lower()


def normalize_username(username: str) -> str:
    return username.strip().lstrip("@").lower()


def create_default_user(user_id: int, username: Optional[str]) -> Dict[str, Any]:
    return {
        "user_id": user_id,
        "username": username or "",
        "language": "",
        "gender": "",
        "last_text": "",
        "total_requests": 0,
        "history": [],
        "daily_count": 0,
        "last_date": today_str(),
        "custom_limit": DEFAULT_DAILY_LIMIT,
    }


def get_or_create_user(users: Dict[str, Any], user_id: int, username: Optional[str]) -> Dict[str, Any]:
    key = str(user_id)

    if key not in users:
        users[key] = create_default_user(user_id, username)
    else:
        users[key].setdefault("user_id", user_id)
        users[key].setdefault("username", username or "")
        users[key].setdefault("language", "")
        users[key].setdefault("gender", "")
        users[key].setdefault("last_text", "")
        users[key].setdefault("total_requests", 0)
        users[key].setdefault("history", [])
        users[key].setdefault("daily_count", 0)
        users[key].setdefault("last_date", today_str())
        users[key].setdefault("custom_limit", DEFAULT_DAILY_LIMIT)

        if username:
            users[key]["username"] = username

    reset_daily_if_needed(users[key])
    return users[key]


def reset_daily_if_needed(user_data: Dict[str, Any]) -> None:
    current_date = today_str()

    if user_data.get("last_date") != current_date:
        user_data["last_date"] = current_date
        user_data["daily_count"] = 0


def build_language_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("বাংলা", callback_data="lang:bn"),
                InlineKeyboardButton("English", callback_data="lang:en"),
            ]
        ]
    )


def build_gender_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Male", callback_data="gender:male"),
                InlineKeyboardButton("Female", callback_data="gender:female"),
            ]
        ]
    )


def most_used_language(users: Dict[str, Any]) -> str:
    langs = [
        user.get("language")
        for user in users.values()
        if user.get("language") in LANGUAGE_OPTIONS
    ]

    if not langs:
        return "N/A"

    lang_code, count = Counter(langs).most_common(1)[0]
    return f"{LANGUAGE_OPTIONS.get(lang_code, lang_code)} ({count})"


def today_total_generated(users: Dict[str, Any]) -> int:
    current_date = today_str()

    return sum(
        int(user.get("daily_count", 0))
        for user in users.values()
        if user.get("last_date") == current_date
    )


def find_user_by_username(users: Dict[str, Any], username: str) -> Optional[Dict[str, Any]]:
    target = normalize_username(username)

    for user_data in users.values():
        stored_username = normalize_username(str(user_data.get("username", "")))

        if stored_username == target:
            return user_data

    return None


# =========================
# TTS Helper
# =========================

def generate_tts_file(text: str, lang_code: str, user_id: int) -> Path:
    gtts_lang = GTTS_LANG_MAP.get(lang_code, "en")

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
    filename = f"voice_{user_id}_{timestamp}.ogg"
    output_path = VOICE_DIR / filename

    tts = gTTS(text=text, lang=gtts_lang)
    tts.save(str(output_path))

    return output_path


# =========================
# Commands
# =========================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user

    if not user or not update.message:
        return

    def mutator(users):
        get_or_create_user(users, user.id, user.username)

    await update_users(mutator)

    await update.message.reply_text(
        "স্বাগতম! Welcome!\n\nPlease select your language:",
        reply_markup=build_language_keyboard(),
    )


async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user

    if not user or not update.message:
        return

    users = await load_users()
    user_data = get_or_create_user(users, user.id, user.username)
    history = user_data.get("history", [])[-5:]

    if not history:
        await update.message.reply_text("No history found.")
        return

    lines = ["Your last 5 texts:"]

    for index, item in enumerate(reversed(history), start=1):
        escaped_text = html.escape(str(item))
        lines.append(f"{index}. {escaped_text}")

    await update.message.reply_text(
        "\n".join(lines),
        parse_mode=ParseMode.HTML,
    )


async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return

    if not is_admin_user(update):
        await update.message.reply_text("Unauthorized.")
        return

    users = await load_users()

    message = (
        "Admin Panel\n\n"
        f"Total users: {len(users)}\n"
        f"Most used language: {most_used_language(users)}\n"
        f\"Today's total generated voices: {today_total_generated(users)}\"
    )

    await update.message.reply_text(message)


async def add_limit_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return

    if not is_admin_user(update):
        await update.message.reply_text("Unauthorized.")
        return

    if len(context.args) != 2:
        await update.message.reply_text("Usage: /add {username} {limit}")
        return

    username = context.args[0]
    limit_raw = context.args[1]

    try:
        new_limit = int(limit_raw)

        if new_limit < 1:
            raise ValueError

    except ValueError:
        await update.message.reply_text("Limit must be a positive number.")
        return

    def mutator(users):
        target_user = find_user_by_username(users, username)

        if not target_user:
            return None

        target_user["custom_limit"] = new_limit
        return target_user

    target_user = await update_users(mutator)

    if not target_user:
        await update.message.reply_text("User not found. User must start the bot first.")
        return

    await update.message.reply_text(
        f"Updated @{target_user.get('username')} daily limit to {new_limit}."
    )


async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return

    if not is_admin_user(update):
        await update.message.reply_text("Unauthorized.")
        return

    message = update.message.text.partition(" ")[2].strip()

    if not message:
        await update.message.reply_text("Usage: /broadcast {message}")
        return

    users = await load_users()

    sent = 0
    failed = 0

    for user_id in list(users.keys()):
        try:
            await context.bot.send_message(
                chat_id=int(user_id),
                text=message,
            )
            sent += 1
            await asyncio.sleep(0.05)

        except Exception:
            failed += 1
            logger.exception("Broadcast failed for user_id=%s", user_id)

    await update.message.reply_text(
        f"Broadcast completed.\nSent: {sent}\nFailed: {failed}"
    )


# =========================
# Callback Handlers
# =========================

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user = update.effective_user

    if not query or not user:
        return

    await query.answer()

    data = query.data or ""

    if data.startswith("lang:"):
        lang_code = data.split(":", 1)[1]

        if lang_code not in LANGUAGE_OPTIONS:
            await query.edit_message_text("Invalid language selected.")
            return

        def mutator(users):
            user_data = get_or_create_user(users, user.id, user.username)
            user_data["language"] = lang_code
            return user_data

        await update_users(mutator)

        await query.edit_message_text(
            "Language selected.\n\nPlease select gender:",
            reply_markup=build_gender_keyboard(),
        )
        return

    if data.startswith("gender:"):
        gender = data.split(":", 1)[1]

        if gender not in GENDER_OPTIONS:
            await query.edit_message_text("Invalid gender selected.")
            return

        def mutator(users):
            user_data = get_or_create_user(users, user.id, user.username)
            user_data["gender"] = gender
            return user_data

        await update_users(mutator)

        await query.edit_message_text(
            "Gender selected.\n\nNow send me your text. Max 500 characters."
        )
        return

    await query.edit_message_text("Invalid option.")


# =========================
# Text Handler
# =========================

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    message = update.message

    if not user or not message or not message.text:
        return

    text = message.text.strip()

    if not text:
        await message.reply_text("Please send valid text.")
        return

    if len(text) > MAX_TEXT_LENGTH:
        await message.reply_text("Text is too long. Maximum 500 characters allowed.")
        return

    def check_and_prepare(users):
        user_data = get_or_create_user(users, user.id, user.username)

        if not user_data.get("language"):
            return {
                "status": "missing_language",
                "user_data": user_data,
            }

        if not user_data.get("gender"):
            return {
                "status": "missing_gender",
                "user_data": user_data,
            }

        if normalize_username(user.username or "") != ADMIN_USERNAME.lower():
            limit = int(user_data.get("custom_limit", DEFAULT_DAILY_LIMIT))
            daily_count = int(user_data.get("daily_count", 0))

            if daily_count >= limit:
                return {
                    "status": "limit_exceeded",
                    "user_data": user_data,
                }

        return {
            "status": "ok",
            "user_data": user_data,
        }

    result = await update_users(check_and_prepare)
    status = result["status"]
    user_data = result["user_data"]

    if status == "missing_language":
        await message.reply_text(
            "Please select your language first:",
            reply_markup=build_language_keyboard(),
        )
        return

    if status == "missing_gender":
        await message.reply_text(
            "Please select your gender first:",
            reply_markup=build_gender_keyboard(),
        )
        return

    if status == "limit_exceeded":
        await message.reply_text("আজকের limit শেষ, কাল আবার এসো।")
        return

    await message.chat.send_action(ChatAction.RECORD_VOICE)

    voice_path: Optional[Path] = None

    try:
        voice_path = await asyncio.to_thread(
            generate_tts_file,
            text,
            user_data.get("language", "en"),
            user.id,
        )

        with voice_path.open("rb") as voice_file:
            await message.reply_voice(voice=voice_file)

        def update_success(users):
            updated_user = get_or_create_user(users, user.id, user.username)
            updated_user["last_text"] = text
            updated_user["total_requests"] = int(updated_user.get("total_requests", 0)) + 1

            if normalize_username(user.username or "") != ADMIN_USERNAME.lower():
                updated_user["daily_count"] = int(updated_user.get("daily_count", 0)) + 1

            history = updated_user.get("history", [])
            history.append(text)
            updated_user["history"] = history[-HISTORY_LIMIT:]

        await update_users(update_success)

    except Exception:
        logger.exception("Failed to generate or send voice")
        await message.reply_text("Voice generation failed. Please try again later.")

    finally:
        if voice_path and voice_path.exists():
            try:
                voice_path.unlink()
            except OSError:
                logger.exception("Failed to delete temporary voice file")


# =========================
# Error Handler
# =========================

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.exception("Unhandled error", exc_info=context.error)

    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "Something went wrong. Please try again later."
            )
        except Exception:
            logger.exception("Failed to send error message")


# =========================
# Main
# =========================

def main() -> None:
    if not BOT_TOKEN:
        raise RuntimeError("BOTTOKEN environment variable is missing.")

    ensure_files()

    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("history", history_command))
    application.add_handler(CommandHandler("admin", admin_command))
    application.add_handler(CommandHandler("add", add_limit_command))
    application.add_handler(CommandHandler("broadcast", broadcast_command))

    application.add_handler(CallbackQueryHandler(callback_handler))

    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler)
    )

    application.add_error_handler(error_handler)

    logger.info("Bot started")
    application.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
    )


if __name__ == "__main__":
    main()

