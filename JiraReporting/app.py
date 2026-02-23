import streamlit as st
import pandas as pd
from jira_client import JiraClient
from metrics import calculate_story_points, calculate_worklog
from charts import *

st.set_page_config(page_title="Jira Resource Dashboard", layout="wide")

st.title("📊 Jira Resource Performance Dashboard")

# Sidebar
st.sidebar.header("🔧 Jira Configuration")

base_url = st.sidebar.text_input("Jira Base URL")
username = st.sidebar.text_input("Username")
password = st.sidebar.text_input("Password", type="password")
verify_ssl = st.sidebar.checkbox("Verify SSL", value=True)

story_point_field = st.sidebar.text_input(
    "Story Point Field ID",
    value="customfield_10016"
)

connect = st.sidebar.button("Connect")

if connect:
    try:
        client = JiraClient(base_url, username, password, verify_ssl)
        client.test_connection()
        st.session_state["client"] = client
        st.success("Connected Successfully")
    except Exception as e:
        st.error(str(e))

if "client" in st.session_state:

    client = st.session_state["client"]

    projects = client.get_projects()
    project_key = st.sidebar.selectbox("Select Project", projects["key"])

    jql = f'project = {project_key}'

    with st.spinner("Loading issues..."):
        issues = client.search_issues(
            jql,
            fields=f"key,assignee,status,{story_point_field}"
        )

    tab1, tab2, tab3 = st.tabs(
        ["📊 Sprint Summary", "⏱ Worklog", "📥 Export"]
    )

    # ---------------- Story Points ----------------
    with tab1:

        df_sp = calculate_story_points(
            issues,
            story_point_field
        )

        if df_sp.empty:
            st.warning("No Story Point data found.")
        else:
            st.dataframe(df_sp, use_container_width=True)

            st.plotly_chart(
                bar_assigned_vs_completed(df_sp),
                use_container_width=True
            )

            st.plotly_chart(
                stacked_spillover(df_sp),
                use_container_width=True
            )

            st.plotly_chart(
                pie_sp_distribution(df_sp),
                use_container_width=True
            )

    # ---------------- Worklog ----------------
    with tab2:

        start_date = st.date_input("Start Date")
        end_date = st.date_input("End Date")

        df_work = calculate_worklog(
            client,
            issues,
            start_date,
            end_date
        )

        if df_work.empty:
            st.info("No worklog data found.")
        else:
            st.dataframe(df_work, use_container_width=True)

    # ---------------- Export ----------------
    with tab3:

        if not df_sp.empty:

            csv = df_sp.to_csv(index=False).encode("utf-8")

            st.download_button(
                "Download CSV",
                csv,
                "story_points.csv",
                "text/csv"
            )

            df_sp.to_excel("story_points.xlsx", index=False)

            with open("story_points.xlsx", "rb") as f:
                st.download_button(
                    "Download Excel",
                    f,
                    "story_points.xlsx",
                    "application/vnd.ms-excel"
                )
