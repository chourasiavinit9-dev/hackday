---
name: youtube-search
description: Search YouTube for videos by topic and return titles, channels, and URLs.
version: "1.0.0"
author: SkillForge
license: Apache-2.0
capabilities:
  - Search YouTube by topic or keyword
  - Return video titles, channel names, and URLs
  - Filter by relevance
tools:
  - youtube_search
execution_timeout: 20
---

# YouTube Search Skill

## Purpose
Enables the agent to find relevant YouTube videos for any topic.

## Examples
- "Find tutorials about Transformers architecture"
- "Search for Python data science beginner videos"
- "Find talks about LLM fine-tuning"

## Notes
- Returns publicly available video metadata only
- Risk level: LOW
