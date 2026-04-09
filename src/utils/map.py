import plotly.express as px
import pandas as pd

def visualize_data(
        data: pd.DataFrame,
        zoom: int = 5,
        postcode: str | None = None,
        origin: tuple[float, float] | None = None,
        radius_miles: int | None = None,
        fuel_type: str = "b7_standard",
        distance: float | None = None,):
    fig = px.scatter_map(
            data,
            lat="latitude",
            lon="longitude",
            hover_name="trading_name",
            hover_data={
                "latitude": False,
                "longitude": False,
                },
            custom_data=["trading_name", f"{fuel_type}_price"],
            zoom=zoom,
            height=600,
            map_style="open-street-map",
        )
    
    fig.update_traces(
        hovertemplate=
                "<b>%{customdata[0]}</b><br>" +
                "<b>%{customdata[1]}p</b><br><br>" +
                "<extra></extra>",
    mode='markers',
    marker={'sizemode':'area',
            'size': 10,
            'color':'#1f77b4',},
    )

    # plot origin
    if origin is not None:
        fig2 = px.scatter_map(
                pd.DataFrame({"latitude": [origin[0]], "longitude": [origin[1]]}),
                lat="latitude",
                lon="longitude",
                zoom=zoom,
                height=600,
                map_style="open-street-map",
            ).data[0]
    
        # TODO: latest trace is grey star of size 20
        fig2.update(marker={'sizemode': 'area', 'size': 20, 'color': '#7f7f7f', 'symbol': 'star'},
                    hovertemplate=f"<b>{postcode}</b><br><extra></extra>",)
        fig.add_trace(fig2)

        # plot radius circle
        fig3 = px.scatter_map(
                pd.DataFrame({"latitude": [origin[0]], "longitude": [origin[1]]}),
                lat="latitude",
                lon="longitude",
                zoom=zoom,
                height=600,
                map_style="open-street-map",
            ).data[0]

        fig3.update(marker={'sizemode': 'area', 'size': radius_miles * zoom * 4, 'color': '#7f7f7f', 'opacity': 0.2},
                    hovertemplate=f"<b>{postcode}</b><br><extra></extra>",)
        fig.add_trace(fig3)

    return fig