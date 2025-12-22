# import os
# import json
# import re
# import ast
# import boto3
# from botocore.config import Config
# from dotenv import load_dotenv

# load_dotenv()


# class BedrockService:
#     def __init__(self):
#         self.region = os.getenv("AWS_REGION", "eu-west-3")
#         self.model_id = os.getenv(
#             "MODEL_ID",
#             "eu.anthropic.claude-3-7-sonnet-20250219-v1:0"
#         )

#         session = boto3.Session(
#             aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
#             aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
#             aws_session_token=os.getenv("AWS_SESSION_TOKEN"),
#             region_name=self.region
#         )

#         self.client = session.client(
#             "bedrock-runtime",
#             verify=False,
#             config=Config(read_timeout=120)
#         )

#     # ---------------------------------------------------
#     # Safe parse (JSON or Python list)
#     # ---------------------------------------------------
#     def _parse_output(self, text: str):
#         cleaned = (
#             text.replace("```json", "")
#                 .replace("```", "")
#                 .replace("\n", " ")
#                 .replace("\r", " ")
#         )

#         match = re.search(r"\[.*\]", cleaned, re.DOTALL)
#         if not match:
#             raise ValueError("No complete list found in model output")

#         block = match.group(0)

#         try:
#             return json.loads(block)
#         except Exception:
#             return ast.literal_eval(block)

#     # ---------------------------------------------------
#     # Single invocation
#     # ---------------------------------------------------
#     def _invoke(self, prompt, max_tokens):
#         payload = {
#             "anthropic_version": "bedrock-2023-05-31",
#             "max_tokens": max_tokens,
#             "messages": [{"role": "user", "content": prompt}]
#         }

#         response = self.client.invoke_model(
#             modelId=self.model_id,
#             body=json.dumps(payload).encode("utf-8")
#         )

#         raw = response["body"].read().decode("utf-8")
#         return json.loads(raw)["content"][0]["text"]

#     # ---------------------------------------------------
#     # 🔥 CHUNKED GENERATION (FINAL FIX)
#     # ---------------------------------------------------
#     def generate_testcases(self, prompt: str):
#         """
#         Generates ETL test cases in SAFE CHUNKS to avoid truncation.
#         """

#         all_tests = []

#         # Ask model how many test cases to generate first
#         plan_prompt = prompt + "\n\nFirst, decide how many test cases are needed. Respond with a single number."
#         plan_text = self._invoke(plan_prompt, max_tokens=50)

#         try:
#             total = int(re.findall(r"\d+", plan_text)[0])
#         except Exception:
#             total = 10  # safe default

#         batch_size = 5
#         batches = max(1, (total + batch_size - 1) // batch_size)

#         for i in range(batches):
#             batch_prompt = f"""
# {prompt}

# Generate ONLY test cases {i * batch_size + 1}
# to {min((i + 1) * batch_size, total)}.

# Return ONLY a list.
# """

#             try:
#                 text = self._invoke(batch_prompt, max_tokens=1200)
#                 batch_tests = self._parse_output(text)
#                 all_tests.extend(batch_tests)
#             except Exception as e:
#                 raise RuntimeError(
#                     f"Failed during batch {i + 1}. "
#                     f"Likely model truncation.\nError: {e}"
#                 )

#         if not all_tests:
#             raise RuntimeError("Model did not generate any valid test cases")

#         return all_tests

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
    Production-grade Bedrock service for structured ETL test case generation.

    Features:
    - .env-based AWS credentials
    - SSL verify disabled (corporate certs)
    - Claude output normalization (JSON / Python list)
    - Truncation-safe batch generation
    - Progressive fallback (batch → single → hard template)
    """

    # ---------------------------------------------------------
    # INIT
    # ---------------------------------------------------------
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
            verify=False,  # corporate SSL
            config=Config(read_timeout=120)
        )

    # ---------------------------------------------------------
    # LOW-LEVEL INVOKE
    # ---------------------------------------------------------
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
        return json.loads(raw)["content"][0]["text"]

    # ---------------------------------------------------------
    # SAFE OUTPUT PARSER
    # ---------------------------------------------------------
    def _parse_output(self, text: str):
        """
        Extracts and parses JSON / Python list from model output.
        """

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
            result = json.loads(block)
        except Exception:
            result = ast.literal_eval(block)

        if isinstance(result, dict):
            return [result]

        if not isinstance(result, list):
            raise ValueError("Parsed output is not a list")

        return result

    # ---------------------------------------------------------
    # 🔥 FINAL, TRUNCATION-SAFE GENERATION
    # ---------------------------------------------------------
    def generate_testcases(self, prompt: str):
        """
        Generates ETL test cases with full truncation protection.

        Strategy:
        1. Ask model for total test count
        2. Generate in batches
        3. On failure → single test fallback
        4. On failure → hard-coded minimal ETL test
        """

        all_tests = []

        # -------------------------------
        # STEP 1: Decide test count
        # -------------------------------
        plan_prompt = (
            prompt
            + "\n\nFirst decide how many ETL test cases are required. "
            + "Respond with ONLY a number."
        )

        try:
            plan_text = self._invoke(plan_prompt, max_tokens=50)
            total = int(re.findall(r"\d+", plan_text)[0])
        except Exception:
            total = 10  # safe default

        # -------------------------------
        # STEP 2: Progressive batching
        # -------------------------------
        batch_size = 5
        index = 1

        while index <= total:
            end = min(index + batch_size - 1, total)

            batch_prompt = f"""
{prompt}

Generate ETL test cases {index} to {end}.
Return ONLY a list.
"""

            try:
                text = self._invoke(batch_prompt, max_tokens=1200)
                batch_tests = self._parse_output(text)
                all_tests.extend(batch_tests)
                index = end + 1
                continue

            except Exception:
                # -----------------------------------------
                # FALLBACK 1: Single test generation
                # -----------------------------------------
                try:
                    single_prompt = f"""
{prompt}

Generate ONLY ONE ETL test case (number {index}).
Return ONLY a list with one item.
"""
                    text = self._invoke(single_prompt, max_tokens=600)
                    single_test = self._parse_output(text)
                    all_tests.extend(single_test)
                    index += 1
                    continue

                except Exception:
                    # -----------------------------------------
                    # FALLBACK 2: Hard-coded ETL template
                    # -----------------------------------------
                    hard_prompt = """
Generate ONE ETL test case.
Return EXACTLY this format:

[
  {
    "id": "TC-X",
    "title": "ETL record count validation",
    "preconditions": "Source and target datasets exist",
    "steps": [
      {
        "action": "Compare record count between source and target",
        "expected": "Record counts must match"
      }
    ],
    "priority": "High",
    "type": "ETL",
    "expected_result": "Data validation successful"
  }
]
"""
                    text = self._invoke(hard_prompt, max_tokens=400)
                    single_test = self._parse_output(text)
                    all_tests.extend(single_test)
                    index += 1
                    continue

        if not all_tests:
            raise RuntimeError("Model failed to generate any valid ETL test cases")

        return all_tests
