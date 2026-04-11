# Streamlit frontend - user input for postcode
import streamlit as st
import plotly.express as px

from src.utils.utils import route_distance, postcode_lookup, load_fuel_data
from src.utils.map import visualize_data

tank_litres = 50 # litres

st.set_page_config(
    page_title="Fuel Prices Near Me",
    page_icon=":fuelpump:",
    layout="wide",
    )
st.title(
    ":fuelpump: Fuel Prices Near Me",
    help="**Assumptions**\n\nTotal cost includes a 50 litre tank refuel.")

distance_by_road_network = st.checkbox(
    "Calculate distance on road network (slower than 'as the crow flies').",
    value=False,
    key="distance_calculation_method",
    disabled=True,
    help="This feature uses `osmnx` to calculate the distance from your location to each fuel station by the road network, which is more accurate but can be slow to compute. It is currently **disabled** while I work on optimizing the performance. In the meantime, the app uses straight-line distance as a proxy for road distance, which should still give a good indication of nearby fuel stations.",
    )

# Refresh Data button — clears the cached fuel data so it is re-downloaded on next query
if st.button("🔄 Refresh Fuel Data", help="Force re-download of fuel price and station data from the API. Use this if you think the data may be stale."):
    load_fuel_data.clear()
    st.toast("Cache cleared — data will be re-downloaded on your next search.", icon="✅")

col1, col2, col3, col4 = st.columns(4)

with col1:
    postcode = st.text_input(
        "Postcode:",
        max_chars=7,
        width=400,
        on_change=lambda: None,
        placeholder="e.g. YO1 7NJ / YO179JN",
        help="Enter your postcode to find nearby fuel stations and prices. The app will use the coordinates of the postcode to calculate distances to fuel stations. You should enter a 6-character postcode with <SPACE> and a 7-character postcode without <SPACE>."
        )

with col2:
    fuel_type = st.selectbox(
        "Select fuel type:",
        options=["DIESEL (B7 Standard)", "PETROL (E10 Standard)"],
        key="fuel_type",
        width=400,
        help="Currently only DIESEL (B7 Standard) and PETROL (E10 Standard) are supported, as these are the most common fuel types. Select the fuel type you want to compare prices for at nearby stations."
        )

with col3:
    assumed_miles_per_litre = st.number_input(
        "Assumed miles per litre (additional travel cost):",
        value=10,
        min_value=1,
        max_value=20,
        key="assumed_miles_per_litre",
        width=400,
        help="Enter an assumed miles per litre for your vehicle to calculate the additional travel cost of going to each fuel station. This is used to estimate the total cost of refuelling at each station, including the cost of travelling there and back. The default value is 10 miles per litre but will vary considerably between vehicles."
        )
    
with col4:
    radius_from_origin = st.slider(
        "Maximum distance from your location (miles):",
        min_value=1,
        max_value=20,
        value=15,
        key="max_distance",
        width=400,
        help="Select the maximum radius from your location (in miles) to consider when showing nearby fuel stations."
    )

if fuel_type == "DIESEL (B7 Standard)":
    fuel_type_key = "b7_standard"
elif fuel_type == "PETROL (E10 Standard)":
    fuel_type_key = "e10_standard"

if postcode:
    try:
        client_id = st.secrets["CLIENT_ID"]
        client_secret = st.secrets["CLIENT_SECRET"]
    except (KeyError, AttributeError) as e:
        st.error(
            "⚠️ API credentials not found. Please ensure `CLIENT_ID` and `CLIENT_SECRET` "
            "are configured in Streamlit secrets (Settings → Secrets on Streamlit Cloud, "
            "or `.streamlit/secrets.toml` locally)."
        )
        st.stop()

    if not client_id or not client_secret:
        st.error(
            "⚠️ API credentials are empty. Please check that `CLIENT_ID` and `CLIENT_SECRET` "
            "are set correctly in Streamlit secrets."
        )
        st.stop()

    try:
        merged_data, last_download_time = load_fuel_data(client_id=client_id, client_secret=client_secret)
    except Exception as e:
        st.error(f"⚠️ Failed to load fuel data: {e}")
        st.stop()

    coords = postcode_lookup(postcode)

    merged_data["latitude"] = merged_data["location"].apply(lambda x: x["latitude"] if isinstance(x, dict) else eval(x)["latitude"])
    merged_data["longitude"] = merged_data["location"].apply(lambda x: x["longitude"] if isinstance(x, dict) else eval(x)["longitude"])

    # list 5 fuel stations and prices closest to the coordinates given (as the crow flies)
    merged_data["distance"] = ((merged_data["latitude"] - coords[0])**2 + (merged_data["longitude"] - coords[1])**2)**0.5

    # convert distance to miles
    merged_data["distance_miles"] = merged_data["distance"] * 69

    closest_stations = merged_data.sort_values("distance_miles")

    if distance_by_road_network:
        # calculate distance by road network
        closest_stations["distance_by_road_miles"] = closest_stations.apply(lambda row: route_distance(coords, (row["latitude"], row["longitude"])), axis=1)
    else:
        # use straight line distance as a proxy for road distance
        closest_stations["distance_by_road_miles"] = closest_stations["distance_miles"]

    closest_stations = closest_stations.sort_values(["distance_by_road_miles", f"{fuel_type_key}_price"]).reset_index(drop=True)
    
    # show all fuel stations within 10 miles by road, sorted by distance and price, but limit to 10 results maximum
    closest_stations = closest_stations[
         (closest_stations["distance_by_road_miles"] <= radius_from_origin) &
         (closest_stations[f"{fuel_type_key}_price"].notnull())
        #  ].head(20)
    ]    # show all stations within selected radius

    actual_closest_distance = closest_stations.loc[0, "distance_by_road_miles"]
    actual_closest_price = closest_stations.loc[0, f"{fuel_type_key}_price"]
    
    def _calculate_travel_cost(df):
        travel_cost = (df["distance_by_road_miles"] / assumed_miles_per_litre) * df[f"{fuel_type_key}_price"] * 2
        return travel_cost

    closest_stations["core_fuel_cost"] = closest_stations[f"{fuel_type_key}_price"] * tank_litres
    closest_stations["additional_travel_cost"] = _calculate_travel_cost(closest_stations)
    closest_stations["total_cost_£"] = (closest_stations["core_fuel_cost"] + closest_stations["additional_travel_cost"]) / 100

    # final sort by total cost, then distance
    closest_stations.sort_values(["total_cost_£", "distance_by_road_miles"], inplace=True)

    # cost saving over the closest station
    closest_stations["cost_saving_£"] = (closest_stations["total_cost_£"] - closest_stations.loc[0, "total_cost_£"]).apply(lambda x: f"{x:.2f}")

    # format total cost to 2 decimal places
    closest_stations["total_cost_£"] = closest_stations["total_cost_£"].apply(lambda x: f"{x:.2f}")
    
    st.divider()
    st.warning(f"Only showing fuel stations within {radius_from_origin} miles by road.")

    col1, col2 = st.columns([0.6, 0.4])

    with col1:
        def highlight_savings(val):
            try:
                val_float = float(val)
                if val_float < 0:
                    # green for savings, with intensity based on magnitude
                    intensity = min(1, abs(val_float) / 10) # cap intensity at £10 savings
                    return f"background-color: rgba(144, 238, 144, {intensity}); font-weight: bold"
                elif val_float >= 0:
                    # red for extra cost, with intensity based on magnitude
                    intensity = min(1, abs(val_float) / 10) # cap intensity at £10 extra cost
                    return f"background-color: rgba(255, 182, 193, {intensity}); font-weight: bold"
            except ValueError:
                print(f"Could not convert value to float: {val}")


        closest_stations_display = closest_stations[[
                "trading_name",
                "distance_by_road_miles",
                f"{fuel_type_key}_price",
                f"{fuel_type_key}_effective_from",
                "total_cost_£",
                "cost_saving_£",]]
        st.dataframe(
            closest_stations_display.style.applymap(highlight_savings, subset=["cost_saving_£"]),
            column_config={
                "trading_name": st.column_config.TextColumn(
                    "Fuel Station",
                    help="The name of the fuel station.",
                    width="medium"
                ),
                "distance_by_road_miles": st.column_config.NumberColumn(
                    "Distance (mi)",
                    help="The distance to the fuel station by road.",
                    width="small",
                    format="%.4f",
                ),
                f"{fuel_type_key}_price": st.column_config.NumberColumn(
                    f"Price (p/ltr)",
                    help=f"The price of {fuel_type} at the fuel station, in pence per litre.",
                    width="small",
                    format="%.1f",
                ),
                f"{fuel_type_key}_effective_from": st.column_config.TextColumn(
                    "Price Effective From",
                    help=f"The date and time from which the displayed price of {fuel_type} is effective.",
                    width="medium"
                ),
                "total_cost_£": st.column_config.NumberColumn(
                    "Total (£)",
                    help="The estimated total cost of refuelling at this station, including the cost of the fuel and the additional travel cost based on the distance and assumed miles per litre.",
                    width="small",
                    format="%.2f",
                ),
                "cost_saving_£": st.column_config.NumberColumn(
                    "Saving (£)",
                    help="The estimated cost saving (or extra cost if positive) of refuelling at this station compared to the closest station, based on the total cost.",
                    width="small",
                    format="%.2f",
                ),
            },
            hide_index=True,
        )

        st.divider()

        uk_price_range = merged_data[f"{fuel_type_key}_price"].dropna()

        # remove outliers from uk_price_range using IQR method
        Q_low = uk_price_range.quantile(0.01)
        Q_high = uk_price_range.quantile(0.99)
        uk_price_range = uk_price_range[(uk_price_range >= Q_low) & (uk_price_range <= Q_high)]

        # Add y column with value 0 but jitter with small random noise where prices are the same to avoid overlapping points
        closest_stations["y"] = 0
        
        # Add jitter to y values where prices are the same to avoid overlapping points
        import random
        price_counts = closest_stations[f"{fuel_type_key}_price"].value_counts()
        for price, count in price_counts.items():
            if count > 1:
                indices = closest_stations[closest_stations[f"{fuel_type_key}_price"] == price].index
                # ensure the first point has no jitter and subsequent points have jitter between -0.1 and 0.1
                jitter = [0]
                jitter.extend(random.uniform(-0.1, 0.1) for _ in range(count-1))
                closest_stations.loc[indices, "y"] += jitter

        # add a chart showing the distribution of prices for the closest stations, along a horizontal line from min to max UK prices
        fig = px.scatter(
            closest_stations,
            x=f"{fuel_type_key}_price",
            y="y",
            size="distance_by_road_miles",
            range_x=[uk_price_range.min(), uk_price_range.max()],
            hover_name="trading_name",
        )
        fig.update_traces(
            hovertemplate=
                    "<b>%{hovertext}</b><br>" +
                    "<b>Price: %{x}p</b><br>" +
                    "<b>Distance: %{marker.size:.2f} miles</b><br><br>" +
                    "<extra></extra>",
        mode='markers',
)
        fig.update_layout(
            margin={"r":0,"t":0,"l":0,"b":0},
            height=100,
            )
        fig.update_xaxes(visible=False, showticklabels=False)
        fig.update_yaxes(visible=False, showticklabels=False)

        config = {
            "displayModeBar": False,
            "displaylogo": False,
            "scrollZoom": False,
           }
        fig.add_hline(y=0, line_dash="dash", line_color="grey")

        # add label for min and max UK prices
        fig.add_annotation(x=uk_price_range.min(), y=0, text=f"{uk_price_range.min()}p", showarrow=False, xshift=20, yshift=10)
        fig.add_annotation(x=uk_price_range.max(), y=0, text=f"{uk_price_range.max()}p", showarrow=False, xshift=-20, yshift=10)

        range_info = "The chart below shows the prices of nearby fuel stations in the context of the overall UK price range from 1st to 99th percentile (i.e. excluding outliers). Each point represents a fuel station, with the size of the point indicating the distance from the current location. The horizontal dashed line represents the price of the closest station. You can hover over each point to see more details about the station and its price."
        st.subheader("Local fuel prices compared to UK range", help=range_info)
        st.plotly_chart(
            fig,
            config=config,
       )

    with col2:
        zoom = 9 # fixed as we are showing stations within 15 miles by road, so a zoom of 9 should be appropriate to show the area clearly
        fig = visualize_data(closest_stations, zoom=zoom, postcode=postcode, origin=coords, radius_miles=radius_from_origin, fuel_type=fuel_type_key)

        fig.update_layout(
            margin={"r":0,"t":0,"l":0,"b":0},
            mapbox={"center": {"lat": coords[0], "lon": coords[1]}},
            )
        config = {
            "displayModeBar": False,
            "displaylogo": False,
            # currently fixed zoom as radius display not updating
            "scrollZoom": False
           }
        st.plotly_chart(
            fig,
            config=config,
            # width="stretch",
        )
    
    st.divider()
    
    # line ranging from minimum to maximum total cost, with markers for each station, and a vertical line for the actual closest station's total cost
    fig_cost = px.scatter(
        closest_stations,
        x="total_cost_£",
        y="trading_name",
        size="distance_by_road_miles",
        color="distance_by_road_miles",
        color_continuous_scale="Viridis",
        title="Total Cost of Refuelling (including travel cost)",
    )

else:
    pass

if 'last_download_time' not in dir():
    last_download_time = None

if last_download_time:
    st.write(f"Data last downloaded at: {last_download_time}")
