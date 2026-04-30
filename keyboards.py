from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton


BTN_TTS = "🎤 Text To Voice"
BTN_PROFILE = "👤 Profile"
BTN_HELP = "❓ Help"

BTN_SETTINGS = "⚙️ Settings"
BTN_BACK = "⬅️ Back"

BTN_LANG_BN = "Bangla 🇧🇩"
BTN_LANG_EN = "English 🇺🇸"

BTN_MALE = "Male 👨"
BTN_FEMALE = "Female 👩"

BTN_NATURAL = "Natural 🎙️"
BTN_ROBOTIC = "Robotic 🤖"

BTN_SLOW = "Slow 🐢"
BTN_NORMAL = "Normal 🚶"
BTN_FAST = "Fast ⚡"


def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_TTS)],
            [KeyboardButton(text=BTN_PROFILE), KeyboardButton(text=BTN_HELP)],
            [KeyboardButton(text=BTN_SETTINGS)],
        ],
        resize_keyboard=True,
        input_field_placeholder="Choose an option 👇",
    )


def settings_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🌍 Language"), KeyboardButton(text="🧑‍🎤 Gender")],
            [KeyboardButton(text="🎙️ Style"), KeyboardButton(text="🚀 Speed")],
            [KeyboardButton(text="🎚️ Pitch")],
            [KeyboardButton(text=BTN_BACK)],
        ],
        resize_keyboard=True,
        input_field_placeholder="Customize your voice settings",
    )


def language_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=BTN_LANG_BN, callback_data="set_lang:bn"),
                InlineKeyboardButton(text=BTN_LANG_EN, callback_data="set_lang:en"),
            ]
        ]
    )


def gender_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=BTN_MALE, callback_data="set_gender:male"),
                InlineKeyboardButton(text=BTN_FEMALE, callback_data="set_gender:female"),
            ]
        ]
    )


def style_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=BTN_NATURAL, callback_data="set_style:natural"),
                InlineKeyboardButton(text=BTN_ROBOTIC, callback_data="set_style:robotic"),
            ]
        ]
    )


def speed_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=BTN_SLOW, callback_data="set_speed:slow"),
                InlineKeyboardButton(text=BTN_NORMAL, callback_data="set_speed:normal"),
                InlineKeyboardButton(text=BTN_FAST, callback_data="set_speed:fast"),
            ]
        ]
    )


def pitch_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Low", callback_data="set_pitch:0.85"),
                InlineKeyboardButton(text="Normal", callback_data="set_pitch:1.0"),
                InlineKeyboardButton(text="High", callback_data="set_pitch:1.15"),
            ]
        ]
    )
