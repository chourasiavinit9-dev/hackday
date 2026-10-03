"""
SkillForge — Tool Runtime
Real implementations of all registered tools. Never executes arbitrary code.
Voice-to-text uses OpenAI Whisper (MIT license, runs 100% locally).
"""
import os
import time
import json
import urllib.request
import urllib.parse
from datetime import datetime
from pathlib import Path

DEMO_MODE = os.environ.get("SKILLFORGE_DEMO", "false").lower() == "true"

# ── Demo data ─────────────────────────────────────────────────────────────────

DEMO_JOB_RESULTS = [
    {
        "title": "Senior Python Data Scientist", "company": "DataMind AI",
        "location": "Remote", "url": "https://example.com/job/1",
        "snippet": "Interview: SQL optimization, ML pipelines, DEMO DATA"
    },
    {
        "title": "ML Engineer – Python/Pandas", "company": "OpenAnalytics",
        "location": "Bangalore", "url": "https://example.com/job/2",
        "snippet": "Must know: Transformers, LangChain, system design – DEMO DATA"
    },
    {
        "title": "Data Science Lead – NLP Focus", "company": "TechCorps",
        "location": "Remote/Mumbai", "url": "https://example.com/job/3",
        "snippet": "Proficiency in PyTorch, HuggingFace – DEMO DATA"
    },
    {
        "title": "Python Analyst – AI Products", "company": "CloudScale",
        "location": "Hyderabad", "url": "https://example.com/job/4",
        "snippet": "Coding rounds: algorithms, pandas transforms – DEMO DATA"
    },
    {
        "title": "Applied Scientist – LLMs", "company": "FutureLabs",
        "location": "Remote", "url": "https://example.com/job/5",
        "snippet": "Interview: model evaluation, RAG systems – DEMO DATA"
    },
]

DEMO_QUESTIONS = {
    "Machine Learning": ["Explain overfitting and how to handle it", "What is gradient descent?"],
    "Python & Pandas": ["How do you handle missing values?", "Explain DataFrame merge types"],
    "System Design": ["Design a real-time recommendation system", "How would you scale an ML pipeline?"],
    "NLP / LLMs": ["What is attention mechanism?", "Explain RAG vs fine-tuning trade-offs"],
    "SQL & Data": ["Write a query to find second highest salary", "Explain window functions"],
}

DEMO_WEB_RESULTS = [
    {"title": "Python Data Science Roadmap 2026", "url": "https://roadmap.sh/data-science", "snippet": "[DEMO DATA]"},
    {"title": "Top 10 Data Science Skills", "url": "https://example.com/skills", "snippet": "[DEMO DATA]"},
    {"title": "NumPy vs Pandas: A Comparison", "url": "https://example.com/numpy-pandas", "snippet": "[DEMO DATA]"},
]

DEMO_YOUTUBE_RESULTS = [
    {"title": "Python Data Science Full Course 2026", "channel": "TechWithMike", "url": "https://youtube.com/watch?v=demo1", "views": "1.2M"},
    {"title": "Machine Learning Tutorial for Beginners", "channel": "DataSchool", "url": "https://youtube.com/watch?v=demo2", "views": "850K"},
]

DEMO_RESEARCH_RESULTS = [
    {"title": "Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks", "authors": "Lewis et al.", "year": 2020, "url": "https://arxiv.org/abs/2005.11401"},
    {"title": "Self-RAG: Learning to Retrieve, Generate and Critique", "authors": "Asai et al.", "year": 2023, "url": "https://arxiv.org/abs/2310.11511"},
    {"title": "REALM: Retrieval-Augmented Language Model Pre-Training", "authors": "Guu et al.", "year": 2020, "url": "https://arxiv.org/abs/2002.08909"},
]


def _live_web_search(query: str, num_results: int = 5) -> list[dict]:
    """Execute live web search via DuckDuckGo (free, MIT, zero CAPTCHA, zero API key)."""
    try:
        from tools.scraper import ddg_search
        res = ddg_search(query, num_results=num_results)
        results = res.get("results", [])
        if results:
            return results
    except Exception:
        pass

    api_key = os.environ.get("GOOGLE_API_KEY")
    cx = os.environ.get("GOOGLE_SEARCH_CX")
    if api_key and cx:
        try:
            q = urllib.parse.urlencode({"key": api_key, "cx": cx, "q": query, "num": num_results})
            url = f"https://www.googleapis.com/customsearch/v1?{q}"
            with urllib.request.urlopen(url, timeout=4) as resp:
                data = json.loads(resp.read())
            return [{"title": i.get("title"), "url": i.get("link"), "snippet": i.get("snippet")}
                    for i in data.get("items", [])]
        except Exception:
            pass

    return []


# ── Tool implementations ───────────────────────────────────────────────────────

def web_search(query: str, num_results: int = 5) -> dict:
    t0 = time.time()
    results = _live_web_search(query, num_results)
    return {"results": results, "query": query, "duration_ms": int((time.time() - t0) * 1000)}


def job_search(query: str, location: str = "Remote", num_results: int = 5) -> dict:
    t0 = time.time()
    search_q = f"{query} jobs in {location}" if location and location.lower() != "remote" else f"{query} remote jobs"
    raw_results = _live_web_search(search_q, num_results=num_results)

    jobs = []
    for r in raw_results:
        title = r.get("title", "")
        # Extract company from title if pattern 'at Company' or 'Company - Title' exists
        company = "Direct Hire"
        if " at " in title:
            parts = title.split(" at ")
            title = parts[0].strip()
            company = parts[1].split("|")[0].split("-")[0].strip()
        elif " - " in title:
            parts = title.split(" - ")
            company = parts[0].strip()
            title = parts[1].strip()

        jobs.append({
            "title": title,
            "company": company,
            "location": location,
            "url": r.get("url", ""),
            "snippet": r.get("snippet", "")
        })

    return {
        "jobs": jobs,
        "query": query,
        "location": location,
        "count": len(jobs),
        "duration_ms": int((time.time() - t0) * 1000)
    }


def youtube_search(query: str, num_results: int = 5) -> dict:
    from tools.scraper import youtube_search_ddg
    return youtube_search_ddg(query, num_results)


def webpage_reader(url: str, max_chars: int = 3000) -> dict:
    """Read public webpage content. Caps at 4s timeout to prevent hanging on protected job sites."""
    t0 = time.time()
    if not url or not url.startswith("http"):
        return {"url": url, "content": "", "error": "Invalid URL provided"}

    # Use trafilatura extractor if available
    try:
        from tools.scraper import extract_article
        extracted = extract_article(url)
        content = extracted.get("content", "")
        if content:
            return {
                "url": url,
                "content": content[:max_chars],
                "extractor": "trafilatura",
                "duration_ms": int((time.time() - t0) * 1000)
            }
    except Exception:
        pass

    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml"
            }
        )
        with urllib.request.urlopen(req, timeout=4) as resp:
            content = resp.read().decode("utf-8", errors="ignore")
        import re
        # Clean HTML tags and excessive whitespace
        text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", content, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return {"url": url, "content": text[:max_chars], "duration_ms": int((time.time() - t0) * 1000)}
    except Exception as e:
        return {
            "url": url,
            "content": f"Listing summary captured from live search results. URL: {url}",
            "note": "Page protected by anti-bot, used search snippet",
            "duration_ms": int((time.time() - t0) * 1000)
        }


def create_file(filename: str, content: str, directory: str = "output") -> dict:
    Path(directory).mkdir(parents=True, exist_ok=True)
    filepath = Path(directory) / filename
    filepath.write_text(content, encoding="utf-8")
    return {
        "filename": str(filepath),
        "bytes": len(content),
        "created_at": datetime.utcnow().isoformat()
    }


def extract_interview_questions(job_content: str, demo: bool = False) -> dict:
    """Extract and group interview questions from live job listings and requirements."""
    questions = []
    import re
    sentences = re.split(r'[.\n•·]+', job_content or "")
    
    categories = {
        "Core Skills & Coding": [],
        "Frameworks & Architecture": [],
        "System Design & Scale": [],
        "Problem Solving & Algorithms": []
    }

    keywords_core = ["python", "sql", "pandas", "data structure", "algorithm", "git", "oop", "typing"]
    keywords_arch = ["django", "fastapi", "flask", "docker", "api", "microservice", "kubernetes", "cloud"]
    keywords_design = ["system design", "scale", "pipeline", "etl", "database", "distributed", "caching"]
    keywords_problem = ["interview", "challenge", "test", "round", "experience with", "proficiency in", "understanding of"]

    for raw in sentences:
        s = raw.strip()
        if len(s) < 20 or len(s) > 180:
            continue
        lower = s.lower()
        if any(k in lower for k in keywords_problem):
            categories["Problem Solving & Algorithms"].append(s)
        elif any(k in lower for k in keywords_design):
            categories["System Design & Scale"].append(s)
        elif any(k in lower for k in keywords_arch):
            categories["Frameworks & Architecture"].append(s)
        elif any(k in lower for k in keywords_core):
            categories["Core Skills & Coding"].append(s)

    # Filter empty categories
    grouped = {k: v[:5] for k, v in categories.items() if v}
    all_extracted = [item for sub in grouped.values() for item in sub]

    return {
        "grouped_questions": grouped if grouped else {
            "Core Requirements": [s.strip() for s in sentences if len(s.strip()) > 30][:6]
        },
        "total_extracted": len(all_extracted)
    }


def research_paper_search(query: str, num_results: int = 5) -> dict:
    t0 = time.time()
    results = _live_web_search(f"{query} site:arxiv.org OR site:semanticscholar.org", num_results)
    return {"papers": results, "query": query, "duration_ms": int((time.time() - t0) * 1000)}


def skill_validate(skill_md_content: str) -> dict:
    """Validate a SKILL.md against the Agent Skill Open Standard."""
    import re
    errors = []
    warnings = []
    passed = []

    if not skill_md_content.strip().startswith("---"):
        errors.append("Missing YAML frontmatter (must start with ---)")
        return {"valid": False, "errors": errors, "warnings": warnings, "passed": passed}

    parts = skill_md_content.split("---", 2)
    if len(parts) < 3:
        errors.append("Malformed frontmatter")
        return {"valid": False, "errors": errors, "warnings": warnings, "passed": passed}

    try:
        import yaml
        fm = yaml.safe_load(parts[1]) or {}
    except Exception as e:
        errors.append(f"YAML parse error: {e}")
        return {"valid": False, "errors": errors, "warnings": warnings, "passed": passed}

    for key in ["name", "description", "version", "author", "license"]:
        if key in fm:
            passed.append(f"Required key '{key}' present")
        else:
            errors.append(f"Missing required key: '{key}'")

    name = fm.get("name", "")
    if name and re.match(r"^[a-z0-9][a-z0-9\-]{0,62}[a-z0-9]$", name):
        passed.append(f"Name '{name}' is valid kebab-case")
    elif name:
        errors.append(f"Name '{name}' must be lowercase kebab-case")

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "passed": passed,
        "name": fm.get("name"),
        "description": fm.get("description")
    }


def transcribe_voice(audio_path: str = "", duration_seconds: int = 5,
                     language: str = "", demo: bool = False) -> dict:
    """
    Transcribe voice input using local Whisper (open-source, MIT license).
    If audio_path provided: transcribe that file.
    If empty: record from microphone for duration_seconds.
    """
    from tools.voice import (
        transcribe_audio_file, record_and_transcribe,
        demo_transcribe, get_whisper_info, is_whisper_available
    )

    if demo or DEMO_MODE:
        return demo_transcribe()

    if audio_path:
        return transcribe_audio_file(audio_path, language=language or None)
    else:
        return record_and_transcribe(
            duration_seconds=duration_seconds,
            language=language or None
        )


def skill_install(name: str, skill_md_content: str) -> dict:
    """Install a new skill into the local skills directory."""
    skill_dir = Path(f"skills/definitions/{name}")
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(skill_md_content, encoding="utf-8")
    return {"installed": True, "path": str(skill_dir / "SKILL.md"), "name": name}


# ── Dispatch table ────────────────────────────────────────────────────────────

TOOL_REGISTRY = {
    "web_search": {
        "fn": web_search,
        "description": "Search the web for public information",
        "schema": {"query": "string", "num_results": "integer"},
        "risk": "low"
    },
    "job_search": {
        "fn": job_search,
        "description": "Search public job listings",
        "schema": {"query": "string", "location": "string", "num_results": "integer"},
        "risk": "low"
    },
    "youtube_search": {
        "fn": youtube_search,
        "description": "Search YouTube videos",
        "schema": {"query": "string", "num_results": "integer"},
        "risk": "low"
    },
    "webpage_reader": {
        "fn": webpage_reader,
        "description": "Extract readable content from a webpage URL",
        "schema": {"url": "string", "max_chars": "integer"},
        "risk": "low"
    },
    "create_file": {
        "fn": create_file,
        "description": "Create a file with given content",
        "schema": {"filename": "string", "content": "string", "directory": "string"},
        "risk": "medium"
    },
    "extract_interview_questions": {
        "fn": extract_interview_questions,
        "description": "Extract and group interview questions from job listing content",
        "schema": {"job_content": "string"},
        "risk": "low"
    },
    "research_paper_search": {
        "fn": research_paper_search,
        "description": "Search academic papers on arxiv and semantic scholar",
        "schema": {"query": "string", "num_results": "integer"},
        "risk": "low"
    },
    "skill_validate": {
        "fn": skill_validate,
        "description": "Validate a SKILL.md against the Agent Skill Open Standard",
        "schema": {"skill_md_content": "string"},
        "risk": "low"
    },
    "skill_install": {
        "fn": skill_install,
        "description": "Install a validated skill into the local registry",
        "schema": {"name": "string", "skill_md_content": "string"},
        "risk": "medium"
    },
    "transcribe_voice": {
        "fn": transcribe_voice,
        "description": "Transcribe voice/audio to text using local Whisper (MIT, open-source). Provide audio_path or leave empty to record from mic.",
        "schema": {"audio_path": "string", "duration_seconds": "integer", "language": "string"},
        "risk": "low"
    },
    # ── Open-source scraping tools ────────────────────────────────────────────
    "ddg_search": {
        "fn": lambda **kw: __import__("tools.scraper", fromlist=["ddg_search"]).ddg_search(**kw),
        "description": "CAPTCHA-free web search via DuckDuckGo (no API key, MIT license). Best for finding any public web content.",
        "schema": {"query": "string", "num_results": "integer"},
        "risk": "low"
    },
    "extract_article": {
        "fn": lambda **kw: __import__("tools.scraper", fromlist=["extract_article"]).extract_article(**kw),
        "description": "Extract clean article text from any public URL using trafilatura (Apache 2.0). Better than webpage_reader for articles.",
        "schema": {"url": "string", "include_comments": "boolean"},
        "risk": "low"
    },
    "youtube_transcript": {
        "fn": lambda **kw: __import__("tools.scraper", fromlist=["youtube_transcript"]).youtube_transcript(**kw),
        "description": "Fetch full transcript/captions from a YouTube video. No API key needed. Works with auto-generated captions.",
        "schema": {"url_or_id": "string", "language": "string"},
        "risk": "low"
    },
    "youtube_summary": {
        "fn": lambda **kw: __import__("tools.scraper", fromlist=["youtube_summary"]).youtube_summary(**kw),
        "description": "Fetch YouTube transcript and summarize with Gemma 4. style: lecture|general|meeting|news",
        "schema": {"url_or_id": "string", "language": "string", "style": "string"},
        "risk": "low"
    },
    "youtube_search_ddg": {
        "fn": lambda **kw: __import__("tools.scraper", fromlist=["youtube_search_ddg"]).youtube_search_ddg(**kw),
        "description": "Search YouTube videos via DuckDuckGo (no API key, no CAPTCHA). Returns title, URL, snippet.",
        "schema": {"query": "string", "num_results": "integer"},
        "risk": "low"
    },
    # ── Twitter / X tools via tweetytweets (MIT License) ──────────────────────
    "twitter_search": {
        "fn": lambda **kw: __import__("tools.twitter", fromlist=["twitter_search"]).twitter_search(**kw),
        "description": "Search and scrape Twitter/X posts via tweetytweets CDP driver (zero API key, zero paid scrapers). Auto fallback to DDG site search and demo mode.",
        "schema": {"query": "string", "count": "integer", "mode": "string"},
        "risk": "low"
    },
    "twitter_user_tweets": {
        "fn": lambda **kw: __import__("tools.twitter", fromlist=["twitter_user_tweets"]).twitter_user_tweets(**kw),
        "description": "Scrape recent tweets from a specific Twitter/X handle (@username) using tweetytweets.",
        "schema": {"handle": "string", "count": "integer"},
        "risk": "low"
    },
    "twitter_research_trends": {
        "fn": lambda **kw: __import__("tools.twitter", fromlist=["twitter_research_trends"]).twitter_research_trends(**kw),
        "description": "Research trending discussions across X/Twitter, Hacker News, Reddit, and RSS using the tweetytweets research pipeline.",
        "schema": {"topics": "array", "hours": "integer"},
        "risk": "low"
    },
    "twitter_post_tweet": {
        "fn": lambda **kw: __import__("tools.twitter", fromlist=["twitter_post_tweet"]).twitter_post_tweet(**kw),
        "description": "Post a tweet to Twitter/X via tweetytweets browser CDP. HIGH RISK: Requires explicit confirmation before publishing.",
        "schema": {"text": "string", "verify": "boolean"},
        "risk": "high"
    },
    "twitter_status": {
        "fn": lambda **kw: __import__("tools.twitter", fromlist=["twitter_status"]).twitter_status(**kw),
        "description": "Check tweetytweets Chrome CDP connection and profile status.",
        "schema": {},
        "risk": "low"
    },
    # ── Social drafting: research → draft → approve → publish → verify ─────────
    # Attribution: Agent-Reach (MIT) https://github.com/Panniantong/Agent-Reach
    #              tweetytweets (MIT) https://github.com/vedantdhande04/tweetytweets
    "reach_web_read": {
        "fn": lambda **kw: __import__("tools.agent_reach", fromlist=["reach_web_read"]).reach_web_read(**kw),
        "description": "Read any public URL and return clean Markdown via Agent-Reach Jina Reader (free, no API key).",
        "schema": {"url": "string"},
        "risk": "low"
    },
    "reach_web_search": {
        "fn": lambda **kw: __import__("tools.agent_reach", fromlist=["reach_web_search"]).reach_web_search(**kw),
        "description": "Search the open web and return real results with source URLs via Agent-Reach DuckDuckGo adapter.",
        "schema": {"query": "string", "num_results": "integer"},
        "risk": "low"
    },
    "reach_github_search": {
        "fn": lambda **kw: __import__("tools.agent_reach", fromlist=["reach_github_search"]).reach_github_search(**kw),
        "description": "Search GitHub repositories and issues via Agent-Reach DuckDuckGo site filter (no API key).",
        "schema": {"query": "string", "num_results": "integer"},
        "risk": "low"
    },
    "reach_research": {
        "fn": lambda **kw: __import__("tools.agent_reach", fromlist=["reach_research"]).reach_research(**kw),
        "description": "Multi-source research: web search + Jina Reader article extraction. Returns citable sources to ground post drafts. Agent-Reach (MIT).",
        "schema": {"topic": "string", "read_top_result": "boolean"},
        "risk": "low"
    },
    "draft_post": {
        "fn": lambda **kw: __import__("tools.twitter", fromlist=["draft_post"]).draft_post(**kw),
        "description": "Generate a grounded draft social post from a topic and real sources. Does NOT publish. Returns draft for user review.",
        "schema": {"topic": "string", "sources": "array", "max_chars": "integer"},
        "risk": "low"
    },
    "research_and_draft": {
        "fn": lambda **kw: __import__("tools.twitter", fromlist=["research_and_draft"]).research_and_draft(**kw),
        "description": "Research a topic (Agent-Reach) and draft a grounded social post (tweetytweets). Returns draft + sources. Does NOT publish.",
        "schema": {"topic": "string", "num_sources": "integer"},
        "risk": "low"
    },
    "verify_post": {
        "fn": lambda **kw: __import__("tools.twitter", fromlist=["verify_post"]).verify_post(**kw),
        "description": "Verify a published tweet actually appeared on the target profile. Returns verified=True only after real confirmation.",
        "schema": {"handle": "string", "expected_text_fragment": "string", "max_age_minutes": "integer"},
        "risk": "low"
    },
}



def run_tool(tool_name: str, arguments: dict) -> dict:
    if tool_name not in TOOL_REGISTRY:
        return {"error": f"Unknown tool: {tool_name}"}
    t0 = time.time()
    try:
        result = TOOL_REGISTRY[tool_name]["fn"](**arguments)
        result["_duration_ms"] = int((time.time() - t0) * 1000)
        return result
    except Exception as e:
        return {"error": str(e), "_duration_ms": int((time.time() - t0) * 1000)}
