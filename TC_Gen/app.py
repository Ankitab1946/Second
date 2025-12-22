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
    page_title="AI ETL / Data Quality Test Case Generator",
    layout="wide"
)

st.title("🧪 AI ETL / Data Quality Test Case Generator")

# ============================================================
# SESSION STATE
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
# SIDEBAR — JIRA CONFIG
# ============================================================
st.sidebar.header("🔐 Jira Configuration")

jira_base = st.sidebar.text_input("Jira Base URL")
jira_user = st.sidebar.text_input("Username / Email")
jira_pass = st.sidebar.text_input("API Token / Password", type="password")

if st.sidebar.button("Connect to Jira"):
    try:
        st.session_state["jira_service"] = JiraService(
            base_url=jira_base,
            username=jira_user,
            password=jira_pass
        )
        st.session_state["connected"] = True
        st.sidebar.success("Connected to Jira")
    except Exception as e:
        st.sidebar.error(f"Connection failed: {e}")

# ============================================================
# SERVICES
# ============================================================
bedrock = BedrockService()
jira = st.session_state["jira_service"]

# ============================================================
# STORY FETCH
# ============================================================
st.sidebar.header("📌 Story Selection")

if st.session_state["connected"] and jira:
    story_key_input = st.sidebar.text_input(
        "Enter Story Key",
        placeholder="PRJ-2091"
    )

    if st.sidebar.button("Fetch Story"):
        issue = jira.get_issue(story_key_input)

        st.session_state["story_key"] = story_key_input
        st.session_state["story"] = issue

        # Reset old data
        st.session_state["testcases"] = None
        st.session_state["last_prompt"] = None
        st.session_state["last_story_key"] = story_key_input

        st.success(f"Story {story_key_input} loaded")

# ============================================================
# DISPLAY STORY
# ============================================================
if st.session_state["story"]:
    story = st.session_state["story"]

    st.subheader(f"📖 Story: {st.session_state['story_key']}")

    st.markdown("### Summary")
    st.write(story["fields"]["summary"])

    st.markdown("### Description")
    st.write(story["fields"].get("description", ""))

# ============================================================
# GENERATE ETL TEST CASES
# ============================================================
st.header("🧠 Generate ETL / Data Quality Test Cases")

if st.session_state["story"]:

    uploaded_templates = st.file_uploader(
        "Upload ETL Test Templates (CSV / Excel)",
        type=["csv", "xlsx"]
    )

    keywords_input = st.text_input(
        "ETL Keywords (comma separated)",
        placeholder="count, reconciliation, aggregation, distinct, null"
    )

    if st.button("Generate Test Cases"):

        story = st.session_state["story"]

        summary = clean_text(story["fields"]["summary"])
        description = clean_text(story["fields"].get("description", ""))

        acceptance_criteria = clean_text(
            story["fields"].get("customfield_15900", "")
        )

        comments_text = ""
        try:
            comments = story["fields"]["comment"]["comments"]
            comments_text = " ".join(clean_text(c["body"]) for c in comments)
        except Exception:
            pass

        full_req = f"""
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
            full_req
        )

        test_type = "ETL_DQ_ONLY"

        prompt = build_prompt(
            summary,
            full_req,
            keywords,
            templates_filtered,
            test_type
        )

        if (
            st.session_state["last_prompt"] != prompt or
            st.session_state["last_story_key"] != st.session_state["story_key"]
        ):
            with st.spinner("Generating ETL test cases..."):
                raw = bedrock.generate_testcases(prompt)
                testcases = validate_testcases(raw)

            st.session_state["testcases"] = testcases
            st.session_state["last_prompt"] = prompt
            st.session_state["last_story_key"] = st.session_state["story_key"]

            st.success(f"Generated {len(testcases)} ETL test cases")

# ============================================================
# DISPLAY GENERATED TEST CASES
# ============================================================
if st.session_state["testcases"]:
    st.header("📋 Generated ETL Test Cases")

    for tc in st.session_state["testcases"]:
        with st.expander(tc["title"]):
            st.json(tc)

    col1, col2 = st.columns(2)

    with col1:
        st.download_button(
            "⬇️ Download Excel",
            export_to_excel(st.session_state["testcases"]),
            file_name="etl_testcases.xlsx"
        )

    with col2:
        st.download_button(
            "⬇️ Download JSON",
            export_to_json(st.session_state["testcases"]),
            file_name="etl_testcases.json"
        )

# ============================================================
# 🚀 PUSH TO XRAY (FINAL STRUCTURE)
# ============================================================
st.header("🚀 Push ETL Test Cases to Jira Xray")

if st.session_state["testcases"] and st.session_state["connected"]:

    project_key = st.text_input(
        "Jira Project Key (Xray)",
        value=st.session_state["story_key"].split("-")[0]
    )

    xray = XrayService(
        jira=st.session_state["jira_service"],
        project_key=project_key
    )

    testset_name = st.text_input(
        "Test Set Name",
        value=f"{st.session_state['story_key']}-ETL-TestSet"
    )

    if st.button("Push Test Cases to Xray"):
        try:
            # 1. Create ONE Test Set
            with st.spinner("Creating Test Set..."):
                testset_key = xray.create_testset(testset_name)

            # 2. Link Test Set → Story (Tested By)
            with st.spinner("Linking Test Set to Story..."):
                xray.link_testset_to_story(
                    testset_key,
                    st.session_state["story_key"]
                )

            created_tests = []

            # 3. Create Tests + Steps
            with st.spinner("Creating Tests and adding steps..."):
                for tc in st.session_state["testcases"]:
                    test_key = xray.create_xray_test(
                        title=tc["title"],
                        preconditions=tc.get("preconditions", "")
                    )
                    xray.add_test_steps(test_key, tc["steps"])
                    created_tests.append(test_key)

            # 4. Add Tests → Test Set
            with st.spinner("Adding Tests to Test Set..."):
                xray.add_tests_to_testset(testset_key, created_tests)

            st.success(
                f"✅ Story {st.session_state['story_key']} is TESTED BY "
                f"Test Set {testset_key} containing {len(created_tests)} ETL tests"
            )

        except Exception as e:
            st.error(f"❌ Xray push failed: {e}")
