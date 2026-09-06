from rich.console import Console
from rich.panel import Panel
from aegis.agent import AegisAgent

console = Console()

def main():
    console.print(Panel.fit(
        "[bold cyan]Aegis CLI[/bold cyan] — [dim]Deterministic Guardrails & Hybrid Routing Engine[/dim]\n"
        "[italic green]Type your command, or 'exit' / 'quit' to close.[/italic green]",
        border_style="cyan"
    ))

    agent = AegisAgent()

    while True:
        try:
            user_input = console.input("\n[bold magenta]Aegis > [/bold magenta]")
            if user_input.strip().lower() in ["exit", "quit", "q"]:
                console.print("[dim]Exiting Aegis CLI session. Goodbye![/dim]")
                break
            if not user_input.strip():
                continue

            agent.run_turn(user_input)

        except KeyboardInterrupt:
            console.print("\n[dim]Session interrupted. Goodbye![/dim]")
            break

if __name__ == "__main__":
    main()