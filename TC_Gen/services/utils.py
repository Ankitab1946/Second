import json
import pandas as pd
from io import BytesIO


def clean_text(text):
    return " ".join(str(text).split())


def load_predefined_templates(uploaded_file):
    if not uploaded_file:
        return []

    if uploaded_file.name.endswith(".csv"):
        df = pd.read_csv(uploaded_file)
    else:
        df = pd.read_excel(uploaded_file)

    return df.fillna("").to_dict(orient="records")


def filter_templates_by_keywords(templates, keywords, jira_text):
    if not templates or not keywords:
        return []

    results = []
    jira_text = jira_text.lower()
    keywords = [k.lower() for k in keywords]

    for t in templates:
        score = 0
        searchable = " ".join([
            str(t.get("FeatureKeyword", "")),
            str(t.get("TestCaseTitle", "")),
            str(t.get("Category", "")),
            str(t.get("Tags", "")),
        ]).lower()

        for kw in keywords:
            if kw in searchable:
                score += 2
            if kw in jira_text:
                score += 1

        if score > 0:
            t["_match_score"] = score
            results.append(t)

    results.sort(key=lambda x: x["_match_score"], reverse=True)
    return results


def build_prompt(summary, jira_description, keywords, templates, test_type):
    template_block = ""
    for t in templates:
        template_block += f"""
ETL TEMPLATE:
Type: {t.get('FeatureKeyword')}
Description: {t.get('TestCaseTitle')}
Steps: {t.get('Steps')}
Expected: {t.get('ExpectedResult')}
---
"""

    return f"""
YOU ARE A SENIOR ETL / DATA QUALITY TEST ENGINEER.

STRICT RULES:
- DO NOT generate UI, login, security, or browser tests
- ONLY generate ETL / DATA VALIDATION test cases

ALLOWED TEST TYPES:
- Count Check
- Source to Target Reconciliation
- Aggregation Check (SUM, AVG, MIN, MAX)
- Distinct / Duplicate Check
- Null / Mandatory Check
- Range / Threshold Check
- Data Type Validation

REQUIREMENTS:
{jira_description}

KEYWORDS:
{", ".join(keywords)}

PREDEFINED ETL TEMPLATES:
{template_block}

Generate test cases based on complexity:
- Simple ETL → 6–8 tests
- Medium ETL → 10–15 tests
- Complex ETL → 15–25 tests

OUTPUT FORMAT (Python list or JSON):
[
  {{
    "id": "TC-001",
    "title": "Count check between source and target",
    "preconditions": "Source and target tables are loaded",
    "steps": [
      {{
        "action": "Compare record count between SRC_TABLE and TGT_TABLE",
        "expected": "Counts must match"
      }}
    ],
    "priority": "High",
    "type": "ETL",
    "expected_result": "Data validation successful"
  }}
]

RETURN ONLY THE LIST.
"""


def validate_testcases(data):
    if not isinstance(data, list):
        raise ValueError("AI output is not a list")

    cleaned = []

    for i, tc in enumerate(data, start=1):
        if not isinstance(tc, dict):
            continue

        steps = []
        for s in tc.get("steps", []):
            if isinstance(s, dict):
                steps.append({
                    "action": s.get("action") or s.get("actions", ""),
                    "expected": s.get("expected") or s.get("Expected", "")
                })

        cleaned.append({
            "id": tc.get("id", f"TC-{i:03d}"),
            "title": tc.get("title", f"ETL Test Case {i}"),
            "preconditions": clean_text(tc.get("preconditions", "")),
            "steps": steps,
            "priority": tc.get("priority", "High"),
            "type": "ETL",
            "expected_result": tc.get("expected_result", "")
        })

    if not cleaned:
        raise ValueError("No valid ETL test cases generated")

    return cleaned


def export_to_excel(testcases):
    df = pd.DataFrame(testcases)
    buffer = BytesIO()
    df.to_excel(buffer, index=False)
    buffer.seek(0)
    return buffer


def export_to_json(testcases):
    return json.dumps(testcases, indent=2)
