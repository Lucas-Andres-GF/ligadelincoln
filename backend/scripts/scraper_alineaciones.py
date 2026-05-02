# scraper_alineaciones.py - Fixed to parse single table with all matches

import argparse
import requests
from bs4 import BeautifulSoup
import re
import unicodedata
import os
from dotenv import load_dotenv
load_dotenv()
from supabase import create_client
supabase = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])
print("Imports done")

MAPEO_FECHA = {
    "PRIMERA": 1, "SEGUNDA": 2, "TERCERA": 3, "CUARTA": 4,
    "QUINTA": 5, "SEXTA": 6, "SEPTIMA": 7, "OCTAVA": 8,
    "NOVENA": 9, "DECIMA": 10, "UNDECIMA": 11, "DUODECIMA": 12,
    "DECIMOTERCERA": 13, "DECIMOCUARTA": 14, "DECIMOQUINTA": 15,
    "DECIMOSEXTA": 16, "DECIMOSEPTIMA": 17, "DECIMOCTAVA": 18,
    "DECIMONOVENA": 19, "VIGESIMA": 20
}

MAPEO_CLUBES = {
    "ARGENTINO": 1, "ATL. PASTEUR": 2, "ATL PASTEUR": 2,
    "ATL. ROBERTS": 3, "ATL ROBERTS": 3,
    "CA. PINTENSE": 4, "C A PINTENSE": 4,
    "CASET": 5,
    "DEP. ARENAZA": 6, "DEP ARENAZA": 6,
    "DEP. GRAL PINTO": 7, "DEP GRAL PINTO": 7,
    "EL LINQUEÑO": 8, "EL LINQUENO": 8,
    "JUVENTUD UNIDA": 9, "SAN MARTIN": 10, "VILLA FRANCIA": 11,
}

URL = "https://www.ligaamateurdedeportes.com.ar/alineaciones.html"

parser = argparse.ArgumentParser(description="Scrapea alineaciones de Primera desde la web de la Liga")
parser.add_argument("--fecha", type=int, help="Fecha a procesar. Si no se indica, se detecta desde la web")
parser.add_argument("--dry-run", action="store_true", help="Muestra qué haría sin escribir en Supabase")
args = parser.parse_args()

def normalizar(t):
    if not t: return ""
    t = unicodedata.normalize('NFD', t)
    t = ''.join(c for c in t if unicodedata.category(c) != 'Mn')
    return re.sub(r'\s+', ' ', t.replace(".", "").replace(",", "").strip().upper())

def limpiar(t):
    if not t:
        return ""
    # Algunas celdas llegan con mojibake tipo "EL LINQUEÃO" aunque el resto
    # del documento esté usable. Repararlo acá evita perder partidos por acentos.
    if "Ã" in t or "Â" in t:
        try:
            t = t.encode('latin1').decode('utf-8')
        except UnicodeError:
            pass
    return t.replace('\xa0', ' ').replace('\n', ' ').strip()

def detectar_equipos_fila(cells):
    if len(cells) < 4:
        return None, None

    c0 = normalizar(limpiar(cells[0].get_text()))
    c3 = normalizar(limpiar(cells[3].get_text()))

    equipo_local = None
    equipo_visita = None
    for eq_n, eq_id in MAPEO_CLUBES.items():
        eq_norm = normalizar(eq_n)
        if eq_norm in c0 and len(c0) < 30:
            equipo_local = eq_id
        if eq_norm in c3 and len(c3) < 30:
            equipo_visita = eq_id

    return equipo_local, equipo_visita

def es_inicio_partido(cells):
    equipo_local, equipo_visita = detectar_equipos_fila(cells)
    if not equipo_local or not equipo_visita:
        return False

    texto_fila = normalizar(' '.join(limpiar(c.get_text()) for c in cells))
    return 'PRIMER TIEMPO' in texto_fila

# Fetch HTML
print("Fetching HTML...")
response = requests.get(URL, timeout=30)
# La web actualmente viene declarada como ISO-8859-1. Forzar UTF-8 rompe nombres
# como "EL LINQUEÑO" y hace que no matchee contra MAPEO_CLUBES.
if not response.encoding:
    response.encoding = 'ISO-8859-1'
soup = BeautifulSoup(response.text, 'html.parser')
print("Parsed HTML")

# Detectar fecha desde la web
fecha_id = args.fecha
if fecha_id:
    print(f"Fecha indicada por argumento: fecha_id={fecha_id}")
else:
    texto_pagina = normalizar(soup.get_text())
    for palabra, fid in MAPEO_FECHA.items():
        if palabra in texto_pagina:
            fecha_id = fid
            print(f"Fecha detectada en web: {palabra} -> fecha_id={fecha_id}")
            break

if not fecha_id:
    print("ERROR: No se pudo detectar la fecha en la web")
    exit(1)

# Obtener partidos filtrando por fecha detectada
print("Getting partidos...")
partidos = supabase.table("partidos").select("id,local_id,visitante_id").eq("categoria_id",1).eq("fecha_id",fecha_id).execute().data
partidos = [p for p in partidos if p['local_id'] and p['visitante_id']]
print(f"Partidos: {len(partidos)}")

if args.dry_run:
    print("DRY RUN activo: no se borrará ni guardará nada en Supabase")

# Buscar la tabla con datos (la tabla 2 o 3)
tablas = soup.find_all('tabla')
tabla_datos = None

for tabla in soup.find_all('table'):
    txt = normalizar(tabla.get_text())
    # Buscar tabla que contenga varios equipos
    equipos_en_tabla = 0
    for eq_n, eq_id in MAPEO_CLUBES.items():
        if normalizar(eq_n) in txt:
            equipos_en_tabla += 1
    if equipos_en_tabla >= 10:  # La tabla con todos los datos
        tabla_datos = tabla
        print(f"Tabla de datos encontrada con {equipos_en_tabla} equipos")
        break

if not tabla_datos:
    print("ERROR: No se encontró tabla de datos")
    exit(1)

# Analizar filas para detectar límites de cada partido
filas = tabla_datos.find_all('tr')
print(f"Filas: {len(filas)}")

# Encontrar las filas que tienen el patrón de inicio de partido: Equipo - Num - Num - Equipo
# Estas son las filas donde el equipo local está seguido de números y luego el equipo visitante
partidos_en_tabla = []
for idx, fila in enumerate(filas):
    cells = fila.find_all('td')
    if len(cells) >= 4:
        c1 = limpiar(cells[1].get_text())
        c2 = limpiar(cells[2].get_text())
        
        # Detectar fila de inicio de partido: [EquipoLocal] [Numero] [Numero] [EquipoVisitante]
        equipo_local, equipo_visita = detectar_equipos_fila(cells)
        
        if equipo_local and equipo_visita:
            # Verificar que c1 y c2 sean números (scores)
            if c1.isdigit() and c2.isdigit():
                partidos_en_tabla.append({
                    'fila_inicio': idx,
                    'local_id': equipo_local,
                    'visita_id': equipo_visita,
                    'goles_local': int(c1),
                    'goles_visita': int(c2)
                })
                print(f"Partido detectado en fila {idx}: {equipo_local} {c1}-{c2} {equipo_visita}")

print(f"Partidos encontrados en tabla: {len(partidos_en_tabla)}")

# Para cada partido en la DB, buscar sus datos
guardados = 0
for p in partidos:
    local_id = p['local_id']
    visita_id = p['visitante_id']
    partido_id = p['id']
    
    # Buscar el partido en la tabla
    datos_partido = None
    for partido_data in partidos_en_tabla:
        # Buscar por ID de equipos (en cualquier orden)
        if ((partido_data['local_id'] == local_id and partido_data['visita_id'] == visita_id) or
            (partido_data['local_id'] == visita_id and partido_data['visita_id'] == local_id)):
            datos_partido = partido_data
            break
    
    if not datos_partido:
        print(f"Partido {local_id} vs {visita_id}: NO encontrado en tabla")
        continue

    tabla_en_orden_db = (
        datos_partido['local_id'] == local_id and
        datos_partido['visita_id'] == visita_id
    )

    goles_local_db = datos_partido['goles_local'] if tabla_en_orden_db else datos_partido['goles_visita']
    goles_visita_db = datos_partido['goles_visita'] if tabla_en_orden_db else datos_partido['goles_local']

    equipo_columna_local_id = local_id if tabla_en_orden_db else visita_id
    equipo_columna_visita_id = visita_id if tabla_en_orden_db else local_id
    
    print(f"Procesando: {local_id} vs {visita_id}")
    print(f"  Resultado detectado: {goles_local_db}-{goles_visita_db}")
    
    # Determinar filas del partido (desde inicio hasta el siguiente partido o fin)
    fila_inicio = datos_partido['fila_inicio']
    fila_fin = len(filas)
    for idx_siguiente in range(fila_inicio + 1, len(filas)):
        cells_siguiente = filas[idx_siguiente].find_all('td')
        if es_inicio_partido(cells_siguiente):
            fila_fin = idx_siguiente
            break
    
    print(f"  Filas {fila_inicio} a {fila_fin}")

    # BUSCAR DT y ÁRBITRO en las filas del partido
    dt_local = None
    dt_visitante = None
    arbitro = None

    for idx in range(fila_inicio, fila_fin):
        fila = filas[idx]
        cells = fila.find_all('td')
        for i, cell in enumerate(cells):
            txt = normalizar(limpiar(cell.get_text()))

            # Look for D.T. (DT is converted to "DT" by normalizar)
            # First occurrence = DT local, second = DT visitante
            if txt == "DT":
                # Next cell should have the name
                if i + 1 < len(cells):
                    nombre_dt = normalizar(limpiar(cells[i+1].get_text()))
                    if nombre_dt and nombre_dt != "0" and not dt_local:
                        dt_local = nombre_dt
                    elif nombre_dt and nombre_dt != "0" and dt_local and not dt_visitante:
                        dt_visitante = nombre_dt

            # Look for ARBITRO (ARBITRO: becomes "ARBITRO")
            if "ARBITRO" in txt:
                if i + 1 < len(cells):
                    nombre_arbitro = normalizar(limpiar(cells[i+1].get_text()))
                    if nombre_arbitro:
                        arbitro = nombre_arbitro

    dt_local_db = dt_local if tabla_en_orden_db else dt_visitante
    dt_visita_db = dt_visitante if tabla_en_orden_db else dt_local

    print(f"  DT Local: {dt_local_db}, DT Visita: {dt_visita_db}, Arbitro: {arbitro}")

    # Guardar resultado, estado, DTs y árbitro en partidos
    updates = {
        "goles_local": goles_local_db,
        "goles_visitante": goles_visita_db,
        "estado": "jugado"
    }
    if dt_local_db:
        updates["dt_local"] = dt_local_db
    if dt_visita_db:
        updates["dt_visitante"] = dt_visita_db
    if arbitro:
        updates["arbitro"] = arbitro

    if args.dry_run:
        existentes = supabase.table("alineaciones").select("id", count="exact").eq("partido_id", partido_id).execute()
        print(f"  DRY RUN: actualizaría partido con {updates}")
        print(f"  DRY RUN: reemplazaría {existentes.count or 0} alineaciones existentes solo para partido_id={partido_id}")
    else:
        try:
            supabase.table("alineaciones").delete().eq("partido_id", partido_id).execute()
            print(f"  Alineaciones viejas limpiadas para partido_id={partido_id}")
            supabase.table("partidos").update(updates).eq("id", partido_id).execute()
            print(f"  Partido actualizado")
        except Exception as e:
            print(f"  Partido update/error de limpieza: {e}")
            continue

# Procesar jugadores
    numeros_local = set()
    numeros_visita = set()
    rojas_local = set()
    rojas_visita = set()
    
    # PRIMERA PASADA: Recolectar todos los jugadores y sus nombres
    jugadores_local = {}
    jugadores_visita = {}
    
    for idx in range(fila_inicio, fila_fin):
        fila = filas[idx]
        cells = fila.find_all('td')
        
        if len(cells) >= 5:
            c0 = limpiar(cells[0].get_text())
            c1 = limpiar(cells[1].get_text())
            c3 = limpiar(cells[3].get_text())
            c4 = limpiar(cells[4].get_text()) if len(cells) > 4 else ""
            
            if c0.isdigit() and c1:
                jugadores_local[int(c0)] = normalizar(c1)
                # Check for red card (column 2)
                if len(cells) > 2:
                    style = str(cells[2].get('style', '')).lower()
                    if 'background:red' in style or 'background: red' in style:
                        rojas_local.add(int(c0))
            
            if c3.isdigit() and c4:
                jugadores_visita[int(c3)] = normalizar(c4)
                # Check for red card (column 5 - same as column 2 for visitor)
                if len(cells) > 5:
                    style = str(cells[5].get('style', '')).lower()
                    if 'background:red' in style or 'background: red' in style:
                        rojas_visita.add(int(c3))
    
    # SEGUNDA PASADA: Encontrar goleadores buscando nombres
    # Use list to allow duplicate scorers (same player can score multiple times)
    goleadores_local = []
    goleadores_visita = []
    prev_score = "0-0"
    
    def matches_player(scorer_name, player_name):
        """Check if scorer_name matches player_name"""
        if not scorer_name or not player_name:
            return False
        scorer_lower = scorer_name.lower()
        player_lower = player_name.lower()
        
        scorer_words = scorer_lower.split()
        player_words = player_lower.split()
        
        if len(scorer_words) < 2:
            return False
        
        matches = 0
        for sw in scorer_words:
            for pw in player_words:
                if len(sw) >= 3 and len(pw) >= 3 and (sw in pw or pw in sw):
                    matches += 1
                    break
        
        return matches >= 2
    
    for idx in range(fila_inicio, fila_fin):
        fila = filas[idx]
        cells = fila.find_all('td')
        
        if len(cells) >= 9:
            scorer_name = normalizar(limpiar(cells[7].get_text()))
            score = limpiar(cells[8].get_text()) if len(cells) > 8 else ""
            
            if not score or '-' not in score:
                continue
            
            try:
                partes = score.split('-')
                if len(partes) == 2:
                    curr_local = int(partes[0])
                    curr_visita = int(partes[1])
                    
                    prev_parts = prev_score.split('-')
                    if len(prev_parts) == 2:
                        prev_local = int(prev_parts[0])
                        prev_visita = int(prev_parts[1])
                        
                        if curr_local > prev_local and scorer_name and len(scorer_name) > 3:
                            for num, nombre in jugadores_local.items():
                                if matches_player(scorer_name, nombre):
                                    goleadores_local.append(num)
                        
                        if curr_visita > prev_visita and scorer_name and len(scorer_name) > 3:
                            for num, nombre in jugadores_visita.items():
                                if matches_player(scorer_name, nombre):
                                    goleadores_visita.append(num)
                    
                    prev_score = score
            except:
                pass
    
    print(f"  Goleadores local: {len(goleadores_local)}, visita: {len(goleadores_visita)}")
    
    # Segunda pasada: guardar alineaciones
    for idx in range(fila_inicio, fila_fin):
        fila = filas[idx]
        cells = fila.find_all('td')
        
        
        
        if len(cells) >= 5:
            c0 = limpiar(cells[0].get_text())
            c1 = limpiar(cells[1].get_text())
            c3 = limpiar(cells[3].get_text())
            c4 = limpiar(cells[4].get_text()) if len(cells) > 4 else ""
            
# Solo procesar si es un número (jugador)
            if c0.isdigit():
                num = int(c0)
                if num not in numeros_local:
                    numeros_local.add(num)
                    # Now goleo should be integer (count of goals)
                    es_goleador = goleadores_local.count(num)
                    result = None
                    
                    # Skip if name is empty or "0"
                    nombre_limpio = c1.strip() if c1 else ""
                    if nombre_limpio and nombre_limpio != "0":
                        row = {
                            "categoria_id": 1, "partido_id": partido_id,
                            "equipo_id": equipo_columna_local_id, "numero": num,
                            "nombre": nombre_limpio[:100],
                            "es_titular": num <= 11, "tiempo": "PT",
                            "goleo": es_goleador,
                            "roja": num in rojas_local,
                            "fecha_id": fecha_id
                        }
                        if args.dry_run:
                            guardados += 1
                        else:
                            result = supabase.table("alineaciones").insert(row).execute()
                            if result and result.data:
                                guardados += 1
            
            if c3.isdigit():
                num = int(c3)
                if num not in numeros_visita:
                    numeros_visita.add(num)
                    # Now goleo should be integer (count of goals)
                    es_goleador = goleadores_visita.count(num)
                    result = None
                    
                    # Skip if name is empty or "0"
                    nombre_limpio = c4.strip() if c4 else ""
                    if nombre_limpio and nombre_limpio != "0":
                        row = {
                            "categoria_id": 1, "partido_id": partido_id,
                            "equipo_id": equipo_columna_visita_id, "numero": num,
                            "nombre": nombre_limpio[:100],
                            "es_titular": num <= 11, "tiempo": "PT",
                            "goleo": es_goleador,
                            "roja": num in rojas_visita,
                            "fecha_id": fecha_id
                        }
                        if args.dry_run:
                            guardados += 1
                        else:
                            result = supabase.table("alineaciones").insert(row).execute()
                            if result and result.data:
                                guardados += 1

accion = "detectadas" if args.dry_run else "guardadas"
print(f"Listo: {guardados} alineaciones {accion}")
