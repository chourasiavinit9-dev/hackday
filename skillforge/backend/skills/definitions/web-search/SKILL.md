---
name: web-search
description: Search the public web for information using natural language queries.
version: "1.0.0"
author: SkillForge
license: Apache-2.0
capabilities:
  - Search web using text queries
  - Return titles, URLs, and snippets
  - Support multiple search backends
tools:
  - web_search
execution_timeout: 30
---

# Web Search Skill

## Purpose
Enables the SkillForge agent to search the public web for information.
Supports Google Custom Search API with automatic DuckDuckGo fallback.

## Usage
Provide a natural language query. The skill returns a list of matching
web pages with titles, URLs, and text snippets.

## Examples
- "Find recent news about Gemma 4"
- "Search for Python machine learning tutorials"
- "Look up open-source AI agent frameworks"

## Notes
- Only reads public web content; never bypasses authentication
- Results are snippets only; use `webpage-reader` to read full content
- Risk level: LOW
