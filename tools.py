"""
HackGuide — Tool Definitions for Gemma 4 Native Function Calling
Built at Hacktoberfest Hack Day Asansol x HackTropica 2026
"""

import json

# ── Tool schemas (Gemma 4 function declarations) ──────────────────────────────
TOOLS = [
    {
        "name": "analyze_project_feasibility",
        "description": (
            "Given a hackathon challenge, team size, time available, and tech stack, "
            "compute a feasibility score and recommend the optimal MVP scope. "
            "Returns a risk level (LOW/MEDIUM/HIGH), a recommended feature set, "
            "and the maximum safe number of features to build."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "challenge": {
                    "type": "string",
                    "description": "The hackathon challenge or prize track name"
                },
                "team_size": {
                    "type": "integer",
                    "description": "Number of people on the team (1-4)"
                },
                "hours_available": {
                    "type": "number",
                    "description": "Real hacking hours available (subtract 1h for setup/demos)"
                },
                "tech_stack": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Languages, frameworks, or tools the team knows"
                }
            },
            "required": ["challenge", "team_size", "hours_available"]
        }
    },
    {
        "name": "generate_project_timeline",
        "description": (
            "Generate a precise hour-by-hour hackathon execution battle clock "
            "given a project scope, list of features, and available hacking hours. "
            "Returns a structured timeline with time blocks and assigned tasks."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "project_name": {
                    "type": "string",
                    "description": "Name of the project being built"
                },
                "features": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Ordered list of features to build (most critical first)"
                },
                "hours_available": {
                    "type": "number",
                    "description": "Total hacking hours available"
                },
                "must_demo_by": {
                    "type": "string",
                    "description": "Submission deadline e.g. '4:30 PM IST'"
                }
            },
            "required": ["project_name", "features", "hours_available"]
        }
    },
    {
        "name": "generate_readme_template",
        "description": (
            "Generate a complete, competition-ready README.md for a hackathon project. "
            "Includes a Mermaid architecture diagram, tech stack table, setup instructions, "
            "and MLH judging rubric mapping. Output is a markdown string ready to paste."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "project_name": {
                    "type": "string",
                    "description": "Name of the project"
                },
                "description": {
                    "type": "string",
                    "description": "One-line description of what the project does"
                },
                "tech_stack": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Technologies used"
                },
                "github_username": {
                    "type": "string",
                    "description": "GitHub username of the project owner"
                }
            },
            "required": ["project_name", "description", "tech_stack"]
        }
    },
    {
        "name": "transcribe_pitch_audio",
        "description": (
            "Transcribe and analyze a spoken audio pitch or voice note from a hackathon team. "
            "Extracts project requirements, team constraints, problem statement, and scope."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "audio_path": {
                    "type": "string",
                    "description": "Path to the audio file (.mp3, .wav, .m4a, .ogg)"
                }
            },
            "required": ["audio_path"]
        }
    },
    {
        "name": "review_demo_video",
        "description": (
            "Analyze a hackathon demo or pitch rehearsal video (.mp4, .mov, .webm) against "
            "the MLH Judging Rubric (Completion, Technology, Design, Learning) and 60-second pitch rules."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "video_path": {
                    "type": "string",
                    "description": "Path to the video file (.mp4, .mov, .webm)"
                }
            },
            "required": ["video_path"]
        }
    },
    {
        "name": "analyze_architecture_image",
        "description": (
            "Analyze an architecture diagram, whiteboard sketch, or UI wireframe image "
            "to extract system components and identify potential hackathon implementation risks."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "image_path": {
                    "type": "string",
                    "description": "Path to the image file (.png, .jpg, .webp)"
                }
            },
            "required": ["image_path"]
        }
    },
    {
        "name": "generate_digitalocean_spec",
        "description": (
            "Generate a production-ready DigitalOcean App Platform specification (.do/app.yaml) "
            "for one-click deployment. Supports web services, managed PostgreSQL, Redis, "
            "Spaces object storage, and DigitalOcean Gradient AI serverless inference."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "project_name": {
                    "type": "string",
                    "description": "Name of the application/project"
                },
                "services": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of resources needed: web, postgres, redis, spaces, gradient_ai"
                },
                "repo_slug": {
                    "type": "string",
                    "description": "GitHub repo slug, e.g. chourasiavinit9-dev/hackguide"
                },
                "region": {
                    "type": "string",
                    "description": "DigitalOcean datacenter region (blr, nyc, sfo, fra, ams)"
                }
            },
            "required": ["project_name"]
        }
    }
]


# ── Tool execution functions ───────────────────────────────────────────────────
def analyze_project_feasibility(
    challenge: str,
    team_size: int,
    hours_available: float,
    tech_stack: list[str] = None
) -> dict:
    tech_stack = tech_stack or []
    # Compute base risk based on time & team
    risk_score = 0
    if hours_available < 2:
        risk_score += 3
    elif hours_available < 4:
        risk_score += 1

    if team_size == 1:
        risk_score += 2
    elif team_size >= 4:
        risk_score += 0

    max_features = max(1, min(5, int(hours_available * team_size / 1.5)))
    risk = "HIGH" if risk_score >= 3 else ("MEDIUM" if risk_score >= 1 else "LOW")

    return {
        "feasibility_score": max(1, 10 - risk_score * 2),
        "risk_level": risk,
        "max_safe_features": max_features,
        "recommended_mvp": (
            f"Build only the absolute core of '{challenge}'. "
            f"With {team_size} person(s) and {hours_available}h, aim for {max_features} features max."
        ),
        "warning": (
            "⚠️ Over-scoping is the #1 failure mode at hack days. "
            "A flawlessly working 2-feature demo beats a broken 10-feature one every time."
        )
    }


def generate_project_timeline(
    project_name: str,
    features: list[str],
    hours_available: float,
    must_demo_by: str = "4:30 PM IST"
) -> dict:
    slots = []
    # Reserve first 15% for scaffold, last 15% for buffer
    scaffold_h = round(hours_available * 0.15, 1)
    buffer_h = round(hours_available * 0.15, 1)
    coding_h = hours_available - scaffold_h - buffer_h

    per_feature = round(coding_h / max(len(features), 1), 1)

    slots.append({
        "block": f"Hour 0:00 – {scaffold_h:.1f}h",
        "task": "Scaffold: repo, LICENSE, .env, install deps, test API call → confirm it works"
    })

    cursor = scaffold_h
    for i, feat in enumerate(features):
        end = cursor + per_feature
        slots.append({
            "block": f"Hour {cursor:.1f} – {end:.1f}h",
            "task": f"Feature {i+1}: {feat}"
        })
        cursor = end

    slots.append({
        "block": f"Hour {cursor:.1f} – {hours_available:.1f}h",
        "task": f"Buffer: README, push to GitHub, submit on OrganizerHQ, rehearse 60s pitch (deadline: {must_demo_by})"
    })

    return {
        "project": project_name,
        "total_hours": hours_available,
        "timeline": slots,
        "golden_rule": "Stop adding features at Hour {:.1f}h. Polish what you have.".format(
            hours_available - buffer_h
        )
    }


def generate_readme_template(
    project_name: str,
    description: str,
    tech_stack: list[str],
    github_username: str = "chourasiavinit9-dev"
) -> str:
    tech_table = "\n".join([f"| {t} | ✅ |" for t in tech_stack])
    return f"""# {project_name}

> {description}

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Built with Gemma 4](https://img.shields.io/badge/Gemma%204-Apache%202.0-blue)](https://ai.google.dev/gemma)
[![Hacktoberfest 2026](https://img.shields.io/badge/Hacktoberfest-2026-orange)](https://hacktoberfest.com)

Built at **Hacktoberfest Hack Day Asansol × HackTropica 2026**

---

## 🏗️ Architecture

```mermaid
graph TD
    User-->|natural language prompt|Agent[HackGuide Agent]
    Agent-->|thinking mode|Gemma4[Gemma 4 via Gemini API]
    Gemma4-->|tool_call token|Dispatcher[Tool Dispatcher]
    Dispatcher-->|analyze|F1[analyze_project_feasibility]
    Dispatcher-->|timeline|F2[generate_project_timeline]
    Dispatcher-->|readme|F3[generate_readme_template]
    F1-->|result|Gemma4
    F2-->|result|Gemma4
    F3-->|result|Gemma4
    Gemma4-->|final response|User
```

## 🛠️ Tech Stack

| Technology | Used |
| --- | --- |
{tech_table}
| Gemma 4 (Apache 2.0) | ✅ |
| Agent Skill Open Standard | ✅ |

## 🚀 Quick Start

```bash
git clone https://github.com/{github_username}/{project_name.lower().replace(' ', '-')}
cd {project_name.lower().replace(' ', '-')}
pip install google-generativeai rich
cp .env.example .env        # add your GEMINI_API_KEY
python main.py
```

## 📊 MLH Judging Rubric Map

| Criterion | Implementation |
| --- | --- |
| **Technology** | Gemma 4 native tool-calling tokens + Thinking Mode + SKILL.md compliance |
| **Design** | Real-time streaming chain-of-thought in Rich terminal UI |
| **Completion** | Fully working Python CLI — zero deployment dependencies |
| **Learning** | Agent Skill Open Standard, Gemma 4 thinking architecture, tool-call token syntax |

## 📁 Agent Skill

This project is a fully compliant **Agent Skill** under the Agent Skill Open Standard.
The `SKILL.md` file serves as the skill definition, supporting progressive disclosure
across Discovery → Activation → Execution phases.

## 👥 Team

- **Vinit Chaurasia** ([@chourasiavinit9-dev](https://github.com/chourasiavinit9-dev))
- **Avijit Aditya** ([@Avijit010325](https://github.com/Avijit010325))

## 📄 License

MIT — see [LICENSE](LICENSE)
"""


def generate_digitalocean_spec(
    project_name: str,
    services: list[str] = None,
    repo_slug: str = "chourasiavinit9-dev/hackguide",
    region: str = "blr"
) -> str:
    """Generate production-ready DigitalOcean App Platform spec (.do/app.yaml)."""
    services = [s.lower() for s in (services or ["web", "postgres"])]
    clean_name = project_name.lower().replace(" ", "-")

    yaml_lines = [
        f"name: {clean_name}",
        f"region: {region}",
        "services:",
        f"  - name: {clean_name}-api",
        "    github:",
        f"      repo: {repo_slug}",
        "      branch: main",
        "      deploy_on_push: true",
        "    build_command: pip install -r requirements.txt",
        "    run_command: python main.py",
        "    http_port: 8080",
        "    instance_count: 1",
        "    instance_size_slug: basic-xxs",
        "    routes:",
        "      - path: /",
        "    envs:",
        "      - key: GEMINI_API_KEY",
        "        scope: RUN_TIME",
        "        type: SECRET",
        "      - key: GEMMA_MODEL",
        "        value: gemma-4-31b-it",
        "        scope: RUN_TIME",
        "      - key: MULTIMODAL_MODEL",
        "        value: gemini-3.8-flash",
        "        scope: RUN_TIME",
    ]

    if "postgres" in services:
        yaml_lines.extend([
            "databases:",
            f"  - name: {clean_name}-db",
            "    engine: PG",
            "    version: '16'",
            "    production: false",
            "    cluster_name: hackathon-cluster",
        ])

    return "\n".join(yaml_lines)


# ── Tool dispatcher ────────────────────────────────────────────────────────────
def run_tool(tool_name: str, args: dict) -> str:
    """Dispatch a Gemma 4 tool_call to the correct Python function."""
    try:
        if tool_name == "analyze_project_feasibility":
            result = analyze_project_feasibility(**args)
        elif tool_name == "generate_project_timeline":
            result = generate_project_timeline(**args)
        elif tool_name == "generate_readme_template":
            result = generate_readme_template(**args)
        elif tool_name == "transcribe_pitch_audio":
            from multimodal import transcribe_and_extract_voice
            result = transcribe_and_extract_voice(**args)
        elif tool_name == "review_demo_video":
            from multimodal import analyze_demo_video
            result = analyze_demo_video(**args)
        elif tool_name == "analyze_architecture_image":
            from multimodal import analyze_architecture_image
            result = analyze_architecture_image(**args)
        elif tool_name == "generate_digitalocean_spec":
            result = generate_digitalocean_spec(**args)
        else:
            result = {"error": f"Unknown tool: {tool_name}"}
    except Exception as e:
        result = {"error": str(e)}

    return json.dumps(result, indent=2) if isinstance(result, dict) else result

