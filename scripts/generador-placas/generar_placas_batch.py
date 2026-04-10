#!/usr/bin/env python3
import os
import sys
from supabase import create_client

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("ERROR: Faltan credenciales de Supabase")
    sys.exit(1)

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

OUTPUT_HOST = os.environ.get("OUTPUT_HOST", "/home/gallardo/Documentos/ligadelincoln/placares_generados")

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

def obtener_partidos_jugados():
    response = supabase.table("partidos").select("""
        id,
        categoria_id,
        fecha_id,
        local_id,
        visitante_id,
        goles_local,
        goles_visitante,
        estado
    """).eq("estado", "jugado").not_.is_("goles_local", "null").not_.is_("visitante_id", "null").execute()
    
    return response.data or []

def obtener_equipos_libres():
    response = supabase.table("partidos").select("""
        id,
        categoria_id,
        fecha_id,
        local_id,
        visitante_id,
        estado
    """).eq("estado", "jugado").is_("visitante_id", "null").execute()
    
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

def main():
    print("🔍 Buscando partidos jugados...")
    
    partidos = obtener_partidos_jugados()
    
    if not partidos:
        print("No hay partidos jugados pendientes")
        return
    
    print(f"📊 Encontrados {len(partidos)} partidos jugados")
    
    # Generar portadas para cada categoría/fecha única
    print("\n🎨 Generando portadas...")
    portadas_creadas = set()
    
    for partido in partidos:
        cat_id = partido.get('categoria_id')
        fecha_id = partido.get('fecha_id')
        key = (cat_id, fecha_id)
        
        if key not in portadas_creadas and not verificar_portada_existe(cat_id, fecha_id):
            # Crear carpetas
            cat_folder = obtener_categoria_folder(cat_id)
            fecha_folder = f"fecha_{fecha_id}" if fecha_id else "sin_fecha"
            target_dir = os.path.join(OUTPUT_HOST, cat_folder, fecha_folder)
            os.makedirs(target_dir, exist_ok=True)
            
            # Generar portada
            container_output = f"/app/salida/{cat_folder}/{fecha_folder}"
            cmd = [
                "docker", "run", "--rm",
                "-v", f"{os.environ.get('ESCUDOS_HOST', '/home/gallardo/Documentos/ligadelincoln/frontend/public/escudos_hd')}:/app/escudos:ro",
                "-v", f"{OUTPUT_HOST}:/app/salida:rw",
                "-e", f"OUTPUT_FOLDER={container_output}",
                "generador-ligalincoln",
                "python", "generar_placa.py",
                "--portada", str(cat_id), str(fecha_id)
            ]
            
            import subprocess
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0:
                print(f"   ✅ Portada {get_categoria_nombre(cat_id)} - Fecha {fecha_id}")
                portadas_creadas.add(key)
            else:
                print(f"   ❌ Error: {result.stderr}")
    
    print(f"\n📊 {len(portadas_creadas)} portadas generadas")
    
    # Generar placas de equipos libres
    print("\n🎨 Generando equipos libres...")
    libres = obtener_equipos_libres()
    libres_generados = 0
    
    for libre in libres:
        club_id = libre.get('local_id')
        categoria_id = libre.get('categoria_id')
        fecha_id = libre.get('fecha_id')
        
        club_nombre = MAPEO_CLUBES_INVERSO.get(club_id, f"Club {club_id}")
        
        if verificar_libre_existe(categoria_id, fecha_id, club_nombre):
            print(f"⏭️  Libre omitido: {club_nombre}")
            continue
        
        # Crear carpetas
        cat_folder = obtener_categoria_folder(categoria_id)
        fecha_folder = f"fecha_{fecha_id}" if fecha_id else "sin_fecha"
        target_dir = os.path.join(OUTPUT_HOST, cat_folder, fecha_folder)
        os.makedirs(target_dir, exist_ok=True)
        
        container_output = f"/app/salida/{cat_folder}/{fecha_folder}"
        cmd = [
            "docker", "run", "--rm",
            "-v", f"{os.environ.get('ESCUDOS_HOST', '/home/gallardo/Documentos/ligadelincoln/frontend/public/escudos_hd')}:/app/escudos:ro",
            "-v", f"{OUTPUT_HOST}:/app/salida:rw",
            "-e", f"OUTPUT_FOLDER={container_output}",
            "generador-ligalincoln",
            "python", "generar_placa.py",
            "--libre", str(categoria_id), club_nombre, str(fecha_id or '')
        ]
        
        import subprocess
        result = subprocess.run(cmd, capture_output=True, text=True)
        
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
        
        if verificar_placa_existe(categoria_id, fecha_id, local_nombre, visita_nombre, partido['goles_local'], partido['goles_visitante']):
            print(f"⏭️  Omitido: {local_nombre} vs {visita_nombre} ya existe")
            omitidos += 1
            continue
        
        print(f"\n🎨 Generando: {local_nombre} {partido['goles_local']} - {partido['goles_visitante']} {visita_nombre}")
        
        # Crear carpetas si no existen
        categoria_folder = obtener_categoria_folder(categoria_id)
        fecha_folder = f"fecha_{fecha_id}" if fecha_id else "sin_fecha"
        target_dir = os.path.join(OUTPUT_HOST, categoria_folder, fecha_folder)
        os.makedirs(target_dir, exist_ok=True)
        
        # Ruta interna del contenedor (corresponde al volumen mapeado)
        container_output = f"/app/salida/{categoria_folder}/{fecha_folder}"
        
        cmd = [
            "docker", "run", "--rm",
            "-v", f"{os.environ.get('ESCUDOS_HOST', '/home/gallardo/Documentos/ligadelincoln/frontend/public/escudos_hd')}:/app/escudos:ro",
            "-v", f"{OUTPUT_HOST}:/app/salida:rw",
            "-e", f"OUTPUT_FOLDER={container_output}",
            "generador-ligalincoln",
            "python", "generar_placa.py",
            str(partido['categoria_id']),
            local_nombre,
            str(partido['goles_local']),
            visita_nombre,
            str(partido['goles_visitante']),
            str(partido.get('fecha_id') or '')
        ]
        
        import subprocess
        result = subprocess.run(cmd, capture_output=True, text=True)
        
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