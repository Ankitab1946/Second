import os
import json
import re
import ast
import boto3
from botocore.config import Config
from dotenv import load_dotenv

load_dotenv()


class BedrockService:
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

    # ---------------------------------------------------
    # Safe parse (JSON or Python list)
    # ---------------------------------------------------
    def _parse_output(self, text: str):
        cleaned = (
            text.replace("```json", "")
                .replace("```", "")
                .replace("\n", " ")
                .replace("\r", " ")
        )

        match = re.search(r"\[.*\]", cleaned, re.DOTALL)
        if not match:
            raise ValueError("No complete list found in model output")

        block = match.group(0)

        try:
            return json.loads(block)
        except Exception:
            return ast.literal_eval(block)

    # ---------------------------------------------------
    # Single invocation
    # ---------------------------------------------------
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

    # ---------------------------------------------------
    # 🔥 CHUNKED GENERATION (FINAL FIX)
    # ---------------------------------------------------
    def generate_testcases(self, prompt: str):
        """
        Generates ETL test cases in SAFE CHUNKS to avoid truncation.
        """

        all_tests = []

        # Ask model how many test cases to generate first
        plan_prompt = prompt + "\n\nFirst, decide how many test cases are needed. Respond with a single number."
        plan_text = self._invoke(plan_prompt, max_tokens=50)

        try:
            total = int(re.findall(r"\d+", plan_text)[0])
        except Exception:
            total = 10  # safe default

        batch_size = 5
        batches = max(1, (total + batch_size - 1) // batch_size)

        for i in range(batches):
            batch_prompt = f"""
{prompt}

Generate ONLY test cases {i * batch_size + 1}
to {min((i + 1) * batch_size, total)}.

Return ONLY a list.
"""

            try:
                text = self._invoke(batch_prompt, max_tokens=1200)
                batch_tests = self._parse_output(text)
                all_tests.extend(batch_tests)
            except Exception as e:
                raise RuntimeError(
                    f"Failed during batch {i + 1}. "
                    f"Likely model truncation.\nError: {e}"
                )

        if not all_tests:
            raise RuntimeError("Model did not generate any valid test cases")

        return all_tests
