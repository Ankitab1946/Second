import pandas as pd
from datetime import datetime

STORY_POINT_FIELD = "customfield_10003"

VALID_SP_TYPES = [
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
# Sprint Summary (SP Metrics)
# =====================================================

def calculate_story_points(issues, selected_users=None):

    records = []

    for issue in issues:
        fields = issue.get("fields", {})

        issue_type = fields.get("issuetype", {}).get("name", "")
        if issue_type not in VALID_SP_TYPES:
            continue

        sp = float(fields.get(STORY_POINT_FIELD, 0) or 0)

        assignee = fields.get("assignee")
        user = assignee["displayName"] if assignee else "Unassigned"

        # Multi-user filter
        if selected_users and "All" not in selected_users:
            if user not in selected_users:
                continue

        status = fields.get("status", {}).get("name", "")
        is_completed = status in COMPLETION_STATUSES

        records.append({
            "user": user,
            "story_points": sp,
            "is_completed": is_completed
        })

    df = pd.DataFrame(records)

    if df.empty:
        return df

    assigned = df.groupby("user", as_index=False).agg(
        assigned_sp=("story_points", "sum")
    )

    completed = df[df["is_completed"]].groupby(
        "user", as_index=False
    ).agg(
        completed_sp=("story_points", "sum")
    )

    result = assigned.merge(completed, on="user", how="left")
    result["completed_sp"] = result["completed_sp"].fillna(0)

    result["spillover_sp"] = (
        result["assigned_sp"] - result["completed_sp"]
    )

    result["completion_%"] = (
        result["completed_sp"] /
        result["assigned_sp"].replace(0, 1)
    ) * 100

    return result


# =====================================================
# Worklog (All Issue Types)
# =====================================================

def calculate_worklog(client, issues,
                      start_date=None,
                      end_date=None,
                      selected_users=None):

    records = []

    for issue in issues:

        worklogs = client.get_worklogs(issue["key"])

        for wl in worklogs:
            author = wl["author"]["displayName"]

            # Multi-select filter
            if selected_users and "All" not in selected_users:
                if author not in selected_users:
                    continue

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
                "issue_key": issue["key"],
                "hours": hours
            })

    df = pd.DataFrame(records)

    if df.empty:
        return df

    return df.groupby("user", as_index=False).agg(
        total_hours=("hours", "sum")
    )
