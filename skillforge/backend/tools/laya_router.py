"""
SkillForge — Laya Decision Router
Uses the Laya open-source non-autoregressive model (Apache 2.0) to:
  1. Classify user intent → pick the right skill (33ms, zero hallucination)
  2. Assess risk level → decide if approval is needed (no LLM tokens wasted)
  3. Detect if the goal is a pure info-retrieval task vs a write/post action

Laya runs in a single forward pass — no text generation, no hallucination,
no token overhead. Gemma is only called for synthesis/generation steps.

Repo: https://github.com/NandhaKishorM/laya
License: Apache 2.0
"""

import time
from typing import Optional

# ── Laya questions for SkillForge ─────────────────────────────────────────────

SKILL_QUESTIONS = {
    "skill": {
        "type": "choice",
        "instructions": "Which skill should handle this request?",
        "criteria": {
            "job-search":       "finding jobs, careers, interview questions, hiring, recruitment, vacancies",
            "youtube-search":   "searching YouTube, finding videos, tutorials, lectures, transcripts, video summaries",
            "web-search":       "searching the web, finding information, news, general knowledge",
            "webpage-reader":   "reading a specific URL, opening a webpage, extracting text from a page",
            "research-paper":   "academic papers, arxiv, research, publications, studies, journals",
            "twitter-search":   "searching Twitter, X.com, tweets, social media posts, trending topics",
            "skill-builder":    "creating a new skill, building capability, generating SKILL.md",
            "file-creator":     "saving a file, creating a report, writing a document",
        }
    },
    "wants_file": {
        "type": "noul",
        "instructions": "Does the user explicitly ask to save, create, or write a file or report?"
    },
    "wants_post": {
        "type": "noul",
        "instructions": "Does the user explicitly ask to post, publish, tweet, or share on social media?"
    },
    "wants_read": {
        "type": "noul",
        "instructions": "Does the user explicitly ask to read or visit a specific URL or webpage?"
    },
    "wants_summary": {
        "type": "noul",
        "instructions": "Does the user ask to summarize, explain, or get key points from a video or article?"
    },
    "risk": {
        "type": "choice",
        "instructions": "What is the risk level of the intended action?",
        "criteria": {
            "low":    "read-only: searching, reading, finding information",
            "medium": "writing files, creating documents locally",
            "high":   "posting publicly, publishing to social media, sending emails, submitting forms",
        }
    },
}


# ── Router singleton — non-blocking ──────────────────────────────────────────
# Laya downloads its checkpoint (~300MB) on first use. We warm it in a
# background daemon thread so the first classify_goal() call always returns
# immediately via the keyword fallback, and subsequent calls use Laya once ready.

import threading

_laya_router = None
_laya_available = None  # None = still loading | True = ready | False = failed
_laya_lock = threading.Lock()


def _warm_laya():
    """Background thread: download + init Laya router without blocking requests."""
    global _laya_router, _laya_available
    try:
        from laya import Router
        router = Router()          # downloads checkpoint here (slow, first time)
        with _laya_lock:
            _laya_router    = router
            _laya_available = True
    except Exception:
        with _laya_lock:
            _laya_available = False


# Start warming immediately when this module is imported (daemon — dies with process)
_t = threading.Thread(target=_warm_laya, daemon=True, name="laya-warm")
_t.start()


def _get_router():
    """Return router if ready, else None (caller will use keyword fallback)."""
    with _laya_lock:
        if _laya_available is True:
            return _laya_router
    return None   # not yet ready or failed — use keyword fallback


# ── Main entry point ───────────────────────────────────────────────────────────

def classify_goal(goal: str) -> dict:
    """
    Classify the user's goal. Uses Laya if loaded; otherwise fast keyword fallback.
    Always returns immediately — never blocks on model download.
    """
    t0 = time.time()
    router = _get_router()

    if router is not None:
        try:
            result = router.predict(goal, SKILL_QUESTIONS)
            answers = result.get("answers", {})

            def _choice(key, default):
                a = answers.get(key, {})
                return a.get("choice", default)

            def _noul(key) -> bool:
                a = answers.get(key, {})
                return float(a.get("noul", 0.0)) > 0.5

            def _confidence(key) -> float:
                a = answers.get(key, {})
                return float(a.get("confidence", 0.0))

            skill_map = {
                "job-search":     "job-search",
                "youtube-search": "youtube-search",
                "web-search":     "web-search",
                "webpage-reader": "webpage-reader",
                "research-paper": "research-paper-search",
                "twitter-search": "web-search",
                "skill-builder":  "skill-builder",
                "file-creator":   "web-search",
            }

            raw_skill = _choice("skill", "web-search")
            skill_id  = skill_map.get(raw_skill, "web-search")

            twitter_kws = any(w in goal.lower() for w in ["twitter", "tweet", "x.com", "@"])
            if twitter_kws:
                skill_id = "web-search"

            return {
                "skill":         skill_id,
                "wants_file":    _noul("wants_file"),
                "wants_post":    _noul("wants_post"),
                "wants_read":    _noul("wants_read"),
                "wants_summary": _noul("wants_summary"),
                "risk":          _choice("risk", "low"),
                "confidence":    _confidence("skill"),
                "source":        "laya",
                "duration_ms":   int((time.time() - t0) * 1000),
            }

        except Exception:
            pass  # fall through to keyword fallback

    return _keyword_classify(goal, t0)


def _keyword_classify(goal: str, t0: float) -> dict:
    """Fast keyword-based fallback — mirrors the Laya questions."""
    g = goal.lower()

    wants_file    = any(w in g for w in ["save", "create file", "report", "write to", "document", "markdown"])
    wants_post    = any(w in g for w in ["post", "tweet", "publish", "share on twitter", "share on linkedin"])
    wants_read    = any(w in g for w in ["read", "open page", "visit", "browse", "extract from url"])
    wants_summary = any(w in g for w in ["summarize", "summary", "explain", "key points", "tldr"])
    wants_youtube = any(w in g for w in ["youtube", "video", "watch", "tutorial", "lecture", "transcript"])
    wants_twitter = any(w in g for w in ["twitter", "tweet", "x.com", "trending"])
    wants_jobs    = any(w in g for w in ["job", "interview", "career", "hiring", "position", "vacancy"])
    wants_papers  = any(w in g for w in ["paper", "research", "arxiv", "publication", "study", "journal"])
    wants_skill   = any(w in g for w in ["create skill", "new skill", "build skill", "skill.md"])

    if wants_youtube:
        skill = "youtube-search"
    elif wants_twitter:
        skill = "web-search"
    elif wants_jobs:
        skill = "job-search"
    elif wants_papers:
        skill = "research-paper-search"
    elif wants_read:
        skill = "webpage-reader"
    elif wants_skill:
        skill = "skill-builder"
    else:
        skill = "web-search"

    risk = "high" if wants_post else ("medium" if wants_file else "low")

    return {
        "skill":         skill,
        "wants_file":    wants_file,
        "wants_post":    wants_post,
        "wants_read":    wants_read,
        "wants_summary": wants_summary,
        "risk":          risk,
        "confidence":    1.0,
        "source":        "keyword-fallback",
        "duration_ms":   int((time.time() - t0) * 1000),
    }


def is_laya_available() -> bool:
    """Check if Laya is installed and working."""
    return _get_router() is not None
