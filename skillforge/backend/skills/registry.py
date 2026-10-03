"""
SkillForge — Skill Registry
Loads, validates, and serves Skills from the skills/definitions directory.
Each Skill is an independent SKILL.md-based capability descriptor.
"""
import os
import re
from pathlib import Path
from typing import Optional

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False


_default_skills_dir = Path(__file__).parent / "definitions"
SKILLS_DIR = Path(os.environ.get("SKILLFORGE_SKILLS_DIR", str(_default_skills_dir)))
if not SKILLS_DIR.is_absolute() and not SKILLS_DIR.exists():
    SKILLS_DIR = _default_skills_dir

# Built-in skill descriptions keyed by skill directory name
BUILTIN_SKILLS = {
    "web-search": {
        "id": "web-search",
        "name": "web-search",
        "description": "Search the web for public information using natural language queries.",
        "version": "1.0.0",
        "capabilities": ["Search web content", "Find URLs", "Retrieve snippets"],
        "tools": ["web_search"],
        "installed": True,
        "enabled": True,
        "source": "built-in",
    },
    "job-search": {
        "id": "job-search",
        "name": "job-search",
        "description": "Search public job listings and extract requirements and interview questions.",
        "version": "1.0.0",
        "capabilities": ["Search job boards", "Extract requirements", "Extract interview questions"],
        "tools": ["job_search", "webpage_reader", "extract_interview_questions"],
        "installed": True,
        "enabled": True,
        "source": "built-in",
    },
    "webpage-reader": {
        "id": "webpage-reader",
        "name": "webpage-reader",
        "description": "Extract readable text content from any public webpage URL.",
        "version": "1.0.0",
        "capabilities": ["Read webpage content", "Extract text", "Handle redirects"],
        "tools": ["webpage_reader"],
        "installed": True,
        "enabled": True,
        "source": "built-in",
    },
    "youtube-search": {
        "id": "youtube-search",
        "name": "youtube-search",
        "description": "Search YouTube for videos by topic or query.",
        "version": "1.0.0",
        "capabilities": ["Search videos", "Get video metadata", "Filter by topic"],
        "tools": ["youtube_search"],
        "installed": True,
        "enabled": True,
        "source": "built-in",
    },
    "file-creator": {
        "id": "file-creator",
        "name": "file-creator",
        "description": "Create structured files and reports from AI-generated content.",
        "version": "1.0.0",
        "capabilities": ["Create markdown files", "Create text reports", "Create JSON output"],
        "tools": ["create_file"],
        "installed": True,
        "enabled": True,
        "source": "built-in",
    },
    "interview-research": {
        "id": "interview-research",
        "name": "interview-research",
        "description": "Research company interview processes, rounds, technical/coding/behavioral questions, and preparation advice using Agent-Reach.",
        "version": "1.0.0",
        "capabilities": ["Company research", "Interview rounds & process", "Technical & coding questions", "Suggested answers", "Source verification"],
        "tools": ["reach_research", "reach_web_search", "reach_web_read", "extract_interview_questions"],
        "installed": True,
        "enabled": True,
        "source": "built-in",
    },
    "github-research": {
        "id": "github-research",
        "name": "github-research",
        "description": "Search and inspect public GitHub repositories and open-source code via Agent-Reach.",
        "version": "1.0.0",
        "capabilities": ["Search repositories", "Inspect open-source code", "Find issues & PRs"],
        "tools": ["reach_github_search"],
        "installed": True,
        "enabled": True,
        "source": "built-in",
    },
    "skill-builder": {
        "id": "skill-builder",
        "name": "skill-builder",
        "description": "Generate, validate, and install new SKILL.md-based capabilities.",
        "version": "1.0.0",
        "capabilities": ["Generate SKILL.md", "Validate skills", "Install skills"],
        "tools": ["skill_validate", "skill_install"],
        "installed": True,
        "enabled": True,
        "source": "built-in",
    },
}

# Runtime-installed skills (user-created)
_installed_skills: dict[str, dict] = {}


def _parse_skill_md(path: Path) -> Optional[dict]:
    text = path.read_text(encoding="utf-8")
    if not text.strip().startswith("---"):
        return None
    parts = text.split("---", 2)
    if len(parts) < 3:
        return None

    if HAS_YAML:
        fm = yaml.safe_load(parts[1]) or {}
    else:
        # Minimal parser: key: value per line
        fm = {}
        for line in parts[1].splitlines():
            if ":" in line:
                k, _, v = line.partition(":")
                fm[k.strip()] = v.strip()

    name = fm.get("name", path.parent.name)
    return {
        "id": name,
        "name": name,
        "description": fm.get("description", ""),
        "version": fm.get("version", "1.0.0"),
        "capabilities": fm.get("capabilities", []) or [],
        "tools": fm.get("tools", []) or [],
        "installed": True,
        "enabled": True,
        "source": "user",
    }


def list_skills() -> list[dict]:
    all_skills = dict(BUILTIN_SKILLS)
    # Load from disk
    if SKILLS_DIR.exists():
        for skill_dir in SKILLS_DIR.iterdir():
            skill_md = skill_dir / "SKILL.md"
            if skill_md.exists() and skill_dir.name not in all_skills:
                parsed = _parse_skill_md(skill_md)
                if parsed:
                    all_skills[skill_dir.name] = parsed
    # Add runtime-installed
    all_skills.update(_installed_skills)
    return list(all_skills.values())


def get_skill(skill_id: str) -> Optional[dict]:
    if skill_id in BUILTIN_SKILLS:
        return BUILTIN_SKILLS[skill_id]
    if skill_id in _installed_skills:
        return _installed_skills[skill_id]
    # Try disk
    skill_dir = SKILLS_DIR / skill_id
    skill_md = skill_dir / "SKILL.md"
    if skill_md.exists():
        return _parse_skill_md(skill_md)
    return None


def install_skill(name: str, skill_data: dict) -> dict:
    """Register a newly installed skill at runtime."""
    skill_data["id"] = name
    skill_data["name"] = name
    skill_data["installed"] = True
    skill_data["source"] = "user"
    _installed_skills[name] = skill_data
    return skill_data


def resolve_skill_for_goal(goal: str) -> Optional[str]:
    """Simple keyword-based skill resolver. Gemma 4 can do smarter routing."""
    goal_lower = goal.lower()

    if any(kw in goal_lower for kw in ["youtube", "video", "watch", "tutorial"]):
        return "youtube-search"

    # Job-specific (boards, hiring, vacancies)
    if "job" in goal_lower or any(kw in goal_lower for kw in ["career", "hiring", "recruit", "position", "vacancy"]):
        return "job-search"

    # Interview and company research (prioritized for pure interview research)
    if any(kw in goal_lower for kw in ["interview question", "interview process", "interview round", "company background", "interview experience", "fresher", "suggested answer", "preparation advice", "rounds"]):
        return "interview-research"
    if any(kw in goal_lower for kw in ["github", "repository", "open source", "repo", "public repositories"]):
        return "github-research"
    if any(kw in goal_lower for kw in ["paper", "research", "arxiv", "publication", "study", "journal"]):
        return "research-paper-search"
    if any(kw in goal_lower for kw in ["youtube", "video", "watch", "tutorial"]):
        return "youtube-search"
    if any(kw in goal_lower for kw in ["read", "open", "page", "website", "browse", "visit", "url"]):
        return "webpage-reader"
    if any(kw in goal_lower for kw in ["file", "report", "save", "write", "create document", "make a document"]):
        return "file-creator"
    if any(kw in goal_lower for kw in ["skill", "teach", "create skill", "new capability"]):
        return "skill-builder"
    if any(kw in goal_lower for kw in ["search", "find", "look up", "google", "discover"]):
        return "web-search"

    # Check user-installed skills
    for skill in list(_installed_skills.values()):
        skill_name = skill.get("name", "").lower()
        skill_desc = skill.get("description", "").lower()
        if any(word in goal_lower for word in skill_name.split("-")):
            return skill["id"]
        if any(word in skill_desc for word in goal_lower.split()):
            return skill["id"]

    return "web-search"  # Default
