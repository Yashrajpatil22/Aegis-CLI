import os
import re
from typing import List, Dict, Tuple
import httpx
from rich.console import Console
from dotenv import load_dotenv

load_dotenv()
console = Console()

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

class HybridRouter:
    def __init__(
        self,
        local_model: str = "qwen2.5-coder:3b",
        cloud_model: str = "openai/gpt-oss-20b",
    ):
        self.local_model = local_model
        self.cloud_model = cloud_model
        self.cloud_api_key = (
            os.getenv("GROQ_API_KEY")
            or os.getenv("AEGIS_CLOUD_API_KEY")
            or os.getenv("OPENAI_API_KEY")
        )

        self.cloud_triggers = [
            r"\brefactor\b",
            r"\barchitect\w*\b",
            r"\bmultiple files\b",
            r"\bmigrat\w*\b",
            r"\boptimize whole\b",
            r"\bdesign pattern\b"
        ]

    def classify_complexity(self, prompt: str, attempt_count: int = 1) -> str:
        """Determines whether a prompt requires the Cloud Frontier model or Local SLM."""
        if attempt_count > 1:
            return "CLOUD"

        prompt_lower = prompt.lower()
        cloud_keywords = [
            "refactor", "architecture", "microservice", 
            "across multiple files", "multiple files", 
            "test_math.py", "and test", "and add a test", "and add corresponding"
        ]

        # Multi-file heuristic: contains multiple file names or explicit conjunctions
        py_files_mentioned = re.findall(r"\b[\w_]+\.py\b", prompt_lower)
        if len(py_files_mentioned) >= 2 or any(k in prompt_lower for k in cloud_keywords):
            return "CLOUD"

        return "LOCAL"

    def query_local(self, messages: List[Dict[str, str]]) -> str:
        try:
            response = ollama.chat(model=self.local_model, messages=messages)
            return response.message.content
        except Exception as e:
            return f"Local SLM Error: {e}"

    def query_cloud(self, messages: List[Dict[str, str]]) -> str:
        if not self.cloud_api_key or OpenAI is None:
            console.print("[bold yellow][Router Warning][/bold yellow] Groq key or OpenAI library missing. Falling back to local SLM.", highlight=False)
            return self.query_local(messages)

        try:
            # Enforce strict 8-second hard socket timeouts across connect, read, and write
            timeout_config = httpx.Timeout(8.0, connect=4.0)
            http_client = httpx.Client(timeout=timeout_config)

            client = OpenAI(
                base_url="https://api.groq.com/openai/v1",
                api_key=self.cloud_api_key,
                http_client=http_client,
                max_retries=0
            )

            response = client.chat.completions.create(
                model=self.cloud_model,
                messages=messages,
                max_tokens=600,
                temperature=0.2
            )
            return response.choices[0].message.content or ""
        except Exception as e:
            console.print(f"\n[bold red][Cloud Error / Timeout][/bold red] {str(e)[:100]}. Falling back to local SLM.", highlight=False)
            return self.query_local(messages)

    def route_and_generate(
        self,
        messages: List[Dict[str, str]],
        prompt_hint: str = "",
        attempt_count: int = 1
    ) -> Tuple[str, str]:
        tier = self.classify_complexity(prompt_hint, attempt_count)

        # Trim conversation history to System Prompt + last 3 turns
        trimmed_messages = [messages[0]] + messages[-3:] if len(messages) > 4 else messages

        console.print(f"[dim]⚡ Routing to {tier} Tier ({self.cloud_model if tier == 'CLOUD' else self.local_model})...[/dim]")

        if tier == "CLOUD":
            try:
                reply = self.query_cloud(trimmed_messages)
            except Exception as e:
                console.print(f"[bold red][Cloud Failover][/bold red] {str(e)[:120]}. Using Local SLM.", highlight=False)
                reply = self.query_local(trimmed_messages)
                tier = "LOCAL"
        else:
            reply = self.query_local(trimmed_messages)

        return reply, tier