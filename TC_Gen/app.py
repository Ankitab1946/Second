import streamlit as st
import json
import os
import pandas as pd

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
# STREAMLIT PAGE CONFIG
# ============================================================
st.set_page_config(
    page_title="AI Test Case Generator (Xray + Jira + AWS Bedrock)",
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
    "testcases": None
}

if "last_prompt" not in st.session_state:
    st.session_state["last_prompt"] = None

if "last_story_key" not in st.session_state:
    st.session_state["last_story_key"] = None

for key, value in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = value

# ============================================================
# SIDEBAR — JIRA CONFIGURATION
# ============================================================
st.sidebar.header("🔐 Jira Configuration")

jira_type = st.sidebar.radio("Jira Type", ["Cloud", "Data Center"])
jira_base = st.sidebar.text_input("Jira Base URL", placeholder="https://yourcompany.atlassian.net")
jira_user = st.sidebar.text_input("Jira Username / Email")
jira_pass = st.sidebar.text_input("API Token / Password", type="password")
project_key = st.sidebar.text_input("Jira Project Key", placeholder="ABC")

if not jira_base or not jira_user or not jira_pass or not project_key:
    st.sidebar.warning("Enter all Jira configuration values.")

# ============================================================
# SIDEBAR — CONNECT TO JIRA BUTTON
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
        st.sidebar.success("Connected to Jira successfully!")
    except Exception as e:
        st.sidebar.error(f"Jira Connection Failed: {str(e)}")
        st.session_state["connected"] = False

# ============================================================
# SIDEBAR — AWS BEDROCK CONFIG
# ============================================================
st.sidebar.header("🤖 AWS Bedrock")

MODEL_ID = "eu.anthropic.claude-3-7-sonnet-20250219-v1:0"
REGION = "eu-west-3"

st.sidebar.write(f"Model: `{MODEL_ID}`")
st.sidebar.write(f"Region: `{REGION}`")

bedrock = BedrockService(model_id=MODEL_ID, region=REGION)

# ============================================================
# SIDEBAR — STORY SELECTION MODE
# ============================================================
st.sidebar.header("📌 Story Selection")

story_mode = st.sidebar.radio("Select Story Method", ["Enter Story Key", "Search Story"])

# ============================================================
# STORY FETCHING + SEARCH
# ============================================================

jira_service = st.session_state["jira_service"]

if st.session_state["connected"] and jira_service:

    # --------------------------------------------------------
    # OPTION A — Enter Story Key Manually
    # --------------------------------------------------------
    if story_mode == "Enter Story Key":
        manual_key = st.sidebar.text_input("Enter Story Key", placeholder="PRJ-2093")

        # if st.sidebar.button("Fetch Story"):
        #     try:
        #         issue = jira_service.get_issue(manual_key)
        #         st.session_state["story_key"] = manual_key
        #         st.session_state["story"] = issue
        #         st.success(f"Story {manual_key} loaded successfully.")
        #     except Exception as e:
        #         st.error(f"Failed to load story: {str(e)}")

        if st.sidebar.button("Fetch Story"):
            try:
                issue = jira_service.get_issue(manual_key)
        
                # Store new story
                st.session_state["story_key"] = manual_key
                st.session_state["story"] = issue
        
                # 🔥 FIX-1: CLEAR OLD GENERATED DATA
                st.session_state["testcases"] = None
                st.session_state["last_prompt"] = None
                st.session_state["last_story_key"] = manual_key
        
                st.success(f"Story {manual_key} loaded successfully.")
            except Exception as e:
                st.error(f"Failed to load story: {str(e)}")


    # --------------------------------------------------------
    # OPTION B — Search Story
    # --------------------------------------------------------
    else:
        search_type = st.sidebar.radio("Search By", ["Project", "Summary Text", "JQL"])

        # ----------------- Project Search -------------------
        if search_type == "Project":
            if st.sidebar.button("Search Issues"):
                try:
                    issues = jira_service.search_issues_by_project(project_key, issue_type="Story")
                    issue_list = [f"{i['key']} - {i['fields']['summary']}" for i in issues.get("issues", [])]

                    if issue_list:
                        selected_issue = st.sidebar.selectbox("Select Story", issue_list)
                        if selected_issue:
                            selected_key = selected_issue.split(" ")[0]
                            issue = jira_service.get_issue(selected_key)
                            st.session_state["story_key"] = selected_key
                            st.session_state["story"] = issue
                            st.success(f"Story {selected_key} loaded successfully.")
                except Exception as e:
                    st.error(f"Search failed: {str(e)}")

        # ----------------- Summary Text Search -------------------
        elif search_type == "Summary Text":
            text_query = st.sidebar.text_input("Search Keyword")

            if st.sidebar.button("Search by Text"):
                try:
                    issues = jira_service.search_issues_by_summary(project_key, text_query)
                    issue_list = [f"{i['key']} - {i['fields']['summary']}" for i in issues.get("issues", [])]

                    if issue_list:
                        selected_issue = st.sidebar.selectbox("Select Story", issue_list)
                        if selected_issue:
                            selected_key = selected_issue.split(" ")[0]
                            issue = jira_service.get_issue(selected_key)
                            st.session_state["story_key"] = selected_key
                            st.session_state["story"] = issue
                            st.success(f"Story {selected_key} loaded successfully.")
                except Exception as e:
                    st.error(f"Search failed: {str(e)}")

        # ----------------- JQL Search -------------------
        else:
            jql = st.sidebar.text_input("Enter JQL", placeholder='project = "PRJ" AND type = Story')

            if st.sidebar.button("Run JQL"):
                try:
                    issues = jira_service.search_issues_jql(jql)
                    issue_list = [f"{i['key']} - {i['fields']['summary']}" for i in issues.get("issues", [])]

                    if issue_list:
                        selected_issue = st.sidebar.selectbox("Select Story", issue_list)
                        if selected_issue:
                            selected_key = selected_issue.split(" ")[0]
                            issue = jira_service.get_issue(selected_key)
                            st.session_state["story_key"] = selected_key
                            st.session_state["story"] = issue
                            st.success(f"Story {selected_key} loaded successfully.")
                except Exception as e:
                    st.error(f"JQL failed: {str(e)}")

# ============================================================
# DISPLAY LOADED STORY
# ============================================================
if st.session_state["story"]:

    story = st.session_state["story"]

    st.subheader(f"📖 Story: {st.session_state['story_key']}")

    st.write("### Summary")
    st.write(story["fields"]["summary"])

    st.write("### Description")
    st.write(story["fields"].get("description", "No description."))

# ============================================================
# TEST CASE GENERATION SECTION
# ============================================================

st.header("🧠 Generate Test Cases")

if st.session_state["story"]:

    uploaded_templates = st.file_uploader(
        "Upload Predefined Test Case Templates (CSV or Excel)",
        type=["csv", "xlsx"]
    )

    keywords_input = st.text_input("Enter Keywords (comma-separated)", placeholder="login, authentication, negative")

    # if st.button("Generate Test Cases"):
    #     try:
    #         # -------------------------------------------
    #         # Prepare Inputs
    #         # -------------------------------------------
    #         keywords = [k.strip() for k in keywords_input.split(",") if k.strip()]

    #         summary = clean_text(st.session_state["story"]["fields"]["summary"])
    #         description = clean_text(st.session_state["story"]["fields"].get("description", ""))

    #         # -------------------------------------------
    #         # Templates
    #         # -------------------------------------------
    #         templates = load_predefined_templates(uploaded_templates)
    #         filtered = filter_templates_by_keywords(templates, keywords, summary + description)

    #         # -------------------------------------------
    #         # Build AI Prompt
    #         # -------------------------------------------
    #         prompt = build_prompt(summary, description, keywords, filtered)

    #         # -------------------------------------------
    #         # Call AWS Bedrock (Claude Sonnet 3.7)
    #         # -------------------------------------------
    #         raw_output = bedrock.generate_testcases(prompt)

    #         testcases = validate_testcases(raw_output)

    #         st.session_state["testcases"] = testcases
    #         st.success(f"Generated {len(testcases)} test cases successfully!")

    #     except Exception as e:
    #         st.error(f"Test Case Generation Failed: {str(e)}")
if st.button("Generate Test Cases"):

    # Build prompt (depends on story + keywords + templates)
    prompt = build_prompt(
        summary,
        description,
        keywords,
        templates_filtered
    )

    # 🔥 FIX-2: Force regeneration when context changes
    should_regenerate = (
        st.session_state["last_prompt"] != prompt or
        st.session_state["last_story_key"] != st.session_state["story_key"]
    )

    if should_regenerate:
        try:
            raw_output = bedrock.generate_testcases(prompt)
            testcases = validate_testcases(raw_output)

            st.session_state["testcases"] = testcases
            st.session_state["last_prompt"] = prompt
            st.session_state["last_story_key"] = st.session_state["story_key"]

            st.success(f"Generated {len(testcases)} test cases.")

        except Exception as e:
            st.error(f"Test Case generation failed: {e}")

    else:
        st.info("Test cases already generated for this story and inputs.")

# ============================================================
# DISPLAY GENERATED TEST CASES
# ============================================================

if st.session_state["testcases"]:
    testcases = st.session_state["testcases"]

    st.header("📝 Generated Test Cases")

    for tc in testcases:
        with st.expander(tc["title"]):
            st.json(tc)

    # -------------------------------------------
    # Download: Excel export
    # -------------------------------------------
    st.download_button(
        "⬇️ Download as Excel",
        data=export_to_excel(testcases),
        file_name="generated_testcases.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

    # -------------------------------------------
    # Download: JSON export
    # -------------------------------------------
    st.download_button(
        "⬇️ Download as JSON",
        data=export_to_json(testcases),
        file_name="generated_testcases.json",
        mime="application/json"
    )


# ============================================================
# XRAY PUSH SECTION
# ============================================================

st.header("🚀 Push Generated Test Cases to Jira Xray")

if st.session_state["story"] and st.session_state["testcases"] and st.session_state["connected"]:

    # Instantiate Xray Service
    xray = XrayService(
        jira=st.session_state["jira_service"],
        project_key=project_key,
        xray_test_issue_type="Xray Test",
        xray_testset_issue_type="Test Set"
    )

    st.subheader("🧩 Test Set Options")

    testset_mode = st.radio("Choose Test Set Mode", ["Create New Test Set", "Use Existing Test Set"])

    testset_key = None

    # --------------------------------------------------------
    # OPTION A — Create New Test Set
    # --------------------------------------------------------
    if testset_mode == "Create New Test Set":

        default_name = f"{st.session_state['story_key']}-TestSet"
        new_testset_name = st.text_input("New Test Set Name", value=default_name)

        if st.button("Create Test Set"):
            try:
                testset_key = xray.create_testset(new_testset_name)
                xray.link_testset_to_story(testset_key, st.session_state["story_key"])
                st.success(f"Created Test Set: {testset_key}")
            except Exception as e:
                st.error(f"Failed to create Test Set: {str(e)}")

    # --------------------------------------------------------
    # OPTION B — Select Existing Test Set
    # --------------------------------------------------------
    else:
        try:
            results = st.session_state["jira_service"].search_issues_by_project(project_key, issue_type="Test Set")
            options = [f"{i['key']} - {i['fields']['summary']}" for i in results.get("issues", [])]

            if options:
                selection = st.selectbox("Select Existing Test Set", options)
                if selection:
                    testset_key = selection.split(" ")[0]

        except Exception as e:
            st.error(f"Error loading Test Sets: {str(e)}")

    # --------------------------------------------------------
    # PUSH TEST CASES TO XRAY
    # --------------------------------------------------------
    if testset_key:

        if st.button("Push Test Cases to Xray"):
            pushed_tests = []

            try:
                for tc in st.session_state["testcases"]:

                    # ------------------------------------
                    # 1️⃣ Create Xray Test Issue
                    # ------------------------------------
                    test_key = xray.create_xray_test(
                        summary=tc["title"],
                        description=tc.get("preconditions", "")
                    )
                    pushed_tests.append(test_key)

                    # ------------------------------------
                    # 2️⃣ Add Steps
                    # ------------------------------------
                    steps_formatted = []
                    for step in tc["steps"]:
                        steps_formatted.append({
                            "action": step.get("action") or "",
                            "expected": step.get("expected") or tc.get("expected_result", "")
                        })

                    xray.add_test_steps(test_key, steps_formatted)

                    # ------------------------------------
                    # 3️⃣ Link Test → Story
                    # ------------------------------------
                    xray.link_test_to_story(test_key, st.session_state["story_key"])

                # ----------------------------------------
                # 4️⃣ Add all Tests → Test Set
                # ----------------------------------------
                xray.add_tests_to_testset(testset_key, pushed_tests)

                st.success(f"Successfully pushed {len(pushed_tests)} tests to Xray!")

            except Exception as e:
                st.error(f"Error pushing tests to Xray: {str(e)}")
