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


# =====================================================================
# PAGE CONFIG
# =====================================================================
st.set_page_config(
    page_title="AI Test Case Generator (Xray + Jira + AWS Bedrock)",
    layout="wide"
)

st.title("🧪 AI Test Case Generator – Jira + Xray + AWS Bedrock")


# =====================================================================
# SIDEBAR – JIRA CONFIGURATION
# =====================================================================
st.sidebar.header("🔐 Jira Configuration")

jira_type = st.sidebar.radio("Jira Type", ["Cloud", "Data Center"])
jira_base = st.sidebar.text_input("Jira Base URL", placeholder="https://yourcompany.atlassian.net")
jira_user = st.sidebar.text_input("Jira Username / Email")
jira_pass = st.sidebar.text_input("API Token / Password", type="password")

project_key = st.sidebar.text_input("Jira Project Key", placeholder="ABC")

if not jira_base or not jira_user or not jira_pass or not project_key:
    st.sidebar.warning("Enter all Jira configuration values.")


# =====================================================================
# SIDEBAR – AWS BEDROCK CONFIG
# =====================================================================
st.sidebar.header("🤖 AWS Bedrock")

model_id = "eu.anthropic.claude-3-7-sonnet-20250219-v1:0"
region = "eu-west-3"

st.sidebar.write(f"Model: `{model_id}`")
st.sidebar.write(f"Region: `{region}`")

# Instantiate Bedrock Service
bedrock = BedrockService(model_id=model_id, region=region)


# =====================================================================
# SIDEBAR – STORY SELECTION
# =====================================================================
st.sidebar.header("📌 Story Selection")

story_mode = st.sidebar.radio("Select Story Method", ["Enter Story Key", "Search Story"])

jira_service = None
story_key = None
story = None


# =====================================================================
# CONNECT TO JIRA
# =====================================================================
connected = False
if st.sidebar.button("Connect to Jira"):
    try:
        jira_service = JiraService(
            base_url=jira_base,
            username=jira_user,
            password=jira_pass,
            jira_type=jira_type.lower()
        )
        connected = True
        st.sidebar.success("Connected to Jira successfully!")
    except Exception as e:
        st.sidebar.error(f"Jira Connection Failed: {str(e)}")
        connected = False


# =====================================================================
# STORY SELECTION LOGIC
# =====================================================================
if connected:

    # ---------- OPTION A: Enter Story Key Manually ----------
    if story_mode == "Enter Story Key":
        story_key = st.sidebar.text_input("Enter Story Key", placeholder="ABC-123")

        if st.sidebar.button("Fetch Story"):
            try:
                story = jira_service.get_issue(story_key)
                st.success(f"Story {story_key} loaded successfully.")
            except Exception as e:
                st.error(f"Failed to load story: {str(e)}")

    # ---------- OPTION B: Search for Story ----------
    else:
        search_type = st.sidebar.radio("Search By", ["Project", "Summary Text", "JQL"])

        if search_type == "Project":
            if st.sidebar.button("Search Issues"):
                try:
                    issues = jira_service.search_issues_by_project(project_key, issue_type="Story")
                    issue_list = [f"{i['key']} - {i['fields']['summary']}" for i in issues.get("issues", [])]
                    choice = st.sidebar.selectbox("Select Story", issue_list)
                    if choice:
                        story_key = choice.split(" ")[0]
                        story = jira_service.get_issue(story_key)
                        st.success(f"Story {story_key} loaded successfully.")
                except Exception as e:
                    st.error(f"Search failed: {str(e)}")

        elif search_type == "Summary Text":
            text_query = st.sidebar.text_input("Search Keyword")
            if st.sidebar.button("Search"):
                try:
                    issues = jira_service.search_issues_by_summary(project_key, text_query)
                    issue_list = [f"{i['key']} - {i['fields']['summary']}" for i in issues.get("issues", [])]
                    choice = st.sidebar.selectbox("Select Story", issue_list)
                    if choice:
                        story_key = choice.split(" ")[0]
                        story = jira_service.get_issue(story_key)
                        st.success(f"Story {story_key} loaded successfully.")
                except Exception as e:
                    st.error(f"Search failed: {str(e)}")

        else:
            jql = st.sidebar.text_input("Enter JQL", placeholder='project = "ABC" AND type = Story')
            if st.sidebar.button("Run JQL"):
                try:
                    issues = jira_service.search_issues_jql(jql)
                    issue_list = [f"{i['key']} - {i['fields']['summary']}" for i in issues.get("issues", [])]
                    choice = st.sidebar.selectbox("Select Story", issue_list)
                    if choice:
                        story_key = choice.split(" ")[0]
                        story = jira_service.get_issue(story_key)
                        st.success(f"Story {story_key} loaded successfully.")
                except Exception as e:
                    st.error(f"JQL failed: {str(e)}")


# =====================================================================
# MAIN PANEL – STORY DISPLAY
# =====================================================================
if story:
    st.subheader(f"📖 Story: {story_key}")
    st.write("### Summary")
    st.write(story["fields"]["summary"])

    st.write("### Description")
    st.write(story["fields"].get("description", ""))


# =====================================================================
# TEST CASE GENERATION SECTION
# =====================================================================

st.header("🧠 Generate Test Cases")

uploaded_templates = st.file_uploader("Upload Predefined Test Case Templates (CSV/Excel)", type=["csv", "xlsx"])
keywords_input = st.text_input("Enter Keywords (comma-separated)")

if story:
    if st.button("Generate Test Cases"):
        try:
            keywords = [k.strip() for k in keywords_input.split(",") if k.strip()]
            jira_summary = clean_text(story["fields"]["summary"])
            jira_description = clean_text(story["fields"].get("description", ""))

            # Load templates
            templates = load_predefined_templates(uploaded_templates)

            # Filter by keywords + jira text
            templates_filtered = filter_templates_by_keywords(templates, keywords, jira_summary + jira_description)

            # Build prompt
            prompt = build_prompt(jira_summary, jira_description, keywords, templates_filtered)

            # AI generation
            raw = bedrock.generate_testcases(prompt)
            testcases = validate_testcases(raw)

            st.success(f"Generated {len(testcases)} test cases.")
            st.session_state["testcases"] = testcases

        except Exception as e:
            st.error(f"Test Case Generation Failed: {str(e)}")


# =====================================================================
# DISPLAY GENERATED TEST CASES
# =====================================================================
if "testcases" in st.session_state:
    testcases = st.session_state["testcases"]
    st.header("📝 Generated Test Cases")

    for tc in testcases:
        with st.expander(tc["title"]):
            st.json(tc)

    # Download buttons
    st.download_button("⬇️ Download as Excel", data=export_to_excel(testcases),
                       file_name="testcases.xlsx", mime="application/vnd.ms-excel")

    st.download_button("⬇️ Download as JSON", data=export_to_json(testcases),
                       file_name="testcases.json", mime="application/json")


# =====================================================================
# XRAY PUSH SECTION
# =====================================================================
if story and "testcases" in st.session_state and connected:
    st.header("🚀 Push to Jira Xray")

    xray = XrayService(
        jira=jira_service,
        project_key=project_key,
        xray_test_issue_type="Xray Test",
        xray_testset_issue_type="Test Set"
    )

    # Option: create or select Test Set
    testset_mode = st.radio("Test Set Mode", ["Create New Test Set", "Use Existing Test Set"])

    testset_key = None

    if testset_mode == "Create New Test Set":
        testset_name = st.text_input("New Test Set Name", value=f"{story_key}-TestSet")
        if st.button("Create Test Set"):
            try:
                testset_key = xray.create_testset(testset_name)
                xray.link_testset_to_story(testset_key, story_key)
                st.success(f"Test Set created: {testset_key}")
            except Exception as e:
                st.error(f"Failed to create Test Set: {str(e)}")

    else:
        # Load Test Sets from project
        try:
            results = jira_service.search_issues_by_project(project_key, issue_type="Test Set")
            options = [f"{i['key']} - {i['fields']['summary']}" for i in results.get("issues", [])]
            selection = st.selectbox("Select Test Set", options)
            if selection:
                testset_key = selection.split(" ")[0]
        except Exception as e:
            st.error(f"Unable to load Test Sets: {str(e)}")

    # -----------------------------------------------------------------
    # Push Test Cases
    # -----------------------------------------------------------------
    if testset_key and st.button("Push Test Cases to Xray"):
        pushed_tests = []

        try:
            for tc in testcases:
                # 1. Create Test
                test_key = xray.create_xray_test(tc["title"], tc.get("preconditions", ""))
                pushed_tests.append(test_key)

                # 2. Add Steps
                steps_formatted = []
                for step in tc["steps"]:
                    steps_formatted.append({
                        "action": step.get("action") or "",
                        "expected": step.get("expected") or tc.get("expected_result", "")
                    })
                xray.add_test_steps(test_key, steps_formatted)

                # 3. Link Test → Story
                xray.link_test_to_story(test_key, story_key)

            # 4. Add tests to Test Set
            xray.add_tests_to_testset(testset_key, pushed_tests)

            st.success(f"Successfully pushed {len(pushed_tests)} tests to Xray.")

        except Exception as e:
            st.error(f"Error pushing tests: {str(e)}")

