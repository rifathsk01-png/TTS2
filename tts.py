import asyncio
import hashlib
import os
import re
import uuid
import wave
from pathlib import Path
from typing import Any

from langdetect import detect, LangDetectException
from pydub import AudioSegment
from TTS.api import TTS

from config import config


Path(config.CACHE_DIR).mkdir(exist_ok=True)
Path(config.OUTPUT_DIR).mkdir(exist_ok=True)


class OfflineTTS:
    """
    Offline TTS engine using Coqui TTS.

    Notes:
    - First run may download model files.
    - After models are cached, generation is offline.
    - Bangla support depends on selected multilingual model availability.
    """

    def __init__(self) -> None:
        self._model: TTS | None = None
        self._lock = asyncio.Lock()

    def _load_model(self) -> TTS:
        if self._model is None:
            self._model = TTS(config.TTS_MODEL_MULTI)
        return self._model

    @staticmethod
    def detect_language(text: str, fallback: str = "en") -> str:
        try:
            detected = detect(text)
            if detected in {"bn", "en"}:
                return detected
        except LangDetectException:
            pass
        return fallback

    @staticmethod
    def clean_text(text: str) -> str:
        text = text.strip()
        text = re.sub(r"\s+", " ", text)
        return text

    @staticmethod
    def split_text(text: str, max_len: int = 450) -> list[str]:
        text = OfflineTTS.clean_text(text)

        if len(text) <= max_len:
            return [text]

        sentences = re.split(r"(?<=[।.!?])\s+", text)
        chunks: list[str] = []
        current = ""

        for sentence in sentences:
            if len(sentence) > max_len:
                words = sentence.split()
                for word in words:
                    if len(current) + len(word) + 1 <= max_len:
                        current += (" " if current else "") + word
                    else:
                        if current:
                            chunks.append(current)
                        current = word
                continue

            if len(current) + len(sentence) + 1 <= max_len:
                current += (" " if current else "") + sentence
            else:
                if current:
                    chunks.append(current)
                current = sentence

        if current:
            chunks.append(current)

        return chunks

    @staticmethod
    def _cache_key(text: str, prefs: dict[str, Any]) -> str:
        raw = f"{text}|{prefs.get('language')}|{prefs.get('gender')}|{prefs.get('speed')}|{prefs.get('pitch')}|{prefs.get('style')}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    @staticmethod
    def _speed_factor(speed: str) -> float:
        return {
            "slow": 0.85,
            "normal": 1.0,
            "fast": 1.15,
        }.get(speed, 1.0)

    @staticmethod
    def _speaker_for_gender(gender: str) -> str | None:
        """
        Speaker names depend on the selected Coqui model.

        XTTS supports voice cloning and speaker WAVs.
        For a zero-config production bot, we keep speaker optional.

        You can improve quality by adding local speaker reference WAV files:
        speakers/male.wav
        speakers/female.wav
        """
        speaker_file = Path("speakers") / f"{gender}.wav"
        if speaker_file.exists():
            return str(speaker_file)
        return None

    @staticmethod
    def _apply_speed(audio: AudioSegment, speed: str) -> AudioSegment:
        factor = OfflineTTS._speed_factor(speed)

        if factor == 1.0:
            return audio

        new_frame_rate = int(audio.frame_rate * factor)

        return audio._spawn(
            audio.raw_data,
            overrides={"frame_rate": new_frame_rate},
        ).set_frame_rate(audio.frame_rate)

    @staticmethod
    def _apply_pitch(audio: AudioSegment, pitch: float) -> AudioSegment:
        """
        Basic pitch shifting by changing frame rate.
        1.0 = normal, 0.85 = lower, 1.15 = higher.
        """
        try:
            pitch = float(pitch)
        except ValueError:
            pitch = 1.0

        if pitch == 1.0:
            return audio

        new_frame_rate = int(audio.frame_rate * pitch)

        return audio._spawn(
            audio.raw_data,
            overrides={"frame_rate": new_frame_rate},
        ).set_frame_rate(audio.frame_rate)

    @staticmethod
    def _apply_robotic_style(audio: AudioSegment) -> AudioSegment:
        """
        Lightweight robotic effect.
        """
        audio = audio.low_pass_filter(3200).high_pass_filter(250)
        audio = audio + 2
        return audio

    @staticmethod
    def _wav_duration(path: str) -> float:
        with wave.open(path, "rb") as wav_file:
            frames = wav_file.getnframes()
            rate = wav_file.getframerate()
            return frames / float(rate)

    async def synthesize(self, text: str, prefs: dict[str, Any]) -> str:
        clean = self.clean_text(text)

        if not clean:
            raise ValueError("Empty text")

        if len(clean) > config.MAX_TEXT_LENGTH:
            clean = clean[: config.MAX_TEXT_LENGTH]

        language = prefs.get("language", "en")
        if language not in {"bn", "en"}:
            language = self.detect_language(clean, fallback="en")

        cache_key = self._cache_key(clean, prefs)
        cached_path = Path(config.CACHE_DIR) / f"{cache_key}.ogg"

        if cached_path.exists():
            return str(cached_path)

        output_id = str(uuid.uuid4())
        temp_dir = Path(config.OUTPUT_DIR) / output_id
        temp_dir.mkdir(parents=True, exist_ok=True)

        chunks = self.split_text(clean, config.MAX_CHUNK_LENGTH)

        async with self._lock:
            model = self._load_model()

            wav_paths: list[str] = []

            for index, chunk in enumerate(chunks):
                wav_path = temp_dir / f"chunk_{index}.wav"

                await asyncio.to_thread(
                    self._tts_to_file,
                    model,
                    chunk,
                    str(wav_path),
                    language,
                    prefs,
                )

                wav_paths.append(str(wav_path))

        combined = AudioSegment.empty()

        for wav_path in wav_paths:
            audio = AudioSegment.from_wav(wav_path)
            combined += audio + AudioSegment.silent(duration=250)

        combined = self._apply_speed(combined, prefs.get("speed", "normal"))
        combined = self._apply_pitch(combined, float(prefs.get("pitch", 1.0)))

        if prefs.get("style") == "robotic":
            combined = self._apply_robotic_style(combined)

        combined.export(
            cached_path,
            format="ogg",
            codec="libopus",
            bitrate="48k",
        )

        try:
            for file in temp_dir.glob("*"):
                file.unlink(missing_ok=True)
            temp_dir.rmdir()
        except OSError:
            pass

        return str(cached_path)

    def _tts_to_file(
        self,
        model: TTS,
        text: str,
        wav_path: str,
        language: str,
        prefs: dict[str, Any],
    ) -> None:
        gender = prefs.get("gender", "female")
        speaker_wav = self._speaker_for_gender(gender)

        kwargs: dict[str, Any] = {
            "text": text,
            "file_path": wav_path,
        }

        # XTTS-style multilingual models usually require language.
        kwargs["language"] = "bn" if language == "bn" else "en"

        if speaker_wav:
            kwargs["speaker_wav"] = speaker_wav

        try:
            model.tts_to_file(**kwargs)
        except Exception:
            # Some Coqui models do not accept language or speaker_wav.
            fallback_kwargs = {
                "text": text,
                "file_path": wav_path,
            }
            model.tts_to_file(**fallback_kwargs)


tts_engine = OfflineTTS()
