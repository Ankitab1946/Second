import streamlit as st
import pandas as pd
import requests
from io import BytesIO

from jira_client import JiraClient
from metrics import *
from charts import *

st.set_page_config(layout="wide")
st.title("📊 Enterprise Agile + DevOps Dashboard")

# =====================================================
# SIDEBAR CONFIG
# =====================================================

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

# =====================================================
# MAIN DASHBOARD
# =====================================================

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

    start_date = st.sidebar.date_input("Start Date", value=None)
    end_date = st.sidebar.date_input("End Date", value=None)

    base_jql = f'project = {project_key}'

    if start_date:
        base_jql += f' AND created >= "{start_date.strftime("%Y-%m-%d")}"'

    if end_date:
        base_jql += f' AND updated < endOfDay("{end_date.strftime("%Y%m%d")}")'

    issues_for_population = client.search_issues(
        base_jql,
        fields="key,sprint"
    )

    sprint_set = set()

    for issue in issues_for_population or []:
        if not issue:
            continue

        fields = issue.get("fields") or {}
        sprint_field = fields.get("sprint")

        if not sprint_field:
            continue

        if isinstance(sprint_field, list):
            for s in sprint_field:
                if s and isinstance(s, dict):
                    name = s.get("name")
                    if name:
                        sprint_set.add(name)
        elif isinstance(sprint_field, dict):
            name = sprint_field.get("name")
            if name:
                sprint_set.add(name)

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

        st.sidebar.code(final_jql)

        issues = client.search_issues(
            final_jql,
            fields="key,assignee,status,issuetype,customfield_10003,sprint"
        )

        st.session_state["issues"] = issues

    if "issues" in st.session_state:

        issues = st.session_state["issues"]

        assignees = set()

        for issue in issues or []:
            fields = issue.get("fields") or {}
            assignee_obj = fields.get("assignee")

            if assignee_obj and isinstance(assignee_obj, dict):
                name = assignee_obj.get("displayName")
                if name:
                    assignees.add(name)

        assignee_list = ["All"] + sorted(list(assignees))

        selected_users = st.sidebar.multiselect(
            "Filter by Assignee",
            assignee_list,
            default=["All"]
        )

        df_sp = calculate_story_points(issues, selected_users)
        df_work = calculate_worklog(client, issues, start_date, end_date, selected_users)
        df_eff = calculate_efficiency(df_sp, df_work)
        df_velocity = calculate_velocity(issues)
        team_score = calculate_team_score(df_sp, df_work)

        tab1, tab2 = st.tabs(["📊 Sprint Summary", "⏱ Worklog"])

        with tab1:

            st.metric("Team Efficiency Score", team_score)

            if not df_sp.empty:
                st.dataframe(df_sp)

                st.subheader("Over / Under Commitment Indicator")
                st.dataframe(df_sp[["user", "completion_%", "commitment_health"]])

        with tab2:
            if not df_work.empty:
                st.dataframe(df_work)

        def export_excel():

            output = BytesIO()

            with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
                df_sp.to_excel(writer, sheet_name="Sprint Summary", index=False)
                df_work.to_excel(writer, sheet_name="Worklog", index=False)

            output.seek(0)
            return output

        st.download_button(
            "Download Agile Report",
            export_excel(),
            "agile_dashboard.xlsx"
        )
