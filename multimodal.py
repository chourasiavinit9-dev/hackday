"""
HackGuide — Multimodal Engine (Audio, Video, Image)
Handles voice-to-text, audio pitch transcription, demo video evaluation, and architecture image analysis.
Built for Hacktoberfest Hack Day Asansol × HackTropica 2026.
"""

import os
import mimetypes
from pathlib import Path
import google.generativeai as genai

# Default multimodal model: gemini-3.8-flash provides ultra-fast audio/video tokens
MULTIMODAL_MODEL = os.environ.get("MULTIMODAL_MODEL", "gemini-3.8-flash")


def get_mime_type(file_path: Path) -> str:
    """Guess MIME type or provide standard audio/video defaults."""
    mime, _ = mimetypes.guess_type(str(file_path))
    if mime:
        return mime
    ext = file_path.suffix.lower()
    mapping = {
        ".wav": "audio/wav",
        ".mp3": "audio/mp3",
        ".m4a": "audio/m4a",
        ".ogg": "audio/ogg",
        ".aac": "audio/aac",
        ".mp4": "video/mp4",
        ".mov": "video/quicktime",
        ".webm": "video/webm",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
    }
    return mapping.get(ext, "application/octet-stream")


def create_media_part(file_path: Path) -> dict:
    """Read media file into an inline part structure for gRPC multimodal transmission."""
    mime = get_mime_type(file_path)
    with open(file_path, "rb") as f:
        data = f.read()
    return {"mime_type": mime, "data": data}


def transcribe_and_extract_voice(audio_path: str, prompt: str = None) -> str:
    """
    Transcribes spoken voice and extracts hackathon planning essentials:
    1. Full voice-to-text transcription
    2. Hackathon constraints (Team Size, Time, Stack, Problem Statement, MVP)
    """
    path = Path(audio_path)
    if not path.exists():
        return f"❌ Audio file not found at: {audio_path}"

    system_instruction = prompt or (
        "You are an expert audio transcription and analysis assistant for HackGuide. "
        "Transcribe the spoken audio verbatim, and then summarize the key hackathon project details "
        "mentioned (Team Size, Available Time, Tech Stack, Problem Statement, and Proposed MVP)."
    )

    try:
        media_part = create_media_part(path)
        model = genai.GenerativeModel(model_name=MULTIMODAL_MODEL)
        response = model.generate_content([media_part, system_instruction])
        return response.text
    except Exception as e:
        return f"❌ Voice-to-Text processing error: {str(e)}"


def analyze_demo_video(video_path: str, prompt: str = None) -> str:
    """
    Analyzes a hackathon demo or pitch video (.mp4, .mov, .webm):
    1. 60-Second Demo Rule (Is it concise, does it show working code?)
    2. MLH Rubric Alignment (Technology, Design, Completion, Learning)
    3. Actionable improvements before presenting to the judges.
    """
    path = Path(video_path)
    if not path.exists():
        return f"❌ Video file not found at: {video_path}"

    system_instruction = prompt or (
        "You are HackGuide's judging assistant evaluating a hackathon project demo video. "
        "Analyze the video against the official MLH Judging Rubric:\n"
        "1. Completion (25%): Does the working product actually get demonstrated? Any broken steps?\n"
        "2. Technology (25%): How technically impressive or clever is the implementation?\n"
        "3. Design (25%): Visual polish, UI/UX responsiveness, and clarity.\n"
        "4. Learning (25%): Did the team push boundaries or demonstrate new tech?\n\n"
        "Provide timestamped feedback, overall estimated rubric score (/100), and 3 quick fixes "
        "the team should make before presenting to the judges."
    )

    try:
        media_part = create_media_part(path)
        model = genai.GenerativeModel(model_name=MULTIMODAL_MODEL)
        response = model.generate_content([media_part, system_instruction])
        return response.text
    except Exception as e:
        return f"❌ Video analysis error: {str(e)}"


def analyze_architecture_image(image_path: str, prompt: str = None) -> str:
    """
    Analyzes whiteboard sketches, system architecture diagrams, or UI mockups.
    """
    path = Path(image_path)
    if not path.exists():
        return f"❌ Image file not found at: {image_path}"

    system_instruction = prompt or (
        "Analyze this system architecture diagram / whiteboard sketch for a hackathon MVP. "
        "Identify:\n"
        "1. Core components and data flow\n"
        "2. High-risk bottlenecks or over-engineered parts that should be simplified\n"
        "3. Recommended minimal stack to implement this within 4-6 hours."
    )

    try:
        media_part = create_media_part(path)
        model = genai.GenerativeModel(model_name=MULTIMODAL_MODEL)
        response = model.generate_content([media_part, system_instruction])
        return response.text
    except Exception as e:
        return f"❌ Image analysis error: {str(e)}"
