import pandas as pd

def _current_time():
    import datetime
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def _latest_download_time():
    timestamp = _current_time()

    # write timestamp to file
    with open("download.txt", "w") as f:
        f.write(timestamp)

def postcode_lookup(postcode: str):
    
    import uk_postcodes_parsing as ukp

    # Lookup a postcode
    result = ukp.lookup_postcode(postcode)

    if result:
        coords = (result.latitude, result.longitude)

        return coords
    
    else:
        print(f"Postcode {postcode} not found.")
        return None  
        
  
def get_data():
    current_time = _current_time()
    
    # compare current time to timestamp in download.txt, if the difference is less than 30 minutes, skip downloading data
    try:
        with open("download.txt", "r") as f:
            last_download_time = f.read()
            last_download_time = pd.to_datetime(last_download_time)
            current_time_dt = pd.to_datetime(current_time)
            time_diff = (current_time_dt - last_download_time).total_seconds() / 60
            if time_diff < 60:
                print(f"Data was downloaded {time_diff:.2f} minutes ago. Skipping download.")
                return
    except FileNotFoundError:
        pass

    # from dotenv import load_dotenv
    # import os
    import requests
    import streamlit as st

    # load_dotenv()
    # os.environ["CLIENT_ID"] = st.secrets["client_id"]
    # os.environ["CLIENT_SECRET"] = st.secrets["client_secret"]
    # CLIENT_ID = os.getenv("fuel_finder_api_client_id")
    # CLIENT_SECRET = os.getenv("fuel_finder_api_client_secret")
    token_url = "https://www.fuel-finder.service.gov.uk/api/v1/oauth/generate_access_token"
    token_payload = {
        'grant_type': 'client_credentials',
        'client_id': st.secrets["client_id"],
        'client_secret': st.secrets["client_secret"]
    }

    token_response = requests.post(token_url, data=token_payload)

    if token_response.status_code != 200:
        raise Exception(f"Failed to obtain access token: {token_response.text}")

    oauth_token = token_response.json()["data"]["access_token"]

    headers = {
        "Authorization": f"Bearer {oauth_token}"
    }

    required_data = {
        "fuel_prices": "pfs/fuel-prices",
        "pfs_locations": "pfs",
    }

    for key, endpoint in required_data.items():
        print(f"Fetching data for {key}...")
        all_data = []
        batch_number = 1
        while True:
            data = requests.get(
                f"https://www.fuel-finder.service.gov.uk/api/v1/{endpoint}?batch-number={batch_number}",
                headers=headers
            )
            if data.status_code != 200:
                break
            else:
                all_data = all_data + data.json()
                batch_number += 1

        print(f"Total records for {key}: {len(all_data)}")
        pd.DataFrame(all_data).to_csv(f"data/raw/{key}.csv", index=False)

        _latest_download_time()



# def merge_dataframes(df1, df2, on: list[str]):
#     """
#     Merge two DataFrames on a specified column.

#     Parameters:
#     df1 (pd.DataFrame): The first DataFrame.
#     df2 (pd.DataFrame): The second DataFrame.
#     on (list[str]): The column name(s) to merge on.

#     Returns:
#     pd.DataFrame: A merged DataFrame.
#     """
#     try:
#         merged_df = pd.merge(df1, df2, on=on)
#         print(f"DataFrames merged successfully on '{on}'")
#         return merged_df
#     except Exception as e:
#         print(f"Error merging DataFrames: {e}")
#         return None

def _filter_fuel(prices_list: list[dict], fuel_type: str):
    for price_dict in prices_list:
        if price_dict["fuel_type"] == fuel_type:
            return price_dict
    return None

def _effective_from(price_dict: dict):
    from datetime import datetime
    effective_from = datetime.strptime(price_dict["price_change_effective_timestamp"], "%Y-%m-%dT%H:%M:%S.%fZ")
    return effective_from.strftime("%A, %d %B -  %H:%M:%S")

def parse_prices(prices_list: list[dict], fuel_type: str = "B7_STANDARD"):
    filtered_price_dict = _filter_fuel(prices_list, fuel_type=fuel_type)
    filtered_price = float(filtered_price_dict["price"]) if filtered_price_dict else None
    price_effective_from = _effective_from(filtered_price_dict) if filtered_price_dict else None

    return filtered_price, price_effective_from

# def parse_last_updated(prices_list: list[dict]):
#     # extract the last updated timestamp for B7_STANDARD diesel from the list of price dictionaries
#     # record as datetime and return None if not found
#     standard_diesel_last_updated = None
#     for price_dict in prices_list:
#         if price_dict["fuel_type"] == "B7_STANDARD":

#             from datetime import datetime
#             standard_diesel_last_updated = datetime.strptime(price_dict["price_last_updated"], "%Y-%m-%dT%H:%M:%S.%fZ")
#             standard_diesel_last_updated = standard_diesel_last_updated.strftime("%A, %d %B -  %H:%M:%S")
            
#             break

#     return standard_diesel_last_updated

def filter_by_radius(dataframe: pd.DataFrame, center_lat: float, center_lon: float, radius_miles: float) -> pd.DataFrame:
    import geopandas as gpd

    # Convert the DataFrame to a GeoDataFrame
    gdf = gpd.GeoDataFrame(
        dataframe, geometry=gpd.points_from_xy(dataframe.longitude, dataframe.latitude), crs="EPSG:4326"
    )
    # Project to a metric CRS for accurate distance calculations
    gdf = gdf.to_crs(epsg=3857)

    # Create a buffer around the center point
    center_point = gpd.GeoSeries(gpd.points_from_xy([center_lon], [center_lat]), crs="EPSG:4326").to_crs(epsg=3857)
    buffer = center_point.buffer(radius_miles * 1609.34)  # Convert miles to meters

    # Filter the GeoDataFrame to include only points within the buffer
    filtered_gdf = gdf[gdf.geometry.within(buffer.unary_union)]
    # Convert back to the original CRS
    filtered_gdf = filtered_gdf.to_crs(epsg=4326)
    return filtered_gdf.drop(columns="geometry")

def route_distance(origin, destination):
    import osmnx as ox

    ox.settings.use_cache = True

    # Get the nearest road network graph for the area
    G = ox.graph_from_point(
        origin,
        dist=20000,
        dist_type="bbox",
        network_type="drive",
        truncate_by_edge=False,
        custom_filter='["highway"~"primary|secondary|tertiary"]'
        )
    
    # G = ox.load_graphml("53_1283__-1_9189.graphml")

    # Find the nearest graph nodes to the actual coordinates
    orig_node = ox.distance.nearest_nodes(G, origin[1], origin[0])
    dest_node = ox.distance.nearest_nodes(G, destination[1], destination[0])

    # Find the shortest path between the nodes
    import multiprocessing as mp
    cpus = mp.cpu_count() - 1  # Use all but one CPU core
    route = ox.routing.shortest_path(G, orig_node, dest_node, cpus=cpus, weight='length')

    # Calculate the total distance of the route
    route_gdf = ox.routing.route_to_gdf(G, route)
    total_distance_miles = route_gdf['length'].sum()*0.000621371  # Total distance in miles
    return total_distance_miles
