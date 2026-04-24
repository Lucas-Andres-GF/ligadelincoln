import os
from dotenv import load_dotenv
load_dotenv()
from supabase import create_client
supabase = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])

# Check roja
r = supabase.table("alineaciones").select("numero,nombre,roja").eq("roja", True).execute()

print("Expulsados:")
for a in r.data:
    print(f"  #{a['numero']} {a['nombre']}")

# Check goleo
r2 = supabase.table("alineaciones").select("numero,nombre,goleo").eq("goleo", True).execute()
print("\nGoleadores:")
for a in r2.data:
    print(f"  #{a['numero']} {a['nombre']}")