import os
from dotenv import load_dotenv
load_dotenv()
from supabase import create_client
supabase = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])

# Get all matches for fecha 5
r = supabase.table("partidos").select("id,fecha_id,local_id,visitante_id,goles_local,goles_visitante").eq("categoria_id", 1).eq("fecha_id", 5).execute()

print("Partidos Fecha 5:")
for p in r.data:
    print(f"  ID {p['id']}: {p['local_id']} vs {p['visitante_id']} = {p['goles_local']}-{p['goles_visitante']}")