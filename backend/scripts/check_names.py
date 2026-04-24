from supabase import create_client
import os
from dotenv import load_dotenv

load_dotenv()

url = os.getenv('SUPABASE_URL')
key = os.getenv('SUPABASE_KEY')
supabase = create_client(url, key)

response = supabase.table('alineaciones').select('id, nombre').execute()
print(f'Total registros: {len(response.data)}')

# Check for empty/0 names
from collections import Counter
names = Counter(r.get('nombre') for r in response.data)
print('Nombres encontrados:')
for name, count in names.most_common(20):
    print(f'  "{name}": {count}')