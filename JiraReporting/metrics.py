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

    if not issues:
        return pd.DataFrame(columns=columns)

    records = []

    for issue in issues:

        if not issue:
            continue

        fields = issue.get("fields") or {}

        issuetype_obj = fields.get("issuetype") or {}
        issue_type = issuetype_obj.get("name", "")

        if issue_type not in VALID_ISSUE_TYPES:
            continue

        sp = float(fields.get(STORY_POINT_FIELD, 0) or 0)

        status_obj = fields.get("status") or {}
        status = status_obj.get("name", "")

        assignee_obj = fields.get("assignee")
        user = (
            assignee_obj.get("displayName")
            if isinstance(assignee_obj, dict)
            else "Unassigned"
        )

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
        lambda x: "Over" if x > 100 else
                  "Under" if x < 80 else
                  "Healthy"
    )

    return result[columns]


# =====================================================
# WORKLOG
# =====================================================

def calculate_worklog(client, issues, start_date=None, end_date=None, selected_users=None):

    columns = ["user", "hours"]

    if not issues:
        return pd.DataFrame(columns=columns)

    records = []

    for issue in issues:

        fields = issue.get("fields") or {}
        issue_type = (fields.get("issuetype") or {}).get("name", "")

        if issue_type in EXCLUDED_WORKLOG_TYPES:
            continue

        worklogs = client.get_worklogs(issue.get("key"))

        for wl in worklogs or []:

            author = (wl.get("author") or {}).get("displayName")

            if not author:
                continue

            if selected_users and "All" not in selected_users:
                if author not in selected_users:
                    continue

            hours = wl.get("timeSpentSeconds", 0) / 3600

            started = wl.get("started")
            if started:
                try:
                    wl_date = datetime.strptime(
                        started[:10], "%Y-%m-%d"
                    ).date()
                except:
                    continue

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
        return pd.DataFrame(columns=["user", "efficiency", "hours"])

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

    if not issues:
        return pd.DataFrame(columns=["sprint", "completed_sp"])

    records = []

    for issue in issues:

        fields = issue.get("fields") or {}
        sprint_field = fields.get("customfield_10007")
        status = (fields.get("status") or {}).get("name", "")
        sp = float(fields.get(STORY_POINT_FIELD, 0) or 0)

        if not sprint_field:
            continue

        if status not in COMPLETION_STATUSES:
            continue

        if isinstance(sprint_field, list):
            for s in sprint_field:
                if isinstance(s, dict) and s.get("name"):
                    records.append({
                        "sprint": s.get("name"),
                        "completed_sp": sp
                    })

    if not records:
        return pd.DataFrame(columns=["sprint", "completed_sp"])

    df = pd.DataFrame(records)
    return df.groupby("sprint", as_index=False).sum()
