from supabase import create_client
import os
from dotenv import load_dotenv
load_dotenv()

url = os.getenv('SUPABASE_URL')
key = os.getenv('SUPABASE_KEY')
supabase = create_client(url, key)

# Get all dates - filter in code instead
result = supabase.table('partidos').select('dia').execute()

valid_dates = [p.get('dia') for p in result.data if p.get('dia') and p.get('dia') != 'None' and p.get('dia') != None]

print(f'Total: {len(result.data)}')
print(f'Valid dates: {len(valid_dates)}')
print(f'First 10: {valid_dates[:10]}')