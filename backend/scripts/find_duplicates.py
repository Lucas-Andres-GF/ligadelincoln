from supabase import create_client
import os
from dotenv import load_dotenv
load_dotenv()

url = os.getenv('SUPABASE_URL')
key = os.getenv('SUPABASE_KEY')
supabase = create_client(url, key)

# Get all partidos
result = supabase.table('partidos').select('id,local_id,visitante_id,fecha_id,estado,goles_local,goles_visitante').eq('categoria_id', 1).execute()

# Group by (local_id, visitante_id, fecha_id)
from collections import defaultdict
duplicates = defaultdict(list)

for p in result.data:
    local = p['local_id'] or 0
    visita = p['visitante_id'] or 0
    fecha = p['fecha_id'] or 0
    key = (local, visita, fecha)
    duplicates[key].append(p)

print("DUPLICADOS en tabla 'partidos':")
print("=" * 60)
for key, items in sorted(duplicates.items()):
    if len(items) > 1:
        local, visita, fecha = key
        print(f"\nFecha {fecha}: Equipo {local} vs {visita}")
        for p in items:
            print(f"  ID {p['id']}: estado={p['estado']}, goles={p['goles_local']}-{p['goles_visitante']}")

print("\n\nTotal partidos:", len(result.data))
print("Con duplicados:", sum(1 for k,v in duplicates.items() if len(v) > 1))