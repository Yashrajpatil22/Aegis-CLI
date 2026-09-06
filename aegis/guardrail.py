import subprocess
import re

SAFE_PATTERNS = [
    r"^ls\b", r"^dir\b", r"^cat\b", r"^grep\b", 
    r"^git\s+status\b", r"^git\s+diff\b", r"^pytest\b"
]

CRITICAL_PATTERNS = [
    r"\brm\b", r"\bdel\b", r"git\s+reset\s+--hard", 
    r"git\s+push\s+.*--force", r"\bdropdb\b"
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

    def create_shadow_stash(self) -> str | None:
        """Takes a git snapshot of working changes without disrupting HEAD."""
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