import os
import requests
from bs4 import BeautifulSoup
from supabase import create_client
from dotenv import load_dotenv
from mapeo import EQUIPOS_MAP

load_dotenv()
supabase = create_client(os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_KEY"))

NOMBRES_EXCLUIR = {'LOCAL', 'VISITANTE', 'OBSERVACIONES', 'EQUIPOS', ''}


def scrapear_fixture():
    url = "https://www.ligaamateurdedeportes.com.ar/primera.html"
    res = requests.get(url)
    soup = BeautifulSoup(res.content.decode('utf-8'), 'html.parser')

    tabla = soup.find('table', class_='excel1')
    filas = tabla.find_all('tr')

    # Recolectar partidos por fecha
    fixture_por_fecha = {}
    fecha_actual = None

    for fila in filas:
        celdas = fila.find_all('td')
        textos = [c.get_text(strip=True) for c in celdas]

        # Detectar fila "Fecha: N"
        if 'Fecha:' in textos:
            idx = textos.index('Fecha:')
            if idx + 1 < len(textos) and textos[idx + 1].isdigit():
                fecha_actual = int(textos[idx + 1])
            continue

        if not fecha_actual or len(textos) < 5:
            continue

        local_txt = textos[0].strip()
        visitante_txt = textos[3].strip() if len(textos) > 3 else ''

        # Filtrar filas que no son partidos
        if not local_txt or local_txt.upper() in NOMBRES_EXCLUIR:
            continue
        if not any(c.isalpha() for c in local_txt):
            continue
        if local_txt.upper() != local_txt:
            continue
        if len(local_txt) < 3:
            continue

        es_libre = 'LIBRE' in local_txt.upper()

        if es_libre:
            # LIBRE: el visitante queda libre
            equipo_libre = visitante_txt.upper()
            if equipo_libre not in EQUIPOS_MAP:
                continue
            partido = {
                'fecha': fecha_actual,
                'local_id': EQUIPOS_MAP[equipo_libre],
                'visitante_id': None,
                'goles_local': None,
                'goles_visitante': None,
                'observaciones': 'LIBRE',
            }
        else:
            local_upper = local_txt.upper()
            visitante_upper = visitante_txt.upper()
            if local_upper not in EQUIPOS_MAP or visitante_upper not in EQUIPOS_MAP:
                continue

            # Intentar leer goles (posiciones 1 y 2)
            goles_l = textos[1].strip() if len(textos) > 1 else ''
            goles_v = textos[2].strip() if len(textos) > 2 else ''
            gl = int(goles_l) if goles_l.isdigit() else None
            gv = int(goles_v) if goles_v.isdigit() else None

            obs = textos[4].strip() if len(textos) > 4 else None
            if obs == '' or obs == '\xa0':
                obs = None

            partido = {
                'fecha': fecha_actual,
                'local_id': EQUIPOS_MAP[local_upper],
                'visitante_id': EQUIPOS_MAP[visitante_upper],
                'goles_local': gl,
                'goles_visitante': gv,
                'observaciones': obs,
            }

        # Guardar solo la última aparición de cada fecha (la tabla real, no la preview)
        if fecha_actual not in fixture_por_fecha:
            fixture_por_fecha[fecha_actual] = []
        fixture_por_fecha[fecha_actual].append(partido)

    return fixture_por_fecha


def poblar_fixture():
    print("⏳ Scrapeando fixture...")
    fixture = scrapear_fixture()

    if not fixture:
        print("❌ No se encontraron datos del fixture.")
        return

    # Aplanar todos los partidos, pero para la fecha 1 que aparece duplicada,
    # tomar solo la segunda aparición (6 partidos por fecha)
    todos = []
    for fecha_num in sorted(fixture.keys()):
        partidos = fixture[fecha_num]
        # Cada fecha tiene 6 partidos (5 + 1 libre). Si hay duplicados, tomar los últimos 6
        if len(partidos) > 6:
            partidos = partidos[-6:]
        todos.extend(partidos)

    print(f"📊 Total de partidos a insertar: {len(todos)}")

    # Limpiar tabla e insertar
    try:
        # Borrar fixture existente
        supabase.table("fixture").delete().gte("id", 0).execute()
        print("🗑️  Fixture anterior eliminado.")
    except Exception:
        pass

    try:
        resultado = supabase.table("fixture").insert(todos).execute()
        print(f"✅ ¡Fixture cargado! ({len(resultado.data)} partidos)")

        for f in sorted(fixture.keys()):
            partidos_fecha = [p for p in resultado.data if p['fecha'] == f]
            print(f"\n  📅 Fecha {f}:")
            for p in partidos_fecha:
                local = next((k for k, v in EQUIPOS_MAP.items() if v == p['local_id']), '?')
                if p['observaciones'] == 'LIBRE':
                    print(f"     LIBRE: {local}")
                else:
                    visitante = next((k for k, v in EQUIPOS_MAP.items() if v == p['visitante_id']), '?')
                    gl = p['goles_local'] if p['goles_local'] is not None else '-'
                    gv = p['goles_visitante'] if p['goles_visitante'] is not None else '-'
                    print(f"     {local} {gl}-{gv} {visitante}")
    except Exception as e:
        print(f"❌ Error: {e}")


if __name__ == "__main__":
    poblar_fixture()
