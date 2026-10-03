#!/bin/bash
# SkillForge — Backend Startup Script
# Usage:
#   ./start.sh          → production (port 8000)
#   ./start.sh --demo   → demo mode (no live API calls)
#   ./start.sh --dev    → development with uvicorn --reload

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

export PORT=${PORT:-8000}
export SKILLFORGE_DEMO=${SKILLFORGE_DEMO:-false}

# Load .env if present
if [ -f .env ]; then
  set -a
  source .env
  set +a
  echo "✓ Loaded .env"
fi

# Parse flags
DEV_MODE=false
for arg in "$@"; do
  case $arg in
    --demo) export SKILLFORGE_DEMO=true; echo "🎭 DEMO MODE (no live API calls)" ;;
    --dev)  DEV_MODE=true ;;
  esac
done

# Auto-install dependencies if any are missing
if ! python3 -c "import fastapi, uvicorn, trafilatura" 2>/dev/null; then
  echo "⬇ Installing dependencies…"
  pip3 install -r requirements.txt --quiet
fi

echo ""
echo "🚀 SkillForge API v2 starting on http://localhost:$PORT"
echo "   Demo mode : $SKILLFORGE_DEMO"
echo "   Dev mode  : $DEV_MODE"
echo ""

if [ "$DEV_MODE" = "true" ]; then
  exec uvicorn main:app --host 0.0.0.0 --port "$PORT" --reload
else
  exec python3 main.py
fi
