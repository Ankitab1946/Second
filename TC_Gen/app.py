import streamlit as st

from services.bedrock_service import BedrockService
from services.jira_service import JiraService
from services.xray_service import XrayService
from services.utils import (
    load_predefined_templates,
    filter_templates_by_keywords,
    build_prompt,
    validate_testcases,
    export_to_excel,
    export_to_json,
    clean_text
)

# ============================================================
# PAGE CONFIG
# ============================================================
st.set_page_config(
    page_title="AI Test Case Generator (Jira + Xray + Bedrock)",
    layout="wide"
)

st.title("🧪 AI Test Case Generator – Jira + Xray + AWS Bedrock")

# ============================================================
# SESSION STATE DEFAULTS
# ============================================================
defaults = {
    "jira_service": None,
    "connected": False,
    "story_key": None,
    "story": None,
    "testcases": None,
    "last_prompt": None,
    "last_story_key": None
}

for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ============================================================
# SIDEBAR – JIRA CONFIG
# ============================================================
st.sidebar.header("🔐 Jira Configuration")

jira_type = st.sidebar.radio("Jira Type", ["Cloud", "Data Center"])
jira_base = st.sidebar.text_input("Jira Base URL")
jira_user = st.sidebar.text_input("Username / Email")
jira_pass = st.sidebar.text_input("API Token / Password", type="password")
project_key = st.sidebar.text_input("Project Key", placeholder="PRJ")

if st.sidebar.button("Connect to Jira"):
    try:
        st.session_state["jira_service"] = JiraService(
            base_url=jira_base,
            username=jira_user,
            password=jira_pass,
            jira_type=jira_type.lower()
        )
        st.session_state["connected"] = True
        st.sidebar.success("Connected to Jira")
    except Exception as e:
        st.sidebar.error(f"Connection failed: {e}")

# ============================================================
# BEDROCK SERVICE
# ============================================================
bedrock = BedrockService()

# ============================================================
# STORY SELECTION
# ============================================================
st.sidebar.header("📌 Story Selection")
story_mode = st.sidebar.radio("Select Method", ["Enter Story Key", "Search Story"])

jira = st.session_state["jira_service"]

if st.session_state["connected"] and jira:

    if story_mode == "Enter Story Key":
        manual_key = st.sidebar.text_input("Enter Story Key", placeholder="PRJ-2093")

        if st.sidebar.button("Fetch Story"):
            issue = jira.get_issue(manual_key)

            st.session_state["story_key"] = manual_key
            st.session_state["story"] = issue

            # 🔥 Clear old data
            st.session_state["testcases"] = None
            st.session_state["last_prompt"] = None
            st.session_state["last_story_key"] = manual_key

            st.success(f"Story {manual_key} loaded")

# ============================================================
# DISPLAY STORY
# ============================================================
if st.session_state["story"]:
    story = st.session_state["story"]

    st.subheader(f"📖 Story: {st.session_state['story_key']}")
    st.write("### Summary")
    st.write(story["fields"]["summary"])

    st.write("### Description")
    st.write(story["fields"].get("description", ""))

# ============================================================
# GENERATE TEST CASES
# ============================================================
st.header("🧠 Generate Test Cases")

if st.session_state["story"]:
    uploaded_templates = st.file_uploader(
        "Upload Predefined Test Case Templates (CSV / Excel)",
        type=["csv", "xlsx"]
    )

    keywords_input = st.text_input(
        "Keywords (comma separated)",
        placeholder="count check, reconciliation"
    )

    if st.button("Generate Test Cases"):

        story = st.session_state["story"]

        summary = clean_text(story["fields"]["summary"])
        description = clean_text(story["fields"].get("description", ""))

        # Acceptance Criteria (example custom field)
        acceptance_criteria = clean_text(
            story["fields"].get("customfield_15900", "")
        )

        # Comments
        comments_text = ""
        try:
            comments = story["fields"]["comment"]["comments"]
            comments_text = " ".join([clean_text(c["body"]) for c in comments])
        except Exception:
            pass

        full_requirement_text = f"""
SUMMARY:
{summary}

DESCRIPTION:
{description}

ACCEPTANCE CRITERIA:
{acceptance_criteria}

COMMENTS:
{comments_text}
"""

        keywords = [k.strip() for k in keywords_input.split(",") if k.strip()]

        templates = load_predefined_templates(uploaded_templates)
        templates_filtered = filter_templates_by_keywords(
            templates,
            keywords,
            full_requirement_text
        )

        prompt = build_prompt(
            summary=summary,
            jira_description=full_requirement_text,
            keywords=keywords,
            templates=templates_filtered
        )

        should_regenerate = (
            st.session_state["last_prompt"] != prompt or
            st.session_state["last_story_key"] != st.session_state["story_key"]
        )

        if should_regenerate:
            raw = bedrock.generate_testcases(prompt)
            testcases = validate_testcases(raw)

            st.session_state["testcases"] = testcases
            st.session_state["last_prompt"] = prompt
            st.session_state["last_story_key"] = st.session_state["story_key"]

            st.success(f"Generated {len(testcases)} test cases")
        else:
            st.info("Test cases already generated for this story")

# ============================================================
# DISPLAY GENERATED TEST CASES
# ============================================================
if st.session_state["testcases"]:
    st.header("📝 Generated Test Cases")

    for tc in st.session_state["testcases"]:
        with st.expander(tc["title"]):
            st.json(tc)

    st.download_button(
        "⬇️ Download Excel",
        export_to_excel(st.session_state["testcases"]),
        file_name="testcases.xlsx"
    )

    st.download_button(
        "⬇️ Download JSON",
        export_to_json(st.session_state["testcases"]),
        file_name="testcases.json"
    )
