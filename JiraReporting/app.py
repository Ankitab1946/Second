import streamlit as st
import pandas as pd
import requests
from io import BytesIO

from jira_client import JiraClient
from metrics import *
from charts import *

st.set_page_config(layout="wide")
st.title("📊 Enterprise Agile + DevOps Dashboard")

st.sidebar.header("🔧 Jira Configuration")

base_url = st.sidebar.text_input("Jira Base URL")
username = st.sidebar.text_input("Username")
password = st.sidebar.text_input("Password", type="password")
verify_ssl = st.sidebar.checkbox("Verify SSL", value=True)

if st.sidebar.button("Connect"):
    try:
        client = JiraClient(base_url, username, password, verify_ssl)
        client.test_connection()
        st.session_state["client"] = client
        st.success("Connected Successfully")
    except Exception as e:
        st.error(str(e))

if "client" in st.session_state:

    client = st.session_state["client"]

    projects_df = client.get_projects()

    default_project = "ANKPRJ"
    if default_project in projects_df["key"].values:
        default_index = projects_df["key"].tolist().index(default_project)
    else:
        default_index = 0

    project_key = st.sidebar.selectbox(
        "Select Project",
        projects_df["key"],
        index=default_index
    )

    start_date = st.sidebar.date_input("Start Date")
    end_date = st.sidebar.date_input("End Date")

    base_jql = f'project = {project_key}'

    if start_date:
        base_jql += f' AND created >= "{start_date.strftime("%Y-%m-%d")}"'

    if end_date:
        base_jql += f' AND updated < endOfDay("{end_date.strftime("%Y%m%d")}")'

    issues_for_population = client.search_issues(
        base_jql,
        fields="customfield_10007"
    )

    sprint_set = set()

    for issue in issues_for_population or []:
        fields = issue.get("fields") or {}
        sprint_field = fields.get("customfield_10007")

        if isinstance(sprint_field, list):
            for s in sprint_field:
                if isinstance(s, dict) and s.get("name"):
                    sprint_set.add(s.get("name"))

    sprint_list = sorted(list(sprint_set))

    selected_sprints = st.sidebar.multiselect(
        "Select Sprint(s)",
        sprint_list
    )

    if st.sidebar.button("Apply Filter"):

        final_jql = base_jql

        if selected_sprints:
            sprint_clause = ",".join([f'"{s}"' for s in selected_sprints])
            final_jql += f' AND sprint in ({sprint_clause})'

        issues = client.search_issues(
            final_jql,
            fields="key,assignee,status,issuetype,customfield_10003,customfield_10007"
        )

        st.session_state["issues"] = issues

    if "issues" in st.session_state:

        issues = st.session_state["issues"]

        df_sp = calculate_story_points(issues)
        df_work = calculate_worklog(client, issues, start_date, end_date)
        df_eff = calculate_efficiency(df_sp, df_work)
        df_velocity = calculate_velocity(issues)

        tab1, tab2 = st.tabs(["Sprint Summary", "Worklog"])

        with tab1:
            st.dataframe(df_sp)

        with tab2:
            st.dataframe(df_work)

        def export_excel():
            output = BytesIO()
            with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
                df_sp.to_excel(writer, sheet_name="Sprint Summary", index=False)
                df_work.to_excel(writer, sheet_name="Worklog", index=False)
            output.seek(0)
            return output

        st.download_button(
            "Download Report",
            export_excel(),
            "agile_dashboard.xlsx"
        )
