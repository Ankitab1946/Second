import os
import json
import re
import ast
import boto3
from botocore.config import Config
from dotenv import load_dotenv

load_dotenv()


class BedrockService:
    """
    Stable Bedrock wrapper with:
    - .env credentials
    - SSL verify disabled
    - JSON + Python-object tolerant parsing
    - Reduced-prompt fallback only if needed
    """

    def __init__(self):
        self.region = os.getenv("AWS_REGION", "eu-west-3")
        self.model_id = os.getenv(
            "MODEL_ID",
            "eu.anthropic.claude-3-7-sonnet-20250219-v1:0"
        )

        session = boto3.Session(
            aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
            aws_session_token=os.getenv("AWS_SESSION_TOKEN"),
            region_name=self.region
        )

        self.client = session.client(
            "bedrock-runtime",
            verify=False,
            config=Config(read_timeout=120)
        )

    def _parse_output(self, text: str):
        cleaned = (
            text.replace("```json", "")
                .replace("```", "")
                .replace("\n", " ")
                .replace("\r", " ")
        )

        match = re.search(r"\[.*\]", cleaned, re.DOTALL)
        if not match:
            raise ValueError("No array found in output")

        block = match.group(0)

        try:
            return json.loads(block)
        except Exception:
            return ast.literal_eval(block)

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

    def _reduced_prompt(self):
        return """
Return a Python list of dictionaries only.
Max 5 test cases.
No line breaks in strings.
"""

    def generate_testcases(self, prompt: str):

        try:
            text = self._invoke(prompt, max_tokens=3000)
            return self._parse_output(text)
        except Exception as first_error:
            text = self._invoke(self._reduced_prompt(), max_tokens=1200)
            return self._parse_output(text)
