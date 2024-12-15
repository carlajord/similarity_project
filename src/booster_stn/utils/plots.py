import plotly.graph_objects as go

def PlotHydrateTemperature(df, col_name):
    
    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=df.index,
            y=df[col_name],
            name=col_name
        )
    )
    fig.update_layout(
        yaxis=dict(
            title=col_name,
            range=[40,70]
        ),
        xaxis=dict(
            title="Station"
        ),
        title_text="Hydrate Formation Temperature at Booster Station"
    )
    fig.show()

def PlotMethanolRates(df_summer, df_winter, col_name):
    
    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=df_summer.index,
            y=df_summer[col_name],
            name="Summer"
        )
    )
    fig.add_trace(
        go.Bar(
            x=df_winter.index,
            y=df_winter[col_name],
            name="Winter"
        )
    )
    fig.update_layout(
        yaxis=dict(
            title=col_name
        ),
        xaxis=dict(
            title="Station"
        ),
        title_text="Hydrate Formation Temperature at Booster Station"
    )
    fig.show()

def PlotCoolerSensitivity(summer_df, winter_df, x_name, y_methanol_name, y_water_name):
    
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=summer_df[x_name],
            y=summer_df[y_methanol_name],
            name="Summer Injection"
        )
    )
    fig.add_trace(
        go.Scatter(
            x=winter_df[x_name],
            y=winter_df[y_methanol_name],
            name="Winter Injection"
        )
    )
    fig.add_trace(
        go.Scatter(
            x=winter_df[x_name],
            y=winter_df[y_water_name],
            name="Water Content",
            yaxis="y2"
        )
    )
    fig.update_layout(
        xaxis=dict(
            title=x_name,
            showgrid=False
        ),
        title_text="Cooler Temperature Sensitivity",
        yaxis2=dict(
            title=y_water_name,
            overlaying="y",
            side="right",
            range=[0, 50],
            showgrid=False
        ),
        yaxis=dict(
            title=y_methanol_name,
            range=[0, 35],
            showgrid=False
        ),
        legend=dict(
            x=0.01,
            y=0.99
        )
    )
    fig.show()