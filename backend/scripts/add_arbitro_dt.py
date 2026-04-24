from supabase import create_client
import os
from dotenv import load_dotenv

load_dotenv()

url = os.getenv('SUPABASE_URL')
key = os.getenv('SUPABASE_KEY')
supabase = create_client(url, key)

# Add dt and arbitro columns to partidos table
try:
    supabase.table("partidos").alter().add_column("dt_local", "text").execute()
    print("Added dt_local column")
except Exception as e:
    print(f"dt_local: {e}")

try:
    supabase.table("partidos").alter().add_column("dt_visitante", "text").execute()
    print("Added dt_visitante column")
except Exception as e:
    print(f"dt_visitante: {e}")

try:
    supabase.table("partidos").alter().add_column("arbitro", "text").execute()
    print("Added arbitro column")
except Exception as e:
    print(f"arbitro: {e}")