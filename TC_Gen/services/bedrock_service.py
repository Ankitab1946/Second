import os
import json
import boto3
import botocore
from botocore.exceptions import BotoCoreError, ClientError
import time


class BedrockService:
    """
    AWS Bedrock Service wrapper for Claude 3.7 Sonnet (EU Model)
    Model ID: eu.anthropic.claude-3-7-sonnet-20250219-v1:0
    Region: eu-west-3
    """

    def __init__(self, model_id: str = "eu.anthropic.claude-3-7-sonnet-20250219-v1:0", region: str = "eu-west-3"):
        self.model_id = model_id
        self.region = region

        # Read AWS creds automatically from ENV variables
        # AWS_ACCESS_KEY_ID
        # AWS_SECRET_ACCESS_KEY
        # AWS_REGION
        self.client = boto3.client(
            "bedrock-runtime",
            region_name=self.region
        )

    # ----------------------------------------------------------------------
    # Helper: ensure model returns valid JSON
    # ----------------------------------------------------------------------
    def fix_json(self, response_text: str):
        """
        Try correcting invalid JSON returned by the model.
        Ensures robust parsing.
        """
        try:
            return json.loads(response_text)
        except json.JSONDecodeError:
            try:
                # Attempt common fixes:
                # - Remove surrounding ```json fences
                cleaned = (
                    response_text.replace("```json", "")
                    .replace("```", "")
                    .strip()
                )
                return json.loads(cleaned)
            except Exception:
                raise ValueError("Model returned invalid JSON format. Enable debug to inspect raw output.")

    # ----------------------------------------------------------------------
    # Core: Call Claude with retries
    # ----------------------------------------------------------------------
    def generate_testcases(self, prompt: str, max_tokens: int = 4000, retries: int = 3):
        """
        Sends prompt to Claude Sonnet model and returns JSON output.

        :param prompt: Full instruction string for Claude
        :param max_tokens: output token limit
        :param retries: retry count on failure
        :return: parsed JSON list of test cases
        """

        bedrock_payload = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": max_tokens,
            "messages": [
                {"role": "user", "content": prompt}
            ]
        }

        for attempt in range(1, retries + 1):
            try:
                response = self.client.invoke_model(
                    modelId=self.model_id,
                    body=json.dumps(bedrock_payload).encode("utf-8")
                )

                raw = response["body"].read().decode("utf-8")

                # Bedrock text is inside { "content": [{ "text": "..." }] }
                parsed = json.loads(raw)

                if "content" not in parsed:
                    raise ValueError("Unexpected Bedrock response format.")

                model_text = parsed["content"][0].get("text", "")

                # Ensure valid JSON
                return self.fix_json(model_text)

            except (ClientError, BotoCoreError, ValueError) as e:
                if attempt == retries:
                    raise RuntimeError(f"Bedrock model call failed after {retries} attempts: {str(e)}")
                time.sleep(1.5 * attempt)  # exponential backoff
                continue

        raise RuntimeError("Unexpected error in BedrockService.generate_testcases")


# --------------------------------------------------------------------------
# Standalone usage example (for debugging)
# --------------------------------------------------------------------------
if __name__ == "__main__":
    svc = BedrockService()

    sample_prompt = """
    Produce JSON:
    [
      {"id": "TC-1", "title": "Sample", "steps": ["a", "b"], "expected": "OK"}
    ]
    """

    print("Sending prompt...")
    out = svc.generate_testcases(sample_prompt)
    print("Model Output:", out)

