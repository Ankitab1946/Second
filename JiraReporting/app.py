import streamlit as st
from io import BytesIO
import pandas as pd
from jira_client import JiraClient
from metrics import *
from charts import *

st.title("📊 Enterprise Agile Dashboard v2")

sprint_data_mode = st.checkbox("SprintData")

# assume issues already filtered
df_sp = calculate_story_points(issues, selected_users)
df_work = calculate_worklog(client, issues, start_date, end_date, selected_users)
df_eff = calculate_efficiency(df_sp, df_work)
team_score = calculate_team_score(df_sp, df_work)

st.metric("Team Efficiency Score", team_score)

fig_eff = efficiency_chart(df_eff)
fig_commit = commitment_snapshot(df_sp)

st.plotly_chart(fig_eff)
st.plotly_chart(fig_commit)

if sprint_data_mode:
    df_velocity = calculate_velocity(issues)
    if not df_velocity.empty:
        fig_vel = velocity_chart(df_velocity)
        st.plotly_chart(fig_vel)

# =====================================================
# EXPORT EXCEL WITH CHARTS
# =====================================================

def export_excel():

    output = BytesIO()

    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:

        df_sp.to_excel(writer, sheet_name="Sprint Summary", index=False)
        df_work.to_excel(writer, sheet_name="Worklog", index=False)

        workbook = writer.book
        worksheet = workbook.add_worksheet("Charts")

        charts = [fig_eff, fig_commit]

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
