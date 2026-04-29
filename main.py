import os
import json
import logging
import asyncio
from datetime import datetime, date
from pathlib import Path
from io import BytesIO

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardRemove,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)
from gtts import gTTS

# ─── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ─── Config ────────────────────────────────────────────────────────────────────
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
ADMIN_USERNAME = "Sefuax"
USERS_FILE = Path("users.json")
DEFAULT_DAILY_LIMIT = 20

# ─── Data Layer ────────────────────────────────────────────────────────────────

def load_users() -> dict:
    if USERS_FILE.exists():
        try:
            with open(USERS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {}
    return {}


def save_users(data: dict) -> None:
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_user(uid: str) -> dict:
    users = load_users()
    if uid not in users:
        users[uid] = {
            "user_id": uid,
            "username": "",
            "language": None,
            "gender": None,
            "last_text": "",
            "total_requests": 0,
            "history": [],
            "daily_count": 0,
            "last_date": "",
            "daily_limit": DEFAULT_DAILY_LIMIT,
            "state": "start",
        }
        save_users(users)
    return users[uid]


def update_user(uid: str, data: dict) -> None:
    users = load_users()
    if uid not in users:
        users[uid] = {}
    users[uid].update(data)
    save_users(users)


def reset_daily_if_needed(uid: str) -> dict:
    user = get_user(uid)
    today = str(date.today())
    if user.get("last_date") != today:
        update_user(uid, {"daily_count": 0, "last_date": today})
        user["daily_count"] = 0
        user["last_date"] = today
    return user

# ─── Helpers ───────────────────────────────────────────────────────────────────

def is_admin(update: Update) -> bool:
    username = update.effective_user.username or ""
    return username.lower() == ADMIN_USERNAME.lower()


def lang_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🇧🇩 বাংলা", callback_data="lang_bn"),
            InlineKeyboardButton("🇬🇧 English", callback_data="lang_en"),
        ]
    ])


def gender_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("👨 Male", callback_data="gender_male"),
            InlineKeyboardButton("👩 Female", callback_data="gender_female"),
        ]
    ])


def make_tts(text: str, lang: str, gender: str) -> BytesIO:
    """
    gTTS doesn't natively support male/female voices.
    We simulate it via pitch-like tld tricks and slow parameter.
    Male  → tld='com'  (default, slightly deeper feel)
    Female → tld='com.au' (slightly softer accent)
    For proper voice separation we use different TLDs.
    """
    tld_map = {
        ("bn", "male"):   ("com",    False),
        ("bn", "female"): ("com",    True),   # slow=True gives softer tone
        ("en", "male"):   ("com",    False),
        ("en", "female"): ("com.au", False),
    }
    tld, slow = tld_map.get((lang, gender), ("com", False))
    tts = gTTS(text=text, lang=lang, tld=tld, slow=slow)
    audio = BytesIO()
    tts.write_to_fp(audio)
    audio.seek(0)
    audio.name = "voice.mp3"
    return audio


def today_voice_count(users: dict) -> int:
    today = str(date.today())
    total = 0
    for u in users.values():
        if u.get("last_date") == today:
            total += u.get("daily_count", 0)
    return total

# ─── Handlers ──────────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    username = update.effective_user.username or ""
    update_user(uid, {"username": username, "state": "select_lang"})

    await update.message.reply_text(
        "👋 *স্বাগতম! Welcome to TTS Bot!*\n\n"
        "আমি তোমার লেখাকে Voice এ রূপান্তর করতে পারি।\n"
        "I can convert your text into voice.\n\n"
        "প্রথমে ভাষা বেছে নাও / Choose your language:",
        parse_mode="Markdown",
        reply_markup=lang_keyboard(),
    )


async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = str(query.from_user.id)
    data = query.data

    # ── Language selection ──
    if data.startswith("lang_"):
        lang = data.split("_")[1]  # "bn" or "en"
        update_user(uid, {"language": lang, "state": "select_gender"})

        lang_label = "বাংলা 🇧🇩" if lang == "bn" else "English 🇬🇧"
        await query.edit_message_text(
            f"✅ ভাষা নির্বাচিত: *{lang_label}*\n\n"
            "এখন gender বেছে নাও / Choose your gender:",
            parse_mode="Markdown",
            reply_markup=gender_keyboard(),
        )

    # ── Gender selection ──
    elif data.startswith("gender_"):
        gender = data.split("_")[1]  # "male" or "female"
        update_user(uid, {"gender": gender, "state": "ready"})

        gender_label = "👨 Male" if gender == "male" else "👩 Female"
        user = get_user(uid)
        lang = user.get("language", "bn")

        if lang == "bn":
            msg = (
                f"✅ Gender নির্বাচিত: *{gender_label}*\n\n"
                "🎉 সব ঠিকঠাক! এখন যেকোনো টেক্সট পাঠাও, আমি সেটা Voice এ পাঠাবো। 🔊\n\n"
                "⚙️ পরে settings বদলাতে /start আবার দাও।"
            )
        else:
            msg = (
                f"✅ Gender selected: *{gender_label}*\n\n"
                "🎉 All set! Send any text and I'll convert it to voice. 🔊\n\n"
                "⚙️ Use /start again to change settings."
            )

        await query.edit_message_text(msg, parse_mode="Markdown")


async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    user = reset_daily_if_needed(uid)
    state = user.get("state", "start")

    # Not set up yet
    if state != "ready":
        await update.message.reply_text(
            "আগে /start দিয়ে setup করো। / Please run /start first."
        )
        return

    text = update.message.text.strip()
    if not text:
        return

    lang = user.get("language", "bn")
    gender = user.get("gender", "male")
    daily_limit = user.get("daily_limit", DEFAULT_DAILY_LIMIT)
    daily_count = user.get("daily_count", 0)

    # Daily limit check (admin = unlimited)
    if not is_admin(update) and daily_count >= daily_limit:
        if lang == "bn":
            await update.message.reply_text(
                "⛔ আজকের limit শেষ, কাল আবার এসো! 😊\n"
                f"(দৈনিক সীমা: {daily_limit}টি voice)"
            )
        else:
            await update.message.reply_text(
                f"⛔ You've reached today's limit ({daily_limit} voices). Come back tomorrow! 😊"
            )
        return

    # Generate voice
    processing_msg = await update.message.reply_text("🎙️ তৈরি হচ্ছে... / Generating voice...")

    try:
        audio = make_tts(text, lang, gender)
    except Exception as e:
        logger.error(f"TTS error: {e}")
        await processing_msg.delete()
        await update.message.reply_text("❌ Voice তৈরিতে সমস্যা হয়েছে। আবার চেষ্টা করো।")
        return

    await processing_msg.delete()
    await update.message.reply_voice(voice=audio)

    # Update history (keep last 5)
    history = user.get("history", [])
    history.append({
        "text": text[:200],
        "lang": lang,
        "gender": gender,
        "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
    })
    history = history[-5:]

    update_user(uid, {
        "last_text": text[:200],
        "total_requests": user.get("total_requests", 0) + 1,
        "daily_count": daily_count + 1,
        "history": history,
        "last_date": str(date.today()),
    })


async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    user = get_user(uid)
    history = user.get("history", [])
    lang = user.get("language", "bn")

    if not history:
        msg = "📭 কোনো history নেই।" if lang == "bn" else "📭 No history found."
        await update.message.reply_text(msg)
        return

    lines = ["📜 *তোমার শেষ ৫টি voice request:*\n" if lang == "bn"
             else "📜 *Your last 5 voice requests:*\n"]
    for i, item in enumerate(reversed(history), 1):
        lines.append(
            f"{i}. `{item['text'][:80]}`\n"
            f"   🌐 {item['lang'].upper()} | {'👨' if item['gender'] == 'male' else '👩'} {item['gender'].title()}"
            f" | 🕒 {item['time']}\n"
        )

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        await update.message.reply_text("⛔ তুমি admin নও।")
        return

    users = load_users()
    total_users = len(users)
    lang_count = {"bn": 0, "en": 0, "other": 0}
    total_requests = 0

    for u in users.values():
        lang = u.get("language") or "other"
        if lang in lang_count:
            lang_count[lang] += 1
        else:
            lang_count["other"] += 1
        total_requests += u.get("total_requests", 0)

    today_count = today_voice_count(users)

    msg = (
        "📊 *Admin Dashboard*\n\n"
        f"👥 মোট User: *{total_users}*\n"
        f"🎙️ মোট Voice Generated: *{total_requests}*\n"
        f"📅 আজকের Voice Count: *{today_count}*\n\n"
        "🌐 *Language Usage:*\n"
        f"  • বাংলা: {lang_count['bn']} জন\n"
        f"  • English: {lang_count['en']} জন\n"
        f"  • অন্যান্য: {lang_count['other']} জন\n\n"
        f"📋 *Commands:*\n"
        f"  `/add @username {{limit}}` — দৈনিক limit বাড়াও\n"
        f"  `/broadcast {{message}}` — সবাইকে message পাঠাও"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")


async def add_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/add @username {limit}"""
    if not is_admin(update):
        await update.message.reply_text("⛔ তুমি admin নও।")
        return

    args = context.args
    if len(args) < 2:
        await update.message.reply_text(
            "❌ সঠিক format: `/add @username {limit}`\nউদাহরণ: `/add @Sefuax 50`",
            parse_mode="Markdown",
        )
        return

    target_username = args[0].lstrip("@").lower()
    try:
        new_limit = int(args[1])
        if new_limit < 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ Limit অবশ্যই একটি positive সংখ্যা হতে হবে।")
        return

    users = load_users()
    matched_uid = None
    for uid, u in users.items():
        if (u.get("username") or "").lower() == target_username:
            matched_uid = uid
            break

    if not matched_uid:
        await update.message.reply_text(
            f"❌ @{target_username} নামের কোনো user পাওয়া যায়নি।\n"
            "User কে আগে /start করতে হবে।"
        )
        return

    update_user(matched_uid, {"daily_limit": new_limit})
    await update.message.reply_text(
        f"✅ @{target_username} এর দৈনিক voice limit *{new_limit}* এ সেট করা হয়েছে।",
        parse_mode="Markdown",
    )


async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        await update.message.reply_text("⛔ তুমি admin নও।")
        return

    if not context.args:
        await update.message.reply_text(
            "❌ সঠিক format: `/broadcast {message}`\nউদাহরণ: `/broadcast Bot update হয়েছে!`",
            parse_mode="Markdown",
        )
        return

    message_text = " ".join(context.args)
    users = load_users()
    sent = 0
    failed = 0

    status_msg = await update.message.reply_text(f"📤 Broadcast শুরু হচ্ছে ({len(users)} জনকে)...")

    for uid in users:
        try:
            await context.bot.send_message(
                chat_id=int(uid),
                text=f"📢 *Bot Announcement*\n\n{message_text}",
                parse_mode="Markdown",
            )
            sent += 1
            await asyncio.sleep(0.05)  # Avoid flood limits
        except Exception as e:
            logger.warning(f"Broadcast failed for {uid}: {e}")
            failed += 1

    await status_msg.edit_text(
        f"✅ Broadcast সম্পন্ন!\n\n"
        f"📨 পাঠানো হয়েছে: {sent} জনকে\n"
        f"❌ ব্যর্থ: {failed} জন"
    )


# ─── Main ──────────────────────────────────────────────────────────────────────

def main():
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN environment variable is not set!")

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("history", history_command))
    app.add_handler(CommandHandler("admin", admin_command))
    app.add_handler(CommandHandler("add", add_command))
    app.add_handler(CommandHandler("broadcast", broadcast_command))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    logger.info("Bot starting...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
    
