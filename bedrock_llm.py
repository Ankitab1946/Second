# app/bedrock_llm.py
import os, json
from typing import Optional

ANTHROPIC_VERSION = "bedrock-2023-05-31"

PROMPT = (
    "You are an expert BDD analyst. Convert the user's plain-English software requirement "
    "into clean, valid Gherkin using pytest-bdd style.\n"
    "- Use Feature/Scenario/Scenario Outline, Given/When/Then.\n"
    "- Keep steps atomic; avoid UI details unless required.\n"
    "- Do not add code. Output only Gherkin."
)

def _fallback_gherkin(plain_english: str) -> str:
    # Minimal deterministic Gherkin so the demo proceeds without Bedrock.
    return f'''Feature: Generated from plain English
  As a stakeholder
  I want automated acceptance tests from natural language
  So that I can validate behavior continuously

  Scenario: Auto-converted requirement
    Given the system context is ready
    When I interpret: "{plain_english.strip().replace('"','\\"')[:180]}"
    Then I produce valid Gherkin steps
'''

def english_to_gherkin(plain_english: str) -> str:
    if not plain_english or not plain_english.strip():
        raise ValueError("Empty input")
    # Try Bedrock first
    try:
        import boto3
        from botocore.exceptions import ClientError, BotoCoreError

        region = os.getenv("AWS_REGION", "us-east-1")
        model_id = os.getenv("BEDROCK_MODEL_ID", "anthropic.claude-3-5-sonnet-20240620-v1:0")
        client = boto3.client("bedrock-runtime", region_name=region)

        body = {
            "anthropic_version": ANTHROPIC_VERSION,
            "max_tokens": 800,
            "messages": [
                {"role": "user",
                 "content": [{"type": "text", "text": f"{PROMPT}\n\nRequirement:\n{plain_english}"}]}
            ],
        }

        resp = client.invoke_model(
            modelId=model_id,
            body=json.dumps(body).encode("utf-8"),
            accept="application/json",
            contentType="application/json",
        )
        payload = json.loads(resp["body"].read())
        text = "".join(
            block.get("text", "")
            for block in payload.get("content", [])
            if block.get("type") == "text"
        ).strip()

        return text or _fallback_gherkin(plain_english)

    except Exception as e:
        # Any auth/region/model access issue → graceful offline fallback
        return _fallback_gherkin(plain_english)
