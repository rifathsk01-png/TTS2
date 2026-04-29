import os
import logging
from telegram import ReplyKeyboardMarkup, ReplyKeyboardRemove, Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from gtts import gTTS
from database import save_user

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN")

# In-memory user state store
user_data_store = {}

# ── /start ────────────────────────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.message.from_user.id)
    user_data_store[user_id] = {}  # Reset state on /start

    keyboard = [["🇧🇩 Bangla", "🇬🇧 English"]]
    await update.message.reply_text(
        "👋 *Welcome! স্বাগতম!*\n\nSelect your language / ভাষা বেছে নাও 👇",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True),
    )

# ── Message Handler ───────────────────────────────────────────────────────────
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.message.from_user.id)
    text    = update.message.text.strip()

    # Init state if user never did /start
    if user_id not in user_data_store:
        user_data_store[user_id] = {}

    user = user_data_store[user_id]

    # ── Step 1: Language selection ─────────────────────────────────────────
    if text in ["🇧🇩 Bangla", "🇬🇧 English"]:
        user["language"] = "Bangla" if "Bangla" in text else "English"
        user.pop("gender", None)  # clear old gender if restarting

        keyboard = [["👨 Male", "👩 Female"]]
        await update.message.reply_text(
            "✅ Language selected!\n\nNow select your gender 👇",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True),
        )
        return

    # ── Step 2: Gender selection ───────────────────────────────────────────
    if text in ["👨 Male", "👩 Female"]:
        if "language" not in user:
            await update.message.reply_text(
                "⚠️ Please select a language first. Use /start",
                reply_markup=ReplyKeyboardRemove(),
            )
            return

        user["gender"] = "Male" if "Male" in text else "Female"

        lang_label = "বাংলায়" if user["language"] == "Bangla" else "in English"
        await update.message.reply_text(
            f"✅ Gender selected!\n\nNow send your text/script {lang_label} 👇",
            reply_markup=ReplyKeyboardRemove(),
        )
        return

    # ── Step 3: Generate Voice ─────────────────────────────────────────────
    if "language" in user and "gender" in user:
        lang = "bn" if user["language"] == "Bangla" else "en"

        await update.message.reply_text("⏳ Generating voice...")

        try:
            tts = gTTS(text=text, lang=lang, slow=False)
            file_name = f"voice_{user_id}.mp3"
            tts.save(file_name)

            with open(file_name, "rb") as audio:
                await update.message.reply_voice(audio)

            os.remove(file_name)

            # Save to Firebase
            save_user(user_id, {
                "user_id":   user_id,
                "language":  user["language"],
                "gender":    user["gender"],
                "last_text": text[:300],
            })

            keyboard = [["🔁 Send Another", "🏠 Restart"]]
            await update.message.reply_text(
                "✅ Done! Send another text or restart 👇",
                reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True),
            )

        except Exception as e:
            logging.error(f"TTS error: {e}")
            await update.message.reply_text("❌ Something went wrong. Please try again.")

        return

    # ── Control buttons ────────────────────────────────────────────────────
    if text == "🔁 Send Another":
        await update.message.reply_text(
            "Send your next text 👇",
            reply_markup=ReplyKeyboardRemove(),
        )
        return

    if text == "🏠 Restart":
        user_data_store[user_id] = {}
        keyboard = [["🇧🇩 Bangla", "🇬🇧 English"]]
        await update.message.reply_text(
            "🔄 Restarted! Select your language 👇",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True),
        )
        return

    # ── Fallback ───────────────────────────────────────────────────────────
    await update.message.reply_text(
        "⚠️ Please use /start to begin.",
        reply_markup=ReplyKeyboardRemove(),
    )

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("🤖 Bot running...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
            
