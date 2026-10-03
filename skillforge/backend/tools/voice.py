"""
SkillForge — Voice Transcription Tool
Uses OpenAI Whisper (open-source, MIT license, runs 100% locally).
No API keys. No external calls. Pure on-device inference.

Model options (auto-downloaded on first use from HuggingFace):
  tiny   — ~39M params, ~1s/minute audio  (fastest, hackday default)
  base   — ~74M params
  small  — ~244M params
  medium — ~769M params
  large  — ~1550M params

Whisper supports 99 languages out of the box.
"""

import os
import io
import time
import wave
import struct
import tempfile
import threading
from pathlib import Path
from typing import Optional

WHISPER_MODEL = os.environ.get("WHISPER_MODEL", "tiny")   # tiny for hackday speed
_whisper_model = None
_model_lock = threading.Lock()
_model_loading = False


def _load_model(model_name: str = WHISPER_MODEL):
    """Lazy-load Whisper model (downloads once, cached locally)."""
    global _whisper_model, _model_loading
    if _whisper_model is not None:
        return _whisper_model

    with _model_lock:
        if _whisper_model is not None:
            return _whisper_model
        try:
            import whisper
            print(f"[Whisper] Loading '{model_name}' model (first run downloads ~{_model_sizes[model_name]})...")
            _whisper_model = whisper.load_model(model_name)
            print(f"[Whisper] Model '{model_name}' loaded ✓")
            return _whisper_model
        except ImportError:
            raise RuntimeError(
                "Whisper not installed. Run: pip3 install openai-whisper\n"
                "Requires: ffmpeg (brew install ffmpeg)"
            )


_model_sizes = {
    "tiny": "~39MB", "base": "~74MB", "small": "~244MB",
    "medium": "~769MB", "large": "~1.5GB"
}


def is_whisper_available() -> bool:
    """Check if whisper can be imported (no model load)."""
    try:
        import whisper
        return True
    except ImportError:
        return False


def transcribe_audio_file(audio_path: str, language: Optional[str] = None) -> dict:
    """
    Transcribe an audio file using local Whisper model.

    Args:
        audio_path: Path to audio file (mp3, wav, m4a, ogg, flac, webm, etc.)
        language: ISO 639-1 language code (e.g. 'en', 'hi'). None = auto-detect.

    Returns:
        dict with 'text', 'language', 'segments', 'duration_ms'
    """
    t0 = time.time()
    audio_path = str(audio_path)

    if not Path(audio_path).exists():
        return {"error": f"File not found: {audio_path}", "text": ""}

    try:
        model = _load_model(WHISPER_MODEL)

        options = {}
        if language:
            options["language"] = language

        result = model.transcribe(audio_path, **options)

        segments = [
            {
                "start": round(s["start"], 2),
                "end": round(s["end"], 2),
                "text": s["text"].strip()
            }
            for s in result.get("segments", [])
        ]

        return {
            "text": result["text"].strip(),
            "language": result.get("language", "unknown"),
            "segments": segments,
            "model": WHISPER_MODEL,
            "audio_file": audio_path,
            "duration_ms": int((time.time() - t0) * 1000)
        }
    except Exception as e:
        return {"error": str(e), "text": "", "duration_ms": int((time.time() - t0) * 1000)}


def transcribe_audio_bytes(audio_bytes: bytes, suffix: str = ".wav",
                            language: Optional[str] = None) -> dict:
    """
    Transcribe raw audio bytes (e.g. from microphone recording or uploaded file).

    Args:
        audio_bytes: Raw audio bytes
        suffix: File extension hint ('.wav', '.mp3', '.webm', etc.)
        language: Optional language hint
    """
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name

    try:
        result = transcribe_audio_file(tmp_path, language=language)
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass

    return result


def record_and_transcribe(duration_seconds: int = 5, language: Optional[str] = None) -> dict:
    """
    Record from default microphone and transcribe with Whisper.
    Requires: pyaudio (pip3 install pyaudio) + portaudio (brew install portaudio)

    Args:
        duration_seconds: How many seconds to record
        language: Optional language hint
    """
    try:
        import pyaudio
    except ImportError:
        return {
            "error": "pyaudio not installed. Run: pip3 install pyaudio",
            "text": "",
            "hint": "Alternatively, use transcribe_audio_file() with a recorded .wav file"
        }

    RATE = 16000
    CHUNK = 1024
    CHANNELS = 1
    FORMAT = pyaudio.paInt16

    p = pyaudio.PyAudio()

    try:
        stream = p.open(
            format=FORMAT, channels=CHANNELS, rate=RATE,
            input=True, frames_per_buffer=CHUNK
        )

        print(f"[Whisper] 🎤 Recording {duration_seconds}s...")
        frames = []
        for _ in range(0, int(RATE / CHUNK * duration_seconds)):
            data = stream.read(CHUNK, exception_on_overflow=False)
            frames.append(data)

        stream.stop_stream()
        stream.close()
        print("[Whisper] Recording done. Transcribing...")

    except Exception as e:
        p.terminate()
        return {"error": f"Microphone error: {e}", "text": ""}
    finally:
        p.terminate()

    # Save to temp WAV
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        with wave.open(tmp.name, "wb") as wf:
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(p.get_sample_size(FORMAT))
            wf.setframerate(RATE)
            wf.writeframes(b"".join(frames))
        tmp_path = tmp.name

    try:
        result = transcribe_audio_file(tmp_path, language=language)
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass

    return result


def get_whisper_info() -> dict:
    """Return info about Whisper availability and configured model."""
    available = is_whisper_available()
    info = {
        "available": available,
        "model": WHISPER_MODEL,
        "model_size": _model_sizes.get(WHISPER_MODEL, "unknown"),
        "loaded": _whisper_model is not None,
        "license": "MIT",
        "source": "openai/whisper (open-source, runs locally)",
        "languages": "99 languages supported",
        "install_command": "pip3 install openai-whisper && brew install ffmpeg"
    }
    if not available:
        info["error"] = "Whisper not installed. Run: pip3 install openai-whisper"
    return info


# ── Demo transcription (no model needed) ──────────────────────────────────────

DEMO_TRANSCRIPTIONS = [
    "Find five Python data science jobs, extract the interview questions, and create a preparation report.",
    "Teach SkillForge a skill for finding research papers about any topic.",
    "Search for the latest news about Gemma 4 open source AI models.",
    "Find YouTube tutorials about retrieval augmented generation.",
]

_demo_idx = 0


def demo_transcribe() -> dict:
    """Return a realistic demo transcription (no model needed, for DEMO_MODE)."""
    global _demo_idx
    text = DEMO_TRANSCRIPTIONS[_demo_idx % len(DEMO_TRANSCRIPTIONS)]
    _demo_idx += 1
    return {
        "text": text,
        "language": "en",
        "segments": [{"start": 0.0, "end": 3.5, "text": text}],
        "model": "demo",
        "source": "DEMO DATA",
        "duration_ms": 150
    }
