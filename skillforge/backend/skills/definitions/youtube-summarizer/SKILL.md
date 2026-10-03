---
name: youtube-summarizer
description: Fetch YouTube video transcripts (no API key) and generate structured summaries using Gemma 4. Works for lectures, tutorials, meetings, and news videos.
version: "1.0.0"
author: SkillForge
license: Apache-2.0
capabilities:
  - Fetch auto-generated captions from any YouTube video
  - Generate structured Gemma 4 summaries (lecture, meeting, news styles)
  - Search YouTube videos without API key via DuckDuckGo
  - Extract key concepts, timestamps, and action items
  - Works on any public video with captions enabled
tools:
  - youtube_transcript
  - youtube_summary
  - youtube_search_ddg
execution_timeout: 60
---

# YouTube Summarizer Skill

## Purpose
Turn any YouTube video into structured knowledge using:
- **youtube-transcript-api** — fetches captions without YouTube API (MIT license)
- **Gemma 4** — summarizes transcripts locally
- **DuckDuckGo** — finds videos without API key

## Summary Styles
| Style | Best For |
|-------|----------|
| `lecture` | University lectures, course videos, tutorials |
| `general` | Any video — default |
| `meeting` | Town halls, standups, recorded meetings |
| `news` | News segments, briefings, announcements |

## Install
```bash
pip3 install youtube-transcript-api
```

## Examples
- "Summarize this ML lecture: https://youtube.com/watch?v=abc123"
- "Find and summarize the best Python async tutorial on YouTube"
- "Extract key points from Stanford CS229 lecture 1"
- "What are the action items from this team meeting recording?"

## Workflow
```
YouTube URL / search query
    ↓
youtube_search_ddg(query)    ← if searching
    ↓
youtube_transcript(url)      ← fetch captions (no API key)
    ↓
youtube_summary(url, style="lecture")
    ↓
Returns: {
  summary: "## Key Points\n...",
  transcript: [...segments with timestamps],
  duration_seconds: 3600,
  language: "en"
}
```

## Privacy
- Reads only **public** YouTube video captions
- No YouTube API key — uses publicly available caption endpoints
- Transcripts processed locally by Gemma 4 (no data sent to external AI)

## Notes
- Auto-generated captions available on ~90% of English YouTube videos
- For best results with non-English videos, set `language` parameter
- Transcript quality depends on YouTube's auto-caption accuracy
- Very long videos (>1hr) use the first 6000 chars of transcript for summary
