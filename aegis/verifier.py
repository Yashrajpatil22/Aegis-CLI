import subprocess
from typing import Tuple

class TestVerifier:
    def __init__(self, repo_path: str = "."):
        self.repo_path = repo_path

    def run_tests(self, target_test: str = None) -> Tuple[bool, str]:
        """
        Runs pytest. Ignores manual test runner scripts (test_execution.py, test_pruner.py, test_guard.py).
        """
        cmd = [
            "pytest",
            "-q",
            "--ignore=test_execution.py",
            "--ignore=test_pruner.py",
            "--ignore=test_guard.py"
        ]
        
        if target_test:
            cmd.append(target_test)

        try:
            res = subprocess.run(
                cmd,
                cwd=self.repo_path,
                capture_output=True,
                text=True
            )
            passed = (res.returncode == 0)
            output = res.stdout if passed else (res.stderr + "\n" + res.stdout)
            return passed, output.strip()
        except FileNotFoundError:
            return False, "pytest is not found in the active environment path."