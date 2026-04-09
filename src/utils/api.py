# %%
from dotenv import load_dotenv
import os
import requests
import streamlit as st

load_dotenv()
CLIENT_ID = os.getenv("fuel_finder_api_client_id")
CLIENT_SECRET = os.getenv("fuel_finder_api_client_secret")
token_url = "https://www.fuel-finder.service.gov.uk/api/v1/oauth/generate_access_token"
token_payload = {
    'grant_type': 'client_credentials',
    'client_id': CLIENT_ID,
    'client_secret': CLIENT_SECRET
} or {
    "client_id": st.secrets["api"]["client_id"],
    "client_secret": st.secrets["api"]["client_secret"]
}

token_response = requests.post(token_url, data=token_payload)

if token_response.status_code != 200:
    raise Exception(f"Failed to obtain access token: {token_response.text}")

oauth_token = token_response.json()["data"]["access_token"]

headers = {
    "Authorization": f"Bearer {oauth_token}"
}

all_data = []
batch_number = 1
while True:
    print(f"Fetching data for stations: ... to {batch_number*500}")
    data = requests.get(
        f"https://www.fuel-finder.service.gov.uk/api/v1/pfs/fuel-prices?batch-number={batch_number}",
        headers=headers
    )
    if data.status_code != 200:
        break
    else:
        all_data = all_data + data.json()
        batch_number += 1

# %%
import pandas as pd
pd.DataFrame(all_data).to_csv("fuel_prices.csv", index=False)



# %%
import pandas as pd
df = pd.DataFrame(data.json())
df.head()
# %%

# %%
