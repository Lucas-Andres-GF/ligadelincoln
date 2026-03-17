import os
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()
supabase = create_client(os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_KEY"))

def generar_archivo_mapeo():
    # 1. Traemos los equipos de la DB
    res = supabase.table("equipos").select("id, nombre").execute()
    
    with open("mapeo.py", "w", encoding="utf-8") as f:
        f.write("# Archivo generado automaticamente - NO EDITAR A MANO\n")
        f.write("EQUIPOS_MAP = {\n")
        
        for eq in res.data:
            # Guardamos el nombre en MAYUSCULAS como "llave" 
            # y el ID como valor
            nombre_upper = eq['nombre'].upper().replace("ATL. ", "ATL ").replace("DEP. ", "DEP ").replace("CA. ", "C A ")
            f.write(f"    '{nombre_upper}': {eq['id']},\n")
            
        f.write("}\n")
    print("✅ Archivo 'mapeo.py' creado con éxito.")

if __name__ == "__main__":
    generar_archivo_mapeo()