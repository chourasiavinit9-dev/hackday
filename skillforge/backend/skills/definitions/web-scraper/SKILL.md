---
name: web-scraper
description: Search the web via DuckDuckGo (no CAPTCHA, no API key) and extract clean article text from any URL. Uses trafilatura for best-in-class content extraction.
version: "1.0.0"
author: SkillForge
license: Apache-2.0
capabilities:
  - Search the web without CAPTCHA or API keys via DuckDuckGo
  - Extract clean readable text from any public URL
  - Remove ads, navigation, and boilerplate automatically
  - Works on news sites, blogs, documentation, and research pages
tools:
  - ddg_search
  - extract_article
execution_timeout: 20
---

# Web Scraper Skill

## Purpose
Search and extract content from the web using **100% open-source tools**:
- **DuckDuckGo Search** — no API key, no CAPTCHA, MIT license
- **trafilatura** — state-of-the-art article extractor, Apache 2.0

## Why DuckDuckGo instead of Google?
- ✅ No API key required
- ✅ No CAPTCHA
- ✅ No rate limiting on normal use
- ✅ Returns clean result JSON
- ✅ Privacy-respecting

## Install
```bash
pip3 install duckduckgo-search trafilatura beautifulsoup4
```

## Examples
- "Search for Python data science tutorials"
- "Extract the main article from https://realpython.com/..."
- "Find recent news about Gemma 4 open source AI"

## Workflow
```
User query
    ↓
ddg_search(query, num_results=5)
    ↓
Returns: [{title, url, snippet}, ...]
    ↓
extract_article(url)     ← for each URL you want full content
    ↓
Returns: {url, content, extractor}
```

## Notes
- Only reads **public** pages — no login bypass
- `extract_article` works best on text-heavy pages (articles, docs, blogs)
- Falls back to lxml if trafilatura not installed
- Demo mode returns realistic sample data without any network calls
