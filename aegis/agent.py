import os
import re
import ollama
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
try:
    from aegis.guardrail import GuardrailEngine
    from aegis.pruner import ASTPruner
    from aegis.verifier import TestVerifier
    from aegis.router import HybridRouter
except ModuleNotFoundError:
    from guardrail import GuardrailEngine
    from pruner import ASTPruner
    from verifier import TestVerifier
    from router import HybridRouter
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
When suggesting terminal actions to inspect files or run tasks, ONLY output valid shell commands (e.g., 'type main.py' on Windows, or standard python/pytest commands) enclosed inside ```bash or ```powershell blocks. Never invent custom tool names like read_file.
"""

class AegisAgent:
    def __init__(self, repo_path: str = "."):
        self.repo_path = repo_path
        self.guard = GuardrailEngine(repo_path=repo_path)
        self.pruner = ASTPruner()
        self.verifier = TestVerifier(repo_path=repo_path)
        self.router = HybridRouter()
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
        """Extracts executable shell commands strictly enclosed in ```bash, ```powershell, or ```cmd blocks."""
        pattern = r"```(?:bash|sh|shell|powershell|cmd)\s*\n(.*?)\n```"
        matches = re.findall(pattern, text, re.DOTALL)
        commands = []
        for block in matches:
            for line in block.strip().split("\n"):
                line = line.strip()
                if not line or line.startswith(("#", "```", "import ", "from ", "def ", "class ")):
                    continue
                commands.append(line)
        return commands
    
    def self_heal(self, target_file: str):
        console.print(Panel(f"[bold cyan]Initiating Self-Healing Loop for target:[/bold cyan] {target_file}", border_style="cyan"))

        # 1. Run baseline tests
        passed, trace = self.verifier.run_tests()
        if passed:
            console.print("[bold green]All tests are already passing. No fix required![/bold green]")
            return

        console.print(Panel(trace, title="[bold red]Test Failure Detected[/bold red]", border_style="red"))
        stash_sha = self.guard.create_shadow_stash()

        # 2. Read target source
        target_path = os.path.join(self.repo_path, target_file)
        if not os.path.exists(target_path):
            console.print(f"[bold red]File not found:[/bold red] {target_file}")
            return

        with open(target_path, "r", encoding="utf-8") as f:
            original_code = f.read()

        # 3. Construct repair prompt
        heal_prompt = f"""The following test suite failed:
{trace}

Here is the source code of `{target_file}`:
```python
{original_code}
Fix the bug causing the test failure. Output ONLY the raw replacement Python code inside a single python ...  block. Do not include conversational text."""
        messages = [
            {"role": "system", "content": "You are an automated code repair agent. Provide only correct python code inside a ```python block."},
            {"role": "user", "content": heal_prompt}
        ]

        # 4. Route generation (Local SLM or Cloud Tier)
        raw_reply, tier = self.router.route_and_generate(messages, prompt_hint=trace, attempt_count=1)
        console.print(f"[dim]Patch generated using {tier} tier engine.[/dim]")

        # 5. Extract code patch
        match = re.search(r"```(?:python)?\s*\n(.*?)\n```", raw_reply, re.DOTALL)
        patch_code = match.group(1) if match else raw_reply.strip()

        # 6. Apply patch
        with open(target_path, "w", encoding="utf-8") as f:
            f.write(patch_code)

        console.print(f"[bold yellow]Patch applied to {target_file}. Re-verifying test suite...[/bold yellow]")

        # 7. Verification & deterministic rollback guardrail
        retest_passed, retest_trace = self.verifier.run_tests()
        if retest_passed:
            console.print(Panel(
                f"[bold green]Patch Verified Successfully![/bold green]\n`{target_file}` fixed and all tests passing.",
                title="[bold green]Healing Succeeded[/bold green]",
                border_style="green"
            ))
        else:
            console.print(Panel(
                f"[bold red]Patch failed verification. Rolling back workspace.[/bold red]\n{retest_trace}",
                title="[bold red]Self-Healing Rollback[/bold red]",
                border_style="red"
            ))
            with open(target_path, "w", encoding="utf-8") as f:
                f.write(original_code)

    def run_turn(self, user_input: str):
        # 1. Direct command interception
        cleaned = user_input.strip()
        if cleaned.lower().startswith("heal"):
            parts = cleaned.split()
            target = parts[1] if len(parts) > 1 else "math_utils.py"
            self.self_heal(target)
            return

        # 2. Gather AST repository skeleton
        repo_context = self.get_repo_context()
        full_user_prompt = (
            f"Workspace Code Skeleton:\n{repo_context}\n\nTask: {user_input}"
            if repo_context else user_input
        )

        self.history.append({"role": "user", "content": full_user_prompt})

        # 3. Query via Hybrid Router
        try:
            reply, tier = self.router.route_and_generate(
                self.history,
                prompt_hint=user_input,
                attempt_count=1
            )
            self.history.append({"role": "assistant", "content": reply})
        except Exception as e:
            console.print(f"[bold red]Inference Error:[/bold red] {e}")
            return

        # 4. Render model output
        panel_title = f"[bold green]Aegis Assistant [{tier}][/bold green]"
        console.print(Panel(Markdown(reply), title=panel_title, border_style="green"))

        # 5. Extract and safely execute commands via the Guardrail Engine
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