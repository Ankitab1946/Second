import plotly.express as px

def efficiency_chart(df):
    return px.bar(
        df,
        x="user",
        y="efficiency",
        title="SP vs Hours Efficiency"
    )

def velocity_chart(df):
    return px.line(
        df,
        x="sprint",
        y="completed_sp",
        markers=True,
        title="Velocity Trend"
    )

def commitment_snapshot(df):
    return px.bar(
        df,
        x="user",
        y=["assigned_sp", "completed_sp"],
        barmode="group",
        title="Committed vs Completed SP"
    )
