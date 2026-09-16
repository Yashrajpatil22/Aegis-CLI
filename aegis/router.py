import os
import re
from typing import List, Dict, Tuple
import httpx
from rich.console import Console
from dotenv import load_dotenv
import ollama
load_dotenv()
console = Console()

try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None

class HybridRouter:
    def __init__(self, repo_path: str = "."):
        self.repo_path = repo_path
        self.gemini_api_key = os.getenv("GEMINI_API_KEY")
        self.cloud_model = os.getenv("AEGIS_CLOUD_MODEL", "gemini-2.5-flash")
        self.local_model = os.getenv("AEGIS_LOCAL_MODEL", "qwen2.5-coder:3b")

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
            response = ollama.chat(
                model=self.local_model,
                messages=messages
            )
            return response["message"]["content"]
        except Exception as e:
            return f"Local SLM Error: {e}"

    def query_cloud(self, messages: List[Dict[str, str]]) -> str:
        if not self.gemini_api_key or genai is None:
            console.print("[bold yellow][Router Warning][/bold yellow] Gemini API key or SDK missing. Falling back to local SLM.", highlight=False)
            return self.query_local(messages)

        try:
            client = genai.Client(api_key=self.gemini_api_key)

            # Separate system prompt from conversational history
            system_instruction = None
            contents = []
            for msg in messages:
                if msg["role"] == "system":
                    system_instruction = msg["content"]
                else:
                    role = "user" if msg["role"] == "user" else "model"
                    contents.append(types.Content(
                        role=role,
                        parts=[types.Part.from_text(text=msg["content"])]
                    ))

            config = types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=0.2,
                max_output_tokens=1500,
                # Explicitly disable automatic function calling discovery
                tools=[],
            )

            response = client.models.generate_content(
                model=self.cloud_model,
                contents=contents,
                config=config
            )
            return response.text or ""

        except Exception as e:
            console.print(f"\n[bold red][Cloud Error][/bold red] {str(e)[:150]}. Falling back to local SLM.", highlight=False)
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