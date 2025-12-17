import os
import json
import time
import re
import boto3
from botocore.config import Config
from botocore.exceptions import ClientError, BotoCoreError
from dotenv import load_dotenv

# ---------------------------------------------------------------------
# Load environment variables from .env
# ---------------------------------------------------------------------
load_dotenv()


class BedrockService:
    """
    Robust AWS Bedrock wrapper for Claude 3.7 Sonnet (EU)

    Features:
    - Loads credentials from .env
    - Supports AWS_SESSION_TOKEN
    - SSL verification disabled (corporate proxy safe)
    - Hardened JSON extraction & repair
    - Retry + backoff
    """

    def __init__(self):

        # -------------------------------------------------------------
        # Load AWS credentials
        # -------------------------------------------------------------
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
                "Missing AWS credentials. "
                "Set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY in .env"
            )

        # -------------------------------------------------------------
        # Create boto3 session
        # -------------------------------------------------------------
        session = boto3.Session(
            aws_access_key_id=self.aws_access_key,
            aws_secret_access_key=self.aws_secret_key,
            aws_session_token=self.aws_session_token,
            region_name=self.region
        )

        # -------------------------------------------------------------
        # Bedrock Runtime Client (SSL verify disabled)
        # -------------------------------------------------------------
        self.client = session.client(
            "bedrock-runtime",
            verify=False,  # 🔥 FIX for corporate SSL
            config=Config(
                retries={"max_attempts": 3, "mode": "standard"},
                read_timeout=120,
                connect_timeout=30
            )
        )

    # -----------------------------------------------------------------
    # 🔥 HARDENED JSON EXTRACTOR & REPAIR
    # -----------------------------------------------------------------
    def _safe_json_parse(self, text: str):
        """
        Extracts and repairs JSON from LLM output.
        Handles:
        - Extra text
        - Unterminated strings
        - Newlines inside values
        - Markdown fences
        """

        # Remove markdown fences
        cleaned = (
            text.replace("```json", "")
                .replace("```", "")
                .strip()
        )

        # Extract first JSON array
        match = re.search(r"\[\s*{.*?}\s*]", cleaned, re.DOTALL)
        if not match:
            raise ValueError("No JSON array found in model output.")

        json_text = match.group(0)

        # Normalize whitespace
        json_text = json_text.replace("\r", " ").replace("\n", " ")

        # Fix smart quotes if any
        json_text = json_text.replace("“", '"').replace("”", '"')

        # Attempt strict parse
        try:
            return json.loads(json_text)
        except json.JSONDecodeError:
            pass

        # Escape unescaped quotes inside values (best-effort)
        json_text = re.sub(r'(?<!\\)"(?=[^:,}\]])', r'\"', json_text)

        try:
            return json.loads(json_text)
        except json.JSONDecodeError as e:
            raise ValueError(
                "Model returned malformed JSON that could not be repaired.\n"
                f"Error: {str(e)}\n"
                f"Snippet:\n{json_text[:1500]}"
            )

    # -----------------------------------------------------------------
    # MAIN: Invoke Bedrock Claude
    # -----------------------------------------------------------------
    def generate_testcases(self, prompt: str, max_tokens: int = 2500, retries: int = 3):
        """
        Calls Claude Sonnet and returns parsed JSON test cases.
        """

        payload = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": max_tokens,
            "messages": [
                {"role": "user", "content": prompt}
            ]
        }

        last_error = None

        for attempt in range(1, retries + 1):
            try:
                response = self.client.invoke_model(
                    modelId=self.model_id,
                    body=json.dumps(payload).encode("utf-8")
                )

                raw = response["body"].read().decode("utf-8")
                parsed = json.loads(raw)

                model_text = parsed["content"][0]["text"]

                return self._safe_json_parse(model_text)

            except (ClientError, BotoCoreError, ValueError) as e:
                last_error = e
                time.sleep(attempt * 1.5)

        raise RuntimeError(
            f"Bedrock model invocation failed after {retries} attempts: {last_error}"
        )
