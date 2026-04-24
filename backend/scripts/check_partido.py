from supabase import create_client
import os
from dotenv import load_dotenv
load_dotenv()

url = os.getenv('SUPABASE_URL')
key = os.getenv('SUPABASE_KEY')
supabase = create_client(url, key)

# Find Juventud Unida (9) vs Dep Gral Pinto (7)
result = supabase.table('partidos').select('*').eq('local_id', 9).eq('visitante_id', 7).execute()
print("Juventud Unida (9) Local:")
for p in result.data:
    print(f"  ID: {p['id']}, fecha: {p['fecha_id']}, estado: {p['estado']}, local: {p['local_id']}, visita: {p['visitante_id']}")

# Also check reverse
result2 = supabase.table('partidos').select('*').eq('local_id', 7).eq('visitante_id', 9).execute()
print("Dep Gral Pinto (7) Local:")
for p in result2.data:
    print(f"  ID: {p['id']}, fecha: {p['fecha_id']}, estado: {p['estado']}, local: {p['local_id']}, visita: {p['visitante_id']}")