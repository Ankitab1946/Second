import pandas as pd
from datetime import datetime

STORY_POINT_FIELD = "customfield_10003"

VALID_ISSUE_TYPES = [
    "Story",
    "Task",
    "Sub-task",
    "Bug"
]

COMPLETION_STATUSES = [
    "Closed",
    "Ready for UAT",
    "In UAT",
    "Accepted for Release"
]


# =====================================================
# Story Point Calculation (Transition Based Credit)
# =====================================================

def calculate_story_points(issues):

    assigned_records = []
    completed_records = []

    for issue in issues:
        fields = issue.get("fields", {})

        issue_type = fields.get("issuetype", {}).get("name", "")
        if issue_type not in VALID_ISSUE_TYPES:
            continue

        sp = fields.get(STORY_POINT_FIELD, 0) or 0
        sp = float(sp)

        # ----------------------------
        # Assigned SP (Current Assignee)
        # ----------------------------
        assignee = fields.get("assignee")
        assignee_name = assignee["displayName"] if assignee else "Unassigned"

        assigned_records.append({
            "user": assignee_name,
            "story_points": sp
        })

        # ----------------------------
        # Completed SP (Transition Based)
        # ----------------------------
        changelog = issue.get("changelog", {}).get("histories", [])

        for history in changelog:
            author = history.get("author", {}).get("displayName")

            for item in history.get("items", []):
                if item.get("field") == "status":
                    to_status = item.get("toString")

                    if to_status in COMPLETION_STATUSES:
                        completed_records.append({
                            "user": author,
                            "story_points": sp
                        })
                        break

    df_assigned = pd.DataFrame(assigned_records)
    df_completed = pd.DataFrame(completed_records)

    if df_assigned.empty:
        return pd.DataFrame()

    assigned = df_assigned.groupby("user", as_index=False).agg(
        assigned_sp=("story_points", "sum")
    )

    if not df_completed.empty:
        completed = df_completed.groupby("user", as_index=False).agg(
            completed_sp=("story_points", "sum")
        )
    else:
        completed = pd.DataFrame(columns=["user", "completed_sp"])

    result = assigned.merge(completed, on="user", how="left")

    result["completed_sp"] = result["completed_sp"].fillna(0)

    result["spillover_sp"] = (
        result["assigned_sp"] - result["completed_sp"]
    )

    result["completion_%"] = (
        result["completed_sp"] /
        result["assigned_sp"].replace(0, 1)
    ) * 100

    return result.sort_values(by="assigned_sp", ascending=False)


# =====================================================
# Worklog Calculation
# =====================================================

def calculate_worklog(client, issues, start_date, end_date):

    records = []

    for issue in issues:
        worklogs = client.get_worklogs(issue["key"])

        for wl in worklogs:
            author = wl["author"]["displayName"]
            hours = wl["timeSpentSeconds"] / 3600

            started = wl.get("started")
            if started:
                wl_date = datetime.strptime(
                    started[:10], "%Y-%m-%d"
                ).date()

                if start_date and end_date:
                    if not (start_date <= wl_date <= end_date):
                        continue

            records.append({
                "user": author,
                "hours": hours
            })

    df = pd.DataFrame(records)

    if df.empty:
        return df

    return df.groupby("user", as_index=False).agg(
        total_hours=("hours", "sum")
    )
