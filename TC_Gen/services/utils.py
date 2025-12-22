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
    """
    ETL MODE IS MANDATORY.
    Jira text is used for DATA CONTEXT ONLY and cannot override ETL intent.
    """

    # 1️⃣ ETL AUTHORITY (HIGHEST PRIORITY)
    etl_authority = """
YOU ARE A SENIOR ETL / DATA QUALITY TEST ENGINEER.

THIS IS A DATA PIPELINE VALIDATION TASK.
THIS IS NOT APPLICATION OR UI TESTING.

JIRA TEXT IS PROVIDED ONLY TO UNDERSTAND:
- DATA ENTITIES
- BUSINESS RULES
- TRANSFORMATION LOGIC

THE TESTING DOMAIN MUST NEVER CHANGE FROM ETL / DATA QUALITY.
"""

    # 2️⃣ ETL TEST TAXONOMY
    etl_test_taxonomy = """
ALLOWED ETL / DATA QUALITY TEST TYPES:
1. Record Count Validation
2. Source-to-Target Reconciliation
3. Aggregation Validation (SUM, COUNT, AVG, MIN, MAX)
4. Duplicate / Distinct Validation
5. Null / Mandatory Column Validation
6. Data Type Validation
7. Range / Threshold Validation
8. Referential Integrity Validation
9. Historical vs Current Data Comparison
"""

    # 3️⃣ TEMPLATE CONTEXT
    template_block = ""
    for t in templates:
        template_block += f"""
ETL TEMPLATE:
Validation Type: {t.get('FeatureKeyword')}
Description: {t.get('TestCaseTitle')}
Steps: {t.get('Steps')}
Expected Result: {t.get('ExpectedResult')}
---
"""

    # 4️⃣ FINAL PROMPT (ETL FIRST, JIRA SECOND)
    return f"""
{etl_authority}

{etl_test_taxonomy}

PREDEFINED ETL TEST PATTERNS:
{template_block}

JIRA REQUIREMENTS (DATA CONTEXT ONLY):
{jira_description}

KEYWORDS:
{", ".join(keywords)}

GENERATION RULES:
- Generate ONLY ETL / Data Quality test cases
- Use Jira text only to identify tables, files, columns, and rules
- Each test case MUST mention:
  • Source and target
  • Columns involved
  • Validation logic
  • Expected data result

TEST COUNT GUIDANCE:
- Simple ETL → 6–8 test cases
- Medium ETL → 10–15 test cases
- Complex ETL → 15–25 test cases

OUTPUT FORMAT:
Return ONLY a Python list of dictionaries OR a valid JSON list.

EXAMPLE:
[
  {{
    "id": "TC-001",
    "title": "Record count validation between source and target",
    "preconditions": "Source and target datasets are available",
    "steps": [
      {{
        "action": "Compare record count between SRC_TABLE and TGT_TABLE",
        "expected": "Record counts must match exactly"
      }}
    ],
    "priority": "High",
    "type": "ETL",
    "expected_result": "Data consistency validated"
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
