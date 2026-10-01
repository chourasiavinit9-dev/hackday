"""
HackGuide — SKILL.md Validator
Validates our own SKILL.md against the Agent Skill Open Standard.
This is also a meta-demo moment: the skill audits itself.
"""

import re
import sys
from pathlib import Path

try:
    import yaml
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    RICH = True
except ImportError:
    RICH = False

REQUIRED_FRONTMATTER_KEYS = ["name", "description", "version", "author", "license"]
NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9\-]{0,62}[a-z0-9]$")
MAX_DESC_CHARS = 1024
MAX_BODY_LINES = 200


def parse_skill_md(path: Path) -> tuple[dict, str]:
    """Parse YAML frontmatter and body from a SKILL.md file."""
    content = path.read_text(encoding="utf-8")
    if not content.startswith("---"):
        return {}, content
    parts = content.split("---", 2)
    if len(parts) < 3:
        return {}, content
    try:
        import yaml
        frontmatter = yaml.safe_load(parts[1]) or {}
    except Exception:
        frontmatter = {}
    body = parts[2].strip()
    return frontmatter, body


def validate(skill_path: str = "SKILL.md") -> bool:
    path = Path(skill_path)
    errors = []
    warnings = []
    passed = []

    if not path.exists():
        print(f"❌ File not found: {skill_path}")
        return False

    fm, body = parse_skill_md(path)

    # ── Required keys ──────────────────────────────────────────────────────────
    for key in REQUIRED_FRONTMATTER_KEYS:
        if key in fm:
            passed.append(f"Required key '{key}' present")
        else:
            errors.append(f"Missing required frontmatter key: '{key}'")

    # ── Name format ────────────────────────────────────────────────────────────
    name = fm.get("name", "")
    if name:
        if NAME_PATTERN.match(name):
            passed.append(f"Name '{name}' is valid kebab-case")
        else:
            errors.append(f"Name '{name}' must be lowercase kebab-case, 2–64 chars")

    # ── Description length ─────────────────────────────────────────────────────
    desc = str(fm.get("description", ""))
    if desc:
        if len(desc) <= MAX_DESC_CHARS:
            passed.append(f"Description length OK ({len(desc)} chars)")
        else:
            errors.append(f"Description too long ({len(desc)} chars, max {MAX_DESC_CHARS})")
    else:
        errors.append("Description is empty")

    # ── Body length ────────────────────────────────────────────────────────────
    body_lines = len(body.splitlines())
    if body_lines <= MAX_BODY_LINES:
        passed.append(f"Body length OK ({body_lines} lines)")
    else:
        warnings.append(f"Body is {body_lines} lines (recommend under {MAX_BODY_LINES})")

    # ── License ────────────────────────────────────────────────────────────────
    license_val = fm.get("license", "")
    osi_approved = ["MIT", "Apache-2.0", "GPL-3.0", "BSD-2-Clause", "BSD-3-Clause"]
    if license_val in osi_approved:
        passed.append(f"License '{license_val}' is OSI-approved ✅")
    else:
        errors.append(f"License '{license_val}' may not be OSI-approved")

    # ── Report ─────────────────────────────────────────────────────────────────
    if RICH:
        console = Console()
        table = Table(title="SKILL.md Validation Report", show_header=True)
        table.add_column("Status", style="bold", width=8)
        table.add_column("Check")

        for p in passed:
            table.add_row("✅ PASS", p)
        for w in warnings:
            table.add_row("⚠️  WARN", w)
        for e in errors:
            table.add_row("❌ FAIL", e)

        console.print(table)

        if not errors:
            console.print(Panel(
                f"[bold green]SKILL.md is fully compliant with the Agent Skill Open Standard![/bold green]\n"
                f"[dim]{len(passed)} checks passed, {len(warnings)} warnings, 0 errors[/dim]",
                border_style="green"
            ))
        else:
            console.print(Panel(
                f"[bold red]{len(errors)} error(s) found. Fix before demo.[/bold red]",
                border_style="red"
            ))
    else:
        for p in passed:
            print(f"PASS: {p}")
        for w in warnings:
            print(f"WARN: {w}")
        for e in errors:
            print(f"FAIL: {e}")

    return len(errors) == 0


if __name__ == "__main__":
    skill_file = sys.argv[1] if len(sys.argv) > 1 else "SKILL.md"
    ok = validate(skill_file)
    sys.exit(0 if ok else 1)
