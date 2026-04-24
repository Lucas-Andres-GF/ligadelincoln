import os
from dotenv import load_dotenv
load_dotenv()
from supabase import create_client
supabase = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])

# Get all goleadores
r = supabase.table("alineaciones").select("partido_id,equipo_id,numero,nombre,goleo").eq("goleo", True).execute()

print("Goleadores:")
for a in r.data:
    print(f"  Partido {a['partido_id']}: Equipo {a['equipo_id']} #{a['numero']} {a['nombre']}")