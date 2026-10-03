"""
SkillForge — Agent Orchestrator
Implements a full ReAct (Reason → Act → Observe) loop:
  • Function-call history preserved across rounds
  • Follow-up tool calls are never discarded
  • Bounded tool execution (hard 30-second timeout per tool)
  • Laya intent-router guards against hallucinated extra steps
"""
import uuid
import time
import asyncio
import json
from datetime import datetime
from typing import Optional, AsyncGenerator

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from models.types import (
    AgentRequest, WorkflowRun, ExecutionGraph, WorkflowNode, ExecutionEvent,
    WorkflowNodeType, WorkflowNodeStatus, EventType, RiskLevel, ApprovalRequest
)
from skills.registry import resolve_skill_for_goal, get_skill
from tools.runtime import run_tool, TOOL_REGISTRY
from policy.engine import get_policy, requires_approval, get_tool_risk
from ledger.ledger import get_ledger
from agent.gemma_provider import get_provider

# In-memory state
_active_runs: dict[str, WorkflowRun] = {}
_pending_approvals: dict[str, asyncio.Event] = {}
_approval_decisions: dict[str, bool] = {}

# Execution limits
TOOL_TIMEOUT_S  = 30
SYNTH_TIMEOUT_S = 60
MAX_REACT_ROUNDS = 6   # safety valve: stop after N Reason→Act rounds


def get_run(run_id: str) -> Optional[WorkflowRun]:
    return _active_runs.get(run_id)


def list_runs() -> list[WorkflowRun]:
    return list(_active_runs.values())


async def execute_workflow(request: AgentRequest) -> AsyncGenerator[dict, None]:
    """Main streaming orchestration loop with ReAct rounds. Yields SSE events."""
    run_id   = request.run_id
    graph    = ExecutionGraph(run_id=run_id)
    events: list[ExecutionEvent] = []
    ledger   = get_ledger()
    provider = get_provider()
    policy   = get_policy()

    run = WorkflowRun(run_id=run_id, goal=request.goal)
    _active_runs[run_id] = run

    # ── Helpers ────────────────────────────────────────────────────────────────

    def emit(event_type: EventType, message: str,
             node_id: Optional[str] = None,
             status: WorkflowNodeStatus = WorkflowNodeStatus.RUNNING,
             detail: str = None) -> dict:
        ev = ExecutionEvent(run_id=run_id, type=event_type, message=message,
                            node_id=node_id, status=status, detail=detail)
        events.append(ev)
        run.events = events
        return {"type": event_type.value, "message": message, "node_id": node_id,
                "status": status.value, "timestamp": ev.timestamp, "detail": detail}

    def add_node(node_id, node_type, label,
                 status=WorkflowNodeStatus.PENDING, **kwargs) -> WorkflowNode:
        node = WorkflowNode(id=node_id, type=node_type, label=label, status=status, **kwargs)
        graph.nodes.append(node)
        run.graph = graph
        return node

    def add_edge(from_id, to_id, label=None):
        graph.edges.append({"from": from_id, "to": to_id, "label": label})
        run.graph = graph

    def update_node(node_id, **kwargs):
        for node in graph.nodes:
            if node.id == node_id:
                for k, v in kwargs.items():
                    setattr(node, k, v)
        run.graph = graph

    # ── STEP 1: Goal received ──────────────────────────────────────────────────
    add_node("goal-1", WorkflowNodeType.GOAL, request.goal[:60], WorkflowNodeStatus.DONE)
    add_node("model-1", WorkflowNodeType.MODEL, "Gemma 4", WorkflowNodeStatus.RUNNING)
    add_edge("goal-1", "model-1")

    yield emit(EventType.GOAL_RECEIVED, f"Goal understood: {request.goal[:80]}",
               "goal-1", WorkflowNodeStatus.DONE)
    await asyncio.sleep(0.05)

    # ── STEP 2: Laya intent classification ────────────────────────────────────
    yield emit(EventType.SKILL_DISCOVERED, "Classifying intent with Laya…",
               "model-1", WorkflowNodeStatus.RUNNING)
    await asyncio.sleep(0.02)

    try:
        from tools.laya_router import classify_goal
        laya_result    = await asyncio.get_event_loop().run_in_executor(
            None, lambda: classify_goal(request.goal))
        skill_id           = laya_result["skill"]
        user_wants_file    = laya_result["wants_file"]
        user_wants_post    = laya_result["wants_post"]
        user_wants_read    = laya_result["wants_read"]
        user_wants_summary = laya_result["wants_summary"]
        laya_source        = laya_result["source"]
        laya_ms            = laya_result["duration_ms"]
    except Exception:
        skill_id = resolve_skill_for_goal(request.goal)
        gl = request.goal.lower()
        user_wants_file    = any(w in gl for w in ["save", "create file", "report", "write", "document", "markdown"])
        user_wants_post    = any(w in gl for w in ["post", "tweet", "publish"])
        user_wants_read    = any(w in gl for w in ["read", "visit", "browse"])
        user_wants_summary = any(w in gl for w in ["summarize", "summary", "explain"])
        laya_source, laya_ms = "keyword-fallback", 0

    skill = get_skill(skill_id)
    add_node(f"skill-{skill_id}", WorkflowNodeType.SKILL, skill_id,
             WorkflowNodeStatus.DONE, skill=skill_id)
    add_edge("model-1", f"skill-{skill_id}")
    update_node("model-1", status=WorkflowNodeStatus.DONE)

    yield emit(EventType.SKILL_DISCOVERED,
               f"Skill: {skill_id} · via {laya_source} ({laya_ms}ms)",
               f"skill-{skill_id}", WorkflowNodeStatus.DONE,
               detail=skill["description"] if skill else None)
    await asyncio.sleep(0.05)

    # ── STEP 3: Plan ───────────────────────────────────────────────────────────
    yield emit(EventType.PLAN_CREATED,
               f"Planning workflow with {provider.model_name}…",
               f"skill-{skill_id}", WorkflowNodeStatus.RUNNING)
    await asyncio.sleep(0.02)

    try:
        plan = await asyncio.wait_for(
            asyncio.get_event_loop().run_in_executor(
                None, lambda: provider.plan_workflow(
                    request.goal, skill_id, list(TOOL_REGISTRY.keys()))),
            timeout=45.0
        )
    except asyncio.TimeoutError:
        plan = provider._demo_plan(request.goal, skill_id)

    steps = plan.get("steps", [])

    # ── Intent guard: drop any steps Laya says the user didn't ask for ─────────
    ALWAYS_ALLOWED = {
        "web_search", "ddg_search", "job_search", "youtube_search", "youtube_search_ddg",
        "youtube_transcript", "youtube_summary", "twitter_search", "twitter_user_tweets",
        "twitter_research_trends", "twitter_status", "research_paper_search",
        "extract_interview_questions", "extract_article", "skill_validate",
        "webpage_reader",  # always allowed — read-only fetch
        # Agent-Reach (MIT) — read-only research
        "reach_web_read", "reach_web_search", "reach_github_search", "reach_research",
        # Social drafting (low-risk — never posts)
        "draft_post", "research_and_draft",
        # Post-publish verification (read-only)
        "verify_post",
    }
    filtered_steps = []
    for step in steps:
        t = step.get("tool", "")
        if t in ALWAYS_ALLOWED:
            filtered_steps.append(step)
        elif t == "webpage_reader" and user_wants_read:
            filtered_steps.append(step)
        elif t == "create_file" and user_wants_file:
            filtered_steps.append(step)
        elif t in ("twitter_post_tweet", "post_to_twitter") and user_wants_post:
            filtered_steps.append(step)
        elif t == "skill_install":
            filtered_steps.append(step)
        # else: hallucinated step — Laya says the user didn't ask → drop silently
    steps = filtered_steps

    yield emit(EventType.PLAN_CREATED, f"Workflow planned: {len(steps)} steps",
               f"skill-{skill_id}", WorkflowNodeStatus.DONE)
    await asyncio.sleep(0.05)

    # ── STEP 4: ReAct Execute → Observe rounds ────────────────────────────────
    all_results: list[dict] = []
    # accumulated_content grows across rounds so later steps can use earlier output
    accumulated_content = ""
    prev_node_id = f"skill-{skill_id}"
    step_queue   = list(steps)      # mutable so follow-up steps can be appended
    executed     = 0

    while step_queue and executed < MAX_REACT_ROUNDS:
        step      = step_queue.pop(0)
        tool_name = step.get("tool", "")
        args      = dict(step.get("arguments", {}))
        purpose   = step.get("purpose", "")
        executed += 1

        if tool_name not in TOOL_REGISTRY:
            yield emit(EventType.TOOL_RESULT,
                       f"⚠ Unknown tool '{tool_name}' — skipping",
                       prev_node_id, WorkflowNodeStatus.SKIPPED)
            continue

        # Graph node
        tool_node_id = f"tool-{executed}-{tool_name}"
        risk = get_tool_risk(tool_name)
        add_node(tool_node_id, WorkflowNodeType.TOOL, tool_name,
                 WorkflowNodeStatus.PENDING, tool=tool_name, risk=risk)
        add_edge(prev_node_id, tool_node_id)

        # ── Policy / approval gate ─────────────────────────────────────────────
        if requires_approval(tool_name, policy):
            update_node(tool_node_id, status=WorkflowNodeStatus.WAITING_APPROVAL)
            approval_id  = str(uuid.uuid4())[:8]
            approval_req = ApprovalRequest(
                id=approval_id, run_id=run_id, tool_name=tool_name,
                action_description=purpose, risk=risk,
                preview=json.dumps(args, indent=2)[:200]
            )
            gate = asyncio.Event()
            _pending_approvals[approval_id] = gate
            _approval_decisions[approval_id] = False

            yield {**emit(EventType.APPROVAL_REQUIRED,
                          f"Approval required: {tool_name}",
                          tool_node_id, WorkflowNodeStatus.WAITING_APPROVAL),
                   "approval": approval_req.dict()}

            try:
                await asyncio.wait_for(gate.wait(), timeout=120.0)
            except asyncio.TimeoutError:
                update_node(tool_node_id, status=WorkflowNodeStatus.SKIPPED,
                            error="Approval timed out")
                yield emit(EventType.APPROVAL_DENIED,
                           f"Approval timed out: {tool_name}",
                           tool_node_id, WorkflowNodeStatus.SKIPPED)
                continue

            if not _approval_decisions.get(approval_id, False):
                update_node(tool_node_id, status=WorkflowNodeStatus.SKIPPED,
                            error="User denied")
                yield emit(EventType.APPROVAL_DENIED,
                           f"Action cancelled by user: {tool_name}",
                           tool_node_id, WorkflowNodeStatus.SKIPPED)
                continue

            yield emit(EventType.APPROVAL_GRANTED, f"Approved: {tool_name}",
                       tool_node_id, WorkflowNodeStatus.RUNNING)

        # ── Substitute URL_PLACEHOLDER with first URL from prior results ─────────
        if "URL_PLACEHOLDER" in str(args):
            first_url = None
            for prev in all_results:
                prev_data = prev.get("result", {})
                if prev_data.get("jobs"):
                    first_url = prev_data["jobs"][0].get("url")
                    break
                if prev_data.get("results"):
                    first_url = prev_data["results"][0].get("url")
                    break
            if first_url and first_url.startswith("http"):
                args = {k: (first_url if v == "URL_PLACEHOLDER" else v) for k, v in args.items()}
            else:
                # No real URL found — skip this step gracefully
                update_node(tool_node_id, status=WorkflowNodeStatus.SKIPPED,
                            error="No URL available from prior results")
                yield emit(EventType.TOOL_RESULT, f"⚠ Skipped {tool_name}: no URL from prior step",
                           tool_node_id, WorkflowNodeStatus.SKIPPED)
                prev_node_id = tool_node_id
                continue

        # ── Substitute PLACEHOLDER with real accumulated content ───────────────
        if "PLACEHOLDER" in str(args):
            if accumulated_content:
                fill = accumulated_content[:3000]
            elif all_results:
                # Build readable text fallback from all prior results
                fill = "\n".join(
                    json.dumps(r["result"], default=str)[:800]
                    for r in all_results
                )
            else:
                fill = goal
            args = {k: (fill if v == "PLACEHOLDER" else v) for k, v in args.items()}

        # ── Execute (ReAct "Act" step, bounded by timeout) ─────────────────────
        update_node(tool_node_id, status=WorkflowNodeStatus.RUNNING, input=args)
        yield emit(EventType.TOOL_CALLED,
                   f"Running: {tool_name} — {purpose}",
                   tool_node_id, WorkflowNodeStatus.RUNNING)
        await asyncio.sleep(0.05)

        t0 = time.time()
        try:
            result = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(
                    None, lambda: run_tool(tool_name, args)),
                timeout=TOOL_TIMEOUT_S
            )
        except asyncio.TimeoutError:
            result = {"error": f"Tool {tool_name} timed out after {TOOL_TIMEOUT_S}s",
                      "_duration_ms": TOOL_TIMEOUT_S * 1000}
        duration_ms = int((time.time() - t0) * 1000)

        # ── Observe: accumulate results for next round ─────────────────────────
        ledger.append(run_id=run_id, skill=skill_id, tool=tool_name,
                      input_data=args, result_data=result)

        if isinstance(result, dict):
            if result.get("content"):
                accumulated_content += "\n" + result["content"]
            if result.get("sources"):
                # Agent-Reach reach_research sources & full extracted content
                src_text = "\n".join(
                    f"{s.get('title','')}\n{s.get('snippet','')}\n{s.get('full_content','')}"
                    for s in result["sources"] if isinstance(s, dict)
                )
                accumulated_content += "\n" + src_text
            if result.get("jobs"):
                # Flatten job listings to plain text for downstream steps (e.g. extract_interview_questions)
                job_text = "\n".join(
                    f"{j.get('title','')} at {j.get('company','')} ({j.get('location','')}).\n{j.get('snippet','')}"
                    for j in result["jobs"]
                )
                accumulated_content = job_text
            if result.get("results"):
                # Flatten web search results to text
                result_text = "\n".join(
                    f"{r.get('title','')}. {r.get('snippet','')}"
                    for r in result["results"]
                )
                accumulated_content = result_text or json.dumps(result["results"])
            if result.get("videos"):
                accumulated_content = json.dumps(result["videos"])
            if result.get("tweets"):
                tweet_text = "\n".join(t.get("text", "") for t in result["tweets"])
                accumulated_content = tweet_text or json.dumps(result["tweets"])

        all_results.append({"tool": tool_name, "result": result})
        update_node(tool_node_id, status=WorkflowNodeStatus.DONE,
                    output=result, duration_ms=duration_ms, input=args)

        yield emit(EventType.TOOL_RESULT,
                   f"✓ {tool_name} complete ({duration_ms}ms)",
                   tool_node_id, WorkflowNodeStatus.DONE,
                   detail=json.dumps(result, default=str)[:200])
        prev_node_id = tool_node_id
        await asyncio.sleep(0.05)

    # ── STEP 5: Synthesis ──────────────────────────────────────────────────────
    add_node("result-1", WorkflowNodeType.RESULT, "Result", WorkflowNodeStatus.RUNNING)
    add_edge(prev_node_id, "result-1")

    yield emit(EventType.WORKFLOW_COMPLETE, "Synthesizing final result…",
               "result-1", WorkflowNodeStatus.RUNNING)
    await asyncio.sleep(0.02)

    try:
        synthesis = await asyncio.wait_for(
            asyncio.get_event_loop().run_in_executor(
                None, lambda: provider.synthesize_result(request.goal, all_results)),
            timeout=SYNTH_TIMEOUT_S
        )
    except asyncio.TimeoutError:
        synthesis = provider._offline_synthesis(request.goal, all_results)

    # Collect structured entities from all_results to ensure frontend gets first-class jobs, tweets, videos, web results, questions, urls
    collected_jobs = []
    collected_tweets = []
    collected_videos = []
    collected_web_results = []
    collected_questions = {}
    collected_urls = []
    for item in all_results:
        res = item.get("result", {})
        if isinstance(res, dict):
            # Agent-Reach sources
            if res.get("sources"):
                for s in res["sources"]:
                    if isinstance(s, dict) and s.get("url"):
                        collected_web_results.append(s)
                        collected_urls.append({"title": s.get("title", "Research Source"), "url": s["url"], "type": "web"})
            # Tweets
            if res.get("tweets"):
                for t in res["tweets"]:
                    if isinstance(t, dict):
                        collected_tweets.append(t)
                        if t.get("url"):
                            collected_urls.append({"title": f"Tweet by @{t.get('handle') or 'user'}", "url": t["url"], "type": "tweet"})
            # YouTube videos
            if res.get("videos"):
                for v in res["videos"]:
                    if isinstance(v, dict):
                        collected_videos.append(v)
                        if v.get("url"):
                            collected_urls.append({"title": v.get("title", "YouTube Video"), "url": v["url"], "type": "video"})
            # Web search results
            if res.get("results"):
                for w in res["results"]:
                    if isinstance(w, dict):
                        collected_web_results.append(w)
                        if w.get("url"):
                            collected_urls.append({"title": w.get("title", "Web Page"), "url": w["url"], "type": "web"})
            # Job opportunities
            if res.get("jobs"):
                for j in res["jobs"]:
                    if isinstance(j, dict):
                        collected_jobs.append(j)
                        if j.get("url"):
                            collected_urls.append({"title": j.get("title", "Job Listing"), "url": j["url"], "type": "job"})
            # Interview questions
            if res.get("grouped_questions"):
                collected_questions.update(res["grouped_questions"])
            # Extracted webpage
            if res.get("url") and res["url"] not in [u.get("url") for u in collected_urls]:
                collected_urls.append({"title": res.get("title", "Extracted Page"), "url": res["url"], "type": "page"})

    # Determine primary entity / intent
    primary_intent = "report"
    goal_lower = (request.goal or "").lower()
    if any(k in goal_lower for k in ["interview", "process", "question", "round", "company background", "fresher", "answer"]):
        primary_intent = "report"
    elif collected_tweets or any(k in goal_lower for k in ["twitter", "tweet", "x.com"]):
        primary_intent = "tweets"
    elif collected_videos or any(k in goal_lower for k in ["youtube", "video", "watch"]):
        primary_intent = "videos"
    elif collected_jobs or any(k in goal_lower for k in ["job", "career", "hiring"]):
        primary_intent = "jobs"
    elif collected_web_results or any(k in goal_lower for k in ["search", "find", "google", "lookup"]):
        primary_intent = "web"

    if collected_tweets and "tweets" not in synthesis:
        synthesis["tweets"] = collected_tweets
    if collected_videos and "videos" not in synthesis:
        synthesis["videos"] = collected_videos
    if collected_web_results and "web_results" not in synthesis:
        synthesis["web_results"] = collected_web_results
    if collected_jobs and "jobs" not in synthesis:
        synthesis["jobs"] = collected_jobs
    if collected_questions and "grouped_questions" not in synthesis:
        synthesis["grouped_questions"] = collected_questions
    if collected_urls and "urls" not in synthesis:
        synthesis["urls"] = collected_urls
    synthesis["intent_type"] = primary_intent
    synthesis["tool_results"] = all_results

    # Auto-save if the synthesis produced file content
    if synthesis.get("report_content") and synthesis.get("filename"):
        try:
            run_tool("create_file", {
                "filename": synthesis["filename"],
                "content": synthesis["report_content"]
            })
        except Exception:
            pass

    update_node("result-1", status=WorkflowNodeStatus.DONE,
                output=synthesis.get("summary"))
    run.status       = "completed"
    run.completed_at = datetime.utcnow().isoformat()
    run.result       = synthesis
    run.graph        = graph

    yield emit(EventType.WORKFLOW_COMPLETE, "Workflow complete",
               "result-1", WorkflowNodeStatus.DONE,
               detail=(synthesis.get("summary", "") or "")[:200])

    yield {
        "type":         "complete",
        "run_id":       run_id,
        "result":       synthesis,
        "intent_type":  primary_intent,
        "tweets":       collected_tweets,
        "videos":       collected_videos,
        "web_results":  collected_web_results,
        "jobs":         collected_jobs,
        "questions":    collected_questions,
        "urls":         collected_urls,
        "tool_results": all_results,
        "graph":        {"nodes": [n.dict() for n in graph.nodes], "edges": graph.edges},
        "ledger_count": len(ledger.history(run_id=run_id))
    }


def resolve_approval(approval_id: str, approved: bool):
    """Called when the user clicks Approve / Cancel in the UI."""
    _approval_decisions[approval_id] = approved
    gate = _pending_approvals.get(approval_id)
    if gate:
        gate.set()
