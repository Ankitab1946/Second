import pandas as pd
from datetime import datetime


def calculate_story_points(issues, story_point_field):

    records = []

    for issue in issues:
        fields = issue.get("fields", {})

        assignee = fields.get("assignee")
        assignee_name = assignee["displayName"] if assignee else "Unassigned"

        sp = fields.get(story_point_field, 0) or 0
        status = fields.get("status", {}).get("name", "")

        records.append({
            "assignee": assignee_name,
            "story_points": float(sp),
            "status": status
        })

    df = pd.DataFrame(records)

    if df.empty:
        return df

    grouped = df.groupby("assignee", as_index=False).agg(
        assigned_sp=("story_points", "sum")
    )

    completed = df[
        df["status"].str.lower().str.contains("done")
    ].groupby("assignee", as_index=False)["story_points"].sum()

    completed.columns = ["assignee", "completed_sp"]

    grouped = grouped.merge(completed, on="assignee", how="left")
    grouped["completed_sp"] = grouped["completed_sp"].fillna(0)

    grouped["spillover_sp"] = grouped["assigned_sp"] - grouped["completed_sp"]

    grouped["completion_%"] = (
        grouped["completed_sp"] /
        grouped["assigned_sp"].replace(0, 1)
    ) * 100

    return grouped


def calculate_worklog(client, issues, start_date, end_date):

    data = []

    for issue in issues:
        worklogs = client.get_worklogs(issue["key"])

        for wl in worklogs:
            author = wl["author"]["displayName"]
            time_spent = wl["timeSpentSeconds"] / 3600

            created = wl.get("started")
            if created:
                wl_date = datetime.strptime(
                    created[:10], "%Y-%m-%d"
                ).date()

                if start_date and end_date:
                    if not (start_date <= wl_date <= end_date):
                        continue

            data.append({
                "author": author,
                "hours": time_spent
            })

    df = pd.DataFrame(data)

    if df.empty:
        return df

    return df.groupby("author", as_index=False).agg(
        total_hours=("hours", "sum")
    )   
