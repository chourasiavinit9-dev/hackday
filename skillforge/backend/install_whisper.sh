#!/bin/bash
# SkillForge — Install Whisper Voice-to-Text (open-source, MIT license)
# Whisper runs 100% locally — no API key, no data sent externally.

set -e
echo "🎙️  Installing Whisper Voice-to-Text..."
echo ""
echo "License: MIT (openai/whisper)"
echo "Model: tiny (~39MB, downloads once on first use)"
echo ""

# Check ffmpeg
if ! command -v ffmpeg &> /dev/null; then
    echo "📦 Installing ffmpeg..."
    brew install ffmpeg
    echo "✓ ffmpeg installed"
else
    echo "✓ ffmpeg already installed"
fi

# Check portaudio (for microphone recording)
if brew list portaudio &>/dev/null 2>&1; then
    echo "✓ portaudio already installed"
else
    echo "📦 Installing portaudio (for microphone recording)..."
    brew install portaudio
    echo "✓ portaudio installed"
fi

# Install Whisper
echo ""
echo "📦 Installing openai-whisper..."
pip3 install openai-whisper

# Install pyaudio for mic recording
echo "📦 Installing pyaudio (microphone support)..."
pip3 install pyaudio || echo "⚠️  pyaudio install failed — file upload transcription will still work"

echo ""
echo "✅ Whisper installed! Testing..."
python3 -c "
import whisper
print(f'  ✓ whisper version: {whisper.__version__}')
print(f'  ✓ Available models: {whisper.available_models()}')
print()
print('First transcription will download the tiny model (~39MB).')
print('Set WHISPER_MODEL=base/small/medium/large in .env for better accuracy.')
"

echo ""
echo "🎤 Voice endpoints:"
echo "   GET  /api/voice/info    — Whisper status"
echo "   POST /api/voice         — Transcribe audio file or record from mic"
echo ""
echo "   Upload audio: curl -X POST http://localhost:8000/api/voice -H 'Content-Type: audio/wav' --data-binary @file.wav"
echo "   Demo mode:    curl -X POST http://localhost:8000/api/voice -d '{\"demo\": true}'"
