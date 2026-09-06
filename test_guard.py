from aegis.guardrail import GuardrailEngine

guard = GuardrailEngine()

test_cmds = [
    "git status",
    "rm -rf /some/directory",
    "python script.py",
    "git reset --hard HEAD~1"
]

for cmd in test_cmds:
    classification = guard.classify(cmd)
    print(f"Command: {cmd:<25} -> Category: {classification}")