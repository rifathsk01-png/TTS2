import json
from datetime import datetime, timezone
from typing import Any

import firebase_admin
from firebase_admin import credentials, firestore

from config import config


def _init_firebase():
    if firebase_admin._apps:
        return firestore.client()

    try:
        firebase_json = json.loads(config.FIREBASE_CREDENTIALS)
    except json.JSONDecodeError as exc:
        raise RuntimeError("FIREBASE_CREDENTIALS must be valid JSON.") from exc

    cred = credentials.Certificate(firebase_json)
    firebase_admin.initialize_app(cred)
    return firestore.client()


db = _init_firebase()


DEFAULT_PREFS = {
    "language": config.DEFAULT_LANGUAGE,
    "gender": config.DEFAULT_GENDER,
    "speed": config.DEFAULT_SPEED,
    "pitch": config.DEFAULT_PITCH,
    "style": config.DEFAULT_STYLE,
}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def ensure_user(user_id: int, name: str) -> dict[str, Any]:
    ref = db.collection("users").document(str(user_id))
    snap = ref.get()

    if snap.exists:
        data = snap.to_dict() or {}
        ref.update(
            {
                "name": name,
                "last_seen": utc_now_iso(),
            }
        )
        return data

    data = {
        "user_id": user_id,
        "name": name,
        "preferences": DEFAULT_PREFS.copy(),
        "total_generated": 0,
        "recent_activity": [],
        "created_at": utc_now_iso(),
        "last_seen": utc_now_iso(),
    }

    ref.set(data)
    return data


async def get_user(user_id: int) -> dict[str, Any]:
    ref = db.collection("users").document(str(user_id))
    snap = ref.get()

    if not snap.exists:
        return {}

    return snap.to_dict() or {}


async def get_preferences(user_id: int) -> dict[str, Any]:
    user = await get_user(user_id)
    prefs = user.get("preferences", {})
    merged = DEFAULT_PREFS.copy()
    merged.update(prefs)
    return merged


async def update_preference(user_id: int, key: str, value: Any) -> None:
    ref = db.collection("users").document(str(user_id))
    ref.set(
        {
            "preferences": {
                key: value,
            },
            "last_seen": utc_now_iso(),
        },
        merge=True,
    )


async def add_generation_history(
    user_id: int,
    text_preview: str,
    language: str,
    audio_file: str,
) -> None:
    ref = db.collection("users").document(str(user_id))
    snap = ref.get()

    user = snap.to_dict() if snap.exists else {}
    recent = user.get("recent_activity", [])

    item = {
        "text": text_preview[:120],
        "language": language,
        "audio_file": audio_file,
        "created_at": utc_now_iso(),
    }

    recent.insert(0, item)
    recent = recent[:10]

    ref.set(
        {
            "total_generated": firestore.Increment(1),
            "recent_activity": recent,
            "last_generated_at": utc_now_iso(),
        },
        merge=True,
    )
