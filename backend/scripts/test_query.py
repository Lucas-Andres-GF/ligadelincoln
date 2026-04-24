import os
from dotenv import load_dotenv
load_dotenv()

from supabase import create_client

supabase = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])

# Ver partidos
r = supabase.table("partidos").select("id,categoria_id,fecha_id,local_id,visitante_id").eq("categoria_id", 1).order("fecha_id", desc=True).limit(5).execute()
print("Partidos:", r.data)