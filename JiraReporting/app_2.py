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
# SIDEBAR - JIRA CONFIG
# =====================================================

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

# =====================================================
# MAIN DASHBOARD
# =====================================================

if "client" in st.session_state:

    client = st.session_state["client"]

    # =====================================================
    # PROJECT
    # =====================================================

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

    # =====================================================
    # SCRUM BOARD (Stable Sprint Source)
    # =====================================================

    boards_df = client.get_boards(project_key)

    if boards_df.empty:
        st.warning("No Scrum Boards Found for selected project.")
        st.stop()

    board_name = st.sidebar.selectbox(
        "Select Scrum Board",
        boards_df["name"]
    )

    board_id = boards_df[boards_df["name"] == board_name].iloc[0]["id"]

    # =====================================================
    # SPRINT LIST (Using Agile API - FIXED)
    # =====================================================

    sprints_df = client.get_sprints(board_id)

    if sprints_df.empty:
        sprint_list = []
    else:
        sprint_list = (
            sprints_df["name"]
            .dropna()
            .astype(str)
            .tolist()
        )

    selected_sprints = st.sidebar.multiselect(
        "Select Sprint(s)",
        sprint_list
    )

    # =====================================================
    # DATE FILTER
    # =====================================================

    start_date = st.sidebar.date_input("Start Date", value=None)
    end_date = st.sidebar.date_input("End Date", value=None)

    # =====================================================
    # APPLY FILTER
    # =====================================================

    apply_filter = st.sidebar.button("Apply Filter")

    if apply_filter:

        final_jql = f'project = {project_key}'

        if start_date:
            final_jql += f' AND created >= "{start_date.strftime("%Y-%m-%d")}"'

        if end_date:
            final_jql += f' AND updated < endOfDay("{end_date.strftime("%Y%m%d")}")'

        if selected_sprints:
            sprint_clause = ",".join([f'"{s}"' for s in selected_sprints])
            final_jql += f' AND sprint in ({sprint_clause})'

        st.sidebar.markdown("### 🔎 Applied Filters")
        st.sidebar.code(final_jql)

        issues = client.search_issues(
            final_jql,
            fields="key,assignee,status,issuetype,customfield_10003,sprint"
        ) or []

        # Remove None issues safely
        issues = [i for i in issues if i]

        st.session_state["issues"] = issues

    # =====================================================
    # PROCESS FILTERED DATA
    # =====================================================

    if "issues" in st.session_state:

        issues = st.session_state.get("issues") or []

        # ---------------- ASSIGNEE FILTER ----------------

        assignees = set()

        for issue in issues:
            fields = issue.get("fields") or {}
            assignee = fields.get("assignee") or {}
            name = assignee.get("displayName")
            if name:
                assignees.add(name)

        assignee_list = ["All"] + sorted(list(assignees))

        selected_users = st.sidebar.multiselect(
            "Filter by Assignee",
            assignee_list,
            default=["All"]
        )

        # ---------------- METRICS ----------------

        df_sp = calculate_story_points(issues, selected_users)
        df_work = calculate_worklog(client, issues, start_date, end_date, selected_users)
        df_eff = calculate_efficiency(df_sp, df_work)
        df_velocity = calculate_velocity(issues)
        team_score = calculate_team_score(df_sp, df_work)

        sprint_data_mode = st.checkbox("SprintData")

        tab1, tab2, tab3 = st.tabs([
            "📊 Sprint Summary",
            "⏱ Worklog",
            "💻 Code Activity"
        ])

        # =====================================================
        # TAB 1 - Sprint Summary
        # =====================================================

        with tab1:

            st.metric("Team Efficiency Score", team_score)

            if not df_sp.empty:
                st.subheader("Sprint Summary Table")
                st.dataframe(df_sp, use_container_width=True)

                if "commitment_health" in df_sp.columns:
                    st.subheader("Over / Under Commitment Indicator")
                    st.dataframe(
                        df_sp[["user", "completion_%", "commitment_health"]],
                        use_container_width=True
                    )

            for fig in [
                commitment_snapshot(df_sp),
                efficiency_chart(df_eff),
                sp_vs_hours_chart(df_eff),
                velocity_chart(df_velocity) if sprint_data_mode else None
            ]:
                if fig:
                    st.plotly_chart(fig, use_container_width=True)

        # =====================================================
        # TAB 2 - Worklog
        # =====================================================

        with tab2:
            if not df_work.empty:
                st.dataframe(df_work, use_container_width=True)
            else:
                st.info("No Worklog Data Found")

        # =====================================================
        # TAB 3 - GITLAB
        # =====================================================

        with tab3:

            st.subheader("GitLab Code Check-ins")

            gitlab_url = st.text_input("GitLab Base URL", value="https://gitlab.com")
            gitlab_token = st.text_input("GitLab Private Token", type="password")
            gitlab_project_id = st.text_input("GitLab Project ID")

            if st.button("Fetch Commits"):

                if not gitlab_token or not gitlab_project_id:
                    st.warning("Please provide GitLab Token and Project ID")

                else:
                    try:
                        headers = {"PRIVATE-TOKEN": gitlab_token}
                        url = f"{gitlab_url}/api/v4/projects/{gitlab_project_id}/repository/commits"

                        params = {"per_page": 100}

                        if start_date:
                            params["since"] = start_date.isoformat()
                        if end_date:
                            params["until"] = end_date.isoformat()

                        response = requests.get(url, headers=headers, params=params)

                        if response.status_code == 200:
                            commits = response.json()
                            if not isinstance(commits, list):
                                commits = []

                            df_git = pd.DataFrame(commits)

                            if not df_git.empty and "author_name" not in df_git.columns:
                                df_git["author_name"] = "Unknown"

                            st.session_state["gitlab_commits"] = df_git
                        else:
                            st.error(response.text)
                            st.session_state["gitlab_commits"] = pd.DataFrame()

                    except Exception as e:
                        st.error(f"GitLab API Error: {e}")
                        st.session_state["gitlab_commits"] = pd.DataFrame()

            df_git = st.session_state.get("gitlab_commits")

            if isinstance(df_git, pd.DataFrame) and not df_git.empty:
                author_df = (
                    df_git.groupby("author_name")
                    .size()
                    .reset_index(name="commit_count")
                )

                st.dataframe(author_df, use_container_width=True)

                fig_bar = gitlab_commit_bar(author_df)
                if fig_bar:
                    st.plotly_chart(fig_bar, use_container_width=True)

        # =====================================================
        # EXPORT
        # =====================================================

        def export_excel():

            output = BytesIO()

            with pd.ExcelWriter(output, engine="xlsxwriter") as writer:

                if not df_sp.empty:
                    df_sp.to_excel(writer, sheet_name="Sprint Summary", index=False)

                if not df_work.empty:
                    df_work.to_excel(writer, sheet_name="Worklog", index=False)

                if not df_eff.empty:
                    df_eff.to_excel(writer, sheet_name="Efficiency", index=False)

                if not df_velocity.empty:
                    df_velocity.to_excel(writer, sheet_name="Velocity", index=False)

            output.seek(0)
            return output

        st.download_button(
            "Download Agile Report (Data Only)",
            export_excel(),
            "agile_dashboard.xlsx"
        )