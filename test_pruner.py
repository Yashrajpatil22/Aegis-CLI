from aegis.pruner import ASTPruner

# A sample messy, long python script with dense inner logic
sample_code = """
import os
import sys
from typing import List, Optional

class DatabaseManager:
    \"\"\"Manages database connections.\"\"\"
    def __init__(self, db_url: str):
        self.db_url = db_url
        self.connected = False
        print("Connecting to DB...")
        # Imagine 100 lines of complex connection logic here
        self.connected = True

    def query(self, sql: str, params: Optional[dict] = None) -> List[dict]:
        # 50 lines of cursor logic, transaction commits, error handling
        result = []
        return result

def calculate_discount(price: float, rate: float = 0.1) -> float:
    # 20 lines of business validation logic
    if price < 0:
        raise ValueError("Invalid price")
    return price * (1 - rate)
"""

pruner = ASTPruner()
skeleton = pruner.extract_skeleton(sample_code)

print("=== RAW CODE LENGTH ===")
print(f"Characters: {len(sample_code)}")

print("\n=== PRUNED CODE SKELETON (What the AI will see) ===")
print(skeleton)

print("\n=== PRUNED CODE LENGTH ===")
print(f"Characters: {len(skeleton)}")
print(f"Token/Character Reduction: {((len(sample_code) - len(skeleton)) / len(sample_code)) * 100:.1f}%")