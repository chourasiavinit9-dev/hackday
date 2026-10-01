"""
HackGuide — Gemma 4 Native Tool-Call Hackathon Mentor Agent Skill
Built at Hacktoberfest Hack Day Asansol × HackTropica 2026
Asansol Engineering College, Room NB-507 | October 3, 2026

Prize Tracks:
  - Best Use of Gemma 4
  - Best Open-Source AI Project (Agent Skill Open Standard)

License: MIT
"""

import os
import json
import sys
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from rich.text import Text
from rich.rule import Rule
from rich import print as rprint

import google.generativeai as genai
from tools import TOOLS, run_tool

# ── Configuration ──────────────────────────────────────────────────────────────
API_KEY = os.environ.get("GEMINI_API_KEY")
if not API_KEY:
    print("❌ GEMINI_API_KEY not set. Run: export GEMINI_API_KEY=your_key")
    sys.exit(1)

genai.configure(api_key=API_KEY)

GEMMA_MODEL = "gemma-4-27b-it"  # Switch to gemma-4-e2b-it if quota issues

SYSTEM_PROMPT = """<|think|>
You are HackGuide, an expert hackathon mentor powered by Gemma 4.

You have deep knowledge of the MLH judging rubric:
- Technology (25%): Technical difficulty and cleverness
- Design (25%): UX and interface quality
- Completion (25%): Does it actually work during the demo?
- Learning (25%): Did the team stretch their skills?

Critical insight: COMPLETION is the biggest failure point.
Over-scoping kills more teams than anything else.
A flawless 2-feature demo always beats a broken 10-feature one.

Your workflow when helping a user plan their hack:
1. Ask for: name, challenge track, team size, hours available, tech stack
2. Call analyze_project_feasibility → determine safe MVP scope
3. Call generate_project_timeline → build the battle clock  
4. Call generate_readme_template → output competition-ready README
5. Give a final 2-sentence summary of the winning strategy

You support native Gemma 4 tool calling. Use tools — do not hallucinate results.
Always show your reasoning before giving the final plan.
"""

console = Console()


def stream_response(response) -> tuple[str, list[dict]]:
    """Stream Gemma 4 response text, return (text, tool_calls)."""
    full_text = ""
    tool_calls = []

    for chunk in response:
        if not chunk.candidates:
            continue
        candidate = chunk.candidates[0]
        if not candidate.content or not candidate.content.parts:
            continue
        for part in candidate.content.parts:
            if hasattr(part, "text") and part.text:
                full_text += part.text
                console.print(part.text, end="", markup=False)
            elif hasattr(part, "function_call") and part.function_call:
                fc = part.function_call
                tool_calls.append({
                    "name": fc.name,
                    "args": dict(fc.args)
                })

    console.print()  # newline after streaming
    return full_text, tool_calls


def chat(history: list, user_message: str) -> list:
    """Run one turn of the HackGuide agent loop."""
    history.append({"role": "user", "parts": [{"text": user_message}]})

    model = genai.GenerativeModel(
        model_name=GEMMA_MODEL,
        system_instruction=SYSTEM_PROMPT,
        tools=[{"function_declarations": TOOLS}]
    )

    # ── Initial model call ────────────────────────────────────────────────────
    console.print(Rule("[dim]Gemma 4 Thinking...[/dim]", style="dim"))

    response = model.generate_content(
        history,
        stream=True,
        generation_config=genai.GenerationConfig(
            temperature=0.7,
            max_output_tokens=2048,
        )
    )

    response_text, tool_calls = stream_response(response)
    history.append({"role": "model", "parts": [{"text": response_text}]})

    # ── Tool execution loop ───────────────────────────────────────────────────
    for tc in tool_calls:
        console.print()
        console.print(Panel(
            f"[bold yellow]🔧 Tool:[/bold yellow] [cyan]{tc['name']}[/cyan]\n"
            f"[dim]{json.dumps(tc['args'], indent=2)}[/dim]",
            title="[yellow]Gemma 4 Tool Call[/yellow]",
            border_style="yellow"
        ))

        tool_result = run_tool(tc["name"], tc["args"])

        console.print(Panel(
            f"[green]{tool_result}[/green]",
            title=f"[green]✅ Result: {tc['name']}[/green]",
            border_style="green"
        ))

        # Inject tool result back into history
        history.append({
            "role": "user",
            "parts": [{
                "function_response": {
                    "name": tc["name"],
                    "response": {"result": tool_result}
                }
            }]
        })

        # Get model's follow-up after tool result
        console.print(Rule("[dim]Gemma 4 Continuing...[/dim]", style="dim"))
        follow_up = model.generate_content(
            history,
            stream=True,
            generation_config=genai.GenerationConfig(temperature=0.7, max_output_tokens=2048)
        )
        follow_text, more_calls = stream_response(follow_up)
        history.append({"role": "model", "parts": [{"text": follow_text}]})

    return history


def main():
    console.print(Panel(
        Text.assemble(
            ("HackGuide ", "bold magenta"),
            ("— Gemma 4 Hackathon Mentor\n", "bold white"),
            ("Powered by Gemma 4 Thinking Mode + Native Tool Calling\n", "dim"),
            ("Built at Hacktoberfest Hack Day Asansol × HackTropica 2026\n", "dim green"),
            ("Asansol Engineering College, NB-507 | October 3, 2026", "dim"),
        ),
        subtitle="[dim]MIT License | Apache 2.0 (Gemma 4) | Agent Skill Open Standard[/dim]",
        border_style="magenta",
        expand=False
    ))

    console.print(
        "\n[bold]Type your hackathon situation and I'll build you a complete plan.[/bold]"
        "\n[dim]Example: 'Team of 2, Best Use of Gemma 4 track, 3.5 hours, we know Python'[/dim]\n"
    )

    history = []

    while True:
        try:
            console.print("[bold cyan]You:[/bold cyan] ", end="")
            user_input = input().strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Session ended. Good luck! 🚀[/dim]")
            break

        if not user_input:
            continue
        if user_input.lower() in ("exit", "quit", "q"):
            console.print("[dim]Good luck at the hack day! 🚀[/dim]")
            break

        console.print()
        console.print("[bold magenta]HackGuide:[/bold magenta]")
        history = chat(history, user_input)
        console.print()


if __name__ == "__main__":
    main()
