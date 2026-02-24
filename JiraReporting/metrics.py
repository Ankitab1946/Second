import pandas as pd
from datetime import datetime

STORY_POINT_FIELD = "customfield_10003"

VALID_ISSUE_TYPES = ["Story", "Task", "Bug", "Sub-task"]
EXCLUDED_WORKLOG_TYPES = ["Xray Test"]

COMPLETION_STATUSES = [
    "Closed",
    "Ready for UAT",
    "In UAT",
    "Accepted for Release",
    "Rejected"
]

# =====================================================
# STORY POINTS
# =====================================================

def calculate_story_points(issues, selected_users=None):

    columns = [
        "user",
        "assigned_sp",
        "completed_sp",
        "spillover_sp",
        "completion_%",
        "commitment_health"
    ]

    records = []

    for issue in issues:

        fields = issue.get("fields", {})
        issue_type = fields.get("issuetype", {}).get("name", "")

        if issue_type not in VALID_ISSUE_TYPES:
            continue

        sp = float(fields.get(STORY_POINT_FIELD, 0) or 0)
        status = fields.get("status", {}).get("name", "")

        assignee = fields.get("assignee")
        user = assignee["displayName"] if assignee else "Unassigned"

        if selected_users and "All" not in selected_users:
            if user not in selected_users:
                continue

        records.append({
            "user": user,
            "sp": sp,
            "status": status
        })

    if not records:
        return pd.DataFrame(columns=columns)

    df = pd.DataFrame(records)

    assigned = df.groupby("user", as_index=False)["sp"].sum()
    assigned.rename(columns={"sp": "assigned_sp"}, inplace=True)

    completed = df[df["status"].isin(COMPLETION_STATUSES)] \
        .groupby("user", as_index=False)["sp"].sum()
    completed.rename(columns={"sp": "completed_sp"}, inplace=True)

    result = assigned.merge(completed, on="user", how="left")
    result["completed_sp"] = result["completed_sp"].fillna(0)

    result["spillover_sp"] = result["assigned_sp"] - result["completed_sp"]

    result["completion_%"] = (
        result["completed_sp"] /
        result["assigned_sp"].replace(0, 1)
    ) * 100

    result["commitment_health"] = result["completion_%"].apply(
        lambda x: "Over" if x > 100
        else "Under" if x < 80
        else "Healthy"
    )

    return result[columns]


# =====================================================
# WORKLOG
# =====================================================

def calculate_worklog(client, issues, start_date=None, end_date=None, selected_users=None):

    columns = ["user", "hours"]
    records = []

    for issue in issues:

        fields = issue.get("fields", {})
        issue_type = fields.get("issuetype", {}).get("name", "")

        if issue_type in EXCLUDED_WORKLOG_TYPES:
            continue

        worklogs = client.get_worklogs(issue["key"])

        for wl in worklogs:

            author = wl.get("author", {}).get("displayName")
            if not author:
                continue

            if selected_users and "All" not in selected_users:
                if author not in selected_users:
                    continue

            hours = wl.get("timeSpentSeconds", 0) / 3600

            started = wl.get("started")
            if started:
                wl_date = datetime.strptime(started[:10], "%Y-%m-%d").date()

                if start_date and wl_date < start_date:
                    continue
                if end_date and wl_date > end_date:
                    continue

            records.append({
                "user": author,
                "hours": hours
            })

    if not records:
        return pd.DataFrame(columns=columns)

    df = pd.DataFrame(records)
    return df.groupby("user", as_index=False).sum()


# =====================================================
# EFFICIENCY
# =====================================================

def calculate_efficiency(df_sp, df_work):

    if df_sp.empty:
        return pd.DataFrame(columns=["user", "efficiency"])

    df = df_sp.merge(df_work, on="user", how="left")
    df["hours"] = df["hours"].fillna(0)

    df["efficiency"] = df.apply(
        lambda x: x["completed_sp"] / x["hours"]
        if x["hours"] > 0 else 0,
        axis=1
    )

    return df


# =====================================================
# VELOCITY
# =====================================================

def calculate_velocity(issues):

    records = []

    for issue in issues:

        fields = issue.get("fields", {})
        sprint = fields.get("sprint")
        status = fields.get("status", {}).get("name", "")
        sp = float(fields.get(STORY_POINT_FIELD, 0) or 0)

        if sprint and status in COMPLETION_STATUSES:

            if isinstance(sprint, list):
                sprint_names = [s.get("name") for s in sprint]
            else:
                sprint_names = [sprint.get("name")]

            for s in sprint_names:
                records.append({"sprint": s, "completed_sp": sp})

    if not records:
        return pd.DataFrame(columns=["sprint", "completed_sp"])

    df = pd.DataFrame(records)
    return df.groupby("sprint", as_index=False).sum()


# =====================================================
# TEAM SCORE
# =====================================================

def calculate_team_score(df_sp, df_work):

    if df_sp.empty or df_work.empty:
        return 0

    total_completed = df_sp["completed_sp"].sum()
    total_assigned = df_sp["assigned_sp"].sum()
    total_hours = df_work["hours"].sum()

    if total_assigned == 0 or total_hours == 0:
        return 0

    commitment_ratio = total_completed / total_assigned
    productivity_ratio = total_completed / total_hours

    return round(commitment_ratio * productivity_ratio, 2)
