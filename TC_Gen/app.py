import streamlit as st
import os

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

# ============================================================
# CONNECT TO JIRA
# ============================================================
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

story_mode = st.sidebar.radio(
    "Select Method",
    ["Enter Story Key", "Search Story"]
)

jira = st.session_state["jira_service"]

if st.session_state["connected"] and jira:

    # -----------------------------
    # MANUAL STORY KEY
    # -----------------------------
    if story_mode == "Enter Story Key":
        manual_key = st.sidebar.text_input("Enter Story Key", placeholder="PRJ-2093")

        if st.sidebar.button("Fetch Story"):
            try:
                issue = jira.get_issue(manual_key)

                st.session_state["story_key"] = manual_key
                st.session_state["story"] = issue

                # 🔥 RESET OLD DATA
                st.session_state["testcases"] = None
                st.session_state["last_prompt"] = None
                st.session_state["last_story_key"] = manual_key

                st.success(f"Story {manual_key} loaded")
            except Exception as e:
                st.error(f"Failed to fetch story: {e}")

    # -----------------------------
    # SEARCH STORY
    # -----------------------------
    else:
        search_text = st.sidebar.text_input("Search Summary Text")

        if st.sidebar.button("Search"):
            try:
                results = jira.search_issues_by_summary(project_key, search_text)
                issues = results.get("issues", [])

                options = [f"{i['key']} - {i['fields']['summary']}" for i in issues]

                if options:
                    selected = st.sidebar.selectbox("Select Story", options)
                    if selected:
                        key = selected.split(" ")[0]
                        issue = jira.get_issue(key)

                        st.session_state["story_key"] = key
                        st.session_state["story"] = issue

                        # 🔥 RESET OLD DATA
                        st.session_state["testcases"] = None
                        st.session_state["last_prompt"] = None
                        st.session_state["last_story_key"] = key

                        st.success(f"Story {key} loaded")

            except Exception as e:
                st.error(f"Search failed: {e}")

# ============================================================
# DISPLAY STORY
# ============================================================
if st.session_state["story"]:
    story = st.session_state["story"]

    st.subheader(f"📖 Story: {st.session_state['story_key']}")
    st.write("### Summary")
    st.write(story["fields"]["summary"])

    st.write("### Description")
    st.write(story["fields"].get("description", "No description"))

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

        summary = clean_text(story["fields"]["summary"])
        description = clean_text(story["fields"].get("description", ""))
        keywords = [k.strip() for k in keywords_input.split(",") if k.strip()]

        templates = load_predefined_templates(uploaded_templates)
        templates_filtered = filter_templates_by_keywords(
            templates,
            keywords,
            summary + " " + description
        )

        prompt = build_prompt(
            summary,
            description,
            keywords,
            templates_filtered
        )

        # 🔥 FORCE REGENERATION WHEN CONTEXT CHANGES
        should_regenerate = (
            st.session_state["last_prompt"] != prompt or
            st.session_state["last_story_key"] != st.session_state["story_key"]
        )

        if should_regenerate:
            try:
                raw = bedrock.generate_testcases(prompt)
                testcases = validate_testcases(raw)

                st.session_state["testcases"] = testcases
                st.session_state["last_prompt"] = prompt
                st.session_state["last_story_key"] = st.session_state["story_key"]

                st.success(f"Generated {len(testcases)} test cases")

            except Exception as e:
                st.error(f"Test case generation failed: {e}")
        else:
            st.info("Test cases already generated for this story & inputs")

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

# ============================================================
# XRAY PUSH
# ============================================================
st.header("🚀 Push to Jira Xray")

if st.session_state["story"] and st.session_state["testcases"] and st.session_state["connected"]:

    xray = XrayService(
        jira=st.session_state["jira_service"],
        project_key=project_key
    )

    mode = st.radio("Test Set Mode", ["Create New Test Set", "Use Existing Test Set"])
    testset_key = None

    if mode == "Create New Test Set":
        name = st.text_input("Test Set Name", value=f"{st.session_state['story_key']}-TestSet")

        if st.button("Create Test Set"):
            try:
                testset_key = xray.create_testset(name)
                xray.link_testset_to_story(testset_key, st.session_state["story_key"])
                st.success(f"Created Test Set {testset_key}")
            except Exception as e:
                st.error(e)

    else:
        results = jira.search_issues_by_project(project_key, "Test Set")
        options = [f"{i['key']} - {i['fields']['summary']}" for i in results.get("issues", [])]
        if options:
            selection = st.selectbox("Select Test Set", options)
            testset_key = selection.split(" ")[0]

    if testset_key and st.button("Push Test Cases to Xray"):
        try:
            created = []

            for tc in st.session_state["testcases"]:
                key = xray.create_xray_test(tc["title"], tc.get("preconditions", ""))
                xray.add_test_steps(key, tc["steps"])
                xray.link_test_to_story(key, st.session_state["story_key"])
                created.append(key)

            xray.add_tests_to_testset(testset_key, created)
            st.success(f"Pushed {len(created)} tests to Xray")

        except Exception as e:
            st.error(f"Xray push failed: {e}")
