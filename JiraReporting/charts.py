import plotly.express as px


def commitment_snapshot(df):
    if df is None or df.empty:
        return None

    return px.bar(
        df,
        x="user",
        y=["assigned_sp", "completed_sp"],
        barmode="group",
        title="Committed vs Completed Story Points"
    )


def efficiency_chart(df):
    if df is None or df.empty:
        return None

    return px.bar(
        df,
        x="user",
        y="efficiency",
        title="SP vs Hours Efficiency"
    )


def velocity_chart(df):
    if df is None or df.empty:
        return None

    return px.line(
        df,
        x="sprint",
        y="completed_sp",
        markers=True,
        title="Velocity Trend"
    )


def sp_vs_hours_chart(df):
    if df is None or df.empty:
        return None

    return px.bar(
        df,
        x="user",
        y=["completed_sp", "hours"],
        barmode="group",
        title="SP vs Logged Hours"
    )


def gitlab_commit_bar(df):
    if df is None or df.empty:
        return None

    return px.bar(
        df,
        x="author_name",
        y="commit_count",
        title="Commits per Author"
    )


def gitlab_commit_trend(df):
    if df is None or df.empty:
        return None

    return px.line(
        df,
        x="date",
        y="commit_count",
        markers=True,
        title="Commit Trend"
    )
