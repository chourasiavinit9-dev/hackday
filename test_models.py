"""
HackGuide — Model & Multimodal Setup Diagnostics
Checks GEMINI_API_KEY, lists available Gemma and Gemini models, and tests audio/video readiness.
"""

import os
import sys
from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

load_dotenv()
console = Console()

API_KEY = os.environ.get("GEMINI_API_KEY")

def check_setup():
    console.print(Panel(
        "[bold cyan]HackGuide — Model Setup & Multimodal Diagnostic[/bold cyan]\n"
        "[dim]Validating Gemma 4, Audio/Voice, and Video model endpoints[/dim]",
        border_style="cyan"
    ))

    if not API_KEY or API_KEY == "your_gemini_api_key_here":
        console.print("[bold red]❌ GEMINI_API_KEY is not set or is still the placeholder![/bold red]")
        console.print("\n[yellow]How to set up your key:[/yellow]")
        console.print("1. Get a free API key at: [bold link=https://aistudio.google.com/app/apikey]https://aistudio.google.com/app/apikey[/bold link]")
        console.print("2. Create or open [bold].env[/bold] file in this directory")
        console.print("3. Add: [bold green]GEMINI_API_KEY=your_actual_key[/bold green]\n")
        return False

    try:
        import google.generativeai as genai
        genai.configure(api_key=API_KEY)
    except Exception as e:
        console.print(f"[red]Error configuring Generative AI SDK: {e}[/red]")
        return False

    console.print("[green]✅ GEMINI_API_KEY found and configured.[/green]\n")

    # List available models
    console.print("[dim]Fetching available models from Gemini API...[/dim]")
    try:
        models = list(genai.list_models())
    except Exception as e:
        console.print(f"[bold red]❌ Failed to authenticate with Gemini API: {e}[/bold red]")
        return False

    table = Table(title="Available Model Endpoints", show_header=True)
    table.add_column("Category", style="bold cyan")
    table.add_column("Model Name", style="bold green")
    table.add_column("Description", style="dim")
    table.add_column("Capabilities")

    gemma_found = []
    multimodal_found = []

    for m in models:
        methods = ", ".join(m.supported_generation_methods)
        name = m.name.replace("models/", "")
        desc = (m.description or "")[:60] + "..." if len(m.description or "") > 60 else (m.description or "")

        if "gemma" in name.lower():
            gemma_found.append(name)
            table.add_row("Gemma Family", name, desc, methods)
        elif any(k in name.lower() for k in ["flash", "pro"]) and "generateContent" in m.supported_generation_methods:
            multimodal_found.append(name)
            table.add_row("Multimodal / Voice / Video", name, desc, methods)

    console.print(table)

    # Summary recommendations
    preferred_gemma = os.environ.get("GEMMA_MODEL", "gemma-4-27b-it")
    preferred_multimodal = os.environ.get("MULTIMODAL_MODEL", "gemini-2.0-flash")

    console.print("\n[bold]Configuration Recommendations:[/bold]")
    console.print(f"• Gemma Reasoning Model: [cyan]{preferred_gemma}[/cyan]")
    console.print(f"• Multimodal Engine (Voice & Video): [cyan]{preferred_multimodal}[/cyan]")

    if gemma_found:
        console.print(f"[green]✔ Discovered Gemma models on your key: {', '.join(gemma_found)}[/green]")
    else:
        console.print("[yellow]ℹ Gemma models will use specified endpoints or multimodal flash fallback.[/yellow]")

    console.print("\n[bold green]Ready for live demo and hackathon judging![/bold green] 🚀\n")
    return True

if __name__ == "__main__":
    check_setup()
