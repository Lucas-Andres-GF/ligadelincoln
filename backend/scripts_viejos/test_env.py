import os
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()
supabase = create_client(os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_KEY"))

# Vamos a pedirle a Supabase que nos de las posiciones 
# PERO que también nos traiga el NOMBRE del equipo que está en la otra tabla
try:
    respuesta = supabase.table("posiciones").select("pts, jugados, equipos(nombre)").execute()
    
    print("--- TABLA DE POSICIONES ACTUAL ---")
    for fila in respuesta.data:
        nombre_equipo = fila['equipos']['nombre']
        pts = fila['pts']
        print(f"Equipo: {nombre_equipo} | pts: {pts}")
        
except Exception as e:
    print(f"Error al leer: {e}")