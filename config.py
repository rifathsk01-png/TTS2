import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
    FIREBASE_CREDENTIALS: str = os.getenv("FIREBASE_CREDENTIALS", "")

    ADMIN_USERNAME: str = "@Sefuax"

    DEFAULT_LANGUAGE: str = "en"
    DEFAULT_GENDER: str = "female"
    DEFAULT_SPEED: str = "normal"
    DEFAULT_PITCH: float = 1.0
    DEFAULT_STYLE: str = "natural"

    MAX_TEXT_LENGTH: int = 4000
    MAX_CHUNK_LENGTH: int = 450

    CACHE_DIR: str = "cache"
    OUTPUT_DIR: str = "outputs"

    TTS_MODEL_EN: str = "tts_models/en/vctk/vits"
    TTS_MODEL_MULTI: str = "tts_models/multilingual/multi-dataset/xtts_v2"


config = Config()

if not config.BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN environment variable is missing.")

if not config.FIREBASE_CREDENTIALS:
    raise RuntimeError("FIREBASE_CREDENTIALS environment variable is missing.")
