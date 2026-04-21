# scraper_alineaciones.py
# Scrapea las alineaciones de alineaciones.html y las guarda en Supabase

import requests
from bs4 import BeautifulSoup
import re
import unicodedata
import sys
sys.stdout.reconfigure(encoding='utf-8')

from config import supabase, MAPEO_CLUBES, CATEGORIAS

URL = "https://www.ligaamateurdedeportes.com.ar/alineaciones.html"

def normalizar(nombre):
    if not nombre:
        return ""
    nombre = unicodedata.normalize('NFD', nombre)
    nombre = ''.join(c for c in nombre if unicodedata.category(c) != 'Mn')
    nombre = nombre.replace(".", "").replace(",", "").strip().upper()
    nombre = re.sub(r'\s+', ' ', nombre)
    return nombre

def limpiar(texto):
    if not texto:
        return ""
    return texto.replace('\xa0', ' ').replace('\n', ' ').replace('\r', ' ').strip()

def encontrar_equipo(nombre_limpio, equipos_norm):
    # Buscar coincidencia exacta o parcial
    for eq_nombre, eq_id in equipos_norm.items():
        eq_norm = normalizar(eq_nombre)
        if nombre_limpio.startswith(eq_norm[:10]) or eq_norm.startswith(nombre_limpio[:10]):
            return eq_id
    return None

def parsear_aline(url, cat_id=1):
    print(f"\n=== Parseando alineaciones ===")
    
    response = requests.get(url, timeout=30)
    response.encoding = 'utf-8'
    soup = BeautifulSoup(response.text, 'html.parser')
    
    equipos_norm = {normalizar(k): v for k, v in MAPEO_CLUBES.items()}
    
    tablas = soup.find_all('table')
    print(f"Tablas encontradas: {len(tablas)}")
    
    for idx, tabla in enumerate(tablas):
        filas = tabla.find_all('tr')
        if len(filas) < 5:
            continue
        
        # Buscar fila con nombres de equipos (fila 5 aproximadamente)
        equipos_fila = None
        for f in filas[:8]:
            cells = f.find_all('td')
            if len(cells) >= 4:
                texto = ' '.join([limpiar(c.get_text()) for c in cells])
                if 'PRIMER TIEMPO' in texto.upper():
                    equipos_fila = f
                    break
        
        if not equipos_fila:
            continue
            
        cells = equipos_fila.find_all('td')
        if len(cells) < 4:
            continue
            
        # Nombres de equipos
        eq_local = normalizar(limpiar(cells[0].get_text()))
        eq_visita = normalizar(limpiar(cells[3].get_text()))
        
        # Buscar IDs
        local_id = None
        visita_id = None
        
        for eq_n, eq_id in equipos_norm.items():
            eq_norm = normalizar(eq_n)
            if eq_norm[:8] in eq_local[:15] or eq_local[:8] in eq_norm:
                local_id = eq_id
            if eq_norm[:8] in eq_visita[:15] or eq_visita[:8] in eq_norm:
                visita_id = eq_id
        
        if not local_id or not visita_id:
            print(f"  Equipo no encontrado: {eq_local} vs {eq_visita}")
            continue
            
        # Limpiar alineaciones anteriores de este partido
        try:
            supabase.table("alineaciones").delete().eq("categoria_id", cat_id).execute()
            supabase.table("goleadores_partido").delete().eq("categoria_id", cat_id).execute()
        except:
            pass
        
        print(f"\n--- Partido {idx+1}: {local_id} vs {visita_id} ---")
        
        # Parsear jugadores (filas con numeros de camiseta)
        for fila in filas[8:]:  # Empezar despues de encabezado
            cells = fila.find_all('td')
            if len(cells) < 4:
                continue
            
            # Skip headers
            if 'PRIMER' in limpiar(cells[0].get_text()).upper():
                continue
            if 'SEGUNDO' in limpiar(cells[0].get_text()).upper():
                continue
            if 'ARBITRO' in limpiar(cells[0].get_text()).upper():
                break
            
            # Local (columnas 0-1)
            num_local = limpiar(cells[0].get_text())
            jug_local = limpiar(cells[1].get_text())
            
            # Visitante (columnas 3-4)
            num_visita = limpiar(cells[3].get_text())
            jug_visita = limpiar(cells[4].get_text())
            
            if num_local.isdigit() and jug_local:
                print(f"  Local {num_local}: {jug_local}")
                try:
                    supabase.table("alineaciones").insert({
                        "categoria_id": cat_id,
                        "partido_id": idx + 1,
                        "equipo_id": local_id,
                        "numero": int(num_local),
                        "es_titular": int(num_local) <= 11
                    }).execute()
                except:
                    pass
            
            if num_visita.isdigit() and jug_visita:
                print(f"  Visita {num_visita}: {jug_visita}")
                try:
                    supabase.table("alineaciones").insert({
                        "categoria_id": cat_id,
                        "partido_id": idx + 1,
                        "equipo_id": visita_id,
                        "numero": int(num_visita),
                        "es_titular": int(num_visita) <= 11
                    }).execute()
                except:
                    pass
        
    print("\n=== Fin ===")

def main():
    parsear_aline(URL, cat_id=1)

if __name__ == "__main__":
    main()