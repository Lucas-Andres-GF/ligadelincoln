from supabase import create_client
import os
from dotenv import load_dotenv
load_dotenv()

url = os.getenv('SUPABASE_URL')
key = os.getenv('SUPABASE_KEY')
supabase = create_client(url, key)

slugToId = {
    'argentino': 1, 'atl-pasteur': 2, 'atl-roberts': 3, 'ca-pintense': 4,
    'caset': 5, 'dep-arenaza': 6, 'dep-gral-pinto': 7, 'el-linqueno': 8,
    'juventud-unida': 9, 'san-martin': 10, 'villa-francia': 11,
}
idToSlug = {v: k for k, v in slugToId.items()}

# Get clubs
clubs_result = supabase.table('clubes').select('id,nombre').execute()
club_dict = {}
for c in clubs_result.data:
    club_dict[c['id']] = c['nombre']

# Get played matches
partidos_result = supabase.table('partidos').select('id,local_id,visitante_id,estado').eq('categoria_id', 1).eq('estado', 'jugado').execute()

print("Partidos jugados (slug generado):")
for p in partidos_result.data:
    localSlug = idToSlug.get(p['local_id'], str(p['local_id']))
    visitaSlug = idToSlug.get(p['visitante_id'], str(p['visitante_id']))
    localName = club_dict.get(p['local_id'], '?')
    visitaName = club_dict.get(p['visitante_id'], '?')
    print(f"  /partido/{localSlug}-vs-{visitaSlug}  ({localName} vs {visitaName})")