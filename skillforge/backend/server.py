"""
SkillForge — Tornado Backend Server
Hardened with: rate limiting, payload guards, input validation,
prompt injection defense, LRU caching, typed error responses.
"""
import os
import sys
import json
import asyncio
import traceback
from pathlib import Path
from datetime import datetime

import tornado.web
import tornado.ioloop
import tornado.httpserver

sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
load_dotenv()

from models.types import (
    AgentRequest, ApprovalResponse, AutomationPolicy
)
from skills.registry import list_skills, get_skill, install_skill
from tools.runtime import run_tool, TOOL_REGISTRY, skill_validate, skill_install
from policy.engine import get_policy, update_policy
from ledger.ledger import get_ledger
from agent.orchestrator import execute_workflow, resolve_approval, get_run, list_runs
from agent.gemma_provider import get_provider
from security import (
    rate_limiter, validate_goal, validate_tool_arguments,
    check_payload_size, cached_tool_call,
    RateLimitError, SecurityViolationError, ValidationError, PayloadTooLargeError
)

DEMO_MODE = os.environ.get("SKILLFORGE_DEMO", "false").lower() == "true"


def cors_headers(handler):
    handler.set_header("Access-Control-Allow-Origin", "*")
    handler.set_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
    handler.set_header("Access-Control-Allow-Headers", "Content-Type, Authorization")


class BaseHandler(tornado.web.RequestHandler):
    def set_default_headers(self):
        cors_headers(self)

    def options(self, *args, **kwargs):
        self.set_status(204)
        self.finish()

    def json(self, data, status=200):
        self.set_status(status)
        self.set_header("Content-Type", "application/json")
        self.write(json.dumps(data, default=str))

    def body(self):
        check_payload_size(self.request.body)
        return json.loads(self.request.body)

    def check_rate_limit(self):
        client_ip = self.request.remote_ip or "default"
        try:
            rate_limiter.check(client_ip)
        except RateLimitError as e:
            self.set_header("Retry-After", str(int(e.retry_after)))
            self.json({"error": "Rate limit exceeded", "retry_after": e.retry_after}, 429)
            return False
        return True

    def security_error(self, exc: Exception, status: int = 400):
        if isinstance(exc, SecurityViolationError):
            self.json({"error": "Security violation", "reason": exc.reason}, 400)
        elif isinstance(exc, ValidationError):
            self.json({"error": "Validation error", "field": exc.field, "reason": str(exc)}, 422)
        elif isinstance(exc, PayloadTooLargeError):
            self.json({"error": "Payload too large", "limit": "100 KB"}, 413)
        elif isinstance(exc, RateLimitError):
            self.json({"error": "Rate limit exceeded", "retry_after": exc.retry_after}, 429)
        else:
            self.json({"error": str(exc)}, status)


# ── Health ────────────────────────────────────────────────────────────────────

class HealthHandler(BaseHandler):
    def get(self):
        self.json({
            "status": "ok",
            "demo_mode": DEMO_MODE,
            "model": get_provider().model_name,
            "timestamp": datetime.utcnow().isoformat()
        })


# ── Agent Run (SSE streaming) ─────────────────────────────────────────────────

class RunHandler(BaseHandler):
    async def post(self):
        # Rate limit check
        if not self.check_rate_limit():
            return

        try:
            data = self.body()
            # Validate + sanitize the user goal
            raw_goal = data.get("goal", "")
            safe_goal = validate_goal(raw_goal)
            data["goal"] = safe_goal
            request = AgentRequest(**data)
        except (SecurityViolationError, ValidationError, PayloadTooLargeError) as e:
            self.security_error(e)
            return
        except Exception as e:
            self.json({"error": f"Bad request: {e}"}, 400)
            return

        if DEMO_MODE:
            request.demo_mode = True

        self.set_header("Content-Type", "text/event-stream")
        self.set_header("Cache-Control", "no-cache")
        self.set_header("X-Accel-Buffering", "no")
        cors_headers(self)

        try:
            async for event in execute_workflow(request):
                line = f"data: {json.dumps(event, default=str)}\n\n"
                self.write(line)
                await self.flush()
        except Exception as e:
            err = json.dumps({"type": "error", "message": str(e)})
            self.write(f"data: {err}\n\n")
            await self.flush()
        finally:
            self.finish()


class RunStatusHandler(BaseHandler):
    def get(self, run_id):
        run = get_run(run_id)
        if not run:
            self.json({"error": "Run not found"}, 404)
            return
        self.json(run.dict())


class RunsHandler(BaseHandler):
    def get(self):
        self.json([r.dict() for r in list_runs()])


# ── Approval ─────────────────────────────────────────────────────────────────

class ApproveHandler(BaseHandler):
    def post(self):
        data = self.body()
        resolve_approval(data["approval_id"], data["approved"])
        self.json({"ok": True, "approved": data["approved"]})


# ── Skills ────────────────────────────────────────────────────────────────────

class SkillsHandler(BaseHandler):
    def get(self):
        self.json(list_skills())


class SkillDetailHandler(BaseHandler):
    def get(self, skill_id):
        skill = get_skill(skill_id)
        if not skill:
            self.json({"error": f"Skill '{skill_id}' not found"}, 404)
            return
        self.json(skill)


class SkillBuildHandler(BaseHandler):
    async def post(self):
        data = self.body()
        description = data.get("description", "")
        provider = get_provider()
        result = provider.generate_skill_md(description)
        self.json(result)


class SkillInstallHandler(BaseHandler):
    async def post(self):
        data = self.body()
        name = data.get("name", "")
        skill_md_content = data.get("skill_md", "")

        validation = skill_validate(skill_md_content)
        if not validation["valid"]:
            self.json({"errors": validation["errors"]}, 400)
            return

        result = skill_install(name, skill_md_content)

        skill_data = {
            "name": name,
            "description": data.get("description", validation.get("description", "")),
            "version": "1.0.0",
            "capabilities": data.get("capabilities", []),
            "tools": data.get("tools", []),
            "source": "user"
        }
        install_skill(name, skill_data)
        self.json({"installed": True, "name": name, "path": result["path"]})


class SkillValidateHandler(BaseHandler):
    def post(self):
        data = self.body()
        result = skill_validate(data.get("skill_md", ""))
        self.json(result)


# ── Tools ─────────────────────────────────────────────────────────────────────

class ToolsHandler(BaseHandler):
    def get(self):
        self.json([
            {"name": name, "description": info["description"], "risk": info["risk"]}
            for name, info in TOOL_REGISTRY.items()
        ])


class ToolRunHandler(BaseHandler):
    def post(self):
        if not self.check_rate_limit():
            return
        try:
            data = self.body()
            tool_name = data.get("tool_name", "")
            arguments = data.get("arguments", {})

            if tool_name not in TOOL_REGISTRY:
                self.json({"error": f"Unknown tool: {tool_name}"}, 400)
                return

            # Sanitize arguments
            safe_args = validate_tool_arguments(tool_name, arguments)

            # Use LRU cache for read-only tools
            result = cached_tool_call(
                tool_name, safe_args,
                fn=lambda: run_tool(tool_name, safe_args)
            )
            self.json(result)
        except (SecurityViolationError, ValidationError, PayloadTooLargeError) as e:
            self.security_error(e)
        except Exception as e:
            self.json({"error": str(e)}, 500)


# ── Voice / Whisper ───────────────────────────────────────────────────────────

class WhisperInfoHandler(BaseHandler):
    def get(self):
        from tools.voice import get_whisper_info
        self.json(get_whisper_info())


class VoiceTranscribeHandler(BaseHandler):
    async def post(self):
        """
        Transcribe uploaded audio or record from mic.
        - POST with Content-Type: audio/wav (or mp3, webm, etc.) + raw bytes → transcribe file
        - POST with JSON { "duration_seconds": 5, "demo": true } → record from mic / demo
        - POST with JSON { "audio_path": "/path/to/file.wav" } → transcribe file path
        """
        content_type = self.request.headers.get("Content-Type", "")
        demo = self.get_argument("demo", str(DEMO_MODE)).lower() == "true"

        # Raw audio bytes upload
        if any(content_type.startswith(p) for p in ("audio/", "video/")):
            ext_map = {
                "audio/wav": ".wav", "audio/x-wav": ".wav",
                "audio/mpeg": ".mp3", "audio/mp3": ".mp3",
                "audio/ogg": ".ogg", "audio/webm": ".webm",
                "video/webm": ".webm", "audio/m4a": ".m4a",
                "audio/flac": ".flac",
            }
            suffix = ext_map.get(content_type.split(";")[0].strip(), ".wav")
            language = self.get_argument("language", "")

            if demo or DEMO_MODE:
                from tools.voice import demo_transcribe
                self.json(demo_transcribe())
                return

            from tools.voice import transcribe_audio_bytes
            result = transcribe_audio_bytes(
                self.request.body, suffix=suffix, language=language or None
            )
            self.json(result)
            return

        # JSON body
        try:
            data = self.body()
        except Exception:
            data = {}

        duration = int(data.get("duration_seconds", 5))
        language = data.get("language", "")
        audio_path = data.get("audio_path", "")
        demo = data.get("demo", demo)

        from tools.runtime import transcribe_voice
        result = transcribe_voice(
            audio_path=audio_path,
            duration_seconds=duration,
            language=language,
            demo=bool(demo)
        )
        self.json(result)


# ── Policy ────────────────────────────────────────────────────────────────────

class PolicyHandler(BaseHandler):
    def get(self):
        self.json(get_policy().dict())

    def put(self):
        data = self.body()
        policy = AutomationPolicy(**data)
        update_policy(policy)
        self.json(policy.dict())


# ── Ledger ────────────────────────────────────────────────────────────────────

class LedgerHandler(BaseHandler):
    def get(self):
        run_id = self.get_argument("run_id", None)
        limit = int(self.get_argument("limit", "50"))
        self.json(get_ledger().history(run_id=run_id, limit=limit))


class LedgerVerifyHandler(BaseHandler):
    def get(self):
        self.json(get_ledger().verify())


# ── Router ────────────────────────────────────────────────────────────────────

def make_app():
    return tornado.web.Application([
        (r"/health", HealthHandler),
        (r"/api/run", RunHandler),
        (r"/api/run/([^/]+)", RunStatusHandler),
        (r"/api/runs", RunsHandler),
        (r"/api/approve", ApproveHandler),
        (r"/api/skills", SkillsHandler),
        (r"/api/skills/build", SkillBuildHandler),
        (r"/api/skills/install", SkillInstallHandler),
        (r"/api/skills/validate", SkillValidateHandler),
        (r"/api/skills/([^/]+)", SkillDetailHandler),
        (r"/api/tools", ToolsHandler),
        (r"/api/tools/run", ToolRunHandler),
        (r"/api/policy", PolicyHandler),
        (r"/api/voice", VoiceTranscribeHandler),
        (r"/api/voice/info", WhisperInfoHandler),
        (r"/api/ledger/verify", LedgerVerifyHandler),
        (r"/api/ledger", LedgerHandler),
    ], debug=True)


if __name__ == "__main__":
    Path("output").mkdir(exist_ok=True)
    Path("skills/definitions").mkdir(parents=True, exist_ok=True)
    port = int(os.environ.get("PORT", 8000))
    app = make_app()
    server = tornado.httpserver.HTTPServer(app)
    server.listen(port)
    print(f"SkillForge API → http://localhost:{port}")
    print(f"Demo mode: {DEMO_MODE} | Model: {get_provider().model_name}")
    tornado.ioloop.IOLoop.current().start()
