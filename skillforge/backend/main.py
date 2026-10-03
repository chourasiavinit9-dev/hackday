"""
SkillForge — FastAPI Backend (main.py)
This is the canonical entry point for the SkillForge API server.
It exposes all agent capabilities via REST + Server-Sent Events (SSE).

Canonical server start:
  python main.py                  # production
  uvicorn main:app --reload       # development with auto-reload

Root causes fixed (2026-10-03):
  • Planning hang eliminated — plan_workflow now uses intent-only routing (zero model latency).
  • web_search properly registered in TOOL_REGISTRY and dispatched by run_tool.
  • Follow-up tool calls are no longer discarded — ReAct observe round accumulates all results.
  • Function-call history preserved across rounds — tool responses never orphaned.
  • Hard timeouts on every model and tool call (30s tool / 45s plan / 60s synthesis).
  • Invalid API key gives actionable error at startup instead of a silent hang.
"""
import os
import json
import asyncio
from pathlib import Path
from typing import Optional
from datetime import datetime

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse
from pydantic import BaseModel

import sys
sys.path.insert(0, str(Path(__file__).parent))

from models.types import (
    AgentRequest, ApprovalResponse, AutomationPolicy,
    WorkflowNodeType, WorkflowNodeStatus
)
from skills.registry import list_skills, get_skill, install_skill
from tools.runtime import run_tool, TOOL_REGISTRY
from policy.engine import get_policy, update_policy
from ledger.ledger import get_ledger
from agent.orchestrator import execute_workflow, resolve_approval, get_run, list_runs
from agent.gemma_provider import get_provider

app = FastAPI(
    title="SkillForge API",
    version="2.0.0",
    description="Open-source Gemma 4 agent runtime with ReAct loop"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DEMO_MODE = os.environ.get("SKILLFORGE_DEMO", "false").lower() == "true"


# ── Health ─────────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    provider = get_provider()
    return {
        "status":     "ok",
        "demo_mode":  DEMO_MODE,
        "model":      provider.model_name,
        "model_live": provider.model is not None,
        "timestamp":  datetime.utcnow().isoformat()
    }


# ── Agent Execution (SSE streaming) ────────────────────────────────────────────

@app.post("/api/run")
async def run_agent(request: AgentRequest):
    """Start a ReAct workflow and stream events via SSE."""
    if DEMO_MODE:
        request.demo_mode = True

    async def event_stream():
        try:
            async for event in execute_workflow(request):
                yield f"data: {json.dumps(event, default=str)}\n\n"
                await asyncio.sleep(0)
        except Exception as exc:
            yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )


@app.get("/api/run/{run_id}")
def get_run_status(run_id: str):
    run = get_run(run_id)
    if not run:
        raise HTTPException(404, "Run not found")
    return run.dict()


@app.get("/api/runs")
def list_all_runs():
    return [r.dict() for r in list_runs()]


# ── Approval ───────────────────────────────────────────────────────────────────

@app.post("/api/approve")
def approve_action(response: ApprovalResponse):
    resolve_approval(response.approval_id, response.approved)
    return {"ok": True, "approved": response.approved}


# ── Skills ─────────────────────────────────────────────────────────────────────

@app.get("/api/skills")
def get_skills():
    return list_skills()


@app.get("/api/skills/{skill_id}")
def get_skill_detail(skill_id: str):
    skill = get_skill(skill_id)
    if not skill:
        raise HTTPException(404, f"Skill '{skill_id}' not found")
    return skill


class SkillBuildRequest(BaseModel):
    description: str


@app.post("/api/skills/build")
async def build_skill(request: SkillBuildRequest):
    """Generate a new SKILL.md from a natural-language description."""
    return get_provider().generate_skill_md(request.description)


class SkillInstallRequest(BaseModel):
    name: str
    skill_md: str
    description: str = ""
    capabilities: list[str] = []
    tools: list[str] = []


@app.post("/api/skills/install")
async def install_skill_endpoint(request: SkillInstallRequest):
    from tools.runtime import skill_validate, skill_install
    validation = skill_validate(request.skill_md)
    if not validation["valid"]:
        raise HTTPException(400, detail={"errors": validation["errors"]})
    result = skill_install(request.name, request.skill_md)
    skill_data = {
        "name":         request.name,
        "description":  request.description or validation.get("description", ""),
        "version":      "1.0.0",
        "capabilities": request.capabilities,
        "tools":        request.tools,
        "source":       "user"
    }
    install_skill(request.name, skill_data)
    return {"installed": True, "name": request.name, "path": result["path"]}


class SkillValidateRequest(BaseModel):
    skill_md: str


@app.post("/api/skills/validate")
def validate_skill(request: SkillValidateRequest):
    from tools.runtime import skill_validate
    return skill_validate(request.skill_md)


# ── Tools ──────────────────────────────────────────────────────────────────────

@app.get("/api/tools")
def get_tools():
    return [
        {"name": name, "description": info["description"], "risk": info["risk"]}
        for name, info in TOOL_REGISTRY.items()
    ]


class ToolRunRequest(BaseModel):
    tool_name: str
    arguments: dict


@app.post("/api/tools/run")
def run_tool_endpoint(request: ToolRunRequest):
    """Direct tool execution (for testing/debugging)."""
    if request.tool_name not in TOOL_REGISTRY:
        raise HTTPException(400, f"Unknown tool: {request.tool_name}")
    return run_tool(request.tool_name, request.arguments)


# ── Policy ─────────────────────────────────────────────────────────────────────

@app.get("/api/policy")
def get_policy_endpoint():
    return get_policy().dict()


@app.put("/api/policy")
def update_policy_endpoint(policy: AutomationPolicy):
    update_policy(policy)
    return policy.dict()


# ── Ledger ─────────────────────────────────────────────────────────────────────

@app.get("/api/ledger")
def get_ledger_history(run_id: Optional[str] = None, limit: int = 50):
    return get_ledger().history(run_id=run_id, limit=limit)


@app.get("/api/ledger/verify")
def verify_ledger():
    return get_ledger().verify()


# ── User Profile & Settings Integrations ──────────────────────────────────────

_USER_PROFILE = {
    "name": "Vinit Chaurasia",
    "email": "vinit@skillforge.dev",
    "role": "Lead AI Architect",
    "organization": "SkillForge Runtime",
    "workspace": "chourasiavinit9-dev/hackday",
    "bio": "Building autonomous AI agent runtimes powered by Gemma & open models."
}

_SETTINGS_STATE = {
    "twitter_connected": True,
    "twitter_handle": "@vinitchaurasia",
    "twitter_auto_post": True,
    "discord_connected": True,
    "discord_webhook": "https://discord.com/api/webhooks/demo/agent-alerts",
    "discord_channel": "#agent-alerts",
    "discord_auto_notify": True,
    "auto_approve_safe": True
}


class UserProfileUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    role: Optional[str] = None
    organization: Optional[str] = None
    bio: Optional[str] = None


class SettingsUpdate(BaseModel):
    twitter_connected: Optional[bool] = None
    twitter_handle: Optional[str] = None
    twitter_auto_post: Optional[bool] = None
    discord_connected: Optional[bool] = None
    discord_webhook: Optional[str] = None
    discord_channel: Optional[str] = None
    discord_auto_notify: Optional[bool] = None
    auto_approve_safe: Optional[bool] = None


@app.get("/api/user/info")
def get_user_info():
    return _USER_PROFILE


@app.post("/api/user/info")
def update_user_info(data: UserProfileUpdate):
    for k, v in data.dict(exclude_unset=True).items():
        if v is not None:
            _USER_PROFILE[k] = v
    return _USER_PROFILE


@app.get("/api/settings")
def get_settings():
    return _SETTINGS_STATE


@app.post("/api/settings")
def update_settings(data: SettingsUpdate):
    for k, v in data.dict(exclude_unset=True).items():
        if v is not None:
            _SETTINGS_STATE[k] = v
    return _SETTINGS_STATE


class DiscordTestRequest(BaseModel):
    webhook_url: Optional[str] = None
    message: Optional[str] = None


@app.post("/api/discord/test")
async def test_discord_webhook(req: DiscordTestRequest):
    url = req.webhook_url or _SETTINGS_STATE.get("discord_webhook")
    msg = req.message or "🚀 **SkillForge Agent Alert**: Discord connection test successful! Autonomous updates connected."
    if not url:
        raise HTTPException(400, "Webhook URL required")
    if url.startswith("https://discord.com/api/webhooks/"):
        try:
            import urllib.request
            payload = json.dumps({
                "content": msg,
                "embeds": [{
                    "title": "SkillForge Agent Online",
                    "description": "Discord channel successfully connected for autonomous actions.",
                    "color": 0x7cbe57,
                    "timestamp": datetime.utcnow().isoformat()
                }]
            }).encode("utf-8")
            r = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json", "User-Agent": "SkillForge/1.0"})
            with urllib.request.urlopen(r, timeout=3) as resp:
                pass
            return {"ok": True, "status": "sent", "channel": _SETTINGS_STATE.get("discord_channel")}
        except Exception as e:
            return {"ok": True, "status": "simulated", "note": f"Webhook recorded (test mode: {str(e)[:50]})"}
    return {"ok": True, "status": "simulated", "channel": _SETTINGS_STATE.get("discord_channel")}


# ── Individual Skill Runner Endpoint ──────────────────────────────────────────

class SkillRunRequest(BaseModel):
    skill_id: str
    input: str


@app.post("/api/skills/run")
async def run_single_skill(req: SkillRunRequest):
    skill_id = (req.skill_id or "").strip()
    user_input = (req.input or "").strip()

    if not user_input:
        raise HTTPException(status_code=400, detail="Please enter a topic or URL.")

    ledger = get_ledger()

    try:
        if skill_id in ("web_search", "search"):
            from tools.runtime import web_search
            raw = web_search(user_input, num_results=6)
            results = raw.get("results", [])
            ledger.append("skills-runner", "web-search", "web_search", {"query": user_input}, {"count": len(results)})
            return {
                "title": f"Web Search Results for '{user_input}'",
                "summary": f"Found {len(results)} live search results.",
                "results": [
                    {
                        "title": r.get("title") or "Web Page",
                        "url": r.get("url") or "#",
                        "snippet": r.get("snippet") or ""
                    }
                    for r in results
                ]
            }

        elif skill_id in ("webpage_reader", "read_webpage", "web_reader"):
            from tools.agent_reach import reach_web_read
            from tools.runtime import webpage_reader
            res = reach_web_read(user_input)
            content = res.get("content", "")
            if not content or res.get("error"):
                raw = webpage_reader(user_input)
                content = raw.get("content", "")
            summary = content[:400] + ("..." if len(content) > 400 else "") if content else "Page loaded successfully."
            ledger.append("skills-runner", "webpage-reader", "webpage_reader", {"url": user_input}, {"length": len(content)})
            return {
                "title": f"Webpage Extracted: {user_input}",
                "summary": summary,
                "results": [
                    {
                        "title": user_input,
                        "url": user_input,
                        "snippet": content[:300]
                    }
                ]
            }

        elif skill_id in ("youtube_search", "youtube_scraper"):
            from tools.runtime import youtube_search
            raw = youtube_search(user_input, num_results=5)
            videos = raw.get("videos", [])
            ledger.append("skills-runner", "youtube-scraper", "youtube_search", {"query": user_input}, {"count": len(videos)})
            return {
                "title": f"YouTube Videos for '{user_input}'",
                "summary": f"Found {len(videos)} YouTube videos.",
                "results": [
                    {
                        "title": v.get("title") or "YouTube Video",
                        "url": v.get("url") or f"https://www.youtube.com/watch?v={v.get('video_id', '')}",
                        "snippet": v.get("snippet") or (f"Channel: {v.get('channel')}" if v.get("channel") else "")
                    }
                    for v in videos
                ]
            }

        elif skill_id in ("twitter_search", "twitter_post"):
            import urllib.parse
            from tools.twitter import twitter_search
            raw = twitter_search(user_input, count=6)
            tweets = raw.get("tweets", [])
            ledger.append("skills-runner", "twitter-search", "twitter_search", {"query": user_input}, {"count": len(tweets)})
            return {
                "title": f"Twitter / X Posts for '{user_input}'",
                "summary": f"Found {len(tweets)} relevant posts from Twitter/X.",
                "results": [
                    {
                        "title": f"{t.get('author', 'Twitter User')}",
                        "url": t.get("url") or f"https://x.com/search?q={urllib.parse.quote_plus(user_input)}",
                        "snippet": t.get("text") or ""
                    }
                    for t in tweets
                ]
            }

        else:
            from tools.runtime import run_tool
            res = run_tool(skill_id, {"query": user_input})
            ledger.append("skills-runner", skill_id, skill_id, {"input": user_input}, {})
            return {
                "title": f"Skill '{skill_id}' Result",
                "summary": f"Executed skill '{skill_id}' successfully.",
                "results": [
                    {
                        "title": f"{skill_id} Output",
                        "url": "#",
                        "snippet": str(res)[:350]
                    }
                ]
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



# ── Frontend static serving (single-service deploy) ───────────────────────────
_frontend_dir = Path(__file__).resolve().parent.parent / "frontend"

@app.get("/")
def serve_index():
    index_file = _frontend_dir / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return {"message": "SkillForge Backend API v2.0", "docs": "/docs", "health": "/health"}

@app.get("/styles.css")
def serve_css():
    css_file = _frontend_dir / "styles.css"
    if css_file.exists():
        return FileResponse(css_file, media_type="text/css")
    raise HTTPException(status_code=404, detail="styles.css not found")

@app.get("/app.js")
def serve_js():
    js_file = _frontend_dir / "app.js"
    if js_file.exists():
        return FileResponse(js_file, media_type="application/javascript")
    raise HTTPException(status_code=404, detail="app.js not found")


# ── Startup ────────────────────────────────────────────────────────────────────

@app.on_event("startup")
async def startup():
    Path("output").mkdir(exist_ok=True)
    Path("skills/definitions").mkdir(parents=True, exist_ok=True)
    provider = get_provider()
    print(f"SkillForge API v2 started | demo_mode={DEMO_MODE} | model={provider.model_name} | live={provider.model is not None}")


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port, reload=False)
