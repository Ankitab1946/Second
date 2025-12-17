
import json
import re
import pandas as pd
from io import BytesIO


# -------------------------------------------------------------------------
# Load predefined templates (CSV)
# -------------------------------------------------------------------------
def load_predefined_templates(uploaded_file):
    """
    Reads a CSV or Excel file uploaded by the user.

    Expected columns:
    - FeatureKeyword
    - TestCaseTitle
    - Preconditions
    - Steps
    - ExpectedResult
    - Priority
    - Type
    """
    if uploaded_file is None:
        return []

    filename = uploaded_file.name.lower()

    if filename.endswith(".csv"):
        df = pd.read_csv(uploaded_file)
    else:
        df = pd.read_excel(uploaded_file)

    df = df.fillna("")

    templates = df.to_dict(orient="records")
    return templates


# -------------------------------------------------------------------------
# Filter templates using keywords + Jira text
# -------------------------------------------------------------------------
def filter_templates_by_keywords(templates, keywords, jira_text):
    result = []
    combined = jira_text.lower() + " " + " ".join(keywords).lower()

    for t in templates:
        kw = t.get("FeatureKeyword", "")
        if kw and kw.lower() in combined:
            result.append(t)

    return result


# -------------------------------------------------------------------------
# Build AI prompt
# -------------------------------------------------------------------------
def build_prompt(jira_summary, jira_description, keywords, templates):
    """
    Builds a structured prompt for Claude Sonnet 3.7.

    Output must be JSON array:
    [
      {
        "id": "TC-001",
        "title": "",
        "preconditions": "",
        "steps": [
           {"action": "...", "expected": "..."}
        ],
        "priority": "High/Medium/Low",
        "type": "Functional/Regression"
      }
    ]
    """

    templates_text = ""
    for t in templates:
        templates_text += f"""
- Title: {t.get('TestCaseTitle')}
  Preconditions: {t.get('Preconditions')}
  Steps: {t.get('Steps')}
  Expected: {t.get('ExpectedResult')}
  Priority: {t.get('Priority')}
  Type: {t.get('Type')}
"""

    prompt = f"""
You are a senior QA Test Manager generating detailed Xray test cases.

JIRA STORY SUMMARY:
{jira_summary}

JIRA STORY DESCRIPTION:
{jira_description}

KEYWORDS:
{", ".join(keywords)}

MATCHED PREDEFINED TEST TEMPLATES:
{templates_text if templates_text else "None"}

REQUIREMENTS:
1. Generate functional & negative test cases.
2. Expand & adapt the predefined templates.
3. Ensure steps are clear, numbered, actionable.
4. Return STRICT JSON only, no commentary.

JSON FORMAT:
[
  {{
    "id": "TC-001",
    "title": "",
    "preconditions": "",
    "steps": [
      {{"action": "", "expected": ""}},
      {{"action": "", "expected": ""}}
    ],
    "priority": "Medium",
    "type": "Functional"
  }}
]

RETURN ONLY JSON.
"""

    return prompt


# -------------------------------------------------------------------------
# Validate JSON test case objects
# -------------------------------------------------------------------------
# def validate_testcases(data):
#     """
#     Ensures AI output is a list of valid test case dicts.
#     """
#     if not isinstance(data, list):
#         raise ValueError("AI output is not a list.")

#     cleaned = []

#     for idx, tc in enumerate(data, start=1):
#         if not isinstance(tc, dict):
#             continue

#         cleaned.append({
#             "id": tc.get("id") or f"TC-{idx:03d}",
#             "title": tc.get("title", "").strip(),
#             "preconditions": tc.get("preconditions", "").strip(),
#             "steps": tc.get("steps", []),
#             "priority": tc.get("priority", "Medium"),
#             "type": tc.get("type", "Functional"),
#             "expected_result": tc.get("expected_result", tc.get("expected", "")).strip()
#         })

#     return cleaned

def validate_testcases(data):
    if not isinstance(data, list):
        raise ValueError("AI output is not a list")

    cleaned = []

    for i, tc in enumerate(data, start=1):
        steps = []
        for s in tc.get("steps", []):
            steps.append({
                "action": s.get("action") or s.get("actions") or "",
                "expected": s.get("expected") or s.get("Expected") or ""
            })

        cleaned.append({
            "id": tc.get("id", f"TC-{i:03d}"),
            "title": tc.get("title", "").strip(),
            "preconditions": tc.get("preconditions", "").replace("\n", " ").strip(),
            "steps": steps,
            "priority": tc.get("priority", "Medium"),
            "type": tc.get("type", "Functional"),
            "expected_result": tc.get("expected_result", "")
        })

    return cleaned



# -------------------------------------------------------------------------
# Excel Export
# -------------------------------------------------------------------------
def export_to_excel(testcases: list):
    """
    Convert test cases to Excel binary for Streamlit download.
    """
    df = pd.DataFrame(testcases)
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="TestCases")
    output.seek(0)
    return output


# -------------------------------------------------------------------------
# JSON export helper
# -------------------------------------------------------------------------
def export_to_json(testcases):
    return json.dumps(testcases, indent=2).encode("utf-8")


# -------------------------------------------------------------------------
# Utility: Clean text for LLM
# -------------------------------------------------------------------------
def clean_text(text):
    return re.sub(r"\s+", " ", text or "").strip()
