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

    start_date = st.sidebar.date_input("Start Date", value=None)
    end_date = st.sidebar.date_input("End Date", value=None)

    # =====================================================
    # STEP 1: Build JQL (Date Optional)
    # =====================================================

    base_jql = f'project = {project_key}'

    if start_date:
        start_str = start_date.strftime("%Y%m%d")
        base_jql += f' AND created >= "{start_str}"'

    if end_date:
        end_str = end_date.strftime("%Y%m%d")
        base_jql += f' AND updated < endOfDay("{end_str}")'

    # Fetch issues (date filtered or full project)
    issues = client.search_issues(
        base_jql,
        fields="key,assignee,status,issuetype,customfield_10003,sprint"
    )

    # =====================================================
    # STEP 2: Populate Sprint Multi-Select
    # =====================================================

    sprint_set = set()

    for issue in issues:
        sprint_field = issue.get("fields", {}).get("sprint")

        if sprint_field:
            if isinstance(sprint_field, list):
                for s in sprint_field:
                    if s:
                        sprint_set.add(s.get("name"))
            else:
                sprint_set.add(sprint_field.get("name"))

    sprint_list = sorted(list(sprint_set))

    selected_sprints = st.sidebar.multiselect(
        "Select Sprint(s)",
        sprint_list
    )

    # =====================================================
    # STEP 3: Apply Sprint Filter (If Selected)
    # =====================================================

    if selected_sprints:

        filtered_issues = []

        for issue in issues:
            sprint_field = issue.get("fields", {}).get("sprint")

            if sprint_field:
                issue_sprints = []

                if isinstance(sprint_field, list):
                    issue_sprints = [s.get("name") for s in sprint_field if s]
                else:
                    issue_sprints = [sprint_field.get("name")]

                if any(s in issue_sprints for s in selected_sprints):
                    filtered_issues.append(issue)

        issues = filtered_issues

    # =====================================================
    # Assignee Multi-Select
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
