import os
import re
import ollama
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from typing import Dict, Optional, List
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

CRITICAL OPERATIONAL RULES:
- NEVER output XML tags, tool-call syntax, or function headers like `<tool_call>` or `<function>`.
- Full repository context and code skeletons are already provided.
- NEVER use shell redirection (like 'echo >>') or batch scripts to create or append code to source files.
- When creating or modifying files, you MUST use the structured multi-file format below.
- ALWAYS wrap each file's complete updated contents in a ```python ... ``` code block.
- Do NOT output conversational filler, introductory summaries, or notes between or inside the file blocks.

MULTI-FILE EDIT FORMAT:
*** FILE: <relative_path> ***
```python
<complete updated file contents>

TERMINAL COMMAND FORMAT:
When you need to suggest a shell action (such as running tests or inspecting directories), enclose it strictly in:
```bash
<command>
Keep responses concise, deterministic, and strictly formatted."""

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
        cleaned = user_input.strip()
        if cleaned.lower().startswith("heal"):
            parts = cleaned.split()
            target = parts[1] if len(parts) > 1 else "math_utils.py"
            self.self_heal(target)
            return

        repo_context = self.get_repo_context()
        # Only inject pruned AST context if the prompt explicitly asks for repository-wide analysis
        # or if the user prompt does not name specific target files.
        needs_full_repo = any(kw in user_input.lower() for kw in ["architecture", "workspace", "repo", "all files", "entire project"])
        
        if needs_full_repo:
            repo_context = self.get_repo_context()
            # Cap context at 1500 chars to avoid hitting free-tier token barriers
            if len(repo_context) > 1500:
                repo_context = repo_context[:1500] + "\n... [Remaining skeleton truncated]"
            full_user_prompt = f"Workspace Skeleton:\n{repo_context}\n\nTask: {user_input}"
        else:
            full_user_prompt = user_input

        self.history.append({"role": "user", "content": full_user_prompt})

        try:
            reply, tier = self.router.route_and_generate(
                self.history,
                prompt_hint=user_input,
                attempt_count=1
            )
            self.history.append({"role": "assistant", "content": reply})
        except Exception as e:
            console.print(f"[bold red]Inference Error:[/bold red] {str(e)[:200]}", highlight=False)
            return

        panel_title = f"[bold green]Aegis Assistant [{tier}][/bold green]"
        console.print(Panel(Markdown(reply), title=panel_title, border_style="green"))

        # Check for multi-file patches
        patches = self.parse_multi_file_patches(reply)
        if patches:
            confirm = console.input("\n[bold yellow]Apply multi-file patch transaction? (y/N): [/bold yellow]")
            if confirm.strip().lower() == "y":
                self.apply_atomic_patches(patches)

        # Check for shell commands
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
        
    def parse_multi_file_patches(self, text: str) -> Dict[str, str]:
        """
        Parses structured multi-file output formatted as:
        *** FILE: relative/path/to/file.py ***
        [```python optional]
        <code>
        [``` optional]
        """
        # Split across *** FILE: <path> *** headers
        sections = re.split(r"\*\*\*\s*FILE:\s*([^\n\*]+?)\s*\*\*\*", text)
        patches = {}
        
        # re.split creates [preamble, path1, body1, path2, body2, ...]
        for i in range(1, len(sections), 2):
            rel_path = sections[i].strip().replace("/", os.sep).replace("\\", os.sep)
            raw_body = sections[i + 1].strip()

            # Clean out conversational wrappers if present before next section
            # Strip markdown fences if the model included them
            fence_match = re.search(r"```(?:python)?\s*\n(.*?)\n```", raw_body, re.DOTALL)
            if fence_match:
                code = fence_match.group(1).strip()
            else:
                # Strip out trailing conversational sentences like "Then executing command: ..."
                lines = []
                for line in raw_body.split("\n"):
                    if any(line.strip().startswith(prefix) for prefix in [
                        "Then executing", "Next,", "Execute", "*** FILE:"
                    ]):
                        break
                    lines.append(line)
                code = "\n".join(lines).strip("` \n")

            if code:
                patches[rel_path] = code

        return patches

    def apply_atomic_patches(self, patches: Dict[str, str]) -> bool:
        """
        Applies changes to multiple files transactionally:
        1. Backs up original contents of all target files in memory.
        2. Writes new content to disk.
        3. Runs test verification.
        4. Restores all files if verification fails.
        """
        if not patches:
            return True

        console.print(Panel(
            f"[bold cyan]Detected Multi-File Refactor Transaction ({len(patches)} files)[/bold cyan]:\n" +
            "\n".join(f" - [yellow]{f}[/yellow]" for f in patches.keys()),
            border_style="cyan"
        ))

        # Snapshot originals for in-memory rollback
        backup = {}
        for rel_path in patches.keys():
            full_path = os.path.join(self.repo_path, rel_path)
            if os.path.exists(full_path):
                with open(full_path, "r", encoding="utf-8") as f:
                    backup[rel_path] = f.read()
            else:
                backup[rel_path] = None  # Indicates new file created

        # Apply patches
        try:
            for rel_path, new_code in patches.items():
                full_path = os.path.join(self.repo_path, rel_path)
                os.makedirs(os.path.dirname(full_path), exist_ok=True)
                with open(full_path, "w", encoding="utf-8") as f:
                    f.write(new_code)
            console.print("[bold yellow]Patches written to disk. Running automated verification suite...[/bold yellow]")
        except Exception as e:
            console.print(f"[bold red]File write failed: {e}. Initiating instant rollback.[/bold red]")
            self._restore_backup(backup)
            return False

        # Run test verification
        passed, trace = self.verifier.run_tests()
        if passed:
            console.print(Panel(
                f"[bold green]Multi-file patch verified successfully![/bold green]\n"
                f"Touched files: {', '.join(patches.keys())}",
                title="[bold green]Transaction Committed[/bold green]",
                border_style="green"
            ))
            return True
        else:
            console.print(Panel(
                f"[bold red]Tests failed after applying patches. Rolling back all files.[/bold red]\n{trace}",
                title="[bold red]Atomic Rollback Triggered[/bold red]",
                border_style="red"
            ))
            self._restore_backup(backup)
            return False

    def _restore_backup(self, backup: Dict[str, Optional[str]]):
        """Restores original files or deletes newly created ones."""
        for rel_path, original_content in backup.items():
            full_path = os.path.join(self.repo_path, rel_path)
            if original_content is None:
                if os.path.exists(full_path):
                    os.remove(full_path)
            else:
                with open(full_path, "w", encoding="utf-8") as f:
                    f.write(original_content)
        console.print("[dim]Workspace restored to pre-transaction state.[/dim]")