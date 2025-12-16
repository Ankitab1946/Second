# # import os
# # import json
# # import boto3
# # import botocore
# # from botocore.exceptions import BotoCoreError, ClientError
# # import time


# # class BedrockService:
# #     """
# #     AWS Bedrock Service wrapper for Claude 3.7 Sonnet (EU Model)
# #     Model ID: eu.anthropic.claude-3-7-sonnet-20250219-v1:0
# #     Region: eu-west-3
# #     """

# #     def __init__(self, model_id: str = "eu.anthropic.claude-3-7-sonnet-20250219-v1:0", region: str = "eu-west-3"):
# #         self.model_id = model_id
# #         self.region = region

# #         # Read AWS creds automatically from ENV variables
# #         # AWS_ACCESS_KEY_ID
# #         # AWS_SECRET_ACCESS_KEY
# #         # AWS_REGION
# #         self.client = boto3.client(
# #             "bedrock-runtime",
# #             region_name=self.region
# #         )

# #     # ----------------------------------------------------------------------
# #     # Helper: ensure model returns valid JSON
# #     # ----------------------------------------------------------------------
# #     def fix_json(self, response_text: str):
# #         """
# #         Try correcting invalid JSON returned by the model.
# #         Ensures robust parsing.
# #         """
# #         try:
# #             return json.loads(response_text)
# #         except json.JSONDecodeError:
# #             try:
# #                 # Attempt common fixes:
# #                 # - Remove surrounding ```json fences
# #                 cleaned = (
# #                     response_text.replace("```json", "")
# #                     .replace("```", "")
# #                     .strip()
# #                 )
# #                 return json.loads(cleaned)
# #             except Exception:
# #                 raise ValueError("Model returned invalid JSON format. Enable debug to inspect raw output.")

# #     # ----------------------------------------------------------------------
# #     # Core: Call Claude with retries
# #     # ----------------------------------------------------------------------
# #     def generate_testcases(self, prompt: str, max_tokens: int = 4000, retries: int = 3):
# #         """
# #         Sends prompt to Claude Sonnet model and returns JSON output.

# #         :param prompt: Full instruction string for Claude
# #         :param max_tokens: output token limit
# #         :param retries: retry count on failure
# #         :return: parsed JSON list of test cases
# #         """

# #         bedrock_payload = {
# #             "anthropic_version": "bedrock-2023-05-31",
# #             "max_tokens": max_tokens,
# #             "messages": [
# #                 {"role": "user", "content": prompt}
# #             ]
# #         }

# #         for attempt in range(1, retries + 1):
# #             try:
# #                 response = self.client.invoke_model(
# #                     modelId=self.model_id,
# #                     body=json.dumps(bedrock_payload).encode("utf-8")
# #                 )

# #                 raw = response["body"].read().decode("utf-8")

# #                 # Bedrock text is inside { "content": [{ "text": "..." }] }
# #                 parsed = json.loads(raw)

# #                 if "content" not in parsed:
# #                     raise ValueError("Unexpected Bedrock response format.")

# #                 model_text = parsed["content"][0].get("text", "")

# #                 # Ensure valid JSON
# #                 return self.fix_json(model_text)

# #             except (ClientError, BotoCoreError, ValueError) as e:
# #                 if attempt == retries:
# #                     raise RuntimeError(f"Bedrock model call failed after {retries} attempts: {str(e)}")
# #                 time.sleep(1.5 * attempt)  # exponential backoff
# #                 continue

# #         raise RuntimeError("Unexpected error in BedrockService.generate_testcases")


# # # --------------------------------------------------------------------------
# # # Standalone usage example (for debugging)
# # # --------------------------------------------------------------------------
# # if __name__ == "__main__":
# #     svc = BedrockService()

# #     sample_prompt = """
# #     Produce JSON:
# #     [
# #       {"id": "TC-1", "title": "Sample", "steps": ["a", "b"], "expected": "OK"}
# #     ]
# #     """

# #     print("Sending prompt...")
# #     out = svc.generate_testcases(sample_prompt)
# #     print("Model Output:", out)

# import os
# import json
# import time
# import boto3
# from botocore.exceptions import ClientError, BotoCoreError
# from dotenv import load_dotenv

# # -------------------------------------------------------------------
# # Load .env file into environment variables
# # -------------------------------------------------------------------
# load_dotenv()


# class BedrockService:
#     """
#     AWS Bedrock wrapper for Claude Sonnet 3.7 (EU Model)
#     Automatically loads AWS credentials and MODEL_ID from .env or environment.
#     """

#     def __init__(self):

#         # -------------------------------------------------------------
#         # Load AWS Credentials from environment or .env file
#         # -------------------------------------------------------------
#         self.aws_access_key = os.getenv("AWS_ACCESS_KEY_ID")
#         self.aws_secret_key = os.getenv("AWS_SECRET_ACCESS_KEY")
#         self.aws_session_token = os.getenv("AWS_SESSION_TOKEN")  # optional (for temp creds)
#         self.region = os.getenv("AWS_REGION", "eu-west-3")

#         # -------------------------------------------------------------
#         # Load Model ID
#         # -------------------------------------------------------------
#         self.model_id = os.getenv(
#             "MODEL_ID",
#             "eu.anthropic.claude-3-7-sonnet-20250219-v1:0"
#         )

#         # -------------------------------------------------------------
#         # Validate AWS credentials
#         # -------------------------------------------------------------
#         if not self.aws_access_key or not self.aws_secret_key:
#             raise RuntimeError(
#                 "AWS credentials are missing.\n"
#                 "Ensure AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY exist in your .env file or environment variables."
#             )

#         # -------------------------------------------------------------
#         # Create a boto3 Session with explicit credentials
#         # -------------------------------------------------------------
#         session = boto3.Session(
#             aws_access_key_id=self.aws_access_key,
#             aws_secret_access_key=self.aws_secret_key,
#             aws_session_token=self.aws_session_token,
#             region_name=self.region
#         )

#         # Instantiate Bedrock Runtime Client
#         self.client = session.client("bedrock-runtime")

#     # -------------------------------------------------------------------
#     # Fix common JSON output issues from Bedrock models
#     # -------------------------------------------------------------------
#     def fix_json(self, text: str):
#         """
#         Cleans and parses model output into valid JSON.
#         Handles cases where model returns ```json fences.
#         """
#         try:
#             return json.loads(text)
#         except json.JSONDecodeError:
#             try:
#                 cleaned = (
#                     text.replace("```json", "")
#                         .replace("```", "")
#                         .strip()
#                 )
#                 return json.loads(cleaned)
#             except Exception as e:
#                 raise ValueError(f"Unable to parse JSON from model output: {str(e)}")

#     # -------------------------------------------------------------------
#     # Main method: call Claude Sonnet 3.7
#     # -------------------------------------------------------------------
#     def generate_testcases(self, prompt: str, max_tokens: int = 4096, retries: int = 3):
#         """
#         Sends prompt to Bedrock Claude Sonnet and retrieves structured JSON output.
#         """

#         body = {
#             "anthropic_version": "bedrock-2023-05-31",
#             "max_tokens": max_tokens,
#             "messages": [
#                 {"role": "user", "content": prompt}
#             ]
#         }

#         for attempt in range(1, retries + 1):
#             try:
#                 response = self.client.invoke_model(
#                     modelId=self.model_id,
#                     body=json.dumps(body).encode("utf-8")
#                 )

#                 raw = response["body"].read().decode("utf-8")
#                 parsed = json.loads(raw)

#                 # Extract Bedrock text output
#                 model_text = parsed["content"][0]["text"]

#                 # Convert model output into JSON
#                 return self.fix_json(model_text)

#             except (ClientError, BotoCoreError, ValueError) as e:

#                 if attempt == retries:
#                     raise RuntimeError(
#                         f"Bedrock model invocation failed after {retries} attempts: {str(e)}"
#                     )

#                 # Retry with exponential backoff
#                 time.sleep(attempt * 1.5)

#         raise RuntimeError("Unexpected Bedrock error.")



import os
import json
import time
import boto3
from botocore.config import Config
from botocore.exceptions import ClientError, BotoCoreError
from dotenv import load_dotenv

# Load .env variables
load_dotenv()


class BedrockService:
    """
    AWS Bedrock wrapper for Claude Sonnet 3.7 (EU Model)
    Supports:
    - .env credential loading
    - SSL verification skip (verify=False)
    """

    def __init__(self):

        # -----------------------------
        # Load AWS credentials from env
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
                "Missing AWS credentials. Please set them in .env or OS environment."
            )

        # -----------------------------
        # boto3 Session with verify=False
        # -----------------------------
        session = boto3.Session(
            aws_access_key_id=self.aws_access_key,
            aws_secret_access_key=self.aws_secret_key,
            aws_session_token=self.aws_session_token,
            region_name=self.region
        )

        # Disable SSL verification here 👇
        self.client = session.client(
            "bedrock-runtime",
            region_name=self.region,
            verify=False,   # ******** IMPORTANT ********
            config=Config(
                retries={"max_attempts": 3, "mode": "standard"}
            )
        )

    # -----------------------------
    # JSON cleanup
    # -----------------------------
    def fix_json(self, text: str):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            cleaned = (
                text.replace("```json", "")
                    .replace("```", "")
                    .strip()
            )
            return json.loads(cleaned)

    # -----------------------------
    # Invoke Model
    # -----------------------------
    def generate_testcases(self, prompt: str, max_tokens: int = 4096, retries: int = 3):
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

                text = parsed["content"][0]["text"]

                return self.fix_json(text)

            except Exception as e:
                last_error = e
                time.sleep(attempt * 1.5)

        raise RuntimeError(
            f"Bedrock model invocation failed after {retries} attempts: {last_error}"
        )
