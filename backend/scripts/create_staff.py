import requests
import json
import os
from dotenv import load_dotenv

load_dotenv()

url = os.getenv('SUPABASE_URL')
key = os.getenv('SUPABASE_KEY')

# Check if table exists
response = requests.get(
    f"{url}/rest/v1/partido_staff?select=id&limit=1",
    headers={"apikey": key, "Authorization": f"Bearer {key}"}
)
print(f"Check status: {response.status_code}")

if response.status_code == 200:
    print("Table exists")
else:
    # Create via insert (will fail but let's see)
    print(f"Table doesn't exist, trying to create: {response.status_code}")
    # Try POST to create
    res = requests.post(
        f"{url}/rest/v1/partido_staff",
        json={"partido_id": 999999, "dt_local": "test", "dt_visitante": "test", "arbitro": "test"},
        headers={
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Prefer": "return=minimal",
            "Content-Type": "application/json"
        }
    )
    print(f"Create attempt: {res.status_code} - {res.text[:300]}")