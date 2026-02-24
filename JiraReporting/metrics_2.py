import pandas as pd
from datetime import datetime

# =====================================================
# CONFIGURATION
# =====================================================

STORY_POINT_FIELD = "customfield_10003"

VALID_ISSUE_TYPES = [
    "Story",
    "Task",
    "Bug",
    "Sub-task"
]

EXCLUDED_WORKLOG_TYPES = [
    "Xray Test"
]

COMPLETION_STATUSES = [
    "Closed",
    "Ready for UAT",
    "In UAT",
    "Accepted for Release",
    "Rejected"
]

# =====================================================
# STORY POINT CALCULATION
# =====================================================

def calculate_story_points(issues, selected_users=None):

    assigned_records = []
    completed_records = []

    for issue in issues:

        fields = issue.get("fields") or {}

        issue_type = (fields.get("issuetype") or {}).get("name", "")

        if issue_type not in VALID_ISSUE_TYPES:
            continue

        sp = float(fields.get(STORY_POINT_FIELD, 0) or 0)

        assignee = fields.get("assignee") or {}
        user = assignee.get("displayName", "Unassigned")

        if selected_users and "All" not in selected_users:
            if user not in selected_users:
                continue

        assigned_records.append({
            "user": user,
            "story_points": sp
        })

        status = (fields.get("status") or {}).get("name", "")

        if status in COMPLETION_STATUSES:
            completed_records.append({
                "user": user,
                "story_points": sp
            })

    df_assigned = pd.DataFrame(assigned_records)
    df_completed = pd.DataFrame(completed_records)

    if df_assigned.empty:
        return df_assigned

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

    def commitment_status(p):
        if p >= 100:
            return "Over Delivered"
        elif p >= 80:
            return "Healthy"
        elif p >= 50:
            return "Slight Risk"
        else:
            return "At Risk"

    result["commitment_health"] = result["completion_%"].apply(commitment_status)

    return result.sort_values(by="assigned_sp", ascending=False)


# =====================================================
# WORKLOG CALCULATION
# =====================================================

def calculate_worklog(client,
                      issues,
                      start_date=None,
                      end_date=None,
                      selected_users=None):

    records = []

    for issue in issues:

        fields = issue.get("fields") or {}
        issue_type = (fields.get("issuetype") or {}).get("name", "")

        if issue_type in EXCLUDED_WORKLOG_TYPES:
            continue

        worklogs = client.get_worklogs(issue.get("key"))

        for wl in worklogs:

            author = (wl.get("author") or {}).get("displayName")
            if not author:
                continue

            if selected_users and "All" not in selected_users:
                if author not in selected_users:
                    continue

            hours = wl.get("timeSpentSeconds", 0) / 3600
            started = wl.get("started")

            if started:
                wl_date = datetime.strptime(
                    started[:10], "%Y-%m-%d"
                ).date()

                if start_date and wl_date < start_date:
                    continue

                if end_date and wl_date > end_date:
                    continue

            records.append({
                "user": author,
                "issue_key": issue.get("key"),
                "hours": hours
            })

    df = pd.DataFrame(records)

    if df.empty:
        return df

    return df.groupby("user", as_index=False).agg(
        total_hours=("hours", "sum")
    )


# =====================================================
# EFFICIENCY CALCULATION
# =====================================================

def calculate_efficiency(df_sp, df_work):

    if df_sp.empty or df_work.empty:
        return pd.DataFrame()

    df = df_sp.merge(df_work, on="user", how="left")
    df["total_hours"] = df["total_hours"].fillna(0)

    df["efficiency"] = df.apply(
        lambda row: row["completed_sp"] / row["total_hours"]
        if row["total_hours"] > 0 else 0,
        axis=1
    )

    df.rename(columns={"total_hours": "hours"}, inplace=True)

    return df


# =====================================================
# VELOCITY CALCULATION (FIXED SAFE)
# =====================================================

def calculate_velocity(issues):

    records = []

    for issue in issues:

        fields = issue.get("fields") or {}
        sprint = fields.get("sprint")
        status = (fields.get("status") or {}).get("name", "")

        if not sprint:
            continue

        sprint_name = None

        if isinstance(sprint, list):
            if sprint:
                sprint_name = (sprint[-1] or {}).get("name")
        else:
            sprint_name = (sprint or {}).get("name")

        if not sprint_name:
            continue

        if status in COMPLETION_STATUSES:
            sp = float(fields.get(STORY_POINT_FIELD, 0) or 0)
            records.append({
                "sprint": sprint_name,
                "completed_sp": sp
            })

    df = pd.DataFrame(records)

    if df.empty:
        return df

    return df.groupby("sprint", as_index=False).agg(
        completed_sp=("completed_sp", "sum")
    )


# =====================================================
# TEAM SCORE CALCULATION
# =====================================================

def calculate_team_score(df_sp, df_work):

    if df_sp.empty:
        return 0

    avg_completion = df_sp["completion_%"].mean()

    if not df_work.empty:
        total_sp = df_sp["completed_sp"].sum()
        total_hours = df_work["total_hours"].sum()
        efficiency = total_sp / total_hours if total_hours > 0 else 0
    else:
        efficiency = 0

    score = (avg_completion * 0.7) + (efficiency * 30)

    return round(min(score, 100), 2)
