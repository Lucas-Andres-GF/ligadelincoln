import requests
import sys
from bs4 import BeautifulSoup
import re
import unicodedata
from config import supabase, MAPEO_CLUBES, CATEGORIAS

def normalizar_equipo(nombre):
    if not nombre:
        return ""
    nombre = unicodedata.normalize('NFD', nombre)
    nombre = ''.join(c for c in nombre if unicodedata.category(c) != 'Mn')
    nombre = nombre.replace(".", "").strip().upper()
    nombre = re.sub(r'\s+', ' ', nombre)
    return nombre

def cargar_calendario_completo(url, cat_name):
    cat_id = CATEGORIAS[cat_name]
    print(f"Analizando archivo para {cat_name}...")
    
    # Si pasas un archivo local o una URL
    if url.startswith('http'):
        response = requests.get(url)
        response.encoding = 'utf-8'
        html_content = response.text
    else:
        with open(url, 'r', encoding='utf-8') as f:
            html_content = f.read()

    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Normalizamos el mapeo
    equipos_norm = {normalizar_equipo(k): v for k, v in MAPEO_CLUBES.items()}

    partidos_batch = []
    partidos_vistos = set()
    fecha_actual = None

    filas = soup.find_all('tr')
    fecha_actual = None
    procesar = False
    en_bloque_partidos = False
    dia_por_fecha = {}  # fecha_id -> string o None
    ultima_fecha_detectada = None
    def convertir_fecha(fecha_str):
        if not fecha_str:
            return None
        fecha_str = fecha_str.strip()
        # dd/mm/yy o dd/mm/yyyy
        m = re.match(r'(\d{2})/(\d{2})/(\d{2,4})', fecha_str)
        if m:
            dd, mm, aa = m.groups()
            if len(aa) == 2:
                # Asumir 20xx para años de 2 dígitos
                aa = '20' + aa
            return f"{aa}-{mm}-{dd}"
        return None

    for idx, fila in enumerate(filas):
        celdas = [c.get_text(strip=True).upper() for c in fila.find_all('td')]
        # Activar procesamiento solo después de encontrar la celda de inicio
        if not procesar:
            # Permitir que 'FIXTURE COMPLETO' esté acompañado de otros textos
            if any('FIXTURE COMPLETO' in celda for celda in celdas):
                procesar = True
            # Si aún no se activa, seguir buscando
            if not procesar:
                continue
        # Detección robusta de fecha: buscar celda con "FECHA:" y la siguiente con el número
        for i, celda in enumerate(celdas):
            if 'FECHA' in celda:
                match = re.search(r'FECHA\s*:?[\s\u00A0]*(\d+)', celda)
                if match:
                    fecha_actual = int(match.group(1))
                elif i+1 < len(celdas) and celdas[i+1].isdigit():
                    fecha_actual = int(celdas[i+1])
                en_bloque_partidos = False  # Reiniciar bloque de partidos para nueva fecha
                # Buscar el día en la fila siguiente (o la subsiguiente si hay una vacía)
                dia_valor = None
                for offset in range(1, 4):
                    if idx + offset < len(filas):
                        next_celdas = [c.get_text(strip=True) for c in filas[idx + offset].find_all('td')]
                        # Buscar celda con formato de fecha tipo dd/mm/yy o dd/mm/yyyy
                        for cel in next_celdas:
                            cel = cel.strip()
                            if re.match(r'\d{2}/\d{2}/\d{2,4}', cel):
                                dia_valor = cel
                                break
                        if dia_valor:
                            break
                dia_por_fecha[fecha_actual] = convertir_fecha(dia_valor) if dia_valor else None
                ultima_fecha_detectada = fecha_actual
                break
        if not fecha_actual:
            continue
        # Detectar inicio del bloque de partidos (fila de encabezado)
        if not en_bloque_partidos:
            if any('LOCAL' in celda for celda in celdas):
                en_bloque_partidos = True
            continue
        # Fin del bloque de partidos: si la fila está vacía o no tiene equipos válidos
        if not celdas or all(not celda.strip() for celda in celdas):
            en_bloque_partidos = False
            continue
        # Solo procesar filas con equipos válidos (evitar filas de tabla de posiciones, etc)
        if len(celdas) >= 4:
            loc_txt = celdas[0]
            vis_txt = celdas[3]
            loc_norm = normalizar_equipo(loc_txt)
            vis_norm = normalizar_equipo(vis_txt)
            id_l = equipos_norm.get(loc_norm)
            id_v = equipos_norm.get(vis_norm)
            # Si no hay equipos válidos, terminar bloque de partidos
            # Asegurar que loc_norm y vis_norm no sean None antes de buscar 'LIBRE'
            loc_norm_str = loc_norm if loc_norm is not None else ""
            vis_norm_str = vis_norm if vis_norm is not None else ""
            if not (id_l or id_v or 'LIBRE' in loc_norm_str or 'LIBRE' in vis_norm_str):
                en_bloque_partidos = False
                continue
            dia_partido = dia_por_fecha.get(fecha_actual, None)
            if 'LIBRE' in loc_norm_str or 'LIBRE' in vis_norm_str:
                equipo_id = id_v if 'LIBRE' in loc_norm_str else id_l
                if equipo_id:
                    clave = (fecha_actual, equipo_id, None)
                    if clave not in partidos_vistos:
                        partidos_batch.append({
                            "categoria_id": cat_id, "fecha_id": fecha_actual,
                            "local_id": equipo_id, "visitante_id": None, "estado": "programado",
                            "dia": dia_partido
                        })
                        partidos_vistos.add(clave)
                continue
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

    if len(partidos_batch) == 66:
        print("\n✅ ¡LOGRADO! Se detectaron los 66 registros correctamente.")
        id_a_nombre = {v: k for k, v in MAPEO_CLUBES.items()}
        for p in partidos_batch:
            p["torneo_id"] = 1
            if p.get("local_id"):
                p["cancha"] = id_a_nombre.get(p["local_id"], "")
        supabase.table("partidos").upsert(partidos_batch).execute()
        print("🚀 Cargado con éxito.")
    else:
        print(f"\n⚠️ Se detectaron {len(partidos_batch)} partidos. No se sube nada. Deben ser exactamente 66.")

if __name__ == "__main__":
    # Si se llama sin argumentos, usa los valores por defecto
    if len(sys.argv) < 3:
        url = "https://www.ligaamateurdedeportes.com.ar/primera.html"
        cat_name = "primera"
        cargar_calendario_completo(url, cat_name)
    else:
        cargar_calendario_completo(sys.argv[1], sys.argv[2])