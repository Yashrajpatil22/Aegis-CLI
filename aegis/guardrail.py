import subprocess
import re
from typing import Tuple, Optional

SAFE_PATTERNS = [
    r"^ls\b", r"^dir\b", r"^cat\b", r"^type\b", r"^grep\b", r"^findstr\b",
    r"^git\s+status\b", r"^git\s+diff\b", r"^pytest\b", r"^python\s+-m\s+pytest\b"
]

CRITICAL_PATTERNS = [
    r"\brm\b", r"\bdel\b", r"\berase\b", r"\brmdir\b",
    r"git\s+reset\s+--hard", r"git\s+push\s+.*--force", 
    r"\bdropdb\b", r"\bformat\b"
]

class GuardrailEngine:
    def __init__(self, repo_path: str = "."):
        self.repo_path = repo_path

    def classify(self, cmd: str) -> str:
        cmd_clean = cmd.strip()
        for pattern in CRITICAL_PATTERNS:
            if re.search(pattern, cmd_clean):
                return "CRITICAL"
        for pattern in SAFE_PATTERNS:
            if re.search(pattern, cmd_clean):
                return "SAFE"
        return "MUTATIVE"

    def create_shadow_stash(self) -> Optional[str]:
        """Takes a git snapshot of uncommitted working changes without disrupting HEAD."""
        try:
            res = subprocess.run(
                ["git", "stash", "create"],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                check=True
            )
            sha = res.stdout.strip()
            return sha if sha else None
        except (subprocess.CalledProcessError, FileNotFoundError):
            return None

    def rollback(self, stash_sha: str) -> bool:
        """Restores the workspace to the captured shadow stash commit."""
        try:
            subprocess.run(
                ["git", "stash", "apply", stash_sha],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                check=True
            )
            return True
        except subprocess.CalledProcessError:
            return False

    def execute_command(self, cmd: str) -> Tuple[bool, str, str]:
        """
        Executes a command through the guardrail safety pipeline.
        Returns: (success_bool, stdout/stderr_message, safety_category)
        """
        category = self.classify(cmd)
        stash_sha = None

        if category in ["MUTATIVE", "CRITICAL"]:
            stash_sha = self.create_shadow_stash()

        if category == "CRITICAL":
            confirm = input(f"\n[AEGIS SECURITY ALERT] '{cmd}' is flagged CRITICAL. Allow execution? (y/N): ")
            if confirm.strip().lower() != "y":
                return False, "Command aborted by user.", category

        # Prevent unittest discovery from recursing into venv/packages
        clean_cmd = cmd.strip()
        if clean_cmd.startswith("python -m unittest discover") and "-s" not in clean_cmd:
            clean_cmd = "python -m unittest discover -s . -p \"test_*.py\""

        try:
            # Execute with DEVNULL to eliminate stdin deadlocks, and enforce a 15s timeout
            result = subprocess.run(
                clean_cmd,
                shell=True,
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                stdin=subprocess.DEVNULL,
                timeout=15.0
            )
            output = result.stdout if result.returncode == 0 else (result.stderr or result.stdout)
            return (result.returncode == 0), output, category

        except subprocess.TimeoutExpired:
            if stash_sha:
                self.rollback(stash_sha)
            return False, f"Execution timed out after 15s: '{cmd}'. Workspace rolled back.", category

        except Exception as e:
            if stash_sha:
                self.rollback(stash_sha)
            return False, f"Execution failed: {str(e)}. Workspace rolled back.", category