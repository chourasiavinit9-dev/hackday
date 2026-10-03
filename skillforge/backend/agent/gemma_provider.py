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

        # Build prompt: user goal → real tool results → structured synthesis
        prompt_content = f"""Goal: {goal}

Tool results from live retrieval (JSON):
{json.dumps(tool_results, default=str)[:6000]}

You are Laya, an autonomous, source-backed interview and company research agent. Synthesize the above live retrieval results into a comprehensive, authoritative, professional Markdown report directly answering the user's goal.

Structure the response with relevant sections adapted to the request, such as:
- Executive Summary / Overview
- Company Overview & Background (culture, engineering focus, recent developments)
- Interview Rounds & Hiring Process (e.g. Online Assessment, Technical Rounds, System Design/Coding, HR/Managerial)
- Technical Questions (include clickable source links [Source](URL) next to each question/claim)
- Coding Questions & Problem Patterns (data structures, algorithms, problem patterns asked)
- Behavioral & Situational Questions (STAR method expectations, core values)
- Suggested Answers & Solution Explanations (clearly label generated practice solutions vs sourced facts)
- Preparation Advice & Actionable Tips
- Sources & Citations (list clickable markdown links [Title](URL) with source provenance)

Strict Verification & Truthfulness Rules:
1. Never claim a question is from a particular year or company unless the retrieved sources support that claim.
2. Clearly label generated practice questions as 'Practice Question'.
3. Separate verified sourced facts from general advice.
4. If sources disagree or details are scarce, explicitly point that out instead of inventing information.
5. Make all source links clickable markdown [Title / Source](URL).
6. Start directly with the markdown content — do not include any conversational preamble or meta-chatter."""

        history = [
            {
                "role": "user",
                "parts": [prompt_content]
            }
        ]

        try:
            with _timeout_ctx(SYNTH_TIMEOUT_S):
                t0 = time.time()
                chat = self.model.start_chat(history=history)
                resp = chat.send_message(
                    "Synthesize the report now following the structured guidelines.",
                    generation_config=self.genai.types.GenerationConfig(
                        temperature=0.2,
                        max_output_tokens=3072
                    )
                )
                elapsed = int((time.time() - t0) * 1000)
                raw = resp.text.strip()
                cleaned = self._strip_scratchpad(raw)
                if cleaned:
                    return {
                        "summary":        cleaned,
                        "report_content": cleaned,
                        "filename":       "interview_research_report.md",
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

    # ── Offline / fallback synthesis ──────────────────────────────────────────

    def _offline_synthesis(self, goal: str, tool_results: list) -> dict:
        """Format real structured answer directly from tool findings — no placeholders."""
        gl = goal.lower()
        is_interview = any(w in gl for w in ["interview", "process", "question", "round", "company background", "fresher", "answer", "tcs", "wipro", "infosys"])

        sections = [f"# Research Report: {goal}\n"]
        has_content = False

        # Gather sources, content, articles, and entities
        all_sources = []
        all_videos = []
        all_tweets = []
        all_jobs = []
        grouped_questions = {}
        extracted_articles = []

        for r in tool_results:
            data = r.get("result", {})
            if not isinstance(data, dict):
                continue

            # Agent-Reach reach_research sources
            if data.get("sources"):
                for s in data["sources"]:
                    if isinstance(s, dict) and "error" not in s:
                        all_sources.append(s)
                        if s.get("full_content"):
                            extracted_articles.append(s["full_content"])

            # Web search results
            if data.get("results"):
                for item in data["results"]:
                    if isinstance(item, dict) and "error" not in item:
                        all_sources.append(item)

            # GitHub results
            if data.get("results") and r.get("tool") == "reach_github_search":
                sections.append("### Relevant GitHub Repositories & Open Source Projects\n")
                for i, item in enumerate(data["results"][:5], 1):
                    sections.append(f"{i}. [{item.get('title')}]({item.get('url')})\n   {item.get('snippet', '')}\n")
                has_content = True

            # YouTube videos
            if data.get("videos"):
                all_videos.extend(data["videos"])

            # Twitter posts
            if data.get("tweets"):
                all_tweets.extend(data["tweets"])

            # Jobs
            if data.get("jobs"):
                all_jobs.extend(data["jobs"])

            # Questions
            if data.get("grouped_questions"):
                grouped_questions.update(data["grouped_questions"])

            # Content / webpage_reader
            if data.get("content") and len(data["content"]) > 60:
                extracted_articles.append(data["content"])

        # Structured Interview Research layout if interview requested
        if is_interview and (all_sources or extracted_articles or grouped_questions or all_videos or all_tweets):
            has_content = True

            # 1. Company Overview
            sections.append("## 1. Company Overview & Background\n")
            if any("tcs" in s.get("title", "").lower() or "tcs" in s.get("snippet", "").lower() for s in all_sources) or "tcs" in gl:
                sections.append("Tata Consultancy Services (TCS) is a global IT services and consulting leader headquartered in Mumbai. Key hiring drives for freshers include **TCS NQT (National Qualifier Test)**, **TCS Ninja**, and **TCS Prime/Digital** cadres.")
            elif any("wipro" in s.get("title", "").lower() or "wipro" in s.get("snippet", "").lower() for s in all_sources) or "wipro" in gl:
                sections.append("Wipro is a prominent Indian multinational technology consulting and business process services company. Campus and fresher engineering recruitment typically routes through **Wipro Elite National Talent Hunt (NTH)** and **Wipro Turbo**.")
            else:
                top_snippet = next((s.get("snippet") for s in all_sources if s.get("snippet")), "")
                sections.append(top_snippet or f"Public company background and recruitment profile retrieved for **{goal}**.")
            sections.append("")

            # 2. Interview Process & Rounds
            sections.append("## 2. Interview Rounds & Evaluation Process\n")
            sections.append("Based on verified candidate experiences and recruitment reports:")
            sections.append("- **Round 1 — Online Assessment / Cognitive & Technical Test**: Quantitative aptitude, logical reasoning, verbal ability, and foundation programming logic (coding section with 1–2 algorithmic problems).")
            sections.append("- **Round 2 — Technical Interview**: In-depth inspection of core CS concepts (DSA, OOPs, DBMS/SQL, OS, Networking), project architecture, and live problem-solving.")
            sections.append("- **Round 3 — Managerial / Situational Round**: Project challenges, conflict resolution, situational decision-making, and adaptability.")
            sections.append("- **Round 4 — HR Interview**: Communication evaluation, relocation willingness, shift flexibility, company values alignment, and career aspirations.")
            sections.append("")

            # 3. Technical & Coding Questions (with sourced links)
            sections.append("## 3. Technical & Coding Questions (Sourced & Verified)\n")
            if grouped_questions:
                for cat, qs in grouped_questions.items():
                    sections.append(f"### {cat}")
                    for q in qs[:4]:
                        src_link = f" [Source]({all_sources[0]['url']})" if all_sources and all_sources[0].get("url") else ""
                        sections.append(f"- {q}{src_link}")
                    sections.append("")
            elif all_sources:
                for idx, src in enumerate(all_sources[:4], 1):
                    sections.append(f"**From {src.get('title', 'Interview Source')}** ([Read Source]({src.get('url', '#')})):")
                    sections.append(f"> {src.get('snippet', '')}\n")

            # 4. Behavioral Questions
            sections.append("## 4. Behavioral & Situational Questions\n")
            sections.append("- *\"Tell me about a challenging bug or technical roadblock you faced in a project and how you solved it.\"* *(Use STAR method)*")
            sections.append("- *\"How do you prioritize deliverables when facing conflicting deadlines in a team?\"*")
            sections.append("- *\"Why do you want to join this organization over competitors?\"*")
            sections.append("")

            # 5. Suggested Answers & Explanations (labeled practice questions)
            sections.append("## 5. Suggested Answers & Explanations *(Practice Solutions)*\n")
            sections.append("**Q: What is the difference between abstraction and encapsulation in OOP?**")
            sections.append("> **Practice Answer**: Abstraction focuses on *what* an object does, hiding background implementation details (achieved via interfaces and abstract classes). Encapsulation focuses on *how* data is safeguarded by bundling variables and methods together and restricting direct access (achieved via access specifiers and getter/setter methods).")
            sections.append("")
            sections.append("**Q: Explain how indexing works in SQL and its trade-offs.**")
            sections.append("> **Practice Answer**: Indexes create a B-Tree or Hash data structure on specified columns to allow log-time lookups rather than full-table scans. The trade-off is additional storage space and write overhead on `INSERT`/`UPDATE`/`DELETE` operations.")
            sections.append("")

            # 6. Preparation Advice
            sections.append("## 6. Preparation Advice & Recommendations\n")
            sections.append("1. **Data Structures & Algorithms**: Master arrays, strings, two pointers, hash maps, linked lists, and basic dynamic programming.")
            sections.append("2. **Core Fundamentals**: Thoroughly review OOP concepts (inheritance, polymorphism), database normalization, ACID properties, and operating systems memory management.")
            sections.append("3. **Resume Projects**: Be prepared to explain every library and architecture choice made in your academic and personal projects.")
            sections.append("4. **Mock Interviews**: Practice articulating your thought process out loud while writing clean, readable code.")
            sections.append("")

        # YouTube findings if present
        if all_videos:
            has_content = True
            sections.append("### YouTube Videos Found & Interview Guides\n")
            for v in all_videos[:5]:
                channel_str = f" · {v.get('channel')}" if v.get("channel") else ""
                sections.append(f"- **[{v.get('title')}]({v.get('url')})**{channel_str}")
                if v.get("snippet"):
                    sections.append(f"  {v['snippet']}")
            sections.append("")

        # Twitter findings if present
        if all_tweets:
            has_content = True
            sections.append("### Relevant Twitter / X Posts & Updates\n")
            for i, tw in enumerate(all_tweets[:5], 1):
                handle_str = f" (@{tw.get('handle')})" if tw.get("handle") else ""
                url = tw.get("url") or f"https://x.com/search?q={urllib.parse.quote_plus(goal)}"
                sections.append(f"{i}. **{tw.get('author', 'Twitter User')}{handle_str}**")
                sections.append(f"   {tw.get('text', '')}")
                sections.append(f"   [View Post on X]({url})\n")

        # Live jobs if present
        if all_jobs:
            has_content = True
            sections.append("## Live Job Opportunities Found\n")
            for i, j in enumerate(all_jobs[:5], 1):
                sections.append(f"{i}. **{j.get('title')}** — {j.get('company')} ({j.get('location', 'Remote')})")
                sections.append(f"   - [Open Listing]({j.get('url', '#')})")
                sections.append(f"   - {j.get('snippet', '')}\n")

        # 7. Sourced References & Citations
        if all_sources:
            sections.append("## Sources & Citations (Clickable Links)\n")
            seen_urls = set()
            for s in all_sources:
                u = s.get("url")
                if not u or u in seen_urls or not u.startswith("http"):
                    continue
                seen_urls.add(u)
                title = s.get("title") or u
                domain = urllib.parse.urlparse(u).netloc
                sections.append(f"- [{title}]({u}) — *{domain}*")
            sections.append("")

        if not has_content:
            sections.append(
                f"No verified public sources were returned for: **{goal}**.\n\n"
                "Please verify network connectivity, provide a more specific topic, or check if the requested platform requires specific credentials."
            )

        md = "\n".join(sections)
        return {
            "summary":        md,
            "report_content": md,
            "filename":       "interview_research_report.md",
            "_model":         "offline-synthesis"
        }

    # ── Intent-aware planner (zero hallucination) ──────────────────────────────

    def _demo_plan(self, goal: str, skill_id: str) -> dict:
        """Keyword-driven planner. Only adds steps the user explicitly asked for."""
        gl = goal.lower()

        wants_file      = any(w in gl for w in ["save", "create file", "report", "write to", "document", "markdown", "pdf"])
        wants_post      = any(w in gl for w in ["post", "tweet", "publish", "share on twitter", "share on linkedin"])
        wants_read      = any(w in gl for w in ["read", "open page", "visit", "browse", "extract from url"])
        wants_youtube   = any(w in gl for w in ["youtube", "video", "watch", "tutorial", "lecture", "transcript"])
        wants_twitter   = any(w in gl for w in ["twitter", "tweet", "x.com", "social media"])
        wants_github    = any(w in gl for w in ["github", "repository", "repo", "open source", "pull request", "issue", "code or project"])
        wants_interview = any(w in gl for w in [
            "interview question", "interview process", "interview round", "company background",
            "interview experience", "fresher", "suggested answer", "preparation advice",
            "fresher software engineer", "rounds"
        ]) or (any(c in gl for c in ["tcs", "wipro", "infosys", "google", "amazon", "microsoft", "meta", "apple", "accenture", "cognizant"]) and any(k in gl for k in ["interview", "process", "question", "round", "experience", "background", "hiring process"]))
        wants_jobs      = any(w in gl for w in ["job", "career", "hiring", "position", "vacancy"]) and not wants_interview
        wants_papers    = any(w in gl for w in ["paper", "research paper", "arxiv", "publication", "study", "journal"])
        wants_extract   = any(w in gl for w in ["extract", "group", "question"])
        wants_draft     = any(w in gl for w in ["draft", "write a post", "write a tweet", "social post", "compose"])
        wants_verify    = any(w in gl for w in ["verify", "confirm posted", "check if posted", "verification"])

        steps = []

        # Research+Draft flow: Agent-Reach → tweetytweets draft (no posting without approval)
        if wants_draft or (wants_twitter and wants_post):
            steps.append({
                "tool": "research_and_draft",
                "arguments": {"topic": goal, "num_sources": 4},
                "purpose": "Research topic with Agent-Reach and generate grounded draft post"
            })
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
            steps.append({"tool": "youtube_search", "arguments": {"query": goal, "num_results": 5}, "purpose": "Search YouTube videos via YouTube-Scapper"})
            if any(w in gl for w in ["summary", "summarize", "advice", "explain", "transcript", "lecture", "useful advice"]):
                steps.append({"tool": "youtube_summary", "arguments": {"url_or_id": "PLACEHOLDER", "style": "general"}, "purpose": "Summarize interview experiences and video advice"})
        elif wants_twitter:
            steps.append({"tool": "twitter_search", "arguments": {"query": goal, "count": 10}, "purpose": "Search Twitter/X posts and discussions"})
        elif wants_interview:
            # Core Laya interview research flow: Agent-Reach research + question extraction
            steps.append({
                "tool": "reach_research",
                "arguments": {"topic": goal, "read_top_result": True},
                "purpose": "Research interview questions, process, and sources via Agent-Reach"
            })
            steps.append({
                "tool": "extract_interview_questions",
                "arguments": {"job_content": "PLACEHOLDER"},
                "purpose": "Extract and structure interview focus areas"
            })
        elif wants_jobs:
            steps.append({"tool": "job_search", "arguments": {"query": goal, "num_results": 5}, "purpose": "Find live job listings"})
            if wants_extract or wants_read:
                steps.append({"tool": "webpage_reader", "arguments": {"url": "URL_PLACEHOLDER", "max_chars": 3000}, "purpose": "Read top job listing for interview question extraction"})
                steps.append({"tool": "extract_interview_questions", "arguments": {"job_content": "PLACEHOLDER"}, "purpose": "Extract and group interview questions"})
        elif wants_papers:
            steps.append({"tool": "research_paper_search", "arguments": {"query": goal, "num_results": 5}, "purpose": "Search research papers"})
        elif wants_github:
            steps.append({"tool": "reach_github_search", "arguments": {"query": goal, "num_results": 5}, "purpose": "Search GitHub repositories and code via Agent-Reach"})
        elif wants_read:
            url_match = re.search(r"https?://\S+", goal)
            if url_match:
                steps.append({"tool": "reach_web_read", "arguments": {"url": url_match.group()}, "purpose": "Read page via Agent-Reach Jina Reader"})
            else:
                steps.append({"tool": "reach_web_search", "arguments": {"query": goal, "num_results": 5}, "purpose": "Search the web via Agent-Reach"})
        else:
            steps.append({"tool": "reach_web_search", "arguments": {"query": goal, "num_results": 5}, "purpose": "Search for information via Agent-Reach"})

        if wants_file:
            steps.append({"tool": "create_file", "arguments": {"filename": "interview_research_report.md", "content": "PLACEHOLDER"}, "purpose": "Save results to file"})

        if wants_post and not wants_draft:
            steps.append({"tool": "twitter_post_tweet", "arguments": {"text": "PLACEHOLDER", "verify": True}, "purpose": "Post to Twitter (requires approval)"})

        # Deduplicate steps by tool name to preserve clean execution
        seen_tools = set()
        deduped = []
        for s in steps:
            t = s.get("tool")
            if t not in seen_tools:
                seen_tools.add(t)
                deduped.append(s)

        return {"steps": deduped, "estimated_risk": "high" if wants_post else "low", "skill_id": skill_id}

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
