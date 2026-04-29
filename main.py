import os
import json
import logging
import tempfile
from datetime import datetime

from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    ContextTypes, filters, ConversationHandler
)
from gtts import gTTS
import firebase_admin
from firebase_admin import credentials, firestore

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ── Environment Variables ─────────────────────────────────────────────────────
BOT_TOKEN            = os.environ["BOT_TOKEN"]
FIREBASE_CREDENTIALS = os.environ["FIREBASE_CREDENTIALS"]  # JSON string from Railway

# ── Firebase Init ─────────────────────────────────────────────────────────────
def init_firebase():
    try:
        cred_dict = json.loads(FIREBASE_CREDENTIALS)
        cred = credentials.Certificate(cred_dict)
        firebase_admin.initialize_app(cred)
        logger.info("✅ Firebase connected.")
        return firestore.client()
    except Exception as e:
        logger.error(f"❌ Firebase init failed: {e}")
        raise

db = init_firebase()

# ── Firebase Helpers ──────────────────────────────────────────────────────────
def save_user(user_id: int, data: dict):
    """Upsert user document in Firestore → collection: users"""
    data["updated_at"] = datetime.utcnow().isoformat()
    db.collection("users").document(str(user_id)).set(data, merge=True)

def log_voice(user_id: int, lang: str, gender: str, text: str):
    """Append a voice-request log → collection: voice_logs"""
    db.collection("voice_logs").add({
        "user_id":    user_id,
        "language":   lang,
        "gender":     gender,
        "text":       text[:500],
        "created_at": datetime.utcnow().isoformat(),
    })

# ── Conversation States ───────────────────────────────────────────────────────
LANGUAGE, GENDER, TEXT_INPUT = range(3)

# ── /start ────────────────────────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user    = update.effective_user
    name    = user.first_name or "বন্ধু"

    save_user(user.id, {
        "user_id":    user.id,
        "username":   user.username,
        "first_name": user.first_name,
        "last_name":  user.last_name,
        "joined_at":  datetime.utcnow().isoformat(),
    })

    keyboard = [["🇧🇩 Bangla", "🇬🇧 English"]]
    await update.message.reply_text(
        f"👋 *স্বাগতম {name}! Welcome!*\n\n"
        "আমি একটি *Text-to-Voice Bot* 🎙️\n"
        "তুমি যা লিখবে, আমি সেটা Voice এ বলে দেবো!\n\n"
        "I'm a *Text-to-Voice Bot* 🎙️\n"
        "Whatever you type, I'll say it aloud!\n\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "প্রথমে ভাষা বেছে নাও / Choose your language 👇",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True),
    )
    return LANGUAGE

# ── Language ──────────────────────────────────────────────────────────────────
async def choose_language(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text    = update.message.text
    user_id = update.effective_user.id

    if "Bangla" in text:
        context.user_data["lang"] = "bn"
        save_user(user_id, {"language": "bn"})
        msg = "✅ বাংলা ভাষা সিলেক্ট হয়েছে!\n\nএখন তোমার লিঙ্গ বেছে নাও 👇"
    else:
        context.user_data["lang"] = "en"
        save_user(user_id, {"language": "en"})
        msg = "✅ English selected!\n\nNow choose your gender 👇"

    keyboard = [["👨 Male", "👩 Female"]]
    await update.message.reply_text(
        msg,
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True),
    )
    return GENDER

# ── Gender ────────────────────────────────────────────────────────────────────
async def choose_gender(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text    = update.message.text
    lang    = context.user_data.get("lang", "en")
    user_id = update.effective_user.id

    gender = "male" if "Male" in text else "female"
    context.user_data["gender"] = gender
    save_user(user_id, {"gender": gender})

    if lang == "bn":
        msg = (
            "✅ সিলেক্ট হয়েছে!\n\n"
            "এখন যে টেক্সট বা স্ক্রিপ্ট পড়াতে চাও সেটা পাঠাও। "
            "আমি সেটা Voice এ রূপান্তর করে দেবো! 🎙️"
        )
    else:
        msg = (
            "✅ Selected!\n\n"
            "Now send the text you want me to read aloud. "
            "I'll convert it to Voice! 🎙️"
        )

    await update.message.reply_text(msg, reply_markup=ReplyKeyboardRemove())
    return TEXT_INPUT

# ── Text → Voice ──────────────────────────────────────────────────────────────
META_KEYWORDS = ["Restart", "শুরু", "Write Another", "আরেকটি"]

async def generate_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text.strip()
    lang      = context.user_data.get("lang", "en")
    gender    = context.user_data.get("gender", "male")
    user_id   = update.effective_user.id

    # Handle control buttons
    if any(kw in user_text for kw in META_KEYWORDS):
        if "Restart" in user_text or "শুরু" in user_text:
            context.user_data.clear()
            return await start(update, context)
        # "Write Another"
        prompt = "ঠিক আছে! নতুন টেক্সট পাঠাও 👇" if lang == "bn" else "Sure! Send your next text 👇"
        await update.message.reply_text(prompt, reply_markup=ReplyKeyboardRemove())
        return TEXT_INPUT

    # Wait message
    await update.message.reply_text(
        "⏳ তোমার Voice তৈরি হচ্ছে..." if lang == "bn" else "⏳ Generating your Voice..."
    )

    try:
        tts = gTTS(text=user_text, lang=lang, slow=False)
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
            audio_path = tmp.name
        tts.save(audio_path)

        with open(audio_path, "rb") as af:
            await update.message.reply_voice(voice=af)

        os.remove(audio_path)

        # Save to Firebase
        log_voice(user_id, lang, gender, user_text)

        keyboard = [["🔁 আরেকটি লিখি / Write Another", "🏠 শুরু থেকে / Restart"]]
        done_msg = (
            "✅ Voice তৈরি হয়ে গেছে! আরো পাঠাতে চাও? 👇"
            if lang == "bn" else
            "✅ Voice generated! Want to send more? 👇"
        )
        await update.message.reply_text(
            done_msg,
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True),
        )

    except Exception as e:
        logger.error(f"TTS error | user={user_id} | {e}")
        await update.message.reply_text(
            "❌ কিছু একটা সমস্যা হয়েছে। আবার চেষ্টা করো।\n"
            "Something went wrong. Please try again."
        )

    return TEXT_INPUT

# ── /cancel ───────────────────────────────────────────────────────────────────
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "বাতিল হয়েছে। /start দিয়ে আবার শুরু করো।\n"
        "Cancelled. Use /start to begin again.",
        reply_markup=ReplyKeyboardRemove(),
    )
    return ConversationHandler.END

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            LANGUAGE:   [MessageHandler(filters.TEXT & ~filters.COMMAND, choose_language)],
            GENDER:     [MessageHandler(filters.TEXT & ~filters.COMMAND, choose_gender)],
            TEXT_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, generate_voice)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(conv)
    logger.info("🤖 Bot polling started.")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
