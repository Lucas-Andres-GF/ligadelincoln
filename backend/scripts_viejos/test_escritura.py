import os
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()
supabase = create_client(os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_KEY"))

# Intentamos insertar un equipo nuevo desde el código
nuevo_equipo = {"nombre": "Club de Prueba Lincoln"}

try:
    resultado = supabase.table("equipos").insert(nuevo_equipo).execute()
    print("✅ ¡Éxito! El equipo se guardó desde Python.")
    print(f"Datos guardados: {resultado.data}")
except Exception as e:
    print(f"❌ Algo falló: {e}")