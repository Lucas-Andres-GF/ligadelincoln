from supabase import create_client
import os
from dotenv import load_dotenv
load_dotenv()

url = os.getenv('SUPABASE_URL')
key = os.getenv('SUPABASE_KEY')
supabase = create_client(url, key)

# Check dates with values - get all
 result = supabase.table('partidos').select('dia').execute()

# Separate by None
with_date = [p for p in result.data if p.get('dia')]
without_date = len([p for p in result.data if not p.get('dia')])

print(f'Con fecha: {len(with_date.data)}')
print(f'Sin fecha (None): {len(without_date.data)}')
print(f'Total: {len(with_date.data) + len(without_date.data)}')

# Sample with dates
print('\\nEjemplos con fecha:')
for p in with_date.data[:5]:
    print(f'  {p.get("dia")}')