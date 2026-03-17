import requests
from bs4 import BeautifulSoup
import unicodedata
import re
from config import supabase, MAPEO_CLUBES, CATEGORIAS

def normalizar_equipo(nombre):
    if not nombre:
        return ""
    nombre = unicodedata.normalize('NFD', nombre)
    nombre = ''.join(c for c in nombre if unicodedata.category(c) != 'Mn')
    nombre = nombre.replace(".", "").strip().upper()
    nombre = re.sub(r'\s+', ' ', nombre)
    return nombre

def limpiar_texto(txt):
    return txt.get_text(strip=True).replace('\xa0', ' ')

def cargar_posiciones_primera():
    url = "https://www.ligaamateurdedeportes.com.ar/primera.html"
    cat_name = "primera"
    cat_id = CATEGORIAS[cat_name]
    response = requests.get(url)
    response.encoding = 'utf-8'
    soup = BeautifulSoup(response.text, 'html.parser')
    posiciones = []
    # Buscar la fila de encabezados correcta en cualquier tabla
    encabezados = ["EQUIPOS", "PTS", "J", "G", "E", "P", "GF", "GC"]
    tabla_obj = None
    fila_encabezado_idx = None
    for t in soup.find_all('table'):
        filas = t.find_all('tr')
        for idx, fila in enumerate(filas):
            textos = [limpiar_texto(c).upper() for c in fila.find_all('td')]
            if all(e in textos for e in encabezados):
                tabla_obj = t
                fila_encabezado_idx = idx
                break
        if tabla_obj:
            break
    if not tabla_obj or fila_encabezado_idx is None:
        print("No se encontró la tabla de posiciones principal.")
        return
    filas = tabla_obj.find_all('tr')
    equipos_agregados = set()
    print("Equipos detectados en la tabla de posiciones (columna 7):")
    for fila in filas[fila_encabezado_idx+1:]:
        celdas = fila.find_all('td')
        if len(celdas) < 13:
            continue
        textos = [limpiar_texto(c).upper() for c in celdas]
        nombre_equipo = textos[6] if len(textos) > 6 and textos[6] and textos[6] != "LIBRE:" else textos[0]
        print(f"- {nombre_equipo}")
    print("\n--- Fin de equipos detectados ---\n")

    # Procesar posiciones desde la columna 7 en adelante
    for fila in filas[fila_encabezado_idx+1:]:
        celdas = fila.find_all('td')
        if len(celdas) < 13:
            continue
        textos = [limpiar_texto(c).upper() for c in celdas]
        # Si la celda 6 no es válida, usar la celda 0
        nombre_equipo = textos[6] if len(textos) > 6 and textos[6] and textos[6] != "LIBRE:" else textos[0]
        if (
            not nombre_equipo or
            nombre_equipo == "LIBRE:" or
            nombre_equipo not in MAPEO_CLUBES or
            nombre_equipo in equipos_agregados
        ):
            continue
        club_id = MAPEO_CLUBES[nombre_equipo]
        def get_int(idx):
            try:
                return int(textos[idx])
            except:
                return 0
        registro = {
            "torneo_id": 1,
            "categoria_id": cat_id,
            "club_id": club_id,
            "pts": get_int(7),
            "pj": get_int(8),
            "pg": get_int(9),
            "pe": get_int(10),
            "pp": get_int(11),
            "gf": get_int(12),
            "gc": get_int(13),
            "dif": get_int(14) if len(textos) > 14 else 0,
            "ultimos_5": textos[15] if len(textos) > 15 else None
        }
        posiciones.append(registro)
        equipos_agregados.add(nombre_equipo)

    if posiciones:
        supabase.table("posiciones").upsert(posiciones).execute()
        print(f"🚀 Cargadas posiciones para {cat_name} ({len(posiciones)} equipos)")
    else:
        print(f"⚠️ No se cargaron posiciones para {cat_name}")

if __name__ == "__main__":
    cargar_posiciones_primera()