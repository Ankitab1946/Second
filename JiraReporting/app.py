import streamlit as st
from datetime import datetime
from jira_client import JiraClient
from metrics import calculate_story_points, calculate_worklog
from charts import *

st.set_page_config(page_title="Jira Resource Dashboard", layout="wide")
st.title("📊 Jira Resource Performance Dashboard")

# ---------------- Sidebar ----------------

st.sidebar.header("🔧 Jira Configuration")

base_url = st.sidebar.text_input("Jira Base URL")
username = st.sidebar.text_input("Username")
password = st.sidebar.text_input("Password", type="password")
verify_ssl = st.sidebar.checkbox("Verify SSL", value=True)

connect = st.sidebar.button("Connect")

if connect:
    try:
        client = JiraClient(base_url, username, password, verify_ssl)
        client.test_connection()
        st.session_state["client"] = client
        st.success("Connected Successfully")
    except Exception as e:
        st.error(str(e))

# ---------------- Dashboard ----------------

if "client" in st.session_state:

    client = st.session_state["client"]

    projects = client.get_projects()
    project_key = st.sidebar.selectbox("Select Project", projects["key"])

    filter_mode = st.sidebar.radio(
        "Filter Mode",
        ["Sprint", "Date Range"]
    )

    # ---------------- Filter Setup ----------------

    if filter_mode == "Sprint":

        boards = client.get_boards()
        board_names = [b["name"] for b in boards]
        selected_board = st.sidebar.selectbox("Select Board", board_names)

        board_id = next(
            b["id"] for b in boards if b["name"] == selected_board
        )

        sprints = client.get_sprints(board_id)
        sprint_names = [s["name"] for s in sprints]
        selected_sprint = st.sidebar.selectbox("Select Sprint", sprint_names)

        sprint_data = next(
            s for s in sprints if s["name"] == selected_sprint
        )

        sprint_start = None
        sprint_end = None

        if sprint_data.get("startDate"):
            sprint_start = datetime.fromisoformat(
                sprint_data["startDate"][:10]
            ).date()

        if sprint_data.get("endDate"):
            sprint_end = datetime.fromisoformat(
                sprint_data["endDate"][:10]
            ).date()

        jql = f'project = {project_key} AND sprint = "{selected_sprint}"'

    else:

        sprint_start = st.sidebar.date_input("Start Date")
        sprint_end = st.sidebar.date_input("End Date")

        jql = (
            f'project = {project_key} '
            f'AND updated >= "{sprint_start}" '
            f'AND updated <= "{sprint_end}"'
        )

    # ---------------- Fetch Issues ----------------

    issues = client.search_issues(
        jql,
        fields="key,assignee,status,issuetype,customfield_10003"
    )

    # ---------------- Multi-Select Assignee ----------------

    assignees = set()

    for issue in issues:
        assignee = issue.get("fields", {}).get("assignee")
        if assignee:
            assignees.add(assignee["displayName"])

    assignee_list = sorted(list(assignees))
    assignee_list.insert(0, "All")

    selected_users = st.sidebar.multiselect(
        "Filter by Assignee",
        assignee_list,
        default=["All"]
    )

    # ---------------- Tabs ----------------

    tab1, tab2 = st.tabs(["📊 Sprint Summary", "⏱ Worklog"])

    # ---------------- Sprint Summary ----------------

    with tab1:

        df_sp = calculate_story_points(issues, selected_users)

        if not df_sp.empty:
            st.dataframe(df_sp, use_container_width=True)

            st.plotly_chart(bar_assigned_vs_completed(df_sp),
                            use_container_width=True)

            st.plotly_chart(stacked_spillover(df_sp),
                            use_container_width=True)

            st.plotly_chart(pie_sp_distribution(df_sp),
                            use_container_width=True)

            st.download_button(
                "Download Sprint Summary CSV",
                df_sp.to_csv(index=False),
                "sprint_summary.csv",
                "text/csv"
            )
        else:
            st.info("No Sprint Summary Data Found.")

    # ---------------- Worklog ----------------

    with tab2:

        df_work = calculate_worklog(
            client,
            issues,
            sprint_start,
            sprint_end,
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
            st.info("No Worklog Data Found.")
