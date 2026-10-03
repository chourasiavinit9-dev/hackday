// ── Enums ─────────────────────────────────────────────────
export type RiskLevel = 'low' | 'medium' | 'high';

export type NodeType = 'goal' | 'model' | 'skill' | 'tool' | 'approval' | 'validation' | 'result' | 'error';
export type NodeStatus = 'pending' | 'running' | 'done' | 'error' | 'waiting_approval' | 'skipped';

export type EventType =
  | 'goal_received' | 'skill_discovered' | 'plan_created'
  | 'tool_called' | 'tool_result'
  | 'approval_required' | 'approval_granted' | 'approval_denied'
  | 'skill_installed' | 'validation_passed' | 'workflow_complete' | 'workflow_error'
  | 'complete' | 'error';

export type ConfirmationMode = 'always_ask' | 'ask_risky' | 'auto_safe';

// ── Skill ─────────────────────────────────────────────────
export interface Skill {
  id: string;
  name: string;
  description: string;
  version: string;
  capabilities: string[];
  tools: string[];
  installed: boolean;
  enabled: boolean;
  source: 'built-in' | 'user';
}

// ── Tool ──────────────────────────────────────────────────
export interface Tool {
  name: string;
  description: string;
  risk: RiskLevel;
}

// ── Execution Graph ───────────────────────────────────────
export interface WorkflowNode {
  id: string;
  type: NodeType;
  label: string;
  status: NodeStatus;
  skill?: string;
  tool?: string;
  input?: unknown;
  output?: unknown;
  duration_ms?: number;
  risk?: RiskLevel;
  error?: string;
}

export interface WorkflowEdge {
  from: string;
  to: string;
  label?: string;
}

export interface ExecutionGraph {
  run_id: string;
  nodes: WorkflowNode[];
  edges: WorkflowEdge[];
}

// ── SSE Event (from POST /api/run stream) ─────────────────
export interface StreamEvent {
  type: EventType;
  message: string;
  node_id?: string;
  status?: NodeStatus;
  timestamp: string;
  detail?: string;

  // Only on type === 'approval_required'
  approval?: ApprovalRequest;

  // Only on type === 'complete'
  run_id?: string;
  result?: WorkflowResult;
  graph?: ExecutionGraph;
  ledger_count?: number;
}

// ── Approval ──────────────────────────────────────────────
export interface ApprovalRequest {
  id: string;
  run_id: string;
  tool_name: string;
  action_description: string;
  destination?: string;
  preview?: string;
  risk: RiskLevel;
}

// ── Workflow Result ───────────────────────────────────────
export interface WorkflowResult {
  summary: string;
  report_content?: string;
  filename?: string;
}

// ── Ledger ────────────────────────────────────────────────
export interface LedgerRecord {
  sequence: number;
  timestamp: string;
  run_id: string;
  skill: string | null;
  tool: string;
  input_digest: string;
  result_digest: string;
  previous_hash: string;
  hash: string;
}

export interface LedgerVerification {
  valid: boolean;
  total_records: number;
  first_invalid_sequence?: number;
  message: string;
}

// ── Policy ────────────────────────────────────────────────
export interface AutomationPolicy {
  browser_automation: boolean;
  external_publishing: boolean;
  form_submission: boolean;
  confirmation_mode: ConfirmationMode;
}

// ── Voice ─────────────────────────────────────────────────
export interface TranscriptionResult {
  text: string;
  language: string;
  segments: { start: number; end: number; text: string }[];
  model: string;
  source?: string;
  duration_ms: number;
  error?: string;
}