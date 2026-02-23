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
    "Accepted for Release",
    "Rejected"
]


# =====================================================
# Story Points (Status-Based Completion)
# =====================================================

def calculate_story_points(issues):

    records = []

    for issue in issues:
        fields = issue.get("fields", {})

        issue_type = fields.get("issuetype", {}).get("name", "")
        if issue_type not in VALID_ISSUE_TYPES:
            continue

        sp = fields.get(STORY_POINT_FIELD, 0) or 0
        sp = float(sp)

        assignee = fields.get("assignee")
        assignee_name = assignee["displayName"] if assignee else "Unassigned"

        current_status = fields.get("status", {}).get("name", "")

        is_completed = current_status in COMPLETION_STATUSES

        records.append({
            "user": assignee_name,
            "story_points": sp,
            "is_completed": is_completed
        })

    df = pd.DataFrame(records)

    if df.empty:
        return df

    # Assigned SP
    assigned = df.groupby("user", as_index=False).agg(
        assigned_sp=("story_points", "sum")
    )

    # Completed SP
    completed = df[df["is_completed"]].groupby(
        "user", as_index=False
    ).agg(
        completed_sp=("story_points", "sum")
    )

    result = assigned.merge(completed, on="user", how="left")
    result["completed_sp"] = result["completed_sp"].fillna(0)

    # Spillover
    result["spillover_sp"] = (
        result["assigned_sp"] - result["completed_sp"]
    )

    # Completion %
    result["completion_%"] = (
        result["completed_sp"] /
        result["assigned_sp"].replace(0, 1)
    ) * 100

    return result.sort_values(by="assigned_sp", ascending=False)


# =====================================================
# Worklog (Previous Version – No Optimization Change)
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
