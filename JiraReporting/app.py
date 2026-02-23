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

    # ---------------- Project ----------------
    projects = client.get_projects()
    project_key = st.sidebar.selectbox("Select Project", projects["key"])

    # ---------------- Date Filter ----------------
    start_date = st.sidebar.date_input("Start Date")
    end_date = st.sidebar.date_input("End Date")

    # ---------------- Board & Sprint ----------------
    boards = client.get_boards()

    board_names = [b["name"] for b in boards]
    selected_board = st.sidebar.selectbox("Select Board", board_names)

    board_id = next(b["id"] for b in boards if b["name"] == selected_board)

    sprints = client.get_sprints(board_id)

    sprint_names = ["All"] + [s["name"] for s in sprints]

    selected_sprint = st.sidebar.selectbox("Select Sprint", sprint_names)

    # ---------------- JQL Construction ----------------

    jql = f'project = {project_key}'

    # Date filter always applied
    if start_date and end_date:
        jql += (
            f' AND updated >= "{start_date}" '
            f'AND updated <= "{end_date}"'
        )

    # Sprint filter optional
    if selected_sprint != "All":
        jql += f' AND sprint = "{selected_sprint}"'

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

    assignee_list = ["All"] + sorted(list(assignees))

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
            st.info("No Worklog Data Found.")
