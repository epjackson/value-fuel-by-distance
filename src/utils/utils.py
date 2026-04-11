import pandas as pd
import streamlit as st
import requests

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
        

def authenticate_fuel_finder_api(client_id: str, client_secret: str):
    token_url = "https://www.fuel-finder.service.gov.uk/api/v1/oauth/generate_access_token"
    token_payload = {
        'grant_type': 'client_credentials',
        'client_id': client_id,
        'client_secret': client_secret
    }

    token_response = requests.post(token_url, data=token_payload)

    if token_response.status_code != 200:
        raise Exception(f"Failed to obtain access token: {token_response.text}")

    oauth_token = token_response.json()["data"]["access_token"]

    headers = {
        "Authorization": f"Bearer {oauth_token}"
    }

    return headers

def call_fuelfinder_api(key: str, endpoint: str, headers: dict):
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

    return all_data

@st.cache_data
def load_fuel_data(client_id: str, client_secret: str):
    """Fetch and merge fuel price + location data from the Fuel Finder API.
    
    Results are cached by Streamlit so the API is only called once per session
    (or until the cache is explicitly cleared via the Refresh Data button).
    
    Returns a tuple of (merged_data, download_timestamp).
    """
    import datetime
    download_timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    headers = authenticate_fuel_finder_api(client_id=client_id, client_secret=client_secret)
    prices = call_fuelfinder_api(key="fuel_prices", endpoint="pfs/fuel-prices", headers=headers)
    locations = call_fuelfinder_api(key="pfs_locations", endpoint="pfs", headers=headers)
    merged_data = merge_data(prices, locations)
    return merged_data, download_timestamp

def merge_data(prices: list, locations: list):
    prices_data = pd.DataFrame(prices)
    location_data = pd.DataFrame(locations)

    b7_diesel_prices, b7_diesel_effective_from = zip(*prices_data["fuel_prices"].apply(lambda x: parse_prices(x if isinstance(x, list) else eval(x))))
    e10_petrol_prices, e10_petrol_effective_from = zip(*prices_data["fuel_prices"].apply(lambda x: parse_prices(x if isinstance(x, list) else eval(x), fuel_type="E10")))
    prices_data["b7_standard_price"] = b7_diesel_prices
    prices_data["b7_standard_effective_from"] = b7_diesel_effective_from
    prices_data["e10_standard_price"] = e10_petrol_prices
    prices_data["e10_standard_effective_from"] = e10_petrol_effective_from

    merged_data = pd.merge(location_data, prices_data, on=["node_id", "trading_name"], how="outer")

    return merged_data

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
