from aegis.guardrail import GuardrailEngine

guard = GuardrailEngine()

# Test a safe command
print("--- 1. Testing SAFE command ---")
success, out, cat = guard.execute_command("git status")
print(f"Category: {cat} | Success: {success}")
print(f"Output snippet:\n{out[:120]}...\n")

# Test a mutative command that creates a dummy file
print("--- 2. Testing MUTATIVE command ---")
success, out, cat = guard.execute_command("python -c \"open('temp_test.txt', 'w').write('Aegis Guardrail Test')\"")
print(f"Category: {cat} | Success: {success}")
print("Check: 'temp_test.txt' should now exist.\n")

# Test a critical command (will prompt you y/N)
print("--- 3. Testing CRITICAL command ---")
success, out, cat = guard.execute_command("rm temp_test.txt")
print(f"Category: {cat} | Success: {success} | Message: {out.strip()}")