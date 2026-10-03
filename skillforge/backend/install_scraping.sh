#!/bin/bash
# SkillForge — Install open-source scraping + YouTube tools
# Run this when you have internet access

echo "📦 Installing open-source scraping tools..."

# DuckDuckGo Search — no API key, no CAPTCHA, MIT license
pip3 install duckduckgo-search

# trafilatura — best-in-class article text extractor, Apache 2.0
pip3 install trafilatura

# beautifulsoup4 — HTML parsing, MIT license
pip3 install beautifulsoup4

# YouTube Transcript API — gets auto-captions without API key, MIT license
pip3 install youtube-transcript-api

echo "✅ All scraping tools installed!"
echo ""
echo "Tools available:"
echo "  duckduckgo-search   → CAPTCHA-free web search (DDG API)"
echo "  trafilatura         → Article text extraction (no JS needed)"
echo "  beautifulsoup4      → HTML parsing"
echo "  youtube-transcript-api → YouTube captions → summary"
