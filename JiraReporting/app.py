import streamlit as st
from io import BytesIO
import pandas as pd
from jira_client import JiraClient
from metrics import *
from charts import *

st.set_page_config(layout="wide")
st.title("📊 Enterprise Agile Dashboard")

# =====================================================
# SIDEBAR CONFIG
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
# DASHBOARD
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

    sprint_name = st.sidebar.text_input("Sprint (Optional)")

    apply_filter = st.sidebar.button("Apply Filter")

    if apply_filter:

        jql = f'project = {project_key}'

        if start_date:
            jql += f' AND created >= "{start_date.strftime("%Y-%m-%d")}"'

        if end_date:
            jql += f' AND updated < endOfDay("{end_date.strftime("%Y%m%d")}")'

        if sprint_name:
            jql += f' AND sprint = "{sprint_name}"'

        st.sidebar.markdown("### 🔎 Applied Filters")
        st.sidebar.code(jql)

        issues = client.search_issues(
            jql,
            fields="key,assignee,status,issuetype,customfield_10003,sprint"
        )

        st.session_state["issues"] = issues

    if "issues" in st.session_state:

        issues = st.session_state["issues"]

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

        df_sp = calculate_story_points(issues, selected_users)
        df_work = calculate_worklog(client, issues, start_date, end_date, selected_users)
        df_eff = calculate_efficiency(df_sp, df_work)
        df_velocity = calculate_velocity(issues)
        team_score = calculate_team_score(df_sp, df_work)

        sprint_data_mode = st.checkbox("SprintData")

        st.metric("Team Efficiency Score", team_score)

        if not df_sp.empty:
            fig_commit = commitment_snapshot(df_sp)
            st.plotly_chart(fig_commit)

        if not df_eff.empty:
            fig_eff = efficiency_chart(df_eff)
            st.plotly_chart(fig_eff)

        if sprint_data_mode and not df_velocity.empty:
            fig_vel = velocity_chart(df_velocity)
            st.plotly_chart(fig_vel)

        def export_excel():

            output = BytesIO()

            with pd.ExcelWriter(output, engine="xlsxwriter") as writer:

                df_sp.to_excel(writer, sheet_name="Sprint Summary", index=False)
                df_work.to_excel(writer, sheet_name="Worklog", index=False)

                workbook = writer.book
                worksheet = workbook.add_worksheet("Charts")

                charts = []

                if not df_sp.empty:
                    charts.append(fig_commit)

                if not df_eff.empty:
                    charts.append(fig_eff)

                if sprint_data_mode and not df_velocity.empty:
                    charts.append(fig_vel)

                row = 1
                for fig in charts:
                    img = fig.to_image(format="png")
                    worksheet.insert_image(row, 1, "", {"image_data": BytesIO(img)})
                    row += 25

            output.seek(0)
            return output

        st.download_button(
            "Download Full Agile Report",
            export_excel(),
            "agile_dashboard.xlsx"
        )
