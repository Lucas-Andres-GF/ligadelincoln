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

def cargar_posiciones_octava():
    url = "https://www.ligaamateurdedeportes.com.ar/octava.html"
    cat_name = "octava"
    cat_id = CATEGORIAS[cat_name]
    response = requests.get(url)
    response.encoding = 'utf-8'
    soup = BeautifulSoup(response.text, 'html.parser')
    # Buscar la tabla que tenga encabezado 'Equipos' y columnas de posiciones
    equipos_octava = set(MAPEO_CLUBES.keys())
    encabezado = ["EQUIPOS", "PTS", "J", "G", "E", "P", "GF", "GC"]
    tabla_obj = None
    idx_encabezado = -1
    for t in soup.find_all('table'):
        filas = t.find_all('tr')
        for i, fila in enumerate(filas):
            celdas = fila.find_all('td')
            textos = [limpiar_texto(c).upper() for c in celdas]
            # Buscar encabezado (puede estar desplazado, pero debe contener todos los campos)
            if all(e in textos for e in encabezado):
                tabla_obj = t
                idx_encabezado = i
                break
        if tabla_obj:
            break
    if not tabla_obj:
        print("No se encontró la tabla de posiciones principal.")
        return
    filas_tabla = tabla_obj.find_all('tr')[idx_encabezado+1:]
    posiciones = []
    equipos_agregados = set()
    def es_num(s):
        try:
            int(s)
            return True
        except:
            return False
    for fila in filas_tabla:
        celdas = fila.find_all('td')
        textos = [limpiar_texto(c).upper() for c in celdas]
        if len(textos) < 8:
            continue
        nombre_equipo = textos[0]
        # Si la columna 0 no es un equipo válido, probar la columna 6 (algunos htmls la ponen ahí)
        if nombre_equipo not in equipos_octava:
            if len(textos) > 6 and textos[6] in equipos_octava:
                nombre_equipo = textos[6]
            else:
                continue
        if (
            not nombre_equipo or
            nombre_equipo == "LIBRE:" or
            nombre_equipo not in equipos_octava or
            nombre_equipo in equipos_agregados
        ):
            continue
        # Tomar los 7 valores numéricos siguientes a la columna del equipo
        idx = textos.index(nombre_equipo)
        nums = []
        for i in range(idx+1, len(textos)):
            if es_num(textos[i]):
                nums.append(int(textos[i]))
            if len(nums) == 7:
                break
        if len(nums) < 7:
            continue
        club_id = MAPEO_CLUBES[nombre_equipo]
        registro = {
            "torneo_id": 1,
            "categoria_id": cat_id,
            "club_id": club_id,
            "pts": nums[0],
            "pj": nums[1],
            "pg": nums[2],
            "pe": nums[3],
            "pp": nums[4],
            "gf": nums[5],
            "gc": nums[6],
            "dif": nums[5] - nums[6],
            "ultimos_5": None
        }
        posiciones.append(registro)
        equipos_agregados.add(nombre_equipo)
    if posiciones:
        supabase.table("posiciones").upsert(posiciones).execute()
        print(f"🚀 Cargadas posiciones para {cat_name} ({len(posiciones)} equipos)")
    else:
        print(f"⚠️ No se cargaron posiciones para {cat_name}")

if __name__ == "__main__":
    cargar_posiciones_octava()
