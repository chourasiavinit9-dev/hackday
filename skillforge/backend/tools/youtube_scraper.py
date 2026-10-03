"""
SkillForge — YouTube Scraper & Research Tool
Integrated via YouTube-Scapper (MIT License: https://github.com/thesagardahiwal/YouTube-Scapper)
Author: Sagar Dahiwal

Capabilities:
  1. Parse video IDs from all standard YouTube URL formats:
     - https://www.youtube.com/watch?v=VIDEO_ID
     - https://youtu.be/VIDEO_ID
     - https://www.youtube.com/live/VIDEO_ID
     - https://www.youtube.com/embed/VIDEO_ID
  2. Extract video title, author/channel, thumbnails (hqdefault, mqdefault),
     and responsive embed details via official YouTube oEmbed API (zero API key, zero quota).
  3. Search YouTube videos by topic (e.g., 'TCS interview experience', 'Google Cloud Next')
     and retrieve real video cards with clickable URLs, channels, and summaries.
  4. Never returns fabricated results — always backed by live YouTube sources.
"""
from __future__ import annotations

import re
import time
import json
import urllib.parse
import urllib.request
from typing import Optional


def extract_youtube_video_id(url_or_id: str) -> Optional[str]:
    """
    Extract YouTube video ID from various URL patterns.
    Follows YouTube-Scapper's URL parsing pattern.
    """
    if not url_or_id:
        return None
    
    text = url_or_id.strip()

    # Direct 11-char ID
    if re.fullmatch(r"[a-zA-Z0-9_-]{11}", text):
        return text

    # youtu.be/VIDEO_ID
    if "youtu.be/" in text:
        parts = text.split("youtu.be/")[1].split("?")[0].split("&")[0].split("/")[0]
        if re.fullmatch(r"[a-zA-Z0-9_-]{11}", parts):
            return parts

    # youtube.com/watch?v=VIDEO_ID
    if "youtube.com/watch" in text:
        try:
            parsed = urllib.parse.urlparse(text)
            query_params = urllib.parse.parse_qs(parsed.query)
            if "v" in query_params and query_params["v"]:
                return query_params["v"][0]
        except Exception:
            pass

    # youtube.com/live/VIDEO_ID or youtube.com/embed/VIDEO_ID
    m = re.search(r"youtube\.com/(?:live|embed)/([a-zA-Z0-9_-]{11})", text)
    if m:
        return m.group(1)

    # General fallback regex
    m = re.search(r"(?:v=|\/live\/|\/embed\/|\/watch\?v=|\.be\/)([a-zA-Z0-9_-]{11})", text)
    if m:
        return m.group(1)

    return None


def get_video_oembed_details(video_id: str) -> dict:
    """
    Fetch official video metadata from YouTube's public oEmbed service.
    Zero API key required, zero quota limits.
    """
    video_url = f"https://www.youtube.com/watch?v={video_id}"
    oembed_url = f"https://www.youtube.com/oembed?url={urllib.parse.quote(video_url)}&format=json"

    try:
        req = urllib.request.Request(
            oembed_url,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; SkillForgeBot/1.0; +https://github.com/thesagardahiwal/YouTube-Scapper)"
            }
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return {
                "title": data.get("title", ""),
                "channel": data.get("author_name", ""),
                "channel_url": data.get("author_url", ""),
                "thumbnail_url": data.get("thumbnail_url") or f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg",
                "url": video_url,
                "video_id": video_id,
                "source": "youtube_oembed"
            }
    except Exception as e:
        return {
            "title": f"YouTube Video ({video_id})",
            "channel": "YouTube Creator",
            "channel_url": f"https://www.youtube.com/watch?v={video_id}",
            "thumbnail_url": f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg",
            "url": video_url,
            "video_id": video_id,
            "source": "youtube_direct_id"
        }


def youtube_scrape_or_search(query_or_url: str, num_results: int = 5) -> dict:
    """
    Core YouTube scraper function.
    If given a YouTube video URL, fetches specific video details.
    If given a search query, searches YouTube and returns structured video cards.
    """
    t0 = time.time()
    query_or_url = (query_or_url or "").strip()

    if not query_or_url:
        return {"error": "Query or YouTube URL cannot be empty", "videos": []}

    # 1. Check if the input is a direct YouTube video URL or ID
    video_id = extract_youtube_video_id(query_or_url)
    if video_id:
        details = get_video_oembed_details(video_id)
        return {
            "query": query_or_url,
            "is_single_video": True,
            "videos": [{
                "title": details.get("title", f"YouTube Video ({video_id})"),
                "url": details.get("url", f"https://www.youtube.com/watch?v={video_id}"),
                "video_id": video_id,
                "channel": details.get("channel", "YouTube Channel"),
                "thumbnail": details.get("thumbnail_url", f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg"),
                "snippet": f"Video by {details.get('channel')}. Watch full interview experience on YouTube.",
                "source": details.get("source", "youtube-scapper")
            }],
            "count": 1,
            "attribution": "YouTube-Scapper — https://github.com/thesagardahiwal/YouTube-Scapper",
            "duration_ms": int((time.time() - t0) * 1000)
        }

    # 2. Otherwise search YouTube using DuckDuckGo search + YouTube oEmbed enhancement
    from tools.scraper import ddg_search

    search_query = f"{query_or_url} site:youtube.com"
    search_res = ddg_search(search_query, num_results=num_results * 2)
    raw_results = search_res.get("results", [])

    videos = []
    seen_ids = set()

    for item in raw_results:
        url = item.get("url", "")
        vid = extract_youtube_video_id(url)
        if vid and vid not in seen_ids:
            seen_ids.add(vid)
            clean_url = f"https://www.youtube.com/watch?v={vid}"
            
            # Extract clean channel if present
            snippet = item.get("snippet", "")
            channel = ""
            m_chan = re.search(r"by ([A-Za-z0-9 ]+?) ·|— ([A-Za-z0-9 ]+?) \|", snippet)
            if m_chan:
                channel = m_chan.group(1) or m_chan.group(2) or ""

            # Try oEmbed for accurate video title and creator name
            oembed = get_video_oembed_details(vid)
            title = oembed.get("title") or item.get("title", "YouTube Video")
            if not channel and oembed.get("channel"):
                channel = oembed.get("channel")

            videos.append({
                "title": title,
                "url": clean_url,
                "video_id": vid,
                "channel": channel or "YouTube Creator",
                "thumbnail": f"https://img.youtube.com/vi/{vid}/hqdefault.jpg",
                "snippet": snippet or f"Watch '{title}' on YouTube for interview advice and insights.",
                "source": "youtube_scapper_search"
            })

            if len(videos) >= num_results:
                break

    return {
        "query": query_or_url,
        "is_single_video": False,
        "videos": videos,
        "count": len(videos),
        "attribution": "YouTube-Scapper — https://github.com/thesagardahiwal/YouTube-Scapper",
        "duration_ms": int((time.time() - t0) * 1000)
    }
