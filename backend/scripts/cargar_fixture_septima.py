import requests
import sys
from bs4 import BeautifulSoup
import re
import unicodedata
from config import supabase, MAPEO_CLUBES, CATEGORIAS

def normalizar_equipo(nombre):
    if not nombre: return ""
    nombre = unicodedata.normalize('NFD', nombre)
    nombre = ''.join(c for c in nombre if unicodedata.category(c) != 'Mn')
    nombre = nombre.replace(".", "").strip().upper()
    nombre = re.sub(r'\s+', ' ', nombre)  # Reemplaza múltiples espacios por uno
    return nombre

def cargar_fixture_septima():
    url = "https://www.ligaamateurdedeportes.com.ar/septima.html"
    cat_name = "septima"
    cat_id = CATEGORIAS[cat_name]
    print(f"Analizando archivo para {cat_name}...")
    response = requests.get(url)
    response.encoding = 'utf-8'
    html_content = response.text
    soup = BeautifulSoup(html_content, 'html.parser')
    equipos_norm = {normalizar_equipo(k): v for k, v in MAPEO_CLUBES.items()}
    partidos_batch = []
    partidos_vistos = set()
    fecha_actual = None
    procesar = False
    en_bloque_partidos = False
    dia_por_fecha = {}
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
    filas = soup.find_all('tr')
    for idx, fila in enumerate(filas):
        # Extraer texto plano y también HTML para mayor robustez
        celdas = [c.get_text(separator=' ', strip=True).upper() for c in fila.find_all('td')]
        # Detección robusta de fecha
        for i, celda in enumerate(celdas):
            if 'FECHA' in celda:
                match = re.search(r'FECHA\s*:?[\s\u00A0]*(\d+)', celda)
                if match:
                    fecha_actual = int(match.group(1))
                elif i+1 < len(celdas) and celdas[i+1].isdigit():
                    fecha_actual = int(celdas[i+1])
                # Buscar el día en la fila siguiente
                dia_valor = None
                for offset in range(1, 4):
                    if idx + offset < len(filas):
                        next_celdas = [c.get_text(strip=True) for c in filas[idx + offset].find_all('td')]
                        for cel in next_celdas:
                            cel = cel.strip()
                            if re.match(r'\d{2}/\d{2}/\d{2,4}', cel):
                                dia_valor = cel
                                break
                        if dia_valor:
                            break
                dia_por_fecha[fecha_actual] = convertir_fecha(dia_valor) if dia_valor else None
                en_bloque_partidos = False
                break
        if not fecha_actual:
            continue
        # Detectar inicio del bloque de partidos
        if not en_bloque_partidos:
            if any('LOCAL' in celda for celda in celdas):
                en_bloque_partidos = True
            continue
        # Fin del bloque de partidos
        if not celdas or all(not celda.strip() for celda in celdas):
            en_bloque_partidos = False
            continue
        # Procesar filas de partidos y libres
        if len(celdas) >= 4:
            loc_txt = celdas[0]
            vis_txt = celdas[3]
            loc_norm = normalizar_equipo(loc_txt)
            vis_norm = normalizar_equipo(vis_txt)
            id_l = equipos_norm.get(loc_norm)
            id_v = equipos_norm.get(vis_norm)
            dia_partido = dia_por_fecha.get(fecha_actual, None)
            # Caso LIBRE (pueden ser varios por fecha)
            if loc_norm.startswith('LIBRE'):
                # El equipo libre está en la columna visitante, pero puede haber espacios extra
                equipo_libre = vis_norm
                # A veces el nombre puede tener espacios extra, los normalizamos
                equipo_libre = re.sub(r'\s+', ' ', equipo_libre).strip()
                id_libre = equipos_norm.get(equipo_libre)
                if not id_libre:
                    # Intentar normalizar quitando espacios dobles
                    equipo_libre_simple = equipo_libre.replace(' ', '')
                    for k in equipos_norm:
                        if k.replace(' ', '') == equipo_libre_simple:
                            id_libre = equipos_norm[k]
                            break
                if id_libre:
                    clave = (fecha_actual, id_libre, None)
                    if clave not in partidos_vistos:
                        partidos_batch.append({
                            "categoria_id": cat_id,
                            "fecha_id": fecha_actual,
                            "local_id": id_libre,
                            "visitante_id": None,
                            "estado": "programado",
                            "dia": dia_partido
                        })
                        partidos_vistos.add(clave)
                continue
            # Partido normal
            if id_l and id_v and id_l != id_v:
                clave_unica = (fecha_actual, id_l, id_v)
                if clave_unica not in partidos_vistos:
                    partidos_batch.append({
                        "categoria_id": cat_id,
                        "fecha_id": fecha_actual,
                        "local_id": id_l,
                        "visitante_id": id_v,
                        "estado": "programado",
                        "dia": dia_partido
                    })
                    partidos_vistos.add(clave_unica)
    # --- REPORTE ---
    print(f"\nResultados:")
    print(f"- Partidos/Libres encontrados: {len(partidos_batch)}")
    fechas_encontradas = sorted(list(set(p['fecha_id'] for p in partidos_batch)))
    print(f"- Fechas detectadas: {fechas_encontradas}")
    if len(partidos_batch) >= 1:
        id_a_nombre = {v: k for k, v in MAPEO_CLUBES.items()}
        for p in partidos_batch:
            p["torneo_id"] = 1
            if p.get("local_id"):
                p["cancha"] = id_a_nombre.get(p["local_id"], "")
        supabase.table("partidos").upsert(partidos_batch).execute()
        print("🚀 Cargado con éxito.")
    else:
        print("\n⚠️ No se detectaron partidos.")
        for f in fechas_encontradas:
            cant = len([p for p in partidos_batch if p['fecha_id'] == f])
            print(f"  Fecha {f}: {cant} partidos")

if __name__ == "__main__":
    cargar_fixture_septima()
