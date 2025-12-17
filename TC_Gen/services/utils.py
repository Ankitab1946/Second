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


def build_prompt(summary, jira_description, keywords, templates):
    template_block = ""
    for t in templates:
        template_block += f"""
TEMPLATE:
Title: {t.get('TestCaseTitle')}
Steps: {t.get('Steps')}
Expected: {t.get('ExpectedResult')}
---
"""

    return f"""
You are a senior QA engineer.

REQUIREMENTS:
{jira_description}

KEYWORDS:
{", ".join(keywords)}

PREDEFINED TEMPLATES:
{template_block}

Generate test cases based on complexity:
- Simple: 5–8
- Medium: 8–15
- Complex: 15–25

Return a list of test cases in JSON or Python list format.
"""


def validate_testcases(data):
    cleaned = []

    for i, tc in enumerate(data, start=1):
        steps = []
        for s in tc.get("steps", []):
            steps.append({
                "action": s.get("action") or s.get("actions", ""),
                "expected": s.get("expected") or s.get("Expected", "")
            })

        cleaned.append({
            "id": tc.get("id", f"TC-{i:03d}"),
            "title": tc.get("title", "").strip(),
            "preconditions": clean_text(tc.get("preconditions", "")),
            "steps": steps,
            "priority": tc.get("priority", "Medium"),
            "type": tc.get("type", "Functional"),
            "expected_result": tc.get("expected_result", "")
        })

    return cleaned


def export_to_excel(testcases):
    df = pd.DataFrame(testcases)
    buffer = BytesIO()
    df.to_excel(buffer, index=False)
    buffer.seek(0)
    return buffer


def export_to_json(testcases):
    return json.dumps(testcases, indent=2)

