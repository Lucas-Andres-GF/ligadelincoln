# -*- coding: utf-8 -*-
import requests
from bs4 import BeautifulSoup
import re
import unicodedata
import sys
sys.stdout.reconfigure(encoding='utf-8')

from config import supabase, MAPEO_CLUBES, CATEGORIAS, EQUIPOS_POR_CATEGORIA

def normalizar_equipo(nombre):
    if not nombre:
        return ""
    nombre = unicodedata.normalize('NFD', nombre)
    nombre = ''.join(c for c in nombre if unicodedata.category(c) != 'Mn')
    nombre = nombre.replace(".", "").strip().upper()
    nombre = re.sub(r'\s+', ' ', nombre)
    return nombre

def cargar_fixture(url, cat_name):
    cat_id = CATEGORIAS[cat_name]
    equipos_validos = EQUIPOS_POR_CATEGORIA[cat_id]
    
    response = requests.get(url, timeout=30)
    response.encoding = 'utf-8'
    html = response.text
    
    soup = BeautifulSoup(html, 'html.parser')
    
    # Buscar tabla por índice (tabla 2 tiene los datos)
    tablas = soup.find_all('table')
    if len(tablas) < 3:
        print("WARN: No hay suficientes tablas")
        return
    tabla_encontrada = tablas[2]
    
    filas = tabla_encontrada.find_all('tr')
    
    # Mapeo extendido
    mapeo = {}
    for k, v in MAPEO_CLUBES.items():
        mapeo[normalizar_equipo(k)] = v
        mapeo[k.upper()] = v
    
    partidos = []
    vistos = set()
    fecha = None
    en_partidos = False
    
    for idx, fila in enumerate(filas):
        celdas = [c.get_text(strip=True) for c in fila.find_all('td')]
        if not celdas:
            continue
        
        celdas_up = [c.upper() for c in celdas]
        
        # Detectar fecha
        for i, celda in enumerate(celdas):
            if 'FECHA' in celda.upper():
                match = re.search(r'FECHA\s*:?[\s\u00A0]*(\d+)', celda.upper())
                if match:
                    fecha = int(match.group(1))
                elif i+1 < len(celdas) and celdas[i+1].isdigit():
                    fecha = int(celdas[i+1])
                break
        
        # Detectar inicio de bloque de partidos
        if 'LOCAL' in celdas_up and 'VISITANTE' in celdas_up:
            en_partidos = True
            continue
        
        if not fecha or not en_partidos:
            continue
        
        if len(celdas) >= 4:
            loc = normalizar_equipo(celdas[0])
            vis = normalizar_equipo(celdas[3])
            
            if not loc and not vis:
                continue
            
            id_loc = mapeo.get(loc)
            id_vis = mapeo.get(vis)
            
            # Manejar LIBRE
            es_libre = False
            libre_id = None
            if 'LIBRE' in loc or 'LIBRE' in vis:
                es_libre = True
                if 'LIBRE' in loc and id_vis:
                    libre_id = id_vis
                elif 'LIBRE' in vis and id_loc:
                    libre_id = id_loc
            
            if es_libre and libre_id and libre_id in equipos_validos:
                clave = (fecha, libre_id, None)
                if clave not in vistos:
                    vistos.add(clave)
                    partidos.append({
                        "categoria_id": cat_id,
                        "torneo_id": 1,
                        "fecha_id": fecha,
                        "local_id": libre_id,
                        "visitante_id": None,
                        "estado": "programado"
                    })
                continue
            
            # Partido normal
            if not id_loc or not id_vis:
                continue
            if id_loc not in equipos_validos or id_vis not in equipos_validos:
                continue
            
            if (fecha, id_loc, id_vis) not in vistos:
                vistos.add((fecha, id_loc, id_vis))
                partidos.append({
                    "categoria_id": cat_id,
                    "torneo_id": 1,
                    "fecha_id": fecha,
                    "local_id": id_loc,
                    "visitante_id": id_vis,
                    "estado": "programado"
                })
    
    print(f"Partidos encontrados: {len(partidos)}")
    
    for p in partidos:
        try:
            supabase.table("partidos").insert(p).execute()
        except:
            pass
    
    print(f"OK: {len(partidos)} insertados")

if __name__ == "__main__":
    # Limpiar y cargar novena
    supabase.table("partidos").delete().eq("categoria_id", 4).execute()
    print("Limpiando partidos de novena...")
    cargar_fixture("https://www.ligaamateurdedeportes.com.ar/novena.html", "novena")
    
    # Verificar
    r = supabase.table("partidos").select("id").eq("categoria_id", 4).execute()
    print(f"Total partidos en novena: {len(r.data)}")
