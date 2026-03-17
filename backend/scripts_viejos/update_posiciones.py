import os
import requests
from bs4 import BeautifulSoup
from supabase import create_client
from dotenv import load_dotenv
from mapeo import EQUIPOS_MAP

load_dotenv()
supabase = create_client(os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_KEY"))

def _int_seguro(texto):
    """Convierte texto a int, devuelve 0 si está vacío o no es numérico."""
    texto = texto.strip()
    return int(texto) if texto.lstrip('-').isdigit() else 0

def actualizar_posiciones_desde_primera():
    url = "https://www.ligaamateurdedeportes.com.ar/primera.html"
    
    try:
        res = requests.get(url)
        contenido = res.content.decode('utf-8')
        soup = BeautifulSoup(contenido, 'html.parser')

        # Las clases CSS cambian cada vez que re-exportan el Excel.
        # Estrategia: buscar cualquier <td> con nombre de equipo conocido
        # y verificar que los 7 <td> siguientes sean numéricos (= fila de posiciones).
        # Solo tomamos la primera aparición de cada equipo (= tabla actual).
        nombres_validos = set(EQUIPOS_MAP.keys())

        datos_posiciones = []
        equipos_procesados = set()

        for celda in soup.find_all('td'):
            nombre = celda.get_text(strip=True).upper()
            if nombre not in nombres_validos or nombre in equipos_procesados:
                continue

            # Obtener los 7 <td> hermanos siguientes: Pts, J, G, E, P, Gf, Gc
            stats = []
            siguiente = celda.find_next_sibling('td')
            while siguiente and len(stats) < 7:
                stats.append(siguiente.get_text(strip=True))
                siguiente = siguiente.find_next_sibling('td')

            if len(stats) < 7:
                continue

            # Verificar que los 7 valores sean numéricos (descarta filas de fixture)
            if not all(s.lstrip('-').isdigit() for s in stats):
                continue

            id_db = EQUIPOS_MAP[nombre]
            pts = _int_seguro(stats[0])
            pj  = _int_seguro(stats[1])
            pg  = _int_seguro(stats[2])
            pe  = _int_seguro(stats[3])
            pp  = _int_seguro(stats[4])
            gf  = _int_seguro(stats[5])
            gc  = _int_seguro(stats[6])
            dif = gf - gc

            registro = {
                "equipo_id": id_db,
                "pts": pts,
                "j": pj,
                "g": pg,
                "e": pe,
                "p": pp,
                "gf": gf,
                "gc": gc,
                "dif": dif,
            }
            datos_posiciones.append(registro)
            equipos_procesados.add(nombre)

        if datos_posiciones:
            supabase.table("posiciones").upsert(datos_posiciones, on_conflict="equipo_id").execute()
            print(f"✅ ¡Tabla de posiciones actualizada! ({len(datos_posiciones)} equipos)")
            for d in datos_posiciones:
                nombre = next(k for k, v in EQUIPOS_MAP.items() if v == d["equipo_id"])
                print(f"   {nombre}: Pts={d['pts']} J={d['j']} G={d['g']} E={d['e']} P={d['p']} GF={d['gf']} GC={d['gc']}")
        else:
            print("ℹ️ La tabla de posiciones parece estar vacía (sin datos numéricos aún).")

    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    actualizar_posiciones_desde_primera()