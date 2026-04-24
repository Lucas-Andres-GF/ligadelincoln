import requests
import os
from dotenv import load_dotenv

load_dotenv()

url = os.getenv('SUPABASE_URL')
key = os.getenv('SUPABASE_KEY')

# SQL to add columns
sql = """
ALTER TABLE partidos ADD COLUMN IF NOT EXISTS dt_local text;
ALTER TABLE partidos ADD COLUMN IF NOT EXISTS dt_visitante text;
ALTER TABLE partidos ADD COLUMN IF NOT EXISTS arbitro text;
"""

response = requests.post(
    f"{url}/rest/v1/rpc/exec_sql",
    json={"query": sql},
    headers={
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json"
    }
)

print(f"Status: {response.status_code}")
print(response.text)