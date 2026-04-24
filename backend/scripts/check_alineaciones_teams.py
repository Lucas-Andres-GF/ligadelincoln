from supabase import create_client
import os
from dotenv import load_dotenv
load_dotenv()

url = os.getenv('SUPABASE_URL')
key = os.getenv('SUPABASE_KEY')
supabase = create_client(url, key)

# Get alineaciones with their teams
result = supabase.table('alineaciones').select('partido_id, equipo_id').distinct().execute()

print("Partidos con alineaciones:")
for r in result.data:
    print(f"  Partido {r['partido_id']}: equipo {r['equipo_id']}")

# Get details for those partidos
partido_ids = list(set(r['partido_id'] for r in result.data))
for pid in sorted(partido_ids):
    p = supabase.table('partidos').select('*').eq('id', pid).execute().data
    if p:
        print(f"  Partido {pid}: local={p[0]['local_id']}, visita={p[0]['visitante_id']}, fecha={p[0]['fecha_id']}")