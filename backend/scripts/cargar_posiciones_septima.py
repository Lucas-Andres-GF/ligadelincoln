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

def cargar_posiciones_septima():
    url = "https://www.ligaamateurdedeportes.com.ar/septima.html"
    cat_name = "septima"
    cat_id = CATEGORIAS[cat_name]
    response = requests.get(url)
    response.encoding = 'utf-8'
    soup = BeautifulSoup(response.text, 'html.parser')
    # Buscar la tabla de posiciones (la que tiene al menos 7 columnas y datos numéricos en la 7 en adelante)
    tabla_obj = None
    for t in soup.find_all('table'):
        filas = t.find_all('tr')
        for fila in filas:
            celdas = fila.find_all('td')
            if len(celdas) >= 7:
                textos = [limpiar_texto(c).upper() for c in celdas]
                # Si alguna de las celdas 6, 0, 7, 8, 9, 10, 11, 12, 13 es un club conocido, es la tabla
                if any(textos[i] in MAPEO_CLUBES for i in [0,6] if i < len(textos)):
                    tabla_obj = t
                    break
        if tabla_obj:
            break
    if not tabla_obj:
        print("No se encontró la tabla de posiciones principal.")
        return
    filas = tabla_obj.find_all('tr')
    posiciones = []
    equipos_agregados = set()
    for fila in filas:
        celdas = fila.find_all('td')
        if len(celdas) < 7:
            continue
        textos = [limpiar_texto(c).upper() for c in celdas]
        # Nombre de equipo: preferir columna 6, si no es válida usar columna 0
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
    cargar_posiciones_septima()