"""
SkillForge — Agent-Reach Adapter
Provides the web-research layer that grounds social-post drafts in real sources.

Attribution:
  Agent-Reach (MIT License) — https://github.com/Panniantong/Agent-Reach
  Author: Panniantong
  The integration approach follows Agent-Reach's documented "install doc" pattern:
  use Jina Reader for clean article extraction (zero-config, CAPTCHA-free) and
  DuckDuckGo for general search. No cookies, no API keys required for the
  read+search path.

Capabilities integrated (read-only, all free):
  reach_web_read(url)        — clean Markdown from any public URL via Jina Reader
  reach_web_search(query)    — web search results via DuckDuckGo
  reach_github_search(query) — GitHub repos/issues via DuckDuckGo site filter
  reach_research(topic)      — combined multi-source research swipe file

Not integrated (require per-user cookie export which we cannot automate):
  Twitter/X login-gated timelines — handled by existing tweetytweets adapter
  XiaoHongShu, Facebook, Instagram, LinkedIn profiles — require cookie setup
  Bilibili — regional IP restrictions

Each function returns a dict with a 'source' key recording where data came from
so the UI can show real provenance, never fabricated results.
"""
from __future__ import annotations

import os
import re
import time
import json
import urllib.request
import urllib.parse
from typing import Optional

DEMO_MODE = os.environ.get("SKILLFORGE_DEMO", "false").lower() == "true"

# Jina Reader endpoint — free, open, no API key
JINA_READER_BASE = "https://r.jina.ai/"
REQUEST_TIMEOUT  = 12  # seconds


# ── Internal helpers ───────────────────────────────────────────────────────────

def _ua_headers() -> dict:
    return {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,text/plain;q=0.9,*/*;q=0.8"
    }


def _ddg_search(query: str, num: int = 5, site: str = "") -> list[dict]:
    """
    CAPTCHA-free DuckDuckGo Lite & DDGS search.
    Agent-Reach pattern: use DuckDuckGo as the no-API-key search backbone.
    """
    full_q = f"site:{site} {query}" if site else query
    try:
        from tools.scraper import ddg_search
        s_res = ddg_search(full_q, num_results=num)
        results = s_res.get("results", [])
        if results:
            return [{
                "title": r.get("title", "").strip(),
                "url": r.get("url", ""),
                "snippet": r.get("snippet", ""),
                "source": f"agent_reach/ddg{'/' + site if site else ''}"
            } for r in results[:num]]
    except Exception:
        pass

    encoded = urllib.parse.urlencode({"q": full_q, "kl": "us-en"})
    url = f"https://lite.duckduckgo.com/lite/?{encoded}"
    results: list[dict] = []

    try:
        req = urllib.request.Request(url, headers=_ua_headers())
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            html = resp.read().decode("utf-8", errors="ignore")

        link_pat    = re.compile(r'<a[^>]+class="result-link"[^>]*href="([^"]+)"[^>]*>([^<]+)</a>', re.I)
        snippet_pat = re.compile(r'<td[^>]+class="result-snippet"[^>]*>(.*?)</td>', re.I | re.S)

        links    = link_pat.findall(html)
        snippets = [re.sub(r"<[^>]+>", "", s).strip() for s in snippet_pat.findall(html)]

        for i, (raw_url, title) in enumerate(links[:num]):
            # Unwrap DDG redirect
            if "uddg=" in raw_url:
                m = re.search(r"uddg=([^&]+)", raw_url)
                if m:
                    raw_url = urllib.parse.unquote(m.group(1))
            results.append({
                "title":   title.strip(),
                "url":     raw_url,
                "snippet": snippets[i] if i < len(snippets) else "",
                "source":  f"agent_reach/ddg{'/' + site if site else ''}"
            })
    except Exception as exc:
        # Return empty with error context — callers decide how to surface it
        results.append({"error": str(exc), "source": "agent_reach/ddg"})

    return results


def _jina_read(url: str) -> dict:
    """
    Fetch clean Markdown from any public URL via Jina Reader (Agent-Reach pattern).
    Jina Reader is free, requires no API key, and works without cookies.
    """
    jina_url = JINA_READER_BASE + url
    try:
        req = urllib.request.Request(
            jina_url,
            headers={**_ua_headers(), "Accept": "text/plain,text/markdown,*/*"}
        )
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            content = resp.read().decode("utf-8", errors="ignore")
        return {
            "url":     url,
            "content": content[:4000],
            "source":  "agent_reach/jina_reader",
            "chars":   len(content)
        }
    except Exception as exc:
        return {
            "url":    url,
            "error":  str(exc),
            "content": "",
            "source":  "agent_reach/jina_reader_error"
        }


# ── Exported Tool Functions ────────────────────────────────────────────────────

def reach_web_read(url: str) -> dict:
    """
    Read any public URL and return clean Markdown content.
    Uses Agent-Reach's Jina Reader approach (free, no API key, CAPTCHA-free).
    Returns real content or a clear error — never fabricated data.
    """
    t0 = time.time()
    if not url or not url.startswith("http"):
        return {"error": "reach_web_read requires a valid http/https URL", "url": url}

    if DEMO_MODE:
        return {
            "url":     url,
            "content": f"[DEMO] Simulated article content for: {url}\nThis is placeholder text shown because SKILLFORGE_DEMO=true.",
            "source":  "agent_reach/demo",
            "duration_ms": 0
        }

    result = _jina_read(url)
    result["duration_ms"] = int((time.time() - t0) * 1000)
    return result


def _clean_query(q: str) -> str:
    cleaned = re.sub(r"^(find|search for|give me|explain|get me|look up|show me)\s+", "", q.strip(), flags=re.IGNORECASE)
    cleaned = re.sub(r"[.?!]+$", "", cleaned).strip()
    return cleaned if cleaned else q


def reach_web_search(query: str, num_results: int = 5) -> dict:
    """
    Search the open web and return real results with source URLs.
    Uses Agent-Reach's DuckDuckGo backbone (no API key, no CAPTCHA).
    Never returns fabricated results — if search fails, says so clearly.
    """
    t0 = time.time()
    if not query or not query.strip():
        return {"error": "query cannot be empty", "results": []}

    cleaned = _clean_query(query)

    if DEMO_MODE:
        return {
            "query":    cleaned,
            "results":  [{"title": "[DEMO] Result", "url": "https://example.com", "snippet": "Demo mode active.", "source": "agent_reach/demo"}],
            "source":   "agent_reach/demo",
            "duration_ms": 0
        }

    results = _ddg_search(cleaned, num=max(1, min(num_results, 10)))
    return {
        "query":      cleaned,
        "results":    results,
        "count":      len([r for r in results if "error" not in r]),
        "source":     "agent_reach/ddg",
        "duration_ms": int((time.time() - t0) * 1000)
    }


def reach_github_search(query: str, num_results: int = 5) -> dict:
    """
    Search GitHub repositories via DuckDuckGo site filter + GitHub REST API fallback.
    Agent-Reach supports GitHub as a zero-config platform.
    """
    t0 = time.time()

    results: list[dict] = []

    # 1. DDG with site filter (Agent-Reach pattern)
    ddg_results = _ddg_search(query, num=num_results, site="github.com")
    for r in ddg_results:
        if "error" not in r and r.get("url", "").startswith("http"):
            results.append(r)

    # 2. GitHub REST Search API fallback (no auth, 10 req/min)
    if len(results) < num_results:
        try:
            encoded = urllib.parse.urlencode({"q": query, "sort": "stars", "per_page": num_results})
            gh_url  = f"https://api.github.com/search/repositories?{encoded}"
            req = urllib.request.Request(
                gh_url,
                headers={
                    "User-Agent":  "SkillForge-AgentReach/1.0",
                    "Accept":      "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28"
                }
            )
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
                data = json.loads(resp.read().decode("utf-8", errors="ignore"))

            existing_urls = {r["url"] for r in results}
            for item in data.get("items", [])[:num_results]:
                url = item.get("html_url", "")
                if url and url not in existing_urls:
                    results.append({
                        "title":   item.get("full_name", item.get("name", "")),
                        "url":     url,
                        "snippet": (item.get("description") or "") +
                                   f" ★{item.get('stargazers_count', 0)} | {item.get('language', '')}",
                        "source":  "agent_reach/github_api"
                    })
                    existing_urls.add(url)
        except Exception as exc:
            results.append({"error": str(exc), "source": "agent_reach/github_api"})

    real = [r for r in results if "error" not in r]
    return {
        "query":       query,
        "results":     results[:num_results],
        "count":       len(real),
        "source":      "agent_reach/github_ddg+api",
        "duration_ms": int((time.time() - t0) * 1000)
    }



def reach_research(topic: str, read_top_result: bool = True) -> dict:
    """
    Multi-source research swipe file for a topic.
    Combines web search + optional Jina Reader article extraction.
    This grounds social-post drafts in real, citable sources.

    Flow: search → collect URLs + snippets → (optionally) deep-read top result
    Returns: sources list with title, url, snippet, and optionally full_content
    """
    t0 = time.time()
    if not topic or not topic.strip():
        return {"error": "topic cannot be empty", "sources": []}

    cleaned_topic = _clean_query(topic)
    web_results = _ddg_search(cleaned_topic, num=5)
    sources: list[dict] = []

    for i, r in enumerate(web_results):
        if "error" in r:
            sources.append({"error": r["error"], "source": r.get("source", "unknown")})
            continue
        entry = {
            "index":   i + 1,
            "title":   r.get("title", ""),
            "url":     r.get("url", ""),
            "snippet": r.get("snippet", ""),
            "source":  r.get("source", "agent_reach/ddg")
        }
        # Deep-read the first real result for richer context
        if i == 0 and read_top_result and r.get("url", "").startswith("http") and not DEMO_MODE:
            article = _jina_read(r["url"])
            if article.get("content"):
                entry["full_content"] = article["content"][:1500]
                entry["reader_source"] = article["source"]
        sources.append(entry)

    return {
        "topic":       topic,
        "sources":     sources,
        "source_count": len([s for s in sources if "error" not in s]),
        "attribution": "Agent-Reach (MIT) — https://github.com/Panniantong/Agent-Reach",
        "duration_ms": int((time.time() - t0) * 1000)
    }
