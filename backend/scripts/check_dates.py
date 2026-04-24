from supabase import create_client
import os
from dotenv import load_dotenv
load_dotenv()

url = os.getenv('SUPABASE_URL')
key = os.getenv('SUPABASE_KEY')
supabase = create_client(url, key)

# Sample of dates in DB
result = supabase.table('partidos').select('dia').limit(20).execute()
print('Sample dates in DB:')
for p in result.data:
    print(f'  "{p.get("dia")}"')