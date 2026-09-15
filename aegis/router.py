import os
import re
import ollama
from typing import Tuple, List, Dict
from rich.console import Console

console = Console()

class HybridRouter:
    def __init__(
        self,
        local_model: str = "qwen2.5-coder:3b",
        cloud_model: str = "llama-3.3-70b-versatile",
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
        if attempt_count > 1:
            return "CLOUD"

        prompt_lower = prompt.lower()
        for pattern in self.cloud_triggers:
            if re.search(pattern, prompt_lower):
                return "CLOUD"

        return "LOCAL"

    def query_local(self, messages: List[Dict[str, str]]) -> str:
        try:
            response = ollama.chat(model=self.local_model, messages=messages)
            return response.message.content
        except Exception as e:
            return f"Local SLM Error: {e}"

    def query_cloud(self, messages: List[Dict[str, str]]) -> str:
        if not self.cloud_api_key:
            console.print("[bold yellow][Router Warning][/bold yellow] No GROQ_API_KEY detected. Falling back to local SLM.")
            return self.query_local(messages)

        try:
            from openai import OpenAI
            client = OpenAI(
                base_url="https://api.groq.com/openai/v1",
                api_key=self.cloud_api_key
            )
            response = client.chat.completions.create(
                model=self.cloud_model,
                messages=messages
            )
            return response.choices[0].message.content
        except Exception as e:
            console.print(f"[bold red][Cloud Error][/bold red] {e}. Falling back to local SLM.")
            return self.query_local(messages)

    def route_and_generate(self, messages: List[Dict[str, str]], prompt_hint: str = "", attempt_count: int = 1) -> Tuple[str, str]:
        tier = self.classify_complexity(prompt_hint, attempt_count=attempt_count)

        if tier == "CLOUD":
            with console.status(f"[bold magenta]Routing to Cloud Tier (Groq: {self.cloud_model})...[/bold magenta]"):
                reply = self.query_cloud(messages)
                return reply, "CLOUD"
        else:
            with console.status(f"[bold cyan]Routing to Local SLM ({self.local_model})...[/bold cyan]"):
                reply = self.query_local(messages)
                return reply, "LOCAL"