from supabase import create_client
import os
from dotenv import load_dotenv
load_dotenv()

url = os.getenv('SUPABASE_URL')
key = os.getenv('SUPABASE_KEY')
supabase = create_client(url, key)

# Check recent dates with matches
result = supabase.table('partidos').select('id,dia,fecha_id,categoria_id,estado').limit(10).execute()
print('Ultimos partidos:')
for p in result.data:
    print(f'  {p.get("dia")} -cat {p.get("categoria_id")}- estado: {p.get("estado")}')