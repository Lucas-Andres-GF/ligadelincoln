# scraper_alineaciones.py - Fixed to parse single table with all matches

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

def normalizar(t):
    if not t: return ""
    t = unicodedata.normalize('NFD', t)
    t = ''.join(c for c in t if unicodedata.category(c) != 'Mn')
    return re.sub(r'\s+', ' ', t.replace(".", "").replace(",", "").strip().upper())

def limpiar(t):
    return t.replace('\xa0', ' ').replace('\n', ' ').strip() if t else ""

# Fetch HTML
print("Fetching HTML...")
response = requests.get(URL, timeout=30)
response.encoding = 'utf-8'
soup = BeautifulSoup(response.text, 'html.parser')
print("Parsed HTML")

# Obtener partidos
print("Getting partidos...")
partidos = supabase.table("partidos").select("id,local_id,visitante_id").eq("categoria_id",1).eq("fecha_id",5).execute().data
partidos = [p for p in partidos if p['local_id'] and p['visitante_id']]
print(f"Partidos: {len(partidos)}")

# Limpiar
partido_ids = [p['id'] for p in partidos]
if partido_ids:
    supabase.table("alineaciones").delete().in_("partido_id", partido_ids).execute()
    print("Limpiado")

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
        c0 = normalizar(limpiar(cells[0].get_text()))
        c1 = limpiar(cells[1].get_text())
        c2 = limpiar(cells[2].get_text())
        c3 = normalizar(limpiar(cells[3].get_text()))
        
        # Detectar fila de inicio de partido: [EquipoLocal] [Numero] [Numero] [EquipoVisitante]
        equipo_local = None
        equipo_visita = None
        
        for eq_n, eq_id in MAPEO_CLUBES.items():
            eq_norm = normalizar(eq_n)
            # El equipo local aparece en columna 0
            if eq_norm in c0 and len(c0) < 30:  # No muy largo
                equipo_local = eq_id
            # El equipo visitante aparece en columna 3
            if eq_norm in c3 and len(c3) < 30:
                equipo_visita = eq_id
        
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
    
    print(f"Procesando: {local_id} vs {visita_id}")
    
    # Determinar filas del partido (desde inicio hasta el siguiente partido o fin)
    fila_inicio = datos_partido['fila_inicio']
    fila_fin = len(filas)
    for i, pd in enumerate(partidos_en_tabla):
        if pd['fila_inicio'] > fila_inicio:
            fila_fin = pd['fila_inicio']
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

    print(f"  DT Local: {dt_local}, DT Visita: {dt_visitante}, Arbitro: {arbitro}")

    # Save dt and arbitro to partidos (if columns exist)
    if dt_local or dt_visitante or arbitro:
        updates = {}
        if dt_local:
            updates["dt_local"] = dt_local
        if dt_visitante:
            updates["dt_visitante"] = dt_visitante
        if arbitro:
            updates["arbitro"] = arbitro

        if updates:
            try:
                supabase.table("partidos").update(updates).eq("id", partido_id).execute()
                print(f"  Staff guardado")
            except Exception as e:
                print(f"  Staff error (columns may not exist): {e}")

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
        """Check if scorer_name matches player_name with stricter matching"""
        if not scorer_name or not player_name:
            return False
        scorer_words = scorer_name.split()
        player_words = player_name.split()
        
        # Must match at least first AND last name (2+ words)
        if len(scorer_words) < 2 or len(player_words) < 2:
            return False
        
        # Check first word matches AND at least one other word matches
        first_match = scorer_words[0] == player_words[0]
        other_matches = sum(1 for w in scorer_words[1:] if w in player_words)
        return first_match and other_matches > 0
    
    for idx in range(fila_inicio, fila_fin):
        fila = filas[idx]
        cells = fila.find_all('td')
        
        if len(cells) >= 9:
            scorer_name = normalizar(limpiar(cells[7].get_text()))
            score = limpiar(cells[8].get_text()) if len(cells) > 8 else ""
            
            # Skip invalid
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
                        
                        # Local scored
                        if curr_local > prev_local and scorer_name:
                            for num, nombre in jugadores_local.items():
                                if matches_player(scorer_name, nombre):
                                    goleadores_local.append(num)
                        
                        # Visitor scored
                        if curr_visita > prev_visita and scorer_name:
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
                    
                    # Skip if name is empty or "0"
                    nombre_limpio = c1.strip() if c1 else ""
                    if nombre_limpio and nombre_limpio != "0":
                        result = supabase.table("alineaciones").insert({
                            "categoria_id": 1, "partido_id": partido_id,
                            "equipo_id": local_id, "numero": num,
                            "nombre": nombre_limpio[:100],
                            "es_titular": num <= 11, "tiempo": "PT",
                            "goleo": es_goleador,
                            "roja": num in rojas_local
                        }).execute()
                    if result.data:
                        guardados += 1
            
            if c3.isdigit():
                num = int(c3)
                if num not in numeros_visita:
                    numeros_visita.add(num)
                    # Now goleo should be integer (count of goals)
                    es_goleador = goleadores_visita.count(num)
                    
                    # Skip if name is empty or "0"
                    nombre_limpio = c4.strip() if c4 else ""
                    if nombre_limpio and nombre_limpio != "0":
                        result = supabase.table("alineaciones").insert({
                            "categoria_id": 1, "partido_id": partido_id,
                            "equipo_id": visita_id, "numero": num,
                            "nombre": nombre_limpio[:100],
                            "es_titular": num <= 11, "tiempo": "PT",
                            "goleo": es_goleador,
                            "roja": num in rojas_visita
                        }).execute()
                    if result.data:
                        guardados += 1

print(f"Listo: {guardados} alineaciones")