from supabase import create_client
import os
from dotenv import load_dotenv
load_dotenv()

url = os.getenv('SUPABASE_URL')
key = os.getenv('SUPABASE_KEY')
supabase = create_client(url, key)

# Get all with dates - first 50
result = supabase.table('partidos').select('dia').execute()
total = len(result.data)
with_date = len([p for p in result.data if p.get('dia')])
without_date = total - with_date

print(f'Total: {total}')
print(f'Con fecha: {with_date}')
print(f'Sin fecha: {without_date}')