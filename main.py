import os
import logging
from telegram import ReplyKeyboardMarkup, Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

from gtts import gTTS
from firebase import save_user

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN")

# Temp user data (simple memory)
user_data_store = {}

# Start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [["Bangla", "English"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    await update.message.reply_text(
        "Welcome! Select Language:",
        reply_markup=reply_markup
    )

# Handle messages
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.message.from_user.id)
    text = update.message.text

    if user_id not in user_data_store:
        user_data_store[user_id] = {}

    user = user_data_store[user_id]

    # Step 1: Language
    if text in ["Bangla", "English"]:
        user["language"] = text

        keyboard = [["Male", "Female"]]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

        await update.message.reply_text(
            "Select Gender:",
            reply_markup=reply_markup
        )
        return

    # Step 2: Gender
    if text in ["Male", "Female"]:
        user["gender"] = text

        await update.message.reply_text("Now send your text/script:")
        return

    # Step 3: Generate Voice
    if "language" in user and "gender" in user:
        lang = "bn" if user["language"] == "Bangla" else "en"

        tts = gTTS(text=text, lang=lang)
        file_name = f"voice_{user_id}.mp3"
        tts.save(file_name)

        # Send voice
        with open(file_name, "rb") as audio:
            await update.message.reply_voice(audio)

        # Save to Firebase
        save_user(user_id, user)

        os.remove(file_name)

        await update.message.reply_text("Done! Send another text if you want.")
        return

# Main function
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("Bot running...")
    app.run_polling()

if __name__ == "__main__":
    main()
