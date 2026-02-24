import plotly.express as px


def bar_assigned_vs_completed(df):
    return px.bar(
        df,
        x="user",
        y=["assigned_sp", "completed_sp"],
        barmode="group",
        title="Assigned vs Completed Story Points"
    )


def stacked_spillover(df):
    return px.bar(
        df,
        x="user",
        y=["completed_sp", "spillover_sp"],
        barmode="stack",
        title="Completed vs Spillover"
    )


def pie_sp_distribution(df):
    return px.pie(
        df,
        values="assigned_sp",
        names="user",
        title="Story Point Distribution"
    )
