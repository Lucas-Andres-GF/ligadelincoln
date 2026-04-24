import requests
import os
from dotenv import load_dotenv

load_dotenv()

url = os.getenv('SUPABASE_URL')
key = os.getenv('SUPABASE_KEY')

# Check existing tables first
response = requests.get(
    f"{url}/rest/v1/",
    headers={"apikey": key, "Authorization": f"Bearer {key}"}
)
print("Tables:", response.json()[:5] if response.text else "empty")