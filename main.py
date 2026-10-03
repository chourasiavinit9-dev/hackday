"""
HackGuide — Gemma 4 Native Tool-Call Hackathon Mentor Agent Skill
Built at Hacktoberfest Hack Day Asansol × HackTropica 2026
Asansol Engineering College, Room NB-507 | October 3, 2026

Prize Tracks:
  - Best Use of Gemma 4 (Reasoning, Thinking Mode, Multimodal Voice & Video)
  - Best Open-Source AI Project (Agent Skill Open Standard)

License: MIT
"""

import os
import json
import sys
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from rich.text import Text
from rich.rule import Rule
from rich import print as rprint

load_dotenv()

import google.generativeai as genai
from tools import TOOLS, run_tool
from multimodal import transcribe_and_extract_voice, analyze_demo_video, analyze_architecture_image

console = Console()

# ── Configuration ──────────────────────────────────────────────────────────────
API_KEY = os.environ.get("GEMINI_API_KEY")
if not API_KEY or API_KEY == "your_gemini_api_key_here":
    console.print(Panel(
        "[bold red]❌ GEMINI_API_KEY not configured in .env[/bold red]\n\n"
        "1. Open or create [bold].env[/bold] in this directory.\n"
        "2. Add your key: [green]GEMINI_API_KEY=your_key_here[/green]\n"
        "3. Get a free key at: [bold link=https://aistudio.google.com/app/apikey]https://aistudio.google.com/app/apikey[/bold link]",
        title="Setup Required",
        border_style="red"
    ))
    # Don't hard-crash so user can run help or tests, but guard API calls

if API_KEY:
    genai.configure(api_key=API_KEY)

# Model priority list: Gemma 4 -> Gemma variants -> Multimodal Flash fallbacks
ACTIVE_MODEL = os.environ.get("GEMMA_MODEL", "gemma-4-31b-it")
FALLBACK_MODELS = [
    ACTIVE_MODEL,
    "gemma-4-31b-it",
    "gemma-4-26b-a4b-it",
    "gemma-2-27b-it",
    "gemini-2.0-flash",
    "gemini-1.5-flash"
]

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

Your capabilities include:
1. Feasibility analysis & battle clock generation via native tool calling.
2. Voice & audio pitch transcription via transcribe_pitch_audio.
3. Hackathon demo video auditing against the MLH rubric via review_demo_video.
4. Architecture sketch & whiteboard analysis via analyze_architecture_image.

Your workflow when helping a user plan their hack:
1. Ask for: challenge track, team size, hours available, tech stack (or review their voice pitch/demo video).
2. Call analyze_project_feasibility → determine safe MVP scope.
3. Call generate_project_timeline → build the battle clock.
4. Call generate_readme_template → output competition-ready README.
5. Give a final 2-sentence summary of the winning strategy.

You support native Gemma 4 tool calling. Use tools — do not hallucinate results.
Always show your reasoning before giving the final plan.
"""


def stream_response(response) -> tuple[str, list[dict]]:
    """Stream model response text and parse tool calls."""
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

    console.print()
    return full_text, tool_calls


def get_resilient_model():
    """Try to initialize model with fallback across Gemma and multimodal flash models."""
    global ACTIVE_MODEL
    for candidate in FALLBACK_MODELS:
        try:
            model = genai.GenerativeModel(
                model_name=candidate,
                system_instruction=SYSTEM_PROMPT,
                tools=[{"function_declarations": TOOLS}]
            )
            ACTIVE_MODEL = candidate
            return model
        except Exception:
            continue
    # Default fallback
    return genai.GenerativeModel(
        model_name="gemini-2.0-flash",
        system_instruction=SYSTEM_PROMPT,
        tools=[{"function_declarations": TOOLS}]
    )


def chat(history: list, user_message: str) -> list:
    """Run one turn of the HackGuide agent loop."""
    history.append({"role": "user", "parts": [{"text": user_message}]})

    model = get_resilient_model()

    console.print(Rule(f"[dim]{ACTIVE_MODEL} Thinking...[/dim]", style="dim"))

    try:
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
    except Exception as e:
        console.print(f"[bold red]Generation error ({ACTIVE_MODEL}): {e}[/bold red]")
        return history

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

        # Get model follow-up
        console.print(Rule(f"[dim]{ACTIVE_MODEL} Continuing...[/dim]", style="dim"))
        try:
            follow_up = model.generate_content(
                history,
                stream=True,
                generation_config=genai.GenerationConfig(temperature=0.7, max_output_tokens=2048)
            )
            follow_text, more_calls = stream_response(follow_up)
            history.append({"role": "model", "parts": [{"text": follow_text}]})
        except Exception as e:
            console.print(f"[red]Follow-up error: {e}[/red]")

    return history


def handle_multimodal_command(cmd: str, arg: str, history: list):
    """Handle /voice, /video, /image CLI commands."""
    if not os.path.exists(arg):
        console.print(f"[bold red]File not found: {arg}[/bold red]")
        return history

    if cmd == "/voice" or cmd == "/audio":
        console.print(Rule("[bold cyan]🎤 Transcribing Voice Pitch...[/bold cyan]"))
        result = transcribe_and_extract_voice(arg)
        console.print(Panel(result, title="Voice Pitch Analysis", border_style="cyan"))
        prompt = (
            f"Here is the transcription of our team's voice pitch:\n\n{result}\n\n"
            f"Please review this and formulate our hackathon MVP plan, feasibility, and timeline."
        )
        return chat(history, prompt)

    elif cmd == "/video":
        console.print(Rule("[bold magenta]📹 Auditing Demo Video (MLH Rubric)...[/bold magenta]"))
        result = analyze_demo_video(arg)
        console.print(Panel(result, title="MLH Demo Video Audit", border_style="magenta"))
        return history

    elif cmd == "/image":
        console.print(Rule("[bold blue]🖼️ Analyzing Architecture Diagram...[/bold blue]"))
        result = analyze_architecture_image(arg)
        console.print(Panel(result, title="Architecture Analysis", border_style="blue"))
        prompt = (
            f"Here is the analysis of our architecture diagram sketch:\n\n{result}\n\n"
            f"Help us scope an MVP that we can realistically finish in our hackathon."
        )
        return chat(history, prompt)

    return history


def show_help():
    console.print(Panel(
        "[bold cyan]Available Commands:[/bold cyan]\n"
        "• [bold]Natural Language:[/bold] Type your team size, available hours, stack, and idea\n"
        "• [bold]/voice <path>[/bold]  : Voice-to-text pitch transcription & instant MVP scoping\n"
        "• [bold]/video <path>[/bold]  : Audit demo video against MLH Rubric (60-sec pitch check)\n"
        "• [bold]/image <path>[/bold]  : Analyze architecture whiteboard or wireframe diagram\n"
        "• [bold]/model <name>[/bold]  : Change active model (e.g., gemma-4-27b-it, gemini-2.0-flash)\n"
        "• [bold]/test[/bold]          : Run setup & model diagnostics\n"
        "• [bold]exit / quit[/bold]    : Exit HackGuide",
        title="HackGuide Commands",
        border_style="cyan"
    ))


def main():
    global ACTIVE_MODEL
    console.print(Panel(
        Text.assemble(
            ("HackGuide ", "bold magenta"),
            ("— Gemma 4 Hackathon Mentor\n", "bold white"),
            ("Powered by Gemma 4 Thinking Mode + Native Tool Calling + Multimodal Engine\n", "dim"),
            ("Built at Hacktoberfest Hack Day Asansol × HackTropica 2026\n", "dim green"),
            ("Asansol Engineering College, NB-507 | October 3, 2026", "dim"),
        ),
        subtitle=f"[dim]Model: {ACTIVE_MODEL} | MIT License | Agent Skill Open Standard[/dim]",
        border_style="magenta",
        expand=False
    ))

    console.print(
        "\n[bold]Type your hackathon situation, or use /voice, /video, /image to analyze media.[/bold]"
        "\n[dim]Example: 'Team of 2, Best Use of Gemma 4 track, 3.5 hours, we know Python' (or type /help)[/dim]\n"
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

        if user_input.startswith("/help"):
            show_help()
            continue

        if user_input.startswith("/test"):
            from test_models import check_setup
            check_setup()
            continue

        if user_input.startswith("/model "):
            new_model = user_input.split(" ", 1)[1].strip()
            ACTIVE_MODEL = new_model
            console.print(f"[green]Active model switched to: [bold]{ACTIVE_MODEL}[/bold][/green]")
            continue

        if user_input.startswith(("/voice", "/audio", "/video", "/image")):
            parts = user_input.split(" ", 1)
            cmd = parts[0]
            if len(parts) < 2:
                console.print(f"[yellow]Usage: {cmd} <path_to_file>[/yellow]")
                continue
            history = handle_multimodal_command(cmd, parts[1].strip(), history)
            continue

        console.print()
        console.print(f"[bold magenta]HackGuide ({ACTIVE_MODEL}):[/bold magenta]")
        history = chat(history, user_input)
        console.print()


if __name__ == "__main__":
    main()
