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

    # ---------------- Project ----------------

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

    # ---------------- Date ----------------

    start_date = st.sidebar.date_input("Start Date", value=None)
    end_date = st.sidebar.date_input("End Date", value=None)

    # ---------------- Sprint Population ----------------

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
        fields = issue.get("fields") or {}
        sprint_field = fields.get("sprint")

        if isinstance(sprint_field, list):
            for s in sprint_field:
                if isinstance(s, dict) and s.get("name"):
                    sprint_set.add(s.get("name"))
        elif isinstance(sprint_field, dict):
            if sprint_field.get("name"):
                sprint_set.add(sprint_field.get("name"))

    sprint_list = sorted(list(sprint_set))

    selected_sprints = st.sidebar.multiselect(
        "Select Sprint(s)",
        sprint_list
    )

    # ---------------- Apply Filter ----------------

    if st.sidebar.button("Apply Filter"):

        final_jql = base_jql

        if selected_sprints:
            sprint_clause = ",".join([f'"{s}"' for s in selected_sprints])
            final_jql += f' AND sprint in ({sprint_clause})'

        st.sidebar.markdown("### 🔎 Applied Filters")
        st.sidebar.code(final_jql)

        issues = client.search_issues(
            final_jql,
            fields="key,assignee,status,issuetype,customfield_10003,sprint"
        )

        st.session_state["issues"] = issues

    # =====================================================
    # PROCESS DATA
    # =====================================================

    if "issues" in st.session_state:

        issues = st.session_state["issues"]

        # Assignee filter
        assignees = set()
        for issue in issues or []:
            fields = issue.get("fields") or {}
            assignee = fields.get("assignee")
            if isinstance(assignee, dict) and assignee.get("displayName"):
                assignees.add(assignee.get("displayName"))

        assignee_list = ["All"] + sorted(list(assignees))

        selected_users = st.sidebar.multiselect(
            "Filter by Assignee",
            assignee_list,
            default=["All"]
        )

        # ---------------- Metrics ----------------

        df_sp = calculate_story_points(issues, selected_users)
        df_work = calculate_worklog(client, issues, start_date, end_date, selected_users)
        df_eff = calculate_efficiency(df_sp, df_work)
        df_velocity = calculate_velocity(issues)
        team_score = calculate_team_score(df_sp, df_work)

        tab1, tab2, tab3 = st.tabs([
            "📊 Sprint Summary",
            "⏱ Worklog",
            "💻 GitLab Code Activity"
        ])

        # =====================================================
        # TAB 1
        # =====================================================

        with tab1:

            st.metric("Team Efficiency Score", team_score)

            if not df_sp.empty:
                st.subheader("Sprint Summary Table")
                st.dataframe(df_sp)

                st.subheader("Over / Under Commitment Indicator")
                st.dataframe(df_sp[["user", "completion_%", "commitment_health"]])

            fig_commit = commitment_snapshot(df_sp)
            if fig_commit:
                st.plotly_chart(fig_commit)

            fig_eff = efficiency_chart(df_eff)
            if fig_eff:
                st.plotly_chart(fig_eff)

            fig_sp_hours = sp_vs_hours_chart(df_eff)
            if fig_sp_hours:
                st.plotly_chart(fig_sp_hours)

            fig_vel = velocity_chart(df_velocity)
            if fig_vel:
                st.plotly_chart(fig_vel)

        # =====================================================
        # TAB 2
        # =====================================================

        with tab2:
            if not df_work.empty:
                st.dataframe(df_work)

        # =====================================================
        # TAB 3 - GitLab
        # =====================================================

        with tab3:

            st.subheader("GitLab Code Check-ins")

            gitlab_url = st.text_input("GitLab Base URL", value="https://gitlab.com")
            gitlab_token = st.text_input("GitLab Private Token", type="password")
            gitlab_project_id = st.text_input("GitLab Project ID")

            if st.button("Fetch Commits"):

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
                    if commits:
                        st.session_state["gitlab_commits"] = pd.DataFrame(commits)
                    else:
                        st.warning("No commits found.")
                else:
                    st.error(response.text)

            if "gitlab_commits" in st.session_state:

                df_git = st.session_state["gitlab_commits"]

                author_df = df_git.groupby("author_name") \
                    .size().reset_index(name="commit_count")

                st.dataframe(author_df)

                fig_bar = gitlab_commit_bar(author_df)
                if fig_bar:
                    st.plotly_chart(fig_bar)

        # =====================================================
        # EXPORT (DATA ONLY)
        # =====================================================

        def export_excel():

            output = BytesIO()

            with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
                df_sp.to_excel(writer, sheet_name="Sprint Summary", index=False)
                df_work.to_excel(writer, sheet_name="Worklog", index=False)
                df_eff.to_excel(writer, sheet_name="Efficiency", index=False)
                df_velocity.to_excel(writer, sheet_name="Velocity", index=False)

            output.seek(0)
            return output

        st.download_button(
            "Download Agile Report",
            export_excel(),
            "agile_dashboard.xlsx"
        )
