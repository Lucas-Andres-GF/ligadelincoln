import os
from supabase import create_client
from dotenv import load_dotenv
# Importamos tu función del archivo anterior
from get_fixture_equipos import scrapear_equipos_del_fixture

# 1. Cargamos las credenciales del .env
load_dotenv()
url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_KEY")

# Inicializamos el cliente de Supabase
supabase = create_client(url, key)

def ejecutar_carga():
    # 2. Obtenemos la lista de nombres "lindos"
    print("⏳ Iniciando el scraper para obtener equipos...")
    lista_nombres = scrapear_equipos_del_fixture()
    
    if not lista_nombres:
        print("❌ No se obtuvieron nombres. Revisá el scraper.")
        return

    # 3. Formateamos para Supabase: una lista de diccionarios
    # Ejemplo: [{'nombre': 'Argentino'}, {'nombre': 'Atl. Pasteur'}]
    datos_para_supabase = [{"nombre": n} for n in lista_nombres]

    print(f"🚀 Intentando subir {len(datos_para_supabase)} equipos...")

    try:
        # 4. Usamos upsert para evitar duplicados si volvés a correr el script
        # IMPORTANTE: La columna 'nombre' en Supabase debe ser UNIQUE
        resultado = supabase.table("equipos").upsert(datos_para_supabase, on_conflict="nombre").execute()
        
        print(f"✅ ¡Éxito! Se procesaron {len(resultado.data)} equipos.")
        
        # Mostramos los IDs generados para control
        for eq in resultado.data:
            print(f"ID: {eq['id']} | Nombre: {eq['nombre']}")

    except Exception as e:
        print(f"❌ Error al conectar con Supabase: {e}")

if __name__ == "__main__":
    ejecutar_carga()