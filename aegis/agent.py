import os
import re
import ollama
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown

from aegis.guardrail import GuardrailEngine
from aegis.pruner import ASTPruner
import platform

console = Console()
CURRENT_OS = platform.system().lower()

SYSTEM_PROMPT = f"""You are Aegis CLI, an autonomous software engineering assistant.
Host Operating System: {CURRENT_OS}
Shell syntax guidelines:
- If Windows: Use Windows CMD/PowerShell commands (e.g., 'dir', 'type', 'del', 'copy'). Do NOT use 'ls' or 'cat'.
- If Linux/Darwin: Use POSIX commands (e.g., 'ls', 'cat', 'rm', 'cp').

When you want to run a shell command, enclose it strictly in a markdown bash block:
```bash
<command>
Keep responses concise, technical, and actionable.
"""

class AegisAgent:
    def __init__(self, model: str = "qwen2.5-coder:3b", repo_path: str = "."):
        self.model = model
        self.repo_path = repo_path
        self.guard = GuardrailEngine(repo_path=repo_path)
        self.pruner = ASTPruner()
        self.history = [{"role": "system", "content": SYSTEM_PROMPT}]

    def get_repo_context(self) -> str:
        """Scans workspace Python files, prunes implementations using Tree-sitter, and returns structural skeletons."""
        context_parts = []
        for root, dirs, files in os.walk(self.repo_path):
            # Exclude virtual environments, version control, and cache folders
            dirs[:] = [d for d in dirs if d not in ["venv", ".venv", ".git", "__pycache__", "build", "dist"]]
            for file in files:
                if file.endswith(".py") and not file.startswith("test_"):
                    full_path = os.path.join(root, file)
                    rel_path = os.path.relpath(full_path, self.repo_path)
                    try:
                        skeleton = self.pruner.prune_file(full_path)
                        if skeleton.strip():
                            context_parts.append(f"--- File: {rel_path} ---\n{skeleton}")
                    except Exception:
                        continue
        return "\n\n".join(context_parts)

    def extract_commands(self, text: str) -> list[str]:
        """Extracts executable shell commands enclosed in ```bash ... ``` markdown blocks."""
        pattern = r"```(?:bash|sh|shell)?\s*\n(.*?)\n```"
        matches = re.findall(pattern, text, re.DOTALL)
        commands = []
        for block in matches:
            for line in block.strip().split("\n"):
                line = line.strip()
                # Skip comments and empty lines
                if line and not line.startswith("#"):
                    commands.append(line)
        return commands

    def run_turn(self, user_input: str):
        # 1. Gather repository AST context
        repo_context = self.get_repo_context()
        full_user_prompt = (
            f"Workspace Code Skeleton:\n{repo_context}\n\nTask: {user_input}"
            if repo_context else user_input
        )

        self.history.append({"role": "user", "content": full_user_prompt})

        # 2. Query Local SLM via Ollama
        with console.status("[bold cyan]Aegis thinking (Qwen-2.5-Coder)...[/bold cyan]"):
            try:
                response = ollama.chat(model=self.model, messages=self.history)
                reply = response.message.content
                self.history.append({"role": "assistant", "content": reply})
            except Exception as e:
                console.print(f"[bold red]Ollama Connection Error:[/bold red] {e}")
                return

        # 3. Render Assistant Response
        console.print(Panel(Markdown(reply), title="[bold green]Aegis Assistant[/bold green]", border_style="green"))

        # 4. Extract and safely execute commands via the Guardrail Engine
        commands = self.extract_commands(reply)
        for cmd in commands:
            category = self.guard.classify(cmd)
            console.print(
                f"\n[bold yellow]Suggested Action:[/bold yellow] [cyan]{cmd}[/cyan] "
                f"(Safety Tier: [bold]{category}[/bold])"
            )
            
            run_confirm = console.input("[dim]Execute this command through Guardrail? (y/N): [/dim]")
            if run_confirm.strip().lower() == "y":
                success, output, cat = self.guard.execute_command(cmd)
                style = "green" if success else "red"
                console.print(Panel(output.strip() or "(No output generated)", title=f"Result [{cat}]", border_style=style))