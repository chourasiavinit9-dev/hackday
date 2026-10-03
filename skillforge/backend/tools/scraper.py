"""
SkillForge — Web Scraping & YouTube Tools
Open-source, CAPTCHA-free, no API keys required.

Tools:
  ddg_search()         — DuckDuckGo search (MIT, no CAPTCHA, no key)
  extract_article()    — trafilatura article extractor (Apache 2.0)
  youtube_transcript() — raw captions from any YouTube video (MIT)
  youtube_summary()    — captions → Gemma 4 summary
  youtube_search_ddg() — find YouTube videos via DDG

All have demo-mode fallbacks so the app works without installation.
"""

import os
import re
import time
import json
import urllib.request
import urllib.parse
from typing import Optional

DEMO_MODE = os.environ.get("SKILLFORGE_DEMO", "false").lower() == "true"

# ── Demo data ──────────────────────────────────────────────────────────────────

DEMO_DDG_RESULTS = [
    {
        "title": "Python Data Science Handbook — Jake VanderPlas",
        "url": "https://jakevdp.github.io/PythonDataScienceHandbook/",
        "snippet": "This is the open access version of Python Data Science Handbook — covers NumPy, Pandas, Matplotlib, ML. [DEMO DATA]"
    },
    {
        "title": "Real Python — Machine Learning Tutorials",
        "url": "https://realpython.com/tutorials/machine-learning/",
        "snippet": "Hands-on Python machine learning tutorials for all skill levels. [DEMO DATA]"
    },
    {
        "title": "Towards Data Science — Pandas Tutorial",
        "url": "https://towardsdatascience.com/pandas-tutorial",
        "snippet": "Complete guide to Pandas DataFrames with examples. [DEMO DATA]"
    },
]

DEMO_ARTICLE = """
Python Data Science Handbook

This is a comprehensive guide to data science using Python.
Key topics covered:
- NumPy for numerical computing
- Pandas for data manipulation
- Matplotlib for visualization
- Scikit-learn for machine learning

The book is available free online and covers practical examples
for data scientists at all levels.
[DEMO DATA — trafilatura not installed]
"""

DEMO_TRANSCRIPT = [
    {"text": "Welcome to this lecture on machine learning fundamentals.", "start": 0.0, "duration": 3.5},
    {"text": "Today we'll cover supervised learning, including classification and regression.", "start": 3.5, "duration": 4.0},
    {"text": "Supervised learning means we train a model on labelled data.", "start": 7.5, "duration": 3.8},
    {"text": "The model learns to map inputs to outputs based on examples.", "start": 11.3, "duration": 4.2},
    {"text": "Key algorithms include linear regression, decision trees, and neural networks.", "start": 15.5, "duration": 4.5},
    {"text": "We evaluate performance using metrics like accuracy, precision, and recall.", "start": 20.0, "duration": 4.0},
    {"text": "Cross-validation helps us avoid overfitting to the training data.", "start": 24.0, "duration": 3.5},
    {"text": "Thank you for watching! Next lecture covers unsupervised learning.", "start": 27.5, "duration": 3.0},
]

DEMO_SUMMARY = """## Video Summary [DEMO DATA]

**Topic:** Machine Learning Fundamentals — Supervised Learning

### Key Points
1. **Supervised learning** trains models on labelled input→output pairs
2. **Core algorithms** covered: linear regression, decision trees, neural networks
3. **Evaluation metrics**: accuracy, precision, recall (F1 score)
4. **Cross-validation** prevents overfitting to training data

### Main Takeaways
- Start with simple models (linear regression) before complex ones
- Always split data into train/validation/test sets
- Metric choice depends on the problem (e.g., recall matters more for medical diagnosis)

### Suggested Next Steps
- Watch the unsupervised learning lecture
- Try scikit-learn examples from the Python Data Science Handbook
"""


# ── DuckDuckGo Search (no CAPTCHA, no API key) ────────────────────────────────

def ddg_search(query: str, num_results: int = 5, safe_search: str = "moderate") -> dict:
    """
    Search DuckDuckGo — CAPTCHA-free, no API key, MIT license.
    Uses duckduckgo-search library if available, falls back to DDG Lite HTML scraping.
    Install: pip3 install duckduckgo-search
    """
    t0 = time.time()

    # Try duckduckgo-search / ddgs library first (best)
    try:
        # v9+ renamed to ddgs
        try:
            from ddgs import DDGS
        except ImportError:
            from duckduckgo_search import DDGS

        results = []
        with DDGS() as ddgs_client:
            for r in ddgs_client.text(query, max_results=num_results, safesearch=safe_search):
                results.append({
                    "title": r.get("title", ""),
                    "url": r.get("href", "") or r.get("url", ""),
                    "snippet": r.get("body", "") or r.get("description", "")
                })
                if len(results) >= num_results:
                    break
        return {
            "results": results,
            "query": query,
            "engine": "ddg",
            "duration_ms": int((time.time() - t0) * 1000)
        }
    except Exception:
        pass

    # Fallback: DDG Lite (plain HTML, no JS needed, minimal anti-bot)
    try:
        encoded = urllib.parse.urlencode({"q": query, "kl": "us-en"})
        url = f"https://lite.duckduckgo.com/lite/?{encoded}"
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; SkillForgeBot/1.0; +https://github.com/skillforge)",
                "Accept": "text/html",
            }
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            html = resp.read().decode("utf-8", errors="ignore")

        # Extract results from DDG Lite HTML
        results = _parse_ddg_lite(html, num_results)
        return {
            "results": results,
            "query": query,
            "engine": "ddg-lite-fallback",
            "duration_ms": int((time.time() - t0) * 1000)
        }
    except Exception as e:
        return {
            "results": DEMO_DDG_RESULTS[:num_results],
            "query": query,
            "engine": "demo-fallback",
            "error": str(e),
            "duration_ms": int((time.time() - t0) * 1000)
        }



def _parse_ddg_lite(html: str, limit: int) -> list:
    """Parse DuckDuckGo Lite HTML without BeautifulSoup."""
    results = []
    # DDG Lite puts results in <a class="result-link"> tags
    link_pattern = re.compile(r'<a[^>]+class="result-link"[^>]*href="([^"]+)"[^>]*>([^<]+)</a>', re.IGNORECASE)
    snippet_pattern = re.compile(r'<td[^>]+class="result-snippet"[^>]*>(.*?)</td>', re.IGNORECASE | re.DOTALL)

    links = link_pattern.findall(html)
    snippets = [re.sub(r"<[^>]+>", "", s).strip() for s in snippet_pattern.findall(html)]

    for i, (url, title) in enumerate(links[:limit]):
        results.append({
            "title": title.strip(),
            "url": url,
            "snippet": snippets[i] if i < len(snippets) else ""
        })
    return results


def ddg_web_search(query: str, num_results: int = 5) -> dict:
    """Alias for ddg_search — used as the primary web_search tool replacement."""
    return ddg_search(query, num_results)


# ── Article Extractor (trafilatura) ───────────────────────────────────────────

def extract_article(url: str, include_comments: bool = False) -> dict:
    """
    Extract clean article text from any URL using trafilatura (Apache 2.0).
    Best-in-class for news sites, blogs, documentation pages.
    No CAPTCHA bypass — only reads public pages.
    Install: pip3 install trafilatura
    """
    t0 = time.time()

    # Try trafilatura (best quality)
    try:
        import trafilatura
        downloaded = trafilatura.fetch_url(url)
        if downloaded:
            text = trafilatura.extract(
                downloaded,
                include_comments=include_comments,
                include_tables=True,
                no_fallback=False
            )
            if text:
                return {
                    "url": url,
                    "content": text[:5000],
                    "extractor": "trafilatura",
                    "duration_ms": int((time.time() - t0) * 1000)
                }
    except ImportError:
        pass

    # Fallback: lxml + regex (already installed)
    try:
        from lxml import html as lhtml
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; SkillForge/1.0)"}
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            raw = resp.read().decode("utf-8", errors="ignore")

        tree = lhtml.fromstring(raw)
        # Remove scripts/styles
        for bad in tree.xpath("//script | //style | //nav | //footer | //header"):
            bad.getparent().remove(bad)

        # Get main content
        paragraphs = tree.xpath("//article//p | //main//p | //div[@class='content']//p | //p")
        text = "\n".join(p.text_content().strip() for p in paragraphs if len(p.text_content().strip()) > 40)
        return {
            "url": url,
            "content": text[:5000],
            "extractor": "lxml-fallback",
            "duration_ms": int((time.time() - t0) * 1000)
        }
    except Exception as e:
        return {"url": url, "content": "", "error": str(e), "duration_ms": int((time.time() - t0) * 1000)}


# ── YouTube Transcript ────────────────────────────────────────────────────────

def _extract_video_id(url_or_id: str) -> Optional[str]:
    """Extract YouTube video ID from any URL format or return bare ID."""
    patterns = [
        r"(?:v=|youtu\.be/|/embed/|/shorts/)([a-zA-Z0-9_-]{11})",
        r"^([a-zA-Z0-9_-]{11})$"
    ]
    for pattern in patterns:
        m = re.search(pattern, url_or_id)
        if m:
            return m.group(1)
    return None


def youtube_transcript(url_or_id: str, language: str = "en") -> dict:
    """
    Fetch YouTube video transcript/captions — MIT license, no API key.
    Works with auto-generated captions on most videos.
    Install: pip3 install youtube-transcript-api
    """
    t0 = time.time()

    video_id = _extract_video_id(url_or_id)
    if not video_id:
        return {"error": f"Could not extract video ID from: {url_or_id}", "transcript": []}

    try:
        from youtube_transcript_api import YouTubeTranscriptApi

        api = YouTubeTranscriptApi()   # v1.2+ is instance-based

        # Try requested language, then English, then any available
        try:
            transcript_obj = api.fetch(video_id, languages=[language, "en"])
        except Exception:
            # list all available and pick first
            transcript_list = api.list(video_id)
            all_langs = [t.language_code for t in transcript_list]
            transcript_obj = api.fetch(video_id, languages=all_langs[:3])

        # transcript_obj is iterable of snippet dicts
        segments = [{"text": s.text, "start": s.start, "duration": s.duration}
                    for s in transcript_obj]

        full_text = " ".join(s["text"] for s in segments)
        total_duration = segments[-1]["start"] + segments[-1]["duration"] if segments else 0

        return {
            "video_id": video_id,
            "url": f"https://youtube.com/watch?v={video_id}",
            "transcript": segments,
            "full_text": full_text,
            "duration_seconds": round(total_duration, 1),
            "word_count": len(full_text.split()),
            "duration_ms": int((time.time() - t0) * 1000)
        }

    except ImportError:
        # Fallback: try scraping YouTube's timedtext endpoint
        return _youtube_transcript_scrape(video_id, t0)
    except Exception as e:
        return {"video_id": video_id, "error": str(e), "transcript": [], "full_text": ""}


def _youtube_transcript_scrape(video_id: str, t0: float) -> dict:
    """
    Fallback: fetch captions via YouTube's public timedtext API.
    No API key, no authentication needed for auto-captions.
    """
    try:
        # Get the video page to find caption track URLs
        url = f"https://www.youtube.com/watch?v={video_id}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            html = resp.read().decode("utf-8", errors="ignore")

        # Extract caption URL from page source
        caption_match = re.search(r'"captionTracks":\[({.*?})\]', html)
        if not caption_match:
            return {"video_id": video_id, "error": "No captions found", "transcript": [], "full_text": ""}

        caption_data = caption_match.group(1)
        base_url_match = re.search(r'"baseUrl":"(https://[^"]+)"', caption_data)
        if not base_url_match:
            return {"video_id": video_id, "error": "Caption URL not found", "transcript": [], "full_text": ""}

        caption_url = base_url_match.group(1).replace("\\u0026", "&")
        with urllib.request.urlopen(caption_url, timeout=8) as resp:
            xml = resp.read().decode("utf-8")

        # Parse caption XML
        texts = re.findall(r'<text start="([^"]+)" dur="([^"]+)"[^>]*>([^<]+)</text>', xml)
        segments = [
            {"text": t.replace("&amp;", "&").replace("&#39;", "'").replace("&quot;", '"'),
             "start": float(s), "duration": float(d)}
            for s, d, t in texts
        ]
        full_text = " ".join(s["text"] for s in segments)

        return {
            "video_id": video_id,
            "url": f"https://youtube.com/watch?v={video_id}",
            "transcript": segments,
            "full_text": full_text,
            "duration_seconds": round(float(texts[-1][0]) + float(texts[-1][1]), 1) if texts else 0,
            "extractor": "timedtext-fallback",
            "duration_ms": int((time.time() - t0) * 1000)
        }
    except Exception as e:
        return {
            "video_id": video_id,
            "error": str(e),
            "transcript": DEMO_TRANSCRIPT,
            "full_text": " ".join(s["text"] for s in DEMO_TRANSCRIPT),
            "source": "demo-fallback",
            "duration_ms": int((time.time() - t0) * 1000)
        }


def youtube_summary(url_or_id: str, language: str = "en", style: str = "lecture") -> dict:
    """
    Get YouTube transcript then summarize with Gemma 4.
    style: 'lecture' | 'general' | 'meeting' | 'news'
    """
    t0 = time.time()

    # Step 1: Get transcript
    transcript_result = youtube_transcript(url_or_id, language)
    if "error" in transcript_result and not transcript_result.get("full_text"):
        return {**transcript_result, "summary": None}

    full_text = transcript_result.get("full_text", "")
    duration = transcript_result.get("duration_seconds", 0)

    if not full_text.strip():
        return {"error": "No transcript content found", "summary": None}

    if len(full_text) < 10:
        return {
            **transcript_result,
            "summary": DEMO_SUMMARY,
            "style": style,
            "source": "DEMO DATA FALLBACK",
            "duration_ms": int((time.time() - t0) * 1000)
        }

    # Step 2: Summarize with Gemma 4
    try:
        import sys, os
        sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
        from agent.gemma_provider import get_provider

        style_prompts = {
            "lecture": "Create a structured lecture summary with: key concepts, main points numbered, important definitions, and suggested follow-up topics.",
            "general": "Summarize the main points of this video in a concise, readable format.",
            "meeting": "Extract action items, decisions made, and key discussion points from this meeting transcript.",
            "news": "Summarize the key facts, who/what/when/where/why from this news content.",
        }

        prompt = f"""Summarize this YouTube video transcript ({int(duration)}s long).

Style: {style_prompts.get(style, style_prompts['general'])}

Transcript:
{full_text[:6000]}

Format your response as clean markdown with headers and bullet points."""

        provider = get_provider()
        if provider.model:
            response = provider.model.generate_content(prompt)
            summary_text = response.text if hasattr(response, "text") else DEMO_SUMMARY
        else:
            summary_text = DEMO_SUMMARY

        return {
            **transcript_result,
            "summary": summary_text,
            "style": style,
            "model_used": provider.model_name,
            "duration_ms": int((time.time() - t0) * 1000)
        }

    except Exception as e:
        # Fallback: extractive summary (no model needed)
        sentences = re.split(r'[.!?]+', full_text)
        key_sentences = [s.strip() for s in sentences if len(s.strip()) > 40][:10]
        summary_text = "## Key Points\n\n" + "\n".join(f"- {s}" for s in key_sentences)
        return {
            **transcript_result,
            "summary": summary_text,
            "style": style,
            "model_used": "extractive-fallback",
            "error_note": str(e),
            "duration_ms": int((time.time() - t0) * 1000)
        }


def youtube_search_ddg(query: str, num_results: int = 5) -> dict:
    """
    Search YouTube videos via DuckDuckGo (no API key, no CAPTCHA).
    Returns title, URL, channel, description.
    """
    result = ddg_search(f"{query} site:youtube.com", num_results=num_results * 2)
    videos = []
    for r in result.get("results", []):
        url = r.get("url", "")
        vid_id = _extract_video_id(url)
        if vid_id or "youtube.com/watch" in url or "youtu.be/" in url:
            videos.append({
                "title": r.get("title", ""),
                "url": url if "youtube" in url else f"https://youtube.com/watch?v={vid_id}",
                "video_id": vid_id,
                "snippet": r.get("snippet", ""),
                "channel": _extract_channel_from_snippet(r.get("snippet", ""))
            })
        if len(videos) >= num_results:
            break
    return {
        "videos": videos or result.get("results", [])[:num_results],
        "query": query,
        "duration_ms": result.get("duration_ms", 0)
    }


def _extract_channel_from_snippet(snippet: str) -> str:
    """Try to extract YouTube channel name from search snippet."""
    m = re.search(r"by ([A-Za-z0-9 ]+?) ·|— ([A-Za-z0-9 ]+?) \|", snippet)
    return m.group(1) or m.group(2) if m else ""
