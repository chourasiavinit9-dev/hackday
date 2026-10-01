#!/bin/bash
# HackGuide — One-Command Demo Runner
# Run this at the Hack Day to start the demo

set -e

echo "🚀 HackGuide — Gemma 4 Hackathon Mentor"
echo "Built at Hacktoberfest Hack Day Asansol × HackTropica 2026"
echo ""

# Check API key
if [ -z "$GEMINI_API_KEY" ]; then
  if [ -f ".env" ]; then
    export $(cat .env | xargs)
  else
    echo "❌ GEMINI_API_KEY not set. Add it to .env file"
    exit 1
  fi
fi

# Validate SKILL.md first (meta-demo moment!)
echo "🔍 Validating SKILL.md compliance..."
python skill_validator.py

echo ""
echo "✅ All checks passed. Starting HackGuide..."
echo ""

python main.py
