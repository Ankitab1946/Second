import os
import json
import time
import re
import boto3
from botocore.config import Config
from botocore.exceptions import ClientError, BotoCoreError
from dotenv import load_dotenv

# ---------------------------------------------------------------------
# Load environment variables
# ---------------------------------------------------------------------
load_dotenv()


class BedrockService:
    """
    Production-grade AWS Bedrock wrapper with:
    - .env credential loading
    - SSL verify disabled (corporate proxy safe)
    - Hardened JSON extraction
    - Automatic retry with reduced prompt
    """

    def __init__(self):

        # -----------------------------
        # AWS config
        # -----------------------------
        self.aws_access_key = os.getenv("AWS_ACCESS_KEY_ID")
        self.aws_secret_key = os.getenv("AWS_SECRET_ACCESS_KEY")
        self.aws_session_token = os.getenv("AWS_SESSION_TOKEN")
        self.region = os.getenv("AWS_REGION", "eu-west-3")

        self.model_id = os.getenv(
            "MODEL_ID",
            "eu.anthropic.claude-3-7-sonnet-20250219-v1:0"
        )

        if not self.aws_access_key or not self.aws_secret_key:
            raise RuntimeError(
                "Missing AWS credentials. Check .env file."
            )

        session = boto3.Session(
            aws_access_key_id=self.aws_access_key,
            aws_secret_access_key=self.aws_secret_key,
            aws_session_token=self.aws_session_token,
            region_name=self.region
        )

        self.client = session.client(
            "bedrock-runtime",
            verify=False,  # corporate SSL fix
            config=Config(
                retries={"max_attempts": 3, "mode": "standard"},
                read_timeout=120,
                connect_timeout=30
            )
        )

    # -----------------------------------------------------------------
    # HARDENED JSON PARSER
    # -----------------------------------------------------------------
    def _safe_json_parse(self, text: str):

        cleaned = (
            text.replace("```json", "")
                .replace("```", "")
                .strip()
        )

        match = re.search(r"\[\s*{.*?}\s*]", cleaned, re.DOTALL)
        if not match:
            raise ValueError("No JSON array found in model output.")

        json_text = match.group(0)

        json_text = (
            json_text.replace("\r", " ")
                     .replace("\n", " ")
                     .replace("“", '"')
                     .replace("”", '"')
        )

        try:
            return json.loads(json_text)
        except json.JSONDecodeError:
            pass

        # Best-effort quote repair
        json_text = re.sub(r'(?<!\\)"(?=[^:,}\]])', r'\"', json_text)

        try:
            return json.loads(json_text)
        except json.JSONDecodeError as e:
            raise ValueError(
                "Model returned malformed JSON that could not be repaired.\n"
                f"Error: {e}\n"
                f"Snippet:\n{json_text[:1200]}"
            )

    # -----------------------------------------------------------------
    # REDUCED PROMPT (SAFE FALLBACK)
    # -----------------------------------------------------------------
    def _build_reduced_prompt(self, original_prompt: str) -> str:
        """
        Aggressively simplified prompt used when JSON fails.
        """

        return f"""
You MUST return VALID JSON only.

STRICT RULES:
- Generate MAXIMUM 5 test cases
- Use SIMPLE sentences only
- NO line breaks inside strings
- NO quotes inside text
- SHORT titles and steps
- DO NOT truncate output

JSON FORMAT:
[
  {{
    "id": "TC-001",
    "title": "Short title",
    "preconditions": "Short text",
    "steps": [
      {{"action": "Do something", "expected": "Result"}},
      {{"action": "Do next thing", "expected": "Result"}}
    ],
    "priority": "Medium",
    "type": "Functional",
    "expected_result": "Overall result"
  }}
]

RETURN JSON ONLY.
"""

    # -----------------------------------------------------------------
    # INVOKE MODEL
    # -----------------------------------------------------------------
    def _invoke(self, prompt: str, max_tokens: int):

        payload = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": max_tokens,
            "messages": [
                {"role": "user", "content": prompt}
            ]
        }

        response = self.client.invoke_model(
            modelId=self.model_id,
            body=json.dumps(payload).encode("utf-8")
        )

        raw = response["body"].read().decode("utf-8")
        parsed = json.loads(raw)
        return parsed["content"][0]["text"]

    # -----------------------------------------------------------------
    # MAIN ENTRY POINT
    # -----------------------------------------------------------------
    def generate_testcases(self, prompt: str, max_tokens: int = 1800, retries: int = 2):
        """
        1️⃣ Try full prompt
        2️⃣ If JSON fails → retry with reduced prompt
        """

        last_error = None

        # -----------------------------
        # Attempt 1: Full prompt
        # -----------------------------
        try:
            text = self._invoke(prompt, max_tokens)
            return self._safe_json_parse(text)
        except Exception as e:
            last_error = e

        # -----------------------------
        # Attempt 2: Reduced prompt
        # -----------------------------
        try:
            reduced_prompt = self._build_reduced_prompt(prompt)
            text = self._invoke(reduced_prompt, 1200)
            return self._safe_json_parse(text)
        except Exception as e:
            last_error = e

        raise RuntimeError(
            "Bedrock model invocation failed after retry with reduced prompt.\n"
            f"Last error: {last_error}"
        )
