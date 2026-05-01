#!/usr/bin/env python3
import argparse
import os
import subprocess
import sys

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

from supabase import create_client

SCRIPT_DIR = os.path.dirname(__file__)
PROJECT_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))

if load_dotenv:
    load_dotenv(os.path.join(PROJECT_DIR, "backend", ".env"))

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("ERROR: Faltan credenciales de Supabase")
    sys.exit(1)

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

OUTPUT_HOST = os.environ.get("OUTPUT_HOST", os.path.join(PROJECT_DIR, "placares_generados"))
ESCUDOS_HOST = os.environ.get("ESCUDOS_HOST", os.path.join(PROJECT_DIR, "frontend", "public", "escudos_hd"))
PLACA_SCRIPT = os.path.join(SCRIPT_DIR, "generar_placa.py")

MAPEO_CATEGORIAS = {
    1: "primera",
    2: "septima",
    3: "octava",
    4: "novena",
    5: "decima"
}

def get_categoria_nombre(categoria_id):
    nombres = {
        1: "PRIMERA",
        2: "SÉPTIMA",
        3: "OCTAVA",
        4: "NOVENA",
        5: "DÉCIMA"
    }
    return nombres.get(categoria_id, "LIGA DE LINCOLN")

MAPEO_CLUBES_INVERSO = {
    1: "Argentino",
    2: "Atl. Pasteur",
    3: "Atl. Roberts",
    4: "CA. Pintense",
    5: "Caset",
    6: "Dep. Arenaza",
    7: "Dep. Gral Pinto",
    8: "El Linqueño",
    9: "Juventud Unida",
    10: "San Martin",
    11: "Villa Francia",
    12: "CAEL",
}

def obtener_ultima_fecha_jugada():
    response = (
        supabase.table("partidos")
        .select("fecha_id")
        .eq("estado", "jugado")
        .not_.is_("goles_local", "null")
        .not_.is_("visitante_id", "null")
        .order("fecha_id", desc=True)
        .limit(1)
        .execute()
    )
    if response.data:
        return response.data[0].get("fecha_id")
    return None

def obtener_partidos_jugados(fecha_id=None, categoria_id=None):
    query = supabase.table("partidos").select("""
        id,
        categoria_id,
        fecha_id,
        local_id,
        visitante_id,
        goles_local,
        goles_visitante,
        estado
    """).eq("estado", "jugado").not_.is_("goles_local", "null").not_.is_("visitante_id", "null")
    if fecha_id is not None:
        query = query.eq("fecha_id", fecha_id)
    if categoria_id is not None:
        query = query.eq("categoria_id", categoria_id)
    response = query.order("categoria_id").order("id").execute()
    
    return response.data or []

def obtener_equipos_libres(fecha_id=None, categoria_id=None):
    query = supabase.table("partidos").select("""
        id,
        categoria_id,
        fecha_id,
        local_id,
        visitante_id,
        estado
    """).eq("estado", "jugado").is_("visitante_id", "null")
    if fecha_id is not None:
        query = query.eq("fecha_id", fecha_id)
    if categoria_id is not None:
        query = query.eq("categoria_id", categoria_id)
    response = query.order("categoria_id").order("id").execute()
    
    return response.data or []

def verificar_libre_existe(categoria_id, fecha_id, club_nombre):
    categoria_folder = obtener_categoria_folder(categoria_id)
    fecha_folder = f"fecha_{fecha_id}" if fecha_id else "sin_fecha"
    target_dir = os.path.join(OUTPUT_HOST, categoria_folder, fecha_folder)
    
    if not os.path.exists(target_dir):
        return False
    
    club_clean = club_nombre.replace(' ', '_').lower()
    for f in os.listdir(target_dir):
        if f.endswith('.png') and f.startswith('libre_') and club_clean in f.lower():
            return True
    return False

def obtener_categoria_folder(categoria_id):
    return MAPEO_CATEGORIAS.get(categoria_id, "otros")

def verificar_placa_existe(categoria_id, fecha_id, local_nombre, visita_nombre, goles_local, goles_visita):
    categoria_folder = obtener_categoria_folder(categoria_id)
    fecha_folder = f"fecha_{fecha_id}" if fecha_id else "sin_fecha"
    target_dir = os.path.join(OUTPUT_HOST, categoria_folder, fecha_folder)
    
    if not os.path.exists(target_dir):
        return False
    
    # Normalizar nombres: quitar espacios Y underscores
    local_clean = local_nombre.replace(' ', '').replace('_', '').lower()
    visita_clean = visita_nombre.replace(' ', '').replace('_', '').lower()
    # Buscar sin guiones bajos
    resultado = f"{goles_local}vs{goles_visita}"
    
    for f in os.listdir(target_dir):
        if f.endswith('.png'):
            # Quitar underscores del nombre de archivo también
            f_check = f.replace(' ', '').replace('_', '').lower()
            # Verificar que coincida equipos Y resultado
            if local_clean in f_check and visita_clean in f_check and resultado in f_check:
                return True
    return False

def verificar_portada_existe(categoria_id, fecha_id):
    categoria_folder = obtener_categoria_folder(categoria_id)
    fecha_folder = f"fecha_{fecha_id}" if fecha_id else "sin_fecha"
    target_dir = os.path.join(OUTPUT_HOST, categoria_folder, fecha_folder)
    
    if not os.path.exists(target_dir):
        return False
    
    # Buscar archivo de portada
    categoria_nombre = get_categoria_nombre(categoria_id).lower()
    portada_nombre = f"portada_{categoria_nombre}_fecha_{fecha_id}.png"
    
    return os.path.exists(os.path.join(target_dir, portada_nombre))

def ejecutar_generador(args, output_folder):
    env = os.environ.copy()
    env["OUTPUT_FOLDER"] = output_folder
    env["ESCUDOS_FOLDER"] = ESCUDOS_HOST
    env["PYTHONIOENCODING"] = "utf-8"

    cmd = [sys.executable, PLACA_SCRIPT, *[str(arg) for arg in args]]
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)

def parse_args():
    parser = argparse.ArgumentParser(description="Generar placas de resultados por fecha")
    parser.add_argument("--fecha", type=int, default=None, help="Número de fecha. Si se omite, usa la última fecha jugada.")
    parser.add_argument("--categoria", choices=MAPEO_CATEGORIAS.values(), default=None, help="Categoría específica opcional")
    parser.add_argument("--force", action="store_true", help="Regenerar aunque el archivo ya exista")
    return parser.parse_args()

def main():
    args = parse_args()
    fecha_filtro = args.fecha if args.fecha is not None else obtener_ultima_fecha_jugada()
    categoria_filtro = None
    if args.categoria:
        categoria_filtro = next(cat_id for cat_id, slug in MAPEO_CATEGORIAS.items() if slug == args.categoria)

    if fecha_filtro is None:
        print("No hay fechas jugadas para generar")
        return

    print(f"🔍 Buscando partidos jugados de fecha {fecha_filtro}...")
    
    partidos = obtener_partidos_jugados(fecha_filtro, categoria_filtro)
    
    if not partidos:
        print("No hay partidos jugados para esa fecha")
        return
    
    print(f"📊 Encontrados {len(partidos)} partidos jugados")
    
    # Generar portadas para cada categoría/fecha única
    print("\n🎨 Generando portadas...")
    portadas_creadas = set()
    
    for partido in partidos:
        cat_id = partido.get('categoria_id')
        fecha_id = partido.get('fecha_id')
        key = (cat_id, fecha_id)
        
        if key not in portadas_creadas and (args.force or not verificar_portada_existe(cat_id, fecha_id)):
            # Crear carpetas
            cat_folder = obtener_categoria_folder(cat_id)
            fecha_folder = f"fecha_{fecha_id}" if fecha_id else "sin_fecha"
            target_dir = os.path.join(OUTPUT_HOST, cat_folder, fecha_folder)
            os.makedirs(target_dir, exist_ok=True)
            
            result = ejecutar_generador(["--portada", cat_id, fecha_id], target_dir)
            if result.returncode == 0:
                print(f"   ✅ Portada {get_categoria_nombre(cat_id)} - Fecha {fecha_id}")
                portadas_creadas.add(key)
            else:
                print(f"   ❌ Error: {result.stderr}")
    
    print(f"\n📊 {len(portadas_creadas)} portadas generadas")
    
    # Generar placas de equipos libres
    print("\n🎨 Generando equipos libres...")
    libres = obtener_equipos_libres(fecha_filtro, categoria_filtro)
    libres_generados = 0
    
    for libre in libres:
        club_id = libre.get('local_id')
        categoria_id = libre.get('categoria_id')
        fecha_id = libre.get('fecha_id')
        
        club_nombre = MAPEO_CLUBES_INVERSO.get(club_id, f"Club {club_id}")
        
        if not args.force and verificar_libre_existe(categoria_id, fecha_id, club_nombre):
            print(f"⏭️  Libre omitido: {club_nombre}")
            continue
        
        # Crear carpetas
        cat_folder = obtener_categoria_folder(categoria_id)
        fecha_folder = f"fecha_{fecha_id}" if fecha_id else "sin_fecha"
        target_dir = os.path.join(OUTPUT_HOST, cat_folder, fecha_folder)
        os.makedirs(target_dir, exist_ok=True)
        
        result = ejecutar_generador(["--libre", categoria_id, club_nombre, fecha_id or ""], target_dir)
        
        if result.returncode == 0:
            print(f"   ✅ Libre: {club_nombre}")
            libres_generados += 1
        else:
            print(f"   ❌ Error: {result.stderr}")
    
    print(f"📊 {libres_generados} libres generados")
    
    generados = 0
    omitidos = 0
    
    for partido in partidos:
        local_nombre = MAPEO_CLUBES_INVERSO.get(partido['local_id'], f"Club {partido['local_id']}")
        visita_nombre = MAPEO_CLUBES_INVERSO.get(partido['visitante_id'], f"Club {partido['visitante_id']}")
        categoria_id = partido.get('categoria_id')
        fecha_id = partido.get('fecha_id')
        
        if not args.force and verificar_placa_existe(categoria_id, fecha_id, local_nombre, visita_nombre, partido['goles_local'], partido['goles_visitante']):
            print(f"⏭️  Omitido: {local_nombre} vs {visita_nombre} ya existe")
            omitidos += 1
            continue
        
        print(f"\n🎨 Generando: {local_nombre} {partido['goles_local']} - {partido['goles_visitante']} {visita_nombre}")
        
        # Crear carpetas si no existen
        categoria_folder = obtener_categoria_folder(categoria_id)
        fecha_folder = f"fecha_{fecha_id}" if fecha_id else "sin_fecha"
        target_dir = os.path.join(OUTPUT_HOST, categoria_folder, fecha_folder)
        os.makedirs(target_dir, exist_ok=True)
        
        result = ejecutar_generador([
            partido['categoria_id'],
            local_nombre,
            partido['goles_local'],
            visita_nombre,
            partido['goles_visitante'],
            partido.get('fecha_id') or "",
        ], target_dir)
        
        print(f"   stdout: {result.stdout}")
        if result.stderr:
            print(f"   stderr: {result.stderr}")
        
        if result.returncode == 0:
            generados += 1
            print(f"✅ Generado correctamente")
            
            # Verificar que hay archivos en la carpeta
            if os.path.exists(target_dir):
                archivos = os.listdir(target_dir)
                print(f"   📁 {len(archivos)} archivos en {target_dir}")
        else:
            print(f"❌ Error al generar")
    
    print(f"\n📈 Resumen: {generados} generados, {omitidos} omitidos")

if __name__ == "__main__":
    main()
