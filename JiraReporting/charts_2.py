import plotly.express as px

# =====================================================
# EXISTING SPRINT CHARTS (Baseline)
# =====================================================

def bar_assigned_vs_completed(df):
    if df.empty:
        return None

    return px.bar(
        df,
        x="user",
        y=["assigned_sp", "completed_sp"],
        barmode="group",
        title="Assigned vs Completed Story Points"
    )


def stacked_spillover(df):
    if df.empty:
        return None

    return px.bar(
        df,
        x="user",
        y=["completed_sp", "spillover_sp"],
        barmode="stack",
        title="Completed vs Spillover"
    )


def pie_sp_distribution(df):
    if df.empty:
        return None

    return px.pie(
        df,
        values="assigned_sp",
        names="user",
        title="Story Point Distribution"
    )


# =====================================================
# NEW SPRINT ANALYTICS CHARTS
# =====================================================

def commitment_snapshot(df):
    if df.empty:
        return None

    return px.bar(
        df,
        x="user",
        y=["assigned_sp", "completed_sp"],
        barmode="group",
        title="Committed vs Completed Story Points"
    )


def efficiency_chart(df):
    if df.empty or "efficiency" not in df.columns:
        return None

    return px.bar(
        df,
        x="user",
        y="efficiency",
        title="SP vs Hours Efficiency"
    )


def velocity_chart(df):
    if df.empty:
        return None

    return px.line(
        df,
        x="sprint",
        y="completed_sp",
        markers=True,
        title="Velocity Trend"
    )


def sp_vs_hours_chart(df):
    if df.empty:
        return None

    return px.bar(
        df,
        x="user",
        y=["completed_sp", "hours"],
        barmode="group",
        title="SP vs Logged Hours"
    )


# =====================================================
# GITLAB CHARTS
# =====================================================

def gitlab_commit_bar(df):
    if df.empty:
        return None

    return px.bar(
        df,
        x="author_name",
        y="commit_count",
        title="Commits per Author"
    )


def gitlab_commit_trend(df):
    if df.empty:
        return None

    return px.line(
        df,
        x="date",
        y="commit_count",
        markers=True,
        title="Commit Trend"
    )
