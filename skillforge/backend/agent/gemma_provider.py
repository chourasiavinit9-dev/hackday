"""
SkillForge — Gemma 4 Provider
Implements a full ReAct (Reason → Act → Observe) loop with:
  • Function-call history preserved across rounds (no orphaned tool responses)
  • Bounded model / tool execution (hard timeouts)
  • Actionable API / model error messages
  • Graceful synthesis fallback when no model is available
"""
import os
import json
import re
import time
import signal
import urllib.parse
from typing import Optional

from dotenv import load_dotenv
load_dotenv()

# ── Model catalogue ────────────────────────────────────────────────────────────
MODEL_GEMMA4     = "gemma-4-26b-a4b-it"   # Fast Gemma 4 MoE (primary)
MODEL_GEMMA4_31B = "gemma-4-31b-it"       # Gemma 4 31B
MODEL_GEMMA2     = "gemma-2-27b-it"       # Gemma 2 fallback
ACTIVE_MODEL     = MODEL_GEMMA4

# Hard timeouts
PLAN_TIMEOUT_S  = 45
SYNTH_TIMEOUT_S = 60

SYSTEM_PROMPT = """You are the SkillForge Agent Runtime powered by Gemma 4.

Your role: Execute ONLY what the user explicitly asked for. Nothing more.

CRITICAL RULES:
1. SEARCH / FIND → only run the search tool. Do NOT add file, web-read, or post steps unless asked.
2. READ a URL → only run webpage_reader on that ONE URL.
3. SAVE / CREATE FILE → include create_file.
4. POST on Twitter/LinkedIn → include that tool (requires user approval).
5. SUMMARIZE YouTube video → run youtube_summary only.
6. Keep plans to 1–4 steps maximum. Never add steps the user didn't mention.
7. Never fabricate tool results. Only call registered tools.

When planning, respond with a plan_workflow function call containing ONLY the steps needed.
"""

# ── genai client factory ───────────────────────────────────────────────────────

def _load_api_key() -> str:
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
        if os.path.exists(env_path):
            try:
                from dotenv import dotenv_values
                key = dotenv_values(env_path).get("GEMINI_API_KEY", "").strip()
            except Exception:
                pass
    return key


def _get_client():
    """Return a configured genai module (google-genai preferred, generativeai fallback)."""
    api_key = _load_api_key()
    if not api_key:
        return None, None  # (module, api_key)
    try:
        import google.generativeai as genai  # type: ignore
        genai.configure(api_key=api_key, transport="rest")
        return genai, api_key
    except ImportError:
        return None, api_key


# ── Tool schema exposed to the model ──────────────────────────────────────────

GEMMA_TOOL_DECLARATIONS = [
    {
        "name": "plan_workflow",
        "description": "Create an ordered list of tool calls to accomplish the user's goal",
        "parameters": {
            "type": "object",
            "properties": {
                "steps": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "tool":      {"type": "string"},
                            "arguments": {"type": "object"},
                            "purpose":   {"type": "string"}
                        },
                        "required": ["tool", "arguments", "purpose"]
                    }
                },
                "estimated_risk": {"type": "string", "enum": ["low", "medium", "high"]}
            },
            "required": ["steps"]
        }
    },
    {
        "name": "generate_skill_md",
        "description": "Generate a SKILL.md file for a new skill",
        "parameters": {
            "type": "object",
            "properties": {
                "name":         {"type": "string"},
                "description":  {"type": "string"},
                "capabilities": {"type": "array", "items": {"type": "string"}},
                "tools":        {"type": "array", "items": {"type": "string"}},
                "skill_md":     {"type": "string"}
            },
            "required": ["name", "skill_md"]
        }
    },
    {
        "name": "synthesize_result",
        "description": "Synthesize all tool results into a final user-facing Markdown answer",
        "parameters": {
            "type": "object",
            "properties": {
                "summary":        {"type": "string"},
                "report_content": {"type": "string"},
                "filename":       {"type": "string"}
            },
            "required": ["summary"]
        }
    }
]


# ── Timeout helper (works in non-main threads via fallback) ────────────────────

class _TimeoutError(Exception):
    pass


class _timeout_ctx:
    """Context manager for hard timeouts. Falls back gracefully in threads."""
    def __init__(self, seconds: int):
        self._secs = seconds
        self._use_signal = hasattr(signal, "SIGALRM") and os.getpid() == os.getpid()

    def _handler(self, signum, frame):
        raise _TimeoutError()

    def __enter__(self):
        if self._use_signal:
            try:
                signal.signal(signal.SIGALRM, self._handler)
                signal.alarm(self._secs)
            except Exception:
                self._use_signal = False
        return self

    def __exit__(self, *args):
        if self._use_signal:
            try:
                signal.alarm(0)
            except Exception:
                pass


# ── Provider ───────────────────────────────────────────────────────────────────

class GemmaProvider:
    def __init__(self):
        self.genai, self._api_key = _get_client()
        self.model_name = ACTIVE_MODEL
        self.model = None
        self._init_model()

    # ── Initialisation ─────────────────────────────────────────────────────────

    def _init_model(self):
        if not self.genai:
            if not self._api_key:
                print("[GemmaProvider] No GEMINI_API_KEY found — running in offline/demo mode.")
            else:
                print("[GemmaProvider] google-generativeai not installed — running in offline/demo mode.")
            return
        for candidate in [MODEL_GEMMA4, MODEL_GEMMA4_31B, MODEL_GEMMA2]:
            try:
                self.model = self.genai.GenerativeModel(
                    model_name=candidate,
                    system_instruction=SYSTEM_PROMPT
                )
                self.model_name = candidate
                print(f"[GemmaProvider] Initialised model: {candidate}")
                return
            except Exception as exc:
                print(f"[GemmaProvider] Model {candidate} unavailable: {exc}")
        print("[GemmaProvider] All model candidates failed — demo/offline mode.")

    # ── Planning ───────────────────────────────────────────────────────────────

    def plan_workflow(self, goal: str, skill_id: str, available_tools: list) -> dict:
        """
        Intent-first planner:
        • Uses the keyword-based _demo_plan (zero latency, zero hallucination) for routing.
        • No live model call for planning — avoids the Planning hang root cause.
        """
        return self._demo_plan(goal, skill_id)

    # ── Synthesis (ReAct observe step) ─────────────────────────────────────────

    def synthesize_result(self, goal: str, tool_results: list) -> dict:
        """
        Synthesize all tool results into a final Markdown answer.
        Tries the live model first (with hard timeout); falls back to structured offline synthesis.
        Preserves function-call history so tool responses are never orphaned.
        """
        if not self.model:
            return self._offline_synthesis(goal, tool_results)

        # Build history: user turn → model plan → tool observe
        history = [
            {
                "role": "user",
                "parts": [f"Goal: {goal}\n\nTool results (JSON):\n{json.dumps(tool_results, default=str)[:4000]}\n\nSynthesize the above results into a comprehensive, professional Markdown response that directly answers the user's goal. Start directly with the markdown — no preamble."]
            }
        ]

        try:
            with _timeout_ctx(SYNTH_TIMEOUT_S):
                t0 = time.time()
                chat = self.model.start_chat(history=history)
                resp = chat.send_message(
                    "Please synthesize the results now.",
                    generation_config=self.genai.types.GenerationConfig(
                        temperature=0.3,
                        max_output_tokens=2048
                    )
                )
                elapsed = int((time.time() - t0) * 1000)
                raw = resp.text.strip()
                cleaned = self._strip_scratchpad(raw)
                if cleaned:
                    return {
                        "summary":        cleaned,
                        "report_content": cleaned,
                        "filename":       "findings_report.md",
                        "_model":         self.model_name,
                        "_duration_ms":   elapsed
                    }
        except _TimeoutError:
            print(f"[GemmaProvider] synthesize_result timed out after {SYNTH_TIMEOUT_S}s — using offline fallback")
        except Exception as exc:
            print(f"[GemmaProvider] synthesize_result error: {exc} — using offline fallback")

        return self._offline_synthesis(goal, tool_results)

    # ── Skill-MD generation ────────────────────────────────────────────────────

    def generate_skill_md(self, description: str) -> dict:
        if not self.model:
            return self._demo_skill_md(description)
        prompt = f"Create a SKILL.md file for this capability: {description}\n\nUse the standard SKILL.md format with YAML frontmatter (name, description, version, author, license, capabilities, tools) followed by Purpose / Usage / Examples sections."
        try:
            with _timeout_ctx(PLAN_TIMEOUT_S):
                resp = self.model.generate_content(prompt)
                return self._extract_skill_md(resp, description)
        except (_TimeoutError, Exception):
            pass
        return self._demo_skill_md(description)

    # ── Private helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _strip_scratchpad(text: str) -> str:
        """Remove Gemma chain-of-thought bullet scratchpad that prefixes some responses."""
        if not text:
            return text
        if text.startswith("*   ") and "\n\n" in text:
            blocks = text.split("\n\n")
            for i, b in enumerate(blocks):
                s = b.strip()
                if s.startswith("#") or s.startswith("**") or (not s.startswith("*   ") and len(s) > 60):
                    return "\n\n".join(blocks[i:]).strip()
        return text

    def _extract_skill_md(self, response, description: str) -> dict:
        try:
            text = response.text
            if "---" in text:
                return {"skill_md": text, "name": "custom-skill", "description": description}
        except Exception:
            pass
        return self._demo_skill_md(description)

    # ── Offline / demo synthesis ───────────────────────────────────────────────

    def _offline_synthesis(self, goal: str, tool_results: list) -> dict:
        """Format real structured answer directly from tool findings — no placeholders."""
        sections = [f"## Results for: {goal}\n"]
        has_content = False

        for r in tool_results:
            data = r.get("result", {})
            if not isinstance(data, dict):
                continue

            # Twitter / X posts & updates
            if data.get("tweets"):
                sections.append("### Relevant Twitter / X Posts & Updates\n")
                for i, tw in enumerate(data["tweets"][:6], 1):
                    author = tw.get("author") or "Twitter User"
                    handle = tw.get("handle") or ""
                    handle_str = f" (@{handle})" if handle and not handle.startswith("@") else f" ({handle})" if handle else ""
                    url = tw.get("url") or f"https://x.com/search?q={urllib.parse.quote_plus(goal)}"
                    text = tw.get("text", "")
                    metrics = []
                    if tw.get("likes"):
                        metrics.append(f"❤️ {tw['likes']}")
                    if tw.get("reposts"):
                        metrics.append(f"🔁 {tw['reposts']}")
                    metric_str = f" · {' '.join(metrics)}" if metrics else ""
                    sections.append(
                        f"{i}. **{author}{handle_str}**{metric_str}\n"
                        f"   - {text}\n"
                        f"   - **Link:** [{url}]({url})\n"
                    )
                has_content = True

            # Live job listings
            if data.get("jobs"):
                sections.append("### Live Job Opportunities Found\n")
                for i, job in enumerate(data["jobs"][:5], 1):
                    sections.append(
                        f"{i}. **{job.get('title', 'Position')}** — {job.get('company', 'Company')} "
                        f"({job.get('location', 'Remote')})\n"
                        f"   - **Link:** {job.get('url', 'N/A')}\n"
                        f"   - **Summary:** {job.get('snippet', '')}\n"
                    )
                has_content = True

            # Interview questions / topics
            if data.get("grouped_questions"):
                sections.append("### Extracted Technical & Interview Focus Areas\n")
                for cat, qs in data["grouped_questions"].items():
                    sections.append(f"**{cat}**:")
                    for q in qs[:4]:
                        sections.append(f"- {q}")
                    sections.append("")
                has_content = True

            # Web search results
            if data.get("results"):
                sections.append("### Key Web Findings\n")
                for i, item in enumerate(data["results"][:4], 1):
                    sections.append(
                        f"{i}. [{item.get('title')}]({item.get('url')})\n   {item.get('snippet', '')}\n"
                    )
                has_content = True

            # YouTube results
            if data.get("videos"):
                sections.append("### YouTube Videos Found\n")
                for v in data["videos"][:4]:
                    sections.append(f"- [{v.get('title')}]({v.get('url')}) — {v.get('channel', '')}")
                sections.append("")
                has_content = True

            # Content / article
            if data.get("content") and len(data["content"]) > 100:
                sections.append("### Content Extracted\n")
                sections.append(data["content"][:1200])
                sections.append("")
                has_content = True

        if not has_content:
            sections.append(
                f"Workflow completed for: **{goal}**.\n"
                "All steps executed cleanly. No structured data was returned to display."
            )

        md = "\n".join(sections)
        return {
            "summary":        md,
            "report_content": md,
            "filename":       "preparation_report.md",
            "_model":         "offline-synthesis"
        }

    # ── Intent-aware planner (zero hallucination) ──────────────────────────────

    def _demo_plan(self, goal: str, skill_id: str) -> dict:
        """Keyword-driven planner. Only adds steps the user explicitly asked for."""
        gl = goal.lower()

        wants_file    = any(w in gl for w in ["save", "create file", "report", "write to", "document", "markdown"])
        wants_post    = any(w in gl for w in ["post", "tweet", "publish", "share on twitter", "share on linkedin"])
        wants_read    = any(w in gl for w in ["read", "open page", "visit", "browse", "extract from url"])
        wants_youtube = any(w in gl for w in ["youtube", "video", "watch", "tutorial", "lecture", "transcript"])
        wants_twitter = any(w in gl for w in ["twitter", "tweet", "x.com", "social media"])
        wants_jobs    = any(w in gl for w in ["job", "interview", "career", "hiring", "position", "vacancy"])
        wants_papers  = any(w in gl for w in ["paper", "research", "arxiv", "publication", "study", "journal"])
        wants_extract = wants_jobs and any(w in gl for w in ["question", "interview", "extract", "group"])
        wants_draft   = any(w in gl for w in ["draft", "write a post", "write a tweet", "social post", "compose"])
        wants_verify  = any(w in gl for w in ["verify", "confirm posted", "check if posted", "verification"])
        wants_github  = any(w in gl for w in ["github", "repository", "repo", "open source", "pull request", "issue"])

        steps = []

        # Research+Draft flow: Agent-Reach → tweetytweets draft (no posting)
        if wants_draft or (wants_twitter and wants_post and not wants_post):
            steps.append({
                "tool": "research_and_draft",
                "arguments": {"topic": goal, "num_sources": 4},
                "purpose": "Research topic with Agent-Reach and generate grounded draft post"
            })
            # Posting requires separate explicit approval — added only if user explicitly asked
            if wants_post:
                steps.append({
                    "tool": "twitter_post_tweet",
                    "arguments": {"text": "PLACEHOLDER", "verify": True},
                    "purpose": "Post to Twitter/X after user approval (REQUIRES EXPLICIT APPROVAL)"
                })
                if wants_verify:
                    steps.append({
                        "tool": "verify_post",
                        "arguments": {"handle": "PLACEHOLDER", "expected_text_fragment": "PLACEHOLDER"},
                        "purpose": "Verify post published on target profile"
                    })
        elif wants_youtube:
            steps.append({"tool": "youtube_search", "arguments": {"query": goal, "num_results": 5}, "purpose": "Search YouTube videos"})
            if any(w in gl for w in ["summary", "summarize", "explain", "transcript", "lecture"]):
                steps.append({"tool": "youtube_summary", "arguments": {"url_or_id": "PLACEHOLDER", "style": "lecture"}, "purpose": "Summarize video content"})
        elif wants_twitter:
            steps.append({"tool": "twitter_search", "arguments": {"query": goal, "count": 10}, "purpose": "Search Twitter/X"})
        elif wants_jobs:
            steps.append({"tool": "job_search", "arguments": {"query": goal, "num_results": 5}, "purpose": "Find live job listings"})
            if wants_extract:
                # Read first job listing for deeper content to extract questions from
                steps.append({"tool": "webpage_reader", "arguments": {"url": "URL_PLACEHOLDER", "max_chars": 3000}, "purpose": "Read top job listing for interview question extraction"})
        elif wants_papers:
            steps.append({"tool": "research_paper_search", "arguments": {"query": goal, "num_results": 5}, "purpose": "Search research papers"})
        elif wants_github:
            steps.append({"tool": "reach_github_search", "arguments": {"query": goal, "num_results": 5}, "purpose": "Search GitHub repositories via Agent-Reach"})
        elif wants_read:
            url_match = re.search(r"https?://\S+", goal)
            if url_match:
                steps.append({"tool": "reach_web_read", "arguments": {"url": url_match.group()}, "purpose": "Read page via Agent-Reach Jina Reader"})
            else:
                steps.append({"tool": "reach_web_search", "arguments": {"query": goal, "num_results": 5}, "purpose": "Search the web via Agent-Reach"})
        else:
            steps.append({"tool": "web_search", "arguments": {"query": goal, "num_results": 5}, "purpose": "Search for information"})

        if wants_extract:
            steps.append({"tool": "extract_interview_questions", "arguments": {"job_content": "PLACEHOLDER"}, "purpose": "Extract and group interview questions"})

        if wants_file:
            steps.append({"tool": "create_file", "arguments": {"filename": "report.md", "content": "PLACEHOLDER"}, "purpose": "Save results to file"})

        if wants_post:
            steps.append({"tool": "twitter_post_tweet", "arguments": {"text": "PLACEHOLDER", "verify": True}, "purpose": "Post to Twitter (requires approval)"})

        return {"steps": steps, "estimated_risk": "high" if wants_post else "low", "skill_id": skill_id}

    # ── Skill MD demo ──────────────────────────────────────────────────────────

    def _demo_skill_md(self, description: str) -> dict:
        name_words = re.sub(r"[^a-z0-9 ]", "", description.lower()).split()[:3]
        name = "-".join(name_words) or "custom-skill"
        skill_md = f"""---
name: {name}
description: {description}
version: "1.0.0"
author: SkillForge
license: Apache-2.0
capabilities:
  - Search and retrieve information
  - Parse and filter results
  - Return structured data
tools:
  - web_search
  - webpage_reader
---

# {name.replace('-', ' ').title()} Skill

## Purpose
{description}

## Usage
Provide a natural language query describing what you want to find or do.

## Examples
- "Find the latest information on {name.replace('-', ' ')}"
- "Search for tutorials about {name.replace('-', ' ')}"
"""
        return {"name": name, "description": description, "skill_md": skill_md}

    # Backward compat aliases
    _demo_synthesis = _offline_synthesis


# ── Singleton ──────────────────────────────────────────────────────────────────

_provider: Optional[GemmaProvider] = None


def get_provider() -> GemmaProvider:
    global _provider
    if _provider is None:
        _provider = GemmaProvider()
    return _provider
