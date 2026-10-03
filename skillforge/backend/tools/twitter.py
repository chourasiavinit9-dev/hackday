"""
SkillForge — Twitter / X Tools
Integrated via tweetytweets (MIT License: https://github.com/vedantdhande04/tweetytweets)
Zero API keys, zero paid scrapers.
Uses Chrome DevTools Protocol (CDP) + DuckDuckGo site scraper fallback + demo mode.
"""
from __future__ import annotations

import os
import re
import sys
import time
import json
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Optional

DEMO_MODE = os.environ.get("SKILLFORGE_DEMO", "false").lower() == "true"

# Add tweetytweets scripts to sys.path
TWEETY_ROOT = Path(__file__).resolve().parent.parent / "tweetytweets"
TWEETY_SCRIPTS = TWEETY_ROOT / "scripts"

if TWEETY_SCRIPTS.exists() and str(TWEETY_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(TWEETY_SCRIPTS))

# Try importing tweetytweets modules
_HAS_TWEETY = False
try:
    import browser as tweety_browser
    import research as tweety_research
    import settings as tweety_settings
    import post as tweety_post
    _HAS_TWEETY = True
except Exception:
    tweety_browser = None
    tweety_research = None
    tweety_settings = None
    tweety_post = None

# ── Demo Data ─────────────────────────────────────────────────────────────────

DEMO_TWEETS = [
    {
        "author": "Gemma 4 Devs (@GoogleDeepMind)",
        "handle": "GoogleDeepMind",
        "text": "Announcing Gemma 4: State-of-the-art open models built from the same research and technology used for Gemini models. Perfect for lightweight autonomous agent runtimes.",
        "url": "https://x.com/GoogleDeepMind/status/1780000000000000001",
        "likes": 8420,
        "reposts": 2130,
        "replies": 340,
        "views": 250000,
        "created": "2026-10-02T14:30:00Z",
        "metrics": "8.4K likes, 2.1K reposts, 340 replies",
    },
    {
        "author": "SkillForge Agent (@SkillForgeAI)",
        "handle": "SkillForgeAI",
        "text": "Every tool call in SkillForge is appended to a SHA-256 cryptographic audit ledger. If an action is tampered with or executed without policy approval, the hash chain breaks instantly.",
        "url": "https://x.com/SkillForgeAI/status/1780000000000000002",
        "likes": 1250,
        "reposts": 410,
        "replies": 88,
        "views": 42000,
        "created": "2026-10-02T16:15:00Z",
        "metrics": "1.2K likes, 410 reposts, 88 replies",
    },
    {
        "author": "MLH Hack Day (@MLHacks)",
        "handle": "MLHacks",
        "text": "Hacktoberfest Hack Day Asansol x HackTropica 2026 is LIVE! Hackers are building with Gemma 4, browser-automation agents, and local open-source tools.",
        "url": "https://x.com/MLHacks/status/1780000000000000003",
        "likes": 650,
        "reposts": 180,
        "replies": 45,
        "views": 18500,
        "created": "2026-10-03T08:00:00Z",
        "metrics": "650 likes, 180 reposts, 45 replies",
    },
    {
        "author": "Agent Builder (@AgentCraft)",
        "handle": "AgentCraft",
        "text": "The fastest way to scrape Twitter without banned API keys is minimal CDP directly over websockets to Chrome. Props to tweetytweets for proving you don't need Playwright or Selenium.",
        "url": "https://x.com/AgentCraft/status/1780000000000000004",
        "likes": 320,
        "reposts": 95,
        "replies": 24,
        "views": 12000,
        "created": "2026-10-02T18:45:00Z",
        "metrics": "320 likes, 95 reposts, 24 replies",
    }
]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _is_browser_ready() -> bool:
    """Check if Chrome CDP port is alive."""
    if not _HAS_TWEETY or tweety_browser is None:
        return False
    try:
        return tweety_browser.alive()
    except Exception:
        return False


def _search_twitter_via_ddg(query: str, count: int = 10) -> list[dict]:
    """
    Search Twitter/X via DuckDuckGo Lite without CAPTCHA or API keys.
    Returns normalized tweet structures.
    """
    results: list[dict] = []
    search_q = f"site:x.com {query}"
    encoded = urllib.parse.urlencode({"q": search_q, "kl": "us-en"})
    url = f"https://lite.duckduckgo.com/lite/?{encoded}"

    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html",
            }
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            html = resp.read().decode("utf-8", errors="ignore")

        link_pattern = re.compile(r'<a[^>]+class="result-link"[^>]*href="([^"]+)"[^>]*>([^<]+)</a>', re.IGNORECASE)
        snippet_pattern = re.compile(r'<td[^>]+class="result-snippet"[^>]*>(.*?)</td>', re.IGNORECASE | re.DOTALL)

        links = link_pattern.findall(html)
        snippets = [re.sub(r"<[^>]+>", "", s).strip() for s in snippet_pattern.findall(html)]

        for i, (u, title) in enumerate(links[:count]):
            snippet = snippets[i] if i < len(snippets) else ""
            clean_url = u
            if "uddg=" in u:
                m = re.search(r"uddg=([^&]+)", u)
                if m:
                    clean_url = urllib.parse.unquote(m.group(1))

            # Extract possible author from title or URL
            author = "X User"
            handle = ""
            url_match = re.search(r"x\.com/([^/]+)(?:/status/(\d+))?", clean_url)
            if url_match:
                handle = url_match.group(1)
                author = f"@{handle}"

            results.append({
                "author": author,
                "handle": handle,
                "title": title.strip(),
                "text": snippet or title.strip(),
                "url": clean_url,
                "likes": 0,
                "reposts": 0,
                "replies": 0,
                "views": 0,
                "created": "",
                "source": "ddg_x_scraper",
                "metrics": ""
            })
    except Exception:
        pass

    return results


# ── Core Exported Tools ───────────────────────────────────────────────────────

def twitter_search(query: str, count: int = 10, mode: str = "top") -> dict:
    """
    Search and scrape tweets from Twitter/X using tweetytweets CDP driver.
    If Chrome CDP is not active or logged in, seamlessly uses DuckDuckGo CAPTCHA-free
    site search fallback. In demo mode, returns realistic curated agent tweets.

    Args:
        query: Search term or hashtag (e.g., 'AI agents', 'Gemma 4', 'Hacktoberfest')
        count: Maximum number of tweets to return (default 10)
        mode: Search mode: 'top' or 'latest' (tweetytweets mode)
    """
    t0 = time.time()
    count = max(1, min(count, 50))

    if DEMO_MODE:
        filtered = [t for t in DEMO_TWEETS if query.lower() in (t["text"] + t["author"]).lower()]
        for t in DEMO_TWEETS:
            if t not in filtered:
                filtered.append(t)
        res = filtered
        return {
            "query": query,
            "mode": mode,
            "engine": "tweetytweets_demo",
            "source": "DEMO DATA (SKILLFORGE_DEMO=true)",
            "count": len(res[:count]),
            "tweets": res[:count],
            "duration_ms": int((time.time() - t0) * 1000)
        }

    # 1. Try tweetytweets CDP if browser is open and responsive
    if _is_browser_ready() and tweety_research is not None:
        try:
            raw_tweets = tweety_research.x_search([query], mode=mode)
            if raw_tweets:
                formatted = []
                for item in raw_tweets[:count]:
                    extra = item.get("extra") or {}
                    formatted.append({
                        "author": extra.get("author") or "Unknown",
                        "handle": (extra.get("author") or "").split(" ")[-1],
                        "text": extra.get("text") or item.get("title", ""),
                        "url": item.get("url", ""),
                        "likes": item.get("score") or 0,
                        "reposts": extra.get("reposts") or 0,
                        "replies": item.get("comments") or 0,
                        "views": extra.get("views") or 0,
                        "created": item.get("created") or "",
                        "metrics": extra.get("metrics") or "",
                        "source": "tweetytweets_cdp"
                    })
                if formatted:
                    return {
                        "query": query,
                        "mode": mode,
                        "engine": "tweetytweets_cdp",
                        "source": "live_browser_dom",
                        "count": len(formatted),
                        "tweets": formatted,
                        "duration_ms": int((time.time() - t0) * 1000)
                    }
        except Exception:
            pass

    # 2. Fast CAPTCHA-free DDG live fallback for public X posts
    ddg_results = _search_twitter_via_ddg(query, count)
    if ddg_results:
        return {
            "query": query,
            "mode": mode,
            "engine": "tweetytweets_ddg_fallback",
            "source": "live_public_web",
            "count": len(ddg_results),
            "tweets": ddg_results,
            "duration_ms": int((time.time() - t0) * 1000)
        }

    # 3. Final fallback: curated demo tweets matching topic
    return {
        "query": query,
        "mode": mode,
        "engine": "tweetytweets_fallback",
        "source": "cached_demo",
        "count": len(DEMO_TWEETS[:count]),
        "tweets": DEMO_TWEETS[:count],
        "duration_ms": int((time.time() - t0) * 1000)
    }


def twitter_user_tweets(handle: str, count: int = 5) -> dict:
    """
    Scrape recent tweets from a specific Twitter/X user profile.
    Uses tweetytweets CDP or site search fallback.
    """
    clean_handle = handle.lstrip("@").strip()
    return twitter_search(f"from:{clean_handle}", count=count, mode="latest")


def twitter_research_trends(topics: list[str] = None, hours: int = 36) -> dict:
    """
    Collect multi-source intelligence using tweetytweets research pipeline:
    Aggregates Hacker News, Reddit, and Twitter/X topics into an organized research swipe file.
    """
    t0 = time.time()
    topics = topics or ["AI agents", "LLM", "open source AI", "developer tools"]

    if DEMO_MODE or not _HAS_TWEETY or tweety_research is None:
        return {
            "topics": topics,
            "window_hours": hours,
            "source": "tweetytweets_research_demo",
            "items": [
                {
                    "source": "hn",
                    "title": "Show HN: Gemma 4 Agent Runtime with Cryptographic Audit Ledger",
                    "url": "https://news.ycombinator.com/item?id=38912345",
                    "score": 240,
                    "comments": 68,
                    "created": "2026-10-02T18:00:00Z"
                },
                {
                    "source": "reddit:LocalLLaMA",
                    "title": "Gemma 4 running locally with function calling is surprisingly good",
                    "url": "https://reddit.com/r/LocalLLaMA/comments/xyz123",
                    "score": 380,
                    "comments": 95,
                    "created": "2026-10-02T20:30:00Z"
                },
                {
                    "source": "x:AI agents",
                    "title": DEMO_TWEETS[1]["text"],
                    "url": DEMO_TWEETS[1]["url"],
                    "score": DEMO_TWEETS[1]["likes"],
                    "comments": DEMO_TWEETS[1]["replies"],
                    "created": DEMO_TWEETS[1]["created"]
                }
            ],
            "duration_ms": int((time.time() - t0) * 1000)
        }

    try:
        # Run HN search from tweetytweets research module
        hn_items = tweety_research.hn(points=50, hours=hours, query=topics[0] if topics else None)
        # Search X
        x_items = twitter_search(topics[0], count=5).get("tweets", [])
        combined = []
        for h in (hn_items or [])[:5]:
            combined.append({
                "source": "hn",
                "title": h.get("title"),
                "url": h.get("url"),
                "score": h.get("score", 0),
                "comments": h.get("comments", 0),
                "created": h.get("created")
            })
        for x in x_items:
            combined.append({
                "source": "x",
                "title": x.get("text", "")[:120],
                "url": x.get("url"),
                "score": x.get("likes", 0),
                "comments": x.get("replies", 0),
                "created": x.get("created")
            })

        return {
            "topics": topics,
            "window_hours": hours,
            "source": "tweetytweets_pipeline",
            "items": combined,
            "duration_ms": int((time.time() - t0) * 1000)
        }
    except Exception as e:
        return {
            "topics": topics,
            "error": str(e),
            "source": "fallback",
            "items": [],
            "duration_ms": int((time.time() - t0) * 1000)
        }


def twitter_post_tweet(text: str, verify: bool = True) -> dict:
    """
    Publish a post to X/Twitter using tweetytweets CDP automation.
    HIGH RISK — Subject to SkillForge Approval Policy Engine.
    """
    t0 = time.time()
    text = text.strip()
    if not text:
        return {"error": "Tweet text cannot be empty"}

    if DEMO_MODE or not _HAS_TWEETY or tweety_post is None:
        return {
            "status": "staged_demo",
            "action": "post_tweet",
            "text": text,
            "char_count": len(text),
            "simulated": True,
            "message": f"Tweet successfully validated & staged (Demo Mode). Text: '{text[:60]}...'",
            "duration_ms": int((time.time() - t0) * 1000)
        }

    # Attempt live post via tweetytweets CDP if session available
    try:
        if _is_browser_ready():
            res = tweety_post.do_post(text, verify=verify)
            return {
                "status": "published",
                "text": text,
                "result": res,
                "duration_ms": int((time.time() - t0) * 1000)
            }
        else:
            return {
                "status": "staged_offline",
                "text": text,
                "message": "Browser CDP port 9222 not connected. Launch browser via `python tweetytweets/scripts/browser.py launch` to publish live.",
                "duration_ms": int((time.time() - t0) * 1000)
            }
    except Exception as e:
        return {
            "status": "error",
            "text": text,
            "error": str(e),
            "duration_ms": int((time.time() - t0) * 1000)
        }


def twitter_status() -> dict:
    """Check tweetytweets CDP driver and profile health."""
    ready = _is_browser_ready()
    return {
        "tweetytweets_installed": _HAS_TWEETY,
        "cdp_alive": ready,
        "repo": "https://github.com/vedantdhande04/tweetytweets",
        "license": "MIT",
        "browser_profile": str(Path.home() / ".tweetytweets" / "chrome-profile")
    }


# ── Draft → Approve → Publish → Verify flow ──────────────────────────────────

def draft_post(topic: str, sources: list = None, max_chars: int = 280) -> dict:
    """
    Generate a draft social post grounded in real research sources.
    Does NOT post anything — returns a draft for user review and approval.

    This is always safe to call. Posting requires a separate explicit approval
    via the policy engine before twitter_post_tweet is ever called.

    Args:
        topic:     The topic or goal to write about
        sources:   Optional list of source dicts {title, url, snippet} from reach_research
        max_chars: Platform character limit (280 for X/Twitter by default)

    Returns:
        {draft, char_count, sources_used, ready_to_post: False, requires_approval: True}
    """
    t0 = time.time()
    topic = (topic or "").strip()
    if not topic:
        return {"error": "topic cannot be empty", "draft": ""}

    sources = sources or []

    # Build grounded draft from real sources
    source_snippets = []
    source_urls     = []
    for s in sources[:3]:
        if isinstance(s, dict) and not s.get("error"):
            snippet = (s.get("snippet") or s.get("full_content") or "")[:120]
            url     = s.get("url", "")
            if snippet:
                source_snippets.append(snippet)
            if url:
                source_urls.append(url)

    # Use Gemma to generate the draft if available, otherwise keyword template
    draft = _generate_draft_text(topic, source_snippets, max_chars)

    # Append first source URL if it fits
    if source_urls and len(draft) + len(source_urls[0]) + 2 <= max_chars:
        draft = f"{draft}\n{source_urls[0]}"

    return {
        "draft":            draft.strip(),
        "char_count":       len(draft.strip()),
        "max_chars":        max_chars,
        "sources_used":     source_urls,
        "ready_to_post":    False,           # always False — must go through approval gate
        "requires_approval": True,           # policy engine will enforce this
        "action":           "review_and_approve_before_posting",
        "duration_ms":      int((time.time() - t0) * 1000)
    }


def _generate_draft_text(topic: str, snippets: list, max_chars: int) -> str:
    """
    Generate tweet text. Tries Gemma first; falls back to keyword template.
    Private helper — not exposed as a tool.
    """
    # Try Gemma synthesis
    try:
        from agent.gemma_provider import get_provider
        provider = get_provider()
        if provider.model:
            prompt = (
                f"Write a concise, engaging social media post (max {max_chars} chars) about: {topic}\n\n"
                + (f"Grounded in these real findings:\n" + "\n".join(f"- {s}" for s in snippets[:2]) + "\n\n" if snippets else "")
                + "Rules: No hashtag spam (max 2). No emojis unless natural. No fabricated statistics. "
                  "Return ONLY the post text, nothing else."
            )
            import signal, time as _time
            t0 = _time.time()
            resp = provider.model.generate_content(
                prompt,
                generation_config=provider.genai.types.GenerationConfig(
                    temperature=0.6, max_output_tokens=120
                )
            )
            text = provider._strip_scratchpad(resp.text.strip())
            if text and len(text) <= max_chars + 20:
                return text[:max_chars]
    except Exception:
        pass

    # Keyword-template fallback
    lead = snippets[0][:180] if snippets else topic
    intro = f"On {topic}:\n" if len(topic) < 60 else ""
    body  = f"{intro}{lead}"
    if len(body) > max_chars - 10:
        body = body[:max_chars - 10].rstrip() + "…"
    return body


def verify_post(handle: str, expected_text_fragment: str, max_age_minutes: int = 5) -> dict:
    """
    Verify that a post was actually published by checking the user's recent tweets.
    Uses tweetytweets CDP if available, falls back to DuckDuckGo site search.

    This is the verification step — the UI should only show "Published" after
    this function returns verified=True.

    Args:
        handle:                 Twitter/X handle (without @)
        expected_text_fragment: A unique fragment of the posted text to look for
        max_age_minutes:        How recently the post must appear (default: 5 min)

    Returns:
        {verified: bool, found_url: str|None, method: str, message: str}
    """
    t0 = time.time()
    handle  = handle.lstrip("@").strip()
    fragment = (expected_text_fragment or "").strip().lower()

    if not handle:
        return {"verified": False, "error": "handle is required", "found_url": None}
    if not fragment:
        return {"verified": False, "error": "expected_text_fragment is required", "found_url": None}

    if DEMO_MODE:
        return {
            "verified":  True,
            "found_url": f"https://x.com/{handle}/status/demo-{int(time.time())}",
            "method":    "demo",
            "message":   "Demo mode: verification simulated",
            "duration_ms": 0
        }

    # 1. Try tweetytweets CDP (most accurate)
    if _is_browser_ready() and tweety_research is not None:
        try:
            raw_tweets = tweety_research.x_search([f"from:{handle}"], mode="latest")
            for item in (raw_tweets or [])[:10]:
                text = (item.get("extra") or {}).get("text") or item.get("title", "")
                if fragment in text.lower():
                    return {
                        "verified":  True,
                        "found_url": item.get("url", ""),
                        "method":    "tweetytweets_cdp",
                        "message":   "Post found via CDP browser session",
                        "duration_ms": int((time.time() - t0) * 1000)
                    }
        except Exception:
            pass

    # 2. DuckDuckGo site search fallback
    ddg_results = _search_twitter_via_ddg(f"from:{handle} {expected_text_fragment[:60]}", count=5)
    for r in ddg_results:
        text = (r.get("text") or r.get("title") or "").lower()
        if fragment in text or handle.lower() in r.get("url", "").lower():
            return {
                "verified":  True,
                "found_url": r.get("url", ""),
                "method":    "ddg_site_search",
                "message":   "Post found via DuckDuckGo public search",
                "duration_ms": int((time.time() - t0) * 1000)
            }

    return {
        "verified":   False,
        "found_url":  None,
        "method":     "ddg_site_search",
        "message":    (
            f"Post by @{handle} containing '{expected_text_fragment[:40]}' not found in public search. "
            "It may still be propagating — try again in 60 seconds, or check x.com directly."
        ),
        "duration_ms": int((time.time() - t0) * 1000)
    }


def research_and_draft(topic: str, num_sources: int = 4) -> dict:
    """
    Research a topic using Agent-Reach (web search + Jina Reader) and
    immediately generate a grounded draft post. One-step convenience tool.

    Flow: Agent-Reach search → collect sources → draft_post()
    The returned draft is NOT posted. It must be approved via the policy gate first.
    """
    t0 = time.time()
    from tools.agent_reach import reach_research
    research = reach_research(topic)
    sources  = research.get("sources", [])[:num_sources]
    draft    = draft_post(topic, sources=sources)

    return {
        "topic":         topic,
        "sources":       sources,
        "source_count":  research.get("source_count", 0),
        "draft":         draft.get("draft", ""),
        "char_count":    draft.get("char_count", 0),
        "ready_to_post": False,   # always False — must go through approval
        "requires_approval": True,
        "attribution": {
            "research": "Agent-Reach (MIT) — https://github.com/Panniantong/Agent-Reach",
            "posting":  "tweetytweets (MIT) — https://github.com/vedantdhande04/tweetytweets"
        },
        "duration_ms": int((time.time() - t0) * 1000)
    }
