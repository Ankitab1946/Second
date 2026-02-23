import streamlit as st
from jira_client import JiraClient
from metrics import calculate_story_points, calculate_worklog
from charts import *

st.set_page_config(page_title="Jira Resource Dashboard", layout="wide")
st.title("📊 Jira Resource Performance Dashboard")

# =====================================================
# Sidebar Configuration
# =====================================================

st.sidebar.header("🔧 Jira Configuration")

base_url = st.sidebar.text_input("Jira Base URL")
username = st.sidebar.text_input("Username")
password = st.sidebar.text_input("Password", type="password")
verify_ssl = st.sidebar.checkbox("Verify SSL", value=True)

connect = st.sidebar.button("Connect")

# =====================================================
# Connect to Jira
# =====================================================

if connect:
    try:
        client = JiraClient(base_url, username, password, verify_ssl)
        client.test_connection()
        st.session_state["client"] = client
        st.success("Connected Successfully")
    except Exception as e:
        st.error(str(e))

# =====================================================
# Dashboard
# =====================================================

if "client" in st.session_state:

    client = st.session_state["client"]

    # ---------------- Project ----------------

    projects_df = client.get_projects()

    if projects_df.empty:
        st.warning("No Projects Found")
        st.stop()

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

    # ---------------- Date Filters ----------------

    start_date = st.sidebar.date_input("Start Date")
    end_date = st.sidebar.date_input("End Date")

    # =====================================================
    # STEP 1: Build JQL Based on Date Only
    # =====================================================

    jql = f'project = {project_key}'

    if start_date:
        jql += f' AND created >= "{start_date}"'

    if end_date:
        jql += f' AND updated <= "{end_date}"'

    # Fetch issues initially based on date filter only
    issues = client.search_issues(
        jql,
        fields="key,assignee,status,issuetype,customfield_10003,sprint"
    )

    # =====================================================
    # STEP 2: Populate Sprint Dropdown From Retrieved Issues
    # =====================================================

    sprint_names = set()

    for issue in issues:
        sprint_field = issue.get("fields", {}).get("sprint")

        if sprint_field:
            if isinstance(sprint_field, list):
                for s in sprint_field:
                    sprint_names.add(s.get("name"))
            else:
                sprint_names.add(sprint_field.get("name"))

    sprint_list = ["All"] + sorted(list(sprint_names))

    selected_sprint = st.sidebar.selectbox(
        "Select Sprint",
        sprint_list
    )

    # =====================================================
    # STEP 3: Apply Sprint Filter If Selected
    # =====================================================

    if selected_sprint != "All":

        filtered_issues = []

        for issue in issues:
            sprint_field = issue.get("fields", {}).get("sprint")

            if sprint_field:
                if isinstance(sprint_field, list):
                    issue_sprints = [s.get("name") for s in sprint_field]
                    if selected_sprint in issue_sprints:
                        filtered_issues.append(issue)
                else:
                    if sprint_field.get("name") == selected_sprint:
                        filtered_issues.append(issue)

        issues = filtered_issues

    # =====================================================
    # Multi-Select Assignee Filter
    # =====================================================

    assignees = set()

    for issue in issues:
        assignee = issue.get("fields", {}).get("assignee")
        if assignee:
            assignees.add(assignee["displayName"])

    assignee_list = ["All"] + sorted(list(assignees))

    selected_users = st.sidebar.multiselect(
        "Filter by Assignee",
        assignee_list,
        default=["All"]
    )

    # =====================================================
    # Tabs
    # =====================================================

    tab1, tab2 = st.tabs(["📊 Sprint Summary", "⏱ Worklog"])

    # ---------------- Sprint Summary ----------------

    with tab1:

        df_sp = calculate_story_points(issues, selected_users)

        if not df_sp.empty:

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

            st.download_button(
                "Download Sprint Summary CSV",
                df_sp.to_csv(index=False),
                "sprint_summary.csv",
                "text/csv"
            )

        else:
            st.info("No Sprint Summary Data Found")

    # ---------------- Worklog ----------------

    with tab2:

        df_work = calculate_worklog(
            client,
            issues,
            start_date,
            end_date,
            selected_users
        )

        if not df_work.empty:

            st.dataframe(df_work, use_container_width=True)

            st.download_button(
                "Download Worklog CSV",
                df_work.to_csv(index=False),
                "worklog.csv",
                "text/csv"
            )

        else:
            st.info("No Worklog Data Found")
