"""
SkillForge — Policy Engine
Classifies tool risk and enforces approval policies.
"""
from models.types import RiskLevel, AutomationPolicy, ConfirmationMode

# Tools that publish externally — ALWAYS require human approval regardless of policy.
PUBLISHING_TOOLS = {
    "post_to_twitter",
    "twitter_post_tweet",
    "post_to_linkedin",
    "send_email",
    "submit_form",
}

# Risk map per tool
TOOL_RISK_MAP: dict[str, RiskLevel] = {
    # Read-only / low risk
    "web_search": RiskLevel.LOW,
    "ddg_search": RiskLevel.LOW,
    "youtube_search": RiskLevel.LOW,
    "youtube_search_ddg": RiskLevel.LOW,
    "youtube_transcript": RiskLevel.LOW,
    "youtube_summary": RiskLevel.LOW,
    "webpage_reader": RiskLevel.LOW,
    "webpage_open": RiskLevel.LOW,
    "extract_article": RiskLevel.LOW,
    "job_search": RiskLevel.LOW,
    "research_paper_search": RiskLevel.LOW,
    "twitter_search": RiskLevel.LOW,
    "twitter_user_tweets": RiskLevel.LOW,
    "twitter_research_trends": RiskLevel.LOW,
    "twitter_status": RiskLevel.LOW,
    "transcribe_voice": RiskLevel.LOW,
    "skill_validate": RiskLevel.LOW,
    "extract_interview_questions": RiskLevel.LOW,
    # Agent-Reach read/search tools (MIT, no cookies, no keys)
    "reach_web_read": RiskLevel.LOW,
    "reach_web_search": RiskLevel.LOW,
    "reach_github_search": RiskLevel.LOW,
    "reach_research": RiskLevel.LOW,
    # Social drafting (read-only, does NOT post)
    "draft_post": RiskLevel.LOW,
    "research_and_draft": RiskLevel.LOW,
    # Verification (read-only search)
    "verify_post": RiskLevel.LOW,
    # Write / medium risk
    "create_file": RiskLevel.MEDIUM,
    "skill_install": RiskLevel.MEDIUM,
    "browser_interact": RiskLevel.MEDIUM,
    # Publish / high risk — ALWAYS blocked until user approves
    "post_to_twitter": RiskLevel.HIGH,
    "twitter_post_tweet": RiskLevel.HIGH,
    "post_to_linkedin": RiskLevel.HIGH,
    "send_email": RiskLevel.HIGH,
    "submit_form": RiskLevel.HIGH,
}


def get_tool_risk(tool_name: str) -> RiskLevel:
    return TOOL_RISK_MAP.get(tool_name, RiskLevel.MEDIUM)


def requires_approval(tool_name: str, policy: AutomationPolicy) -> bool:
    """Return True if the agent must pause and wait for the user to approve this action."""

    # Publishing tools ALWAYS require explicit human approval — no policy can bypass this.
    if tool_name in PUBLISHING_TOOLS:
        return True

    risk = get_tool_risk(tool_name)

    if policy.confirmation_mode == ConfirmationMode.ALWAYS_ASK:
        return True
    if policy.confirmation_mode == ConfirmationMode.AUTO_SAFE:
        return risk == RiskLevel.HIGH

    # Default: ASK_RISKY — block HIGH and unapproved MEDIUM
    if risk == RiskLevel.HIGH:
        return True
    if risk == RiskLevel.MEDIUM and not policy.browser_automation:
        return True
    return False


# Default policy (singleton)
_policy = AutomationPolicy()


def get_policy() -> AutomationPolicy:
    return _policy


def update_policy(new_policy: AutomationPolicy):
    global _policy
    _policy = new_policy
