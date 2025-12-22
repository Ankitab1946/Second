import streamlit as st

from services.bedrock_service import BedrockService
from services.jira_service import JiraService
from services.xray_service import XrayService
from services.utils import (
    load_predefined_templates,
    filter_templates_by_keywords,
@@ -60,6 +268,9 @@
    except Exception as e:
        st.sidebar.error(f"Connection failed: {e}")

# ============================================================
# SERVICES
# ============================================================
bedrock = BedrockService()
jira = st.session_state["jira_service"]

@@ -77,7 +288,7 @@
        st.session_state["story_key"] = story_key
        st.session_state["story"] = issue

        # 🔥 Clear old data
        # 🔥 Reset previous generation
        st.session_state["testcases"] = None
        st.session_state["last_prompt"] = None
        st.session_state["last_story_key"] = story_key
@@ -98,7 +309,7 @@
    st.write(story["fields"].get("description", ""))

# ============================================================
# GENERATE ETL TEST CASES (MANDATORY ETL MODE)
# GENERATE ETL TEST CASES
# ============================================================
st.header("🧠 Generate ETL / Data Quality Test Cases")

@@ -157,7 +368,7 @@
            full_req
        )

        # 🔒 ETL MODE IS HARD-CODED
        # 🔒 ETL MODE IS MANDATORY
        test_type = "ETL_DQ_ONLY"

        prompt = build_prompt(
@@ -174,8 +385,9 @@
        )

        if should_regenerate:
            raw = bedrock.generate_testcases(prompt)
            testcases = validate_testcases(raw)
            with st.spinner("Generating ETL test cases..."):
                raw = bedrock.generate_testcases(prompt)
                testcases = validate_testcases(raw)

            st.session_state["testcases"] = testcases
            st.session_state["last_prompt"] = prompt
@@ -184,7 +396,7 @@
            st.success(f"Generated {len(testcases)} ETL test cases")

# ============================================================
# DISPLAY RESULTS
# DISPLAY GENERATED TEST CASES
# ============================================================
if st.session_state["testcases"]:
    st.header("📋 Generated ETL Test Cases")
@@ -193,14 +405,71 @@
        with st.expander(tc["title"]):
            st.json(tc)

    st.download_button(
        "⬇️ Download Excel",
        export_to_excel(st.session_state["testcases"]),
        file_name="etl_testcases.xlsx"
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
# 🚀 PUSH TO XRAY
# ============================================================
st.header("🚀 Push ETL Test Cases to Jira Xray")

if st.session_state["testcases"] and st.session_state["connected"]:

    project_key = st.text_input(
        "Jira Project Key (for Xray)",
        value=st.session_state["story_key"].split("-")[0]
    )

    st.download_button(
        "⬇️ Download JSON",
        export_to_json(st.session_state["testcases"]),
        file_name="etl_testcases.json"
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
            with st.spinner("Creating Xray Test Set..."):
                testset_key = xray.create_testset(testset_name)

            created_tests = []

            with st.spinner("Creating Xray Tests and adding steps..."):
                for tc in st.session_state["testcases"]:
                    test_key = xray.create_xray_test(
                        title=tc["title"],
                        preconditions=tc.get("preconditions", "")
                    )

                    xray.add_test_steps(test_key, tc["steps"])
                    xray.link_test_to_story(
                        test_key,
                        st.session_state["story_key"]
                    )

                    created_tests.append(test_key)

            with st.spinner("Adding Tests to Test Set..."):
                xray.add_tests_to_testset(testset_key, created_tests)

            st.success(
                f"✅ Successfully pushed {len(created_tests)} ETL tests "
                f"to Xray Test Set {testset_key}"
            )

        except Exception as e:
            st.error(f"❌ Xray push failed: {e}")
