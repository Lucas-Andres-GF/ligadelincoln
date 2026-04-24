from supabase import create_client
import os
from dotenv import load_dotenv
load_dotenv()

url = os.getenv('SUPABASE_URL')
key = os.getenv('SUPABASE_KEY')
supabase = create_client(url, key)

# Get distinct dates
result = supabase.table('partidos').select('dia').execute()
all_dates = [p.get('dia') for p in result.data if p.get('dia')]
unique_dates = list(set(all_dates))
print('Unique dates:')
for d in sorted(unique_dates)[:20]:
    print(f'  "{d}"')