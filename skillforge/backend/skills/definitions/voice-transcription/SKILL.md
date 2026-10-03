---
name: voice-transcription
description: Convert speech to text using OpenAI Whisper — open-source, runs 100% locally, no API key required.
version: "1.0.0"
author: SkillForge
license: Apache-2.0
capabilities:
  - Transcribe audio files (WAV, MP3, M4A, OGG, FLAC, WebM)
  - Record from microphone and transcribe in real-time
  - Auto-detect spoken language (99 languages supported)
  - Return timestamped word segments
  - Work completely offline after model download
tools:
  - transcribe_voice
execution_timeout: 60
model:
  name: openai/whisper
  size: tiny (default) / base / small / medium / large
  license: MIT
  runs_locally: true
  api_key_required: false
---

# Voice Transcription Skill

## Purpose
Converts speech to text using **OpenAI Whisper** — a fully open-source,
MIT-licensed speech recognition model that runs **entirely on your machine**.

No API key. No external calls. No data sent anywhere.

## Why Whisper?
- ✅ Open-source (MIT license)
- ✅ Runs 100% locally — complete privacy
- ✅ Supports 99 languages with auto-detection
- ✅ Works with any audio format via ffmpeg
- ✅ Tiny model fits in ~39MB RAM
- ✅ Accurate enough for voice-as-input use cases

## Model Sizes
| Model  | Size   | Speed (CPU) | Use Case |
|--------|--------|-------------|----------|
| tiny   | ~39MB  | ~1s/min     | **Default — hackday speed** |
| base   | ~74MB  | ~2s/min     | Better accuracy |
| small  | ~244MB | ~5s/min     | Good accuracy |
| medium | ~769MB | ~15s/min    | High accuracy |
| large  | ~1.5GB | ~30s/min    | Best accuracy |

Set model via: `WHISPER_MODEL=base` in `.env`

## Install

```bash
pip3 install openai-whisper
brew install ffmpeg        # required for audio format conversion
```

Model downloads automatically on first transcription (~39MB for tiny).

## Usage Examples

### From file
```bash
curl -X POST http://localhost:8000/api/voice \
  -H "Content-Type: audio/wav" \
  --data-binary @recording.wav
```

### From browser (WebM)
```javascript
// Record with MediaRecorder API, send WebM blob
const blob = new Blob(chunks, { type: 'audio/webm' });
const formData = new FormData();
formData.append('audio', blob, 'voice.webm');
await fetch('/api/voice', {
  method: 'POST',
  headers: { 'Content-Type': 'audio/webm' },
  body: blob
});
```

### Demo mode (no model needed)
```bash
curl -X POST http://localhost:8000/api/voice \
  -H "Content-Type: application/json" \
  -d '{"demo": true}'
```

## Response Format
```json
{
  "text": "Find five Python data science jobs and create a report",
  "language": "en",
  "segments": [
    { "start": 0.0, "end": 3.5, "text": "Find five Python data science jobs..." }
  ],
  "model": "tiny",
  "duration_ms": 1200
}
```

## Privacy
All audio processing happens **locally on your machine**.
No audio data is ever sent to any external server.

## Attribution
- OpenAI Whisper: https://github.com/openai/whisper
- License: MIT
- Paper: "Robust Speech Recognition via Large-Scale Weak Supervision" (Radford et al., 2022)
