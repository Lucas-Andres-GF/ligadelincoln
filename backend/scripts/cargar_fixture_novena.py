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
    nombre = re.sub(r'\s+', ' ', nombre)
    return nombre


# Unificación de nombres: CAEL y EL LINQUEÑO son el mismo club
def normalizar_equipo_unificado(nombre):
    n = normalizar_equipo(nombre)
    if n in ["CAEL", "EL LINQUEÑO"]:
        return "EL LINQUEÑO"
    return n

equipos_norm = {normalizar_equipo_unificado(k): v for k, v in MAPEO_CLUBES.items()}

def cargar_fixture_novena(url, cat_name):
    cat_id = CATEGORIAS[cat_name]
    print(f"Analizando archivo para {cat_name}...")
    if url.startswith('http'):
        response = requests.get(url)
        response.encoding = 'utf-8'
        html_content = response.text
    else:
        with open(url, 'r', encoding='utf-8') as f:
            html_content = f.read()
    soup = BeautifulSoup(html_content, 'html.parser')
    partidos_batch = []
    partidos_vistos = set()
    fecha_actual = None
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
    idx = 0
    while idx < len(filas):
        fila = filas[idx]
        celdas = [c.get_text(separator=' ', strip=True).upper() for c in fila.find_all('td')]
        # Detección robusta de fecha
        es_fecha = False
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
                es_fecha = True
                break
        if es_fecha:
            idx += 1
            continue
        if not fecha_actual:
            idx += 1
            continue
        # Detectar inicio del bloque de partidos
        if not en_bloque_partidos:
            if any('LOCAL' in celda for celda in celdas):
                en_bloque_partidos = True
                idx += 1
                continue
        # Procesar filas de partidos y libres mientras no se detecte nueva fecha o encabezado
        if en_bloque_partidos:
            # Si detectamos una fila de encabezado o nueva fecha, salimos del bloque
            if any('FECHA' in celda or 'LOCAL' in celda for celda in celdas):
                en_bloque_partidos = False
                idx += 1
                continue
            # Procesar filas de partidos y libres
            if len(celdas) >= 4:
                loc_txt = celdas[0]
                vis_txt = celdas[3]
                # Usar la función unificada para normalizar los nombres en cada fila
                loc_norm = normalizar_equipo_unificado(loc_txt)
                vis_norm = normalizar_equipo_unificado(vis_txt)
                id_l = equipos_norm.get(loc_norm)
                id_v = equipos_norm.get(vis_norm)
                dia_partido = dia_por_fecha.get(fecha_actual, None)
                # Caso LIBRE (pueden ser varios por fecha)
                if loc_norm.startswith('LIBRE'):
                    equipo_libre = vis_norm
                    equipo_libre = re.sub(r'\s+', ' ', equipo_libre).strip()
                    id_libre = equipos_norm.get(equipo_libre)
                    if not id_libre:
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
                # DEBUG extra: mostrar filas que no se procesan como partido ni libre
                if en_bloque_partidos and len(celdas) >= 4:
                    loc_txt = celdas[0]
                    vis_txt = celdas[3]
                    loc_norm = normalizar_equipo_unificado(loc_txt)
                    vis_norm = normalizar_equipo_unificado(vis_txt)
                    id_l = equipos_norm.get(loc_norm)
                    id_v = equipos_norm.get(vis_norm)
                    if not (loc_norm.startswith('LIBRE') or (id_l and id_v and id_l != id_v)):
                        print(f"[DEBUG] Fila ignorada en fecha {fecha_actual}: {celdas}")
            idx += 1
            continue
        idx += 1
    # --- REPORTE ---
    print(f"\nResultados:")
    print(f"- Partidos/Libres encontrados: {len(partidos_batch)}")
    fechas_encontradas = sorted(list(set(p['fecha_id'] for p in partidos_batch)))
    print(f"- Fechas detectadas: {fechas_encontradas}")
    if len(partidos_batch) >= 1:
        print("\n¿Deseas subir los datos a Supabase? (s/n): ")
        id_a_nombre = {v: k for k, v in MAPEO_CLUBES.items()}
        for p in partidos_batch:
            p["torneo_id"] = 1
            if p.get("local_id"):
                p["cancha"] = id_a_nombre.get(p["local_id"], "")
        confirmar = input()
        if confirmar.lower() == 's':
            supabase.table("partidos").upsert(partidos_batch).execute()
            print("🚀 Cargado con éxito.")
    else:
        print("\n⚠️ No se detectaron partidos.")
        for f in fechas_encontradas:
            cant = len([p for p in partidos_batch if p['fecha_id'] == f])
            print(f"  Fecha {f}: {cant} partidos")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Uso: python cargar_fixture_novena.py <ARCHIVO.html o URL> <CATEGORIA>")
    else:
        cargar_fixture_novena(sys.argv[1], sys.argv[2])
