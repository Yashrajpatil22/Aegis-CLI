import subprocess
from typing import Tuple

class TestVerifier:
    def __init__(self, repo_path: str = "."):
        self.repo_path = repo_path

    def run_tests(self) -> Tuple[bool, str]:
        """
        Executes pytest in the current workspace.
        Returns: (passed: bool, output_trace: str)
        """
        try:
            res = subprocess.run(
                ["pytest", "-q"],
                cwd=self.repo_path,
                capture_output=True,
                text=True
            )
            passed = (res.returncode == 0)
            output = res.stdout if passed else (res.stderr + "\n" + res.stdout)
            return passed, output.strip()
        except FileNotFoundError:
            return False, "pytest is not found in the active environment path."