"""
SkillForge — Shared Type Definitions
Single source of truth for all data contracts between frontend and backend.
"""

from __future__ import annotations
from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field
import uuid
from datetime import datetime


# ── Enums ─────────────────────────────────────────────────────────────────────

class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class WorkflowNodeType(str, Enum):
    GOAL = "goal"
    MODEL = "model"
    SKILL = "skill"
    TOOL = "tool"
    APPROVAL = "approval"
    VALIDATION = "validation"
    RESULT = "result"
    ERROR = "error"


class WorkflowNodeStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    ERROR = "error"
    WAITING_APPROVAL = "waiting_approval"
    SKIPPED = "skipped"


class EventType(str, Enum):
    GOAL_RECEIVED = "goal_received"
    SKILL_DISCOVERED = "skill_discovered"
    PLAN_CREATED = "plan_created"
    TOOL_CALLED = "tool_called"
    TOOL_RESULT = "tool_result"
    APPROVAL_REQUIRED = "approval_required"
    APPROVAL_GRANTED = "approval_granted"
    APPROVAL_DENIED = "approval_denied"
    SKILL_INSTALLED = "skill_installed"
    VALIDATION_PASSED = "validation_passed"
    VALIDATION_FAILED = "validation_failed"
    WORKFLOW_COMPLETE = "workflow_complete"
    WORKFLOW_ERROR = "workflow_error"


class ConfirmationMode(str, Enum):
    ALWAYS_ASK = "always_ask"
    ASK_RISKY = "ask_risky"
    AUTO_SAFE = "auto_safe"


# ── Skill Types ───────────────────────────────────────────────────────────────

class Skill(BaseModel):
    id: str
    name: str
    description: str
    version: str = "1.0.0"
    capabilities: list[str] = []
    tools: list[str] = []
    installed: bool = True
    enabled: bool = True
    source: str = "built-in"


class SkillDefinition(BaseModel):
    """Raw parsed SKILL.md content."""
    name: str
    description: str
    version: str
    capabilities: list[str]
    tools: list[str]
    execution_timeout: int = 60


# ── Tool Types ────────────────────────────────────────────────────────────────

class ToolSchema(BaseModel):
    type: str = "object"
    properties: dict[str, Any]
    required: list[str] = []


class Tool(BaseModel):
    name: str
    description: str
    schema: ToolSchema
    risk_level: RiskLevel = RiskLevel.LOW
    requires_confirmation: bool = False


class ToolCall(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    tool_name: str
    arguments: dict[str, Any]
    skill_id: Optional[str] = None


class ToolResult(BaseModel):
    tool_call_id: str
    tool_name: str
    success: bool
    data: Any
    error: Optional[str] = None
    duration_ms: int = 0


# ── Workflow Types ────────────────────────────────────────────────────────────

class WorkflowNode(BaseModel):
    id: str
    type: WorkflowNodeType
    label: str
    status: WorkflowNodeStatus = WorkflowNodeStatus.PENDING
    skill: Optional[str] = None
    tool: Optional[str] = None
    input: Optional[Any] = None
    output: Optional[Any] = None
    duration_ms: Optional[int] = None
    risk: Optional[RiskLevel] = None
    error: Optional[str] = None


class WorkflowEdge(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    from_node: str = Field(alias="from")
    to_node: str = Field(alias="to")
    label: Optional[str] = None

    class Config:
        populate_by_name = True


class ExecutionGraph(BaseModel):
    run_id: str
    nodes: list[WorkflowNode] = []
    edges: list[dict] = []


# ── Event / Timeline Types ────────────────────────────────────────────────────

class ExecutionEvent(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    run_id: str
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    type: EventType
    message: str
    detail: Optional[str] = None
    node_id: Optional[str] = None
    status: WorkflowNodeStatus = WorkflowNodeStatus.RUNNING


# ── Agent Types ───────────────────────────────────────────────────────────────

class AgentRequest(BaseModel):
    run_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    goal: str
    demo_mode: bool = False


class AgentPlan(BaseModel):
    run_id: str
    goal: str
    selected_skill: Optional[str]
    tool_sequence: list[str]
    estimated_risk: RiskLevel
    requires_approval: bool


class WorkflowRun(BaseModel):
    run_id: str
    goal: str
    status: str = "running"
    started_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    completed_at: Optional[str] = None
    result: Optional[Any] = None
    error: Optional[str] = None
    graph: Optional[ExecutionGraph] = None
    events: list[ExecutionEvent] = []


# ── Approval Types ────────────────────────────────────────────────────────────

class ApprovalRequest(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    run_id: str
    tool_name: str
    action_description: str
    destination: Optional[str] = None
    preview: Optional[str] = None
    risk: RiskLevel = RiskLevel.HIGH


class ApprovalResponse(BaseModel):
    approval_id: str
    approved: bool


# ── Policy Types ─────────────────────────────────────────────────────────────

class AutomationPolicy(BaseModel):
    browser_automation: bool = True
    external_publishing: bool = False
    form_submission: bool = False
    confirmation_mode: ConfirmationMode = ConfirmationMode.ASK_RISKY


# ── Ledger Types ──────────────────────────────────────────────────────────────

class ActionRecord(BaseModel):
    sequence: int
    timestamp: str
    run_id: str
    skill: Optional[str]
    tool: str
    input_digest: str
    result_digest: str
    previous_hash: str
    hash: str


class LedgerVerification(BaseModel):
    valid: bool
    total_records: int
    first_invalid_sequence: Optional[int] = None
    message: str


# ── Evaluation Types ──────────────────────────────────────────────────────────

class EvaluationResult(BaseModel):
    run_id: str
    skill_selection_correct: Optional[bool] = None
    tool_selection_correct: Optional[bool] = None
    workflow_completed: bool = False
    recovery_attempted: bool = False
    notes: str = ""
