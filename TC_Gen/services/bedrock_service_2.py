import os
import json
import time
import re
import ast
import boto3
from botocore.config import Config
from dotenv import load_dotenv

# ----------------------------------------------------
# Load environment variables
# ----------------------------------------------------
load_dotenv()


class BedrockService:
    """
    Enterprise-grade Bedrock wrapper:
    - SSL verify disabled (corporate proxy)
    - .env credentials
    - Auto retry
    - JSON + Python-object tolerant parsing
    """

    def __init__(self):

        self.aws_access_key = os.getenv("AWS_ACCESS_KEY_ID")
        self.aws_secret_key = os.getenv("AWS_SECRET_ACCESS_KEY")
        self.aws_session_token = os.getenv("AWS_SESSION_TOKEN")
        self.region = os.getenv("AWS_REGION", "eu-west-3")

        self.model_id = os.getenv(
            "MODEL_ID",
            "eu.anthropic.claude-3-7-sonnet-20250219-v1:0"
        )

        if not self.aws_access_key or not self.aws_secret_key:
            raise RuntimeError("AWS credentials missing in .env")

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
                read_timeout=120
            )
        )

    # ----------------------------------------------------
    # 🔥 ULTIMATE PARSER (JSON + PYTHON OBJECT)
    # ----------------------------------------------------
    def _parse_llm_output(self, text: str):
        """
        1. Extract array-like content
        2. Try strict JSON
        3. Fallback to ast.literal_eval (Python/JS-style)
        """

        cleaned = (
            text.replace("```json", "")
                .replace("```", "")
                .replace("\r", " ")
                .replace("\n", " ")
                .strip()
        )

        # Extract array block
        match = re.search(r"\[.*\]", cleaned, re.DOTALL)
        if not match:
            raise ValueError("No array-like structure found in LLM output")

        block = match.group(0)

        # ---- Attempt 1: strict JSON ----
        try:
            return json.loads(block)
        except Exception:
            pass

        # ---- Attempt 2: Python literal ----
        try:
            return ast.literal_eval(block)
        except Exception as e:
            raise ValueError(
                "Model output could not be parsed as JSON or Python object.\n"
                f"Error: {e}\n"
                f"Snippet:\n{block[:1200]}"
            )

    # ----------------------------------------------------
    # Reduced prompt fallback
    # ----------------------------------------------------
    def _reduced_prompt(self):
        return """
Return ONLY a Python-style list of dictionaries.
Do NOT use line breaks inside strings.

Example:
[
 {'id':'TC-001','title':'Short title','preconditions':'Short',
  'steps':[{'action':'Do A','expected':'OK'}],
  'priority':'Medium','type':'Functional','expected_result':'OK'}
]

Generate MAX 5 test cases.
Return ONLY the list.
"""

    # ----------------------------------------------------
    # Invoke Bedrock
    # ----------------------------------------------------
    def _invoke(self, prompt, max_tokens):
        payload = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}]
        }

        response = self.client.invoke_model(
            modelId=self.model_id,
            body=json.dumps(payload).encode("utf-8")
        )

        raw = response["body"].read().decode("utf-8")
        return json.loads(raw)["content"][0]["text"]

    # ----------------------------------------------------
    # MAIN ENTRY
    # ----------------------------------------------------
    def generate_testcases(self, prompt: str):

        # Attempt 1 – full prompt
        try:
            text = self._invoke(prompt, 1600)
            return self._parse_llm_output(text)
        except Exception:
            pass

        # Attempt 2 – reduced prompt
        try:
            text = self._invoke(self._reduced_prompt(), 1000)
            return self._parse_llm_output(text)
        except Exception as e:
            raise RuntimeError(
                "Bedrock model invocation failed even after reduced prompt.\n"
                f"Root cause: {e}"
            )
