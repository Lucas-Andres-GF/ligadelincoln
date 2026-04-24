from supabase import create_client
import os
from dotenv import load_dotenv
load_dotenv()

url = os.getenv('SUPABASE_URL')
key = os.getenv('SUPABASE_KEY')
supabase = create_client(url, key)

# Check alineaciones duplicates - (partido_id, equipo_id, numero) should be unique
result = supabase.table('alineaciones').select('id,partido_id,equipo_id,numero,nombre').order('partido_id').order('equipo_id').order('numero').execute()

from collections import defaultdict
duplicates = defaultdict(list)

for p in result.data:
    key = (p['partido_id'], p['equipo_id'], p['numero'])
    duplicates[key].append(p)

print("DUPLICADOS en tabla 'alineaciones' (mismo partido+equipo+numero):")
print("=" * 60)
dup_count = 0
for key, items in sorted(duplicates.items()):
    if len(items) > 1:
        dup_count += 1
        partido, equipo, numero = key
        print(f"\nPartido {partido}, Equipo {equipo}, Numero {numero}:")
        for p in items:
            print(f"  ID {p['id']}: {p['nombre']}")

if dup_count == 0:
    print("No hay duplicados en alineaciones")

print(f"\n\nTotal registros en alineaciones: {len(result.data)}")