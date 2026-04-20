# -*- coding: utf-8 -*-
import requests
from bs4 import BeautifulSoup
import re
import unicodedata
import sys
sys.stdout.reconfigure(encoding='utf-8')

from config import supabase, MAPEO_CLUBES, CATEGORIAS, EQUIPOS_POR_CATEGORIA

URLS = {
    "primera": "https://www.ligaamateurdedeportes.com.ar/primera.html",
    "septima": "https://www.ligaamateurdedeportes.com.ar/septima.html",
    "octava": "https://www.ligaamateurdedeportes.com.ar/octava.html",
    "novena": "https://www.ligaamateurdedeportes.com.ar/novena.html",
    "decima": "https://www.ligaamateurdedeportes.com.ar/decima.html"
}

def normalizar_equipo(nombre):
    if not nombre:
        return ""
    nombre = unicodedata.normalize('NFD', nombre)
    nombre = ''.join(c for c in nombre if unicodedata.category(c) != 'Mn')
    nombre = nombre.replace(".", "").strip().upper()
    nombre = re.sub(r'\s+', ' ', nombre)
    return nombre

def convertir_fecha(fecha_str):
    if not fecha_str:
        return None
    fecha_str = fecha_str.strip()
    m = re.match(r'(\d{2})/(\d{2})/(\d{2,4})', fecha_str)
    if m:
        dd, mm, aa = m.groups()
        if len(aa) == 2:
            aa = '20' + aa
        return f"{aa}-{mm}-{dd}"
    return None

def limpiar_tabla_posiciones(cat_id):
    try:
        supabase.table("posiciones").delete().eq("categoria_id", cat_id).execute()
    except:
        pass

def scrapear_ultima_fecha(url, cat_name):
    cat_id = CATEGORIAS[cat_name]
    print(f"\n=== {cat_name.upper()} ===")
    
    try:
        response = requests.get(url, timeout=30)
        response.encoding = 'utf-8'
        html_content = response.text
    except Exception as e:
        print(f"  ERROR: {e}")
        return [], []
    
    soup = BeautifulSoup(html_content, 'html.parser')
    tablas = soup.find_all('table')
    
    tabla_encontrada = None
    for i, tabla in enumerate(tablas):
        texto = tabla.get_text().upper()
        if 'ULTIMOS ENCUENTROS' in texto or 'ÚLTIMOS ENCUENTROS' in texto:
            tabla_encontrada = tabla
            break
    
    if not tabla_encontrada:
        print(f"  WARN: No se encontro tabla")
        return [], []
    
    filas = tabla_encontrada.find_all('tr')
    
    equipos_norm = {normalizar_equipo(k): v for k, v in MAPEO_CLUBES.items()}
    
    fecha_num = None
    fecha_date = None
    partidos = []
    partidos_vistos = set()
    
    modo_partidos = False
    encabezados_ok = False
    fecha_actual = None  # Trackear qué fecha estamos procesando
    
    for idx, fila in enumerate(filas):
        celdas = [c.get_text(strip=True) for c in fila.find_all('td')]
        if not celdas:
            continue
        
        celdas_up = [c.upper() for c in celdas]
        texto_celda = ' '.join(celdas_up)
        
        # Si ya encontramos la fecha y esta fila tiene UNA FECHA DIFERENTE, salir SIN procesar
        if 'FECHA' in texto_celda and fecha_actual is not None:
            match = re.search(r'FECHA\s*:?[\s\u00A0]*(\d+)', texto_celda)
            if match and int(match.group(1)) != fecha_actual:
                print(f"  -> Cambió de fecha {fecha_actual} a {match.group(1)}, saliendo")
                return partidos, fecha_num
        
        for i, celda in enumerate(celdas):
            celda_up = celda.upper()
            if 'FECHA' in celda_up and fecha_actual is None:
                match = re.search(r'FECHA\s*:?[\s\u00A0]*(\d+)', celda_up)
                if match:
                    fecha_num = int(match.group(1))
                elif i+1 < len(celdas) and celdas[i+1].isdigit():
                    fecha_num = int(celdas[i+1])
                fecha_actual = fecha_num
                
                for off in range(1, 5):
                    if idx + off < len(filas):
                        sig = [c.get_text(strip=True) for c in filas[idx + off].find_all('td')]
                        for c in sig:
                            if re.match(r'\d{2}/\d{2}/\d{2,4}', c):
                                fecha_date = convertir_fecha(c)
                                break
                        if fecha_date:
                            break
                break
            
            # Si encontramos OTRA FECHA diferente, salir del loop
            if 'FECHA' in celda_up:
                match = re.search(r'FECHA\s*:?[\s\u00A0]*(\d+)', celda_up)
                if match:
                    nueva_fecha = int(match.group(1))
                    if nueva_fecha != fecha_actual:
                        return partidos, fecha_num
        
        if 'LOCAL' in celdas_up and 'VISITANTE' in celdas_up:
            encabezados_ok = True
            modo_partidos = True
            continue
        
        if encabezados_ok and modo_partidos:
            if len(celdas) >= 4:
                loc = normalizar_equipo(celdas[0])
                vis = normalizar_equipo(celdas[3])
                
                if not loc or not vis:
                    continue
                
                if 'LIBRE' in loc or 'LIBRE' in vis:
                    continue
                
                if 'LOCAL' in loc or 'VISITANTE' in loc:
                    continue
                
                try:
                    gol_loc = int(celdas[1]) if celdas[1].isdigit() else None
                    gol_vis = int(celdas[2]) if celdas[2].isdigit() else None
                except:
                    continue
                
                if gol_loc is None or gol_vis is None:
                    continue
                
                id_loc = equipos_norm.get(loc)
                id_vis = equipos_norm.get(vis)
                
                if id_loc and id_vis:
                    clave = (id_loc, id_vis, gol_loc, gol_vis)
                    if clave in partidos_vistos:
                        continue
                    partidos_vistos.add(clave)
                    
                    partidos.append({
                        "categoria_id": cat_id,
                        "torneo_id": 1,
                        "fecha_id": fecha_num,
                        "local_id": id_loc,
                        "visitante_id": id_vis,
                        "goles_local": gol_loc,
                        "goles_visitante": gol_vis,
                        "dia": fecha_date,
                        "estado": "jugado"
                    })
    
    print(f"  Fecha: {fecha_num} ({fecha_date})")
    print(f"  Partidos: {len(partidos)}")
    
    for p in partidos:
        loc_n = [k for k, v in MAPEO_CLUBES.items() if v == p['local_id']]
        vis_n = [k for k, v in MAPEO_CLUBES.items() if v == p['visitante_id']]
        print(f"    {loc_n[0] if loc_n else '?'} {p['goles_local']}-{p['goles_visitante']} {vis_n[0] if vis_n else '?'}")
    
    return partidos, fecha_num

def calcular_posiciones(cat_id, todos_partidos):
    """Calcula posiciones usando TODOS los partidos jugados de la DB."""
    if not todos_partidos:
        return []
    
    equipos_validos = EQUIPOS_POR_CATEGORIA.get(cat_id, [])
    stats = {}
    
    for club_id in equipos_validos:
        stats[club_id] = {'pts': 0, 'pj': 0, 'pg': 0, 'pe': 0, 'pp': 0, 'gf': 0, 'gc': 0, 'ultimos': []}
    
    # Ordenar partidos por fecha_id para tener los más recientes al final
    todos_partidos_ordenados = sorted(todos_partidos, key=lambda p: (p.get('fecha_id', 0), p.get('id', 0)))
    
    for p in todos_partidos_ordenados:
        loc = p['local_id']
        vis = p['visitante_id']
        gl = p.get('goles_local', 0) or 0
        gv = p.get('goles_visitante', 0) or 0
        
        if loc not in stats:
            continue
        if vis not in stats:
            continue
        
        stats[loc]['pj'] += 1
        stats[vis]['pj'] += 1
        stats[loc]['gf'] += gl
        stats[loc]['gc'] += gv
        stats[vis]['gf'] += gv
        stats[vis]['gc'] += gl
        
        if gl > gv:
            stats[loc]['pts'] += 3
            stats[loc]['pg'] += 1
            stats[loc]['ultimos'].append('G')
            stats[vis]['pp'] += 1
            stats[vis]['ultimos'].append('P')
        elif gl < gv:
            stats[vis]['pts'] += 3
            stats[vis]['pg'] += 1
            stats[vis]['ultimos'].append('G')
            stats[loc]['pp'] += 1
            stats[loc]['ultimos'].append('P')
        else:
            stats[loc]['pts'] += 1
            stats[vis]['pts'] += 1
            stats[loc]['pe'] += 1
            stats[vis]['pe'] += 1
            stats[loc]['ultimos'].append('E')
            stats[vis]['ultimos'].append('E')
    
    posiciones = []
    for club_id, s in stats.items():
        ult = s['ultimos'][-5:] if s['ultimos'] else []
        posiciones.append({
            "categoria_id": cat_id,
            "torneo_id": 1,
            "club_id": club_id,
            "pts": s['pts'],
            "pj": s['pj'],
            "pg": s['pg'],
            "pe": s['pe'],
            "pp": s['pp'],
            "gf": s['gf'],
            "gc": s['gc'],
            "dif": s['gf'] - s['gc'],
            "ultimos_5": ult
        })
    
    posiciones.sort(key=lambda x: (-x['pts'], -x['dif'], -x['gf']))
    return posiciones

def actualizar_partidos(partidos):
    total_actualizados = 0
    
    for p in partidos:
        try:
            result = supabase.table("partidos").update({
                "goles_local": p['goles_local'],
                "goles_visitante": p['goles_visitante'],
                "estado": "jugado"
            }).eq("categoria_id", p['categoria_id']).eq("fecha_id", p['fecha_id']).eq("local_id", p['local_id']).eq("visitante_id", p['visitante_id']).execute()
            
            if result.data:
                total_actualizados += 1
        except Exception as e:
            pass
    
    return total_actualizados

def main():
    from datetime import datetime
    resultados = []
    
    for cat_name, url in URLS.items():
        try:
            cat_id = CATEGORIAS[cat_name]
            
            # Limpiar tabla de posiciones
            limpiar_tabla_posiciones(cat_id)
            
            # Scrapear última fecha (para actualizar resultados nuevos)
            partidos_nuevos, fecha = scrapear_ultima_fecha(url, cat_name)
            
            if partidos_nuevos:
                resultados.extend(partidos_nuevos)
                
                # Actualizar partidos en DB
                actualizados = actualizar_partidos(partidos_nuevos)
                print(f"  {actualizados} partidos actualizados")
            
            # Obtener TODOS los partidos jugados de esta categoría de la DB (YA ACTUALIZADOS)
            todos_partidos = supabase.table("partidos").select(
                "id, fecha_id, local_id, visitante_id, goles_local, goles_visitante"
            ).eq("categoria_id", cat_id).eq("estado", "jugado").execute()
            
            partidos_data = todos_partidos.data if todos_partidos.data else []
            
            # Calcular posiciones con TODOS los partidos (solo usar partidos_data, ya incluye los actualizados)
            posiciones = calcular_posiciones(cat_id, partidos_data)
            
            for pos in posiciones:
                pos['created_at'] = datetime.now().isoformat()
                try:
                    supabase.table("posiciones").insert(pos).execute()
                except Exception as e:
                    pass
            
            print(f"  {len(posiciones)} posiciones guardadas ({len(partidos_data)} partidos en DB)")
            
        except Exception as e:
            print(f"  ERROR {cat_name}: {e}")
    
    print(f"\n=== Total: {len(resultados)} partidos nuevos ===")

if __name__ == "__main__":
    main()
