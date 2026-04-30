import asyncio
import logging
import os
from typing import Any

from aiogram import Bot, Dispatcher, F
from aiogram.enums import ChatAction
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import FSInputFile, Message, CallbackQuery

from config import config
from db import (
    add_generation_history,
    ensure_user,
    get_preferences,
    get_user,
    update_preference,
)
from keyboards import (
    BTN_BACK,
    BTN_HELP,
    BTN_PROFILE,
    BTN_SETTINGS,
    BTN_TTS,
    gender_keyboard,
    language_keyboard,
    main_menu,
    pitch_keyboard,
    settings_menu,
    speed_keyboard,
    style_keyboard,
)
from tts import tts_engine


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

logger = logging.getLogger(__name__)


class TTSStates(StatesGroup):
    waiting_for_text = State()


bot = Bot(token=config.BOT_TOKEN)
dp = Dispatcher()

generation_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()


def full_name(message: Message) -> str:
    user = message.from_user
    if not user:
        return "Unknown"

    parts = [user.first_name, user.last_name]
    return " ".join(part for part in parts if part)


@dp.message(CommandStart())
async def start_handler(message: Message, state: FSMContext) -> None:
    await state.clear()

    if message.from_user:
        await ensure_user(message.from_user.id, full_name(message))

    await message.answer(
        "👋 Welcome to Offline TTS Bot!\n\n"
        "I can convert your text into realistic voice 🎧\n"
        "No API. Fully offline ⚡\n\n"
        "Please choose an option below 👇",
        reply_markup=main_menu(),
    )


@dp.message(F.text == BTN_BACK)
async def back_handler(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Main menu 👇", reply_markup=main_menu())


@dp.message(F.text == BTN_TTS)
async def text_to_voice_handler(message: Message, state: FSMContext) -> None:
    if message.from_user:
        await ensure_user(message.from_user.id, full_name(message))

    await state.set_state(TTSStates.waiting_for_text)
    await message.answer(
        "Send your text ✍️\n\n"
        "Your saved voice preferences will be used automatically.",
        reply_markup=main_menu(),
    )


@dp.message(TTSStates.waiting_for_text)
async def receive_tts_text(message: Message, state: FSMContext) -> None:
    if not message.from_user:
        return

    text = message.text or ""

    if text in {BTN_TTS, BTN_PROFILE, BTN_HELP, BTN_SETTINGS, BTN_BACK}:
        await state.clear()
        await route_menu_buttons(message, state)
        return

    text = text.strip()

    if not text:
        await message.answer("Please send valid text ✍️")
        return

    if len(text) > config.MAX_TEXT_LENGTH:
        await message.answer(
            f"Your text is too long. I will use the first {config.MAX_TEXT_LENGTH} characters."
        )
        text = text[: config.MAX_TEXT_LENGTH]

    await ensure_user(message.from_user.id, full_name(message))

    await message.answer("Generating your voice... 🎧")
    await bot.send_chat_action(message.chat.id, ChatAction.RECORD_VOICE)

    future: asyncio.Future[str] = asyncio.get_running_loop().create_future()

    await generation_queue.put(
        {
            "future": future,
            "user_id": message.from_user.id,
            "chat_id": message.chat.id,
            "text": text,
        }
    )

    try:
        audio_path = await asyncio.wait_for(future, timeout=300)
    except asyncio.TimeoutError:
        await message.answer("Generation took too long. Please try a shorter text.")
        return
    except Exception as exc:
        logger.exception("TTS generation failed: %s", exc)
        await message.answer("Sorry, voice generation failed. Please try again.")
        return

    voice = FSInputFile(audio_path)

    await message.answer_voice(
        voice=voice,
        caption="𝘾𝙧𝙚𝙖𝙩𝙚𝙙 𝘽𝙮 - 𝙎𝙖𝙖𝙁𝙚 🖤",
        reply_markup=main_menu(),
    )

    prefs = await get_preferences(message.from_user.id)
    await add_generation_history(
        user_id=message.from_user.id,
        text_preview=text,
        language=prefs.get("language", "en"),
        audio_file=os.path.basename(audio_path),
    )


@dp.message(F.text == BTN_PROFILE)
async def profile_handler(message: Message, state: FSMContext) -> None:
    await state.clear()

    if not message.from_user:
        return

    await ensure_user(message.from_user.id, full_name(message))
    user = await get_user(message.from_user.id)

    await message.answer(
        "👤 Profile Info\n\n"
        f"Name: {user.get('name', full_name(message))}\n"
        f"User ID: {message.from_user.id}\n"
        f"Voices Generated: {user.get('total_generated', 0)} 🎧",
        reply_markup=main_menu(),
    )


@dp.message(F.text == BTN_HELP)
async def help_handler(message: Message, state: FSMContext) -> None:
    await state.clear()

    await message.answer(
        "❓ সাহায্য / Help\n\n"
        "1. Click \"Text To Voice\"\n"
        "2. Send your text\n"
        "3. Get instant voice 🎧\n\n"
        f"Admin: {config.ADMIN_USERNAME}",
        reply_markup=main_menu(),
    )


@dp.message(F.text == BTN_SETTINGS)
async def settings_handler(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("⚙️ Settings\n\nChoose what you want to customize 👇", reply_markup=settings_menu())


@dp.message(F.text == "🌍 Language")
async def choose_language(message: Message) -> None:
    await message.answer("Choose language 🌍", reply_markup=language_keyboard())


@dp.message(F.text == "🧑‍🎤 Gender")
async def choose_gender(message: Message) -> None:
    await message.answer("Choose gender 🧑‍🎤", reply_markup=gender_keyboard())


@dp.message(F.text == "🎙️ Style")
async def choose_style(message: Message) -> None:
    await message.answer("Choose voice style 🎙️", reply_markup=style_keyboard())


@dp.message(F.text == "🚀 Speed")
async def choose_speed(message: Message) -> None:
    await message.answer("Choose voice speed 🚀", reply_markup=speed_keyboard())


@dp.message(F.text == "🎚️ Pitch")
async def choose_pitch(message: Message) -> None:
    await message.answer("Choose pitch 🎚️", reply_markup=pitch_keyboard())


@dp.callback_query(F.data.startswith("set_lang:"))
async def set_language_callback(callback: CallbackQuery) -> None:
    if not callback.from_user:
        return

    lang = callback.data.split(":", 1)[1]
    await update_preference(callback.from_user.id, "language", lang)

    label = "Bangla 🇧🇩" if lang == "bn" else "English 🇺🇸"
    await callback.answer("Language saved")
    await callback.message.answer(f"Language set to {label} ✅")


@dp.callback_query(F.data.startswith("set_gender:"))
async def set_gender_callback(callback: CallbackQuery) -> None:
    if not callback.from_user:
        return

    gender = callback.data.split(":", 1)[1]
    await update_preference(callback.from_user.id, "gender", gender)

    label = "Male 👨" if gender == "male" else "Female 👩"
    await callback.answer("Gender saved")
    await callback.message.answer(f"Gender set to {label} ✅")


@dp.callback_query(F.data.startswith("set_style:"))
async def set_style_callback(callback: CallbackQuery) -> None:
    if not callback.from_user:
        return

    style = callback.data.split(":", 1)[1]
    await update_preference(callback.from_user.id, "style", style)

    label = "Natural 🎙️" if style == "natural" else "Robotic 🤖"
    await callback.answer("Style saved")
    await callback.message.answer(f"Voice style set to {label} ✅")


@dp.callback_query(F.data.startswith("set_speed:"))
async def set_speed_callback(callback: CallbackQuery) -> None:
    if not callback.from_user:
        return

    speed = callback.data.split(":", 1)[1]
    await update_preference(callback.from_user.id, "speed", speed)

    labels = {
        "slow": "Slow 🐢",
        "normal": "Normal 🚶",
        "fast": "Fast ⚡",
    }

    await callback.answer("Speed saved")
    await callback.message.answer(f"Speed set to {labels.get(speed, speed)} ✅")


@dp.callback_query(F.data.startswith("set_pitch:"))
async def set_pitch_callback(callback: CallbackQuery) -> None:
    if not callback.from_user:
        return

    pitch = float(callback.data.split(":", 1)[1])
    await update_preference(callback.from_user.id, "pitch", pitch)

    await callback.answer("Pitch saved")
    await callback.message.answer(f"Pitch set to {pitch} ✅")


@dp.message()
async def route_menu_buttons(message: Message, state: FSMContext) -> None:
    text = message.text or ""

    if text == BTN_TTS:
        await text_to_voice_handler(message, state)
    elif text == BTN_PROFILE:
        await profile_handler(message, state)
    elif text == BTN_HELP:
        await help_handler(message, state)
    elif text == BTN_SETTINGS:
        await settings_handler(message, state)
    else:
        await message.answer(
            "Please use the buttons below 👇",
            reply_markup=main_menu(),
        )


async def tts_worker(worker_id: int) -> None:
    logger.info("TTS worker %s started", worker_id)

    while True:
        job = await generation_queue.get()

        future: asyncio.Future[str] = job["future"]
        user_id: int = job["user_id"]
        text: str = job["text"]

        try:
            prefs = await get_preferences(user_id)
            audio_path = await tts_engine.synthesize(text, prefs)

            if not future.done():
                future.set_result(audio_path)

        except Exception as exc:
            logger.exception("Worker %s failed: %s", worker_id, exc)

            if not future.done():
                future.set_exception(exc)

        finally:
            generation_queue.task_done()


async def main() -> None:
    workers = [
        asyncio.create_task(tts_worker(i))
        for i in range(1)
    ]

    try:
        await dp.start_polling(bot)
    finally:
        for worker in workers:
            worker.cancel()

        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
