from rich.console import Console
from rich.panel import Panel
from aegis.agent import AegisAgent

console = Console()

def main():
    console.print(Panel.fit(
        "[bold cyan]Aegis CLI — Deterministic Guardrails & Hybrid Routing Engine[/bold cyan]\n"
        "[dim]Type your command, 'heal <file>', or 'exit' / 'quit' to close.[/dim]",
        border_style="cyan"
    ))

    agent = AegisAgent()

    while True:
        try:
            user_input = console.input("\n[bold green]Aegis > [/bold green]").strip()
            
            if not user_input:
                continue

            if user_input.lower() in ["exit", "quit", "q"]:
                console.print("[yellow]Exiting Aegis CLI. Goodbye![/yellow]")
                break

            agent.run_turn(user_input)

        except KeyboardInterrupt:
            console.print("\n[yellow]Turn cancelled. (Type 'exit' to quit)[/yellow]")
            continue
        except EOFError:
            console.print("\n[yellow]Session terminated. Goodbye![/yellow]")
            break
        except Exception as e:
            console.print(f"\n[bold red]Runtime Error during turn:[/bold red] {e}")
            continue

if __name__ == "__main__":
    main()