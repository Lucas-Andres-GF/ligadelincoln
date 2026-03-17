import requests
from bs4 import BeautifulSoup

# Tu mapeo oficial
MAPEO_CLUBES = {
    "ARGENTINO": 1, "ATL PASTEUR": 2, "ATL ROBERTS": 3,
    "C A PINTENSE": 4, "CASET": 5, "DEP ARENAZA": 6,
    "DEP GRAL PINTO": 7, "EL LINQUEÑO": 8, "JUVENTUD UNIDA": 9,
    "SAN MARTIN": 10, "VILLA FRANCIA": 11
}

def limpiar_texto(txt):
    return txt.get_text(strip=True).replace('\xa0', ' ')

def scrapear_primera_v3():
    url = "https://www.ligaamateurdedeportes.com.ar/octava.html"
    response = requests.get(url)
    response.encoding = 'utf-8'
    soup = BeautifulSoup(response.text, 'html.parser')

    posiciones_finales = {}
    partidos_finales = []
    
    filas = soup.find_all('tr')

    for fila in filas:
        celdas = fila.find_all('td')
        textos = [limpiar_texto(c).upper() for c in celdas]
        
        # --- LÓGICA PARA POSICIONES ---
        # Buscamos en cada celda de la fila si aparece un nombre de club
        for i, texto in enumerate(textos):
            if texto in MAPEO_CLUBES:
                # Una vez que encontramos el nombre, los puntos están en la siguiente celda
                # Verificamos que haya suficientes celdas después del nombre
                if i + 1 < len(textos):
                    pts_txt = textos[i+1]
                    if pts_txt.isdigit():
                        posiciones_finales[texto] = {
                            "club_id": MAPEO_CLUBES[texto],
                            "pts": int(pts_txt),
                            "pj": int(textos[i+2]) if i+2 < len(textos) else 0,
                            "pg": int(textos[i+3]) if i+3 < len(textos) else 0,
                            "pe": int(textos[i+4]) if i+4 < len(textos) else 0,
                            "pp": int(textos[i+5]) if i+5 < len(textos) else 0,
                            "gf": int(textos[i+6]) if i+6 < len(textos) else 0,
                            "gc": int(textos[i+7]) if i+7 < len(textos) else 0,
                        }

        # --- LÓGICA PARA FIXTURE (Sencilla) ---
        if len(textos) >= 4:
            loc = textos[0]
            vis = textos[3] if len(textos) > 3 else ""
            # Si la primera celda es "PRIMERA DIVISIÓN", el local está en la celda index 6
            # (ajuste por el rowspan del HTML)
            if "PRIMERA" in loc and len(textos) > 6:
                loc = textos[6]
                
            if (loc in MAPEO_CLUBES or "LIBRE" in loc) and (vis in MAPEO_CLUBES or "LIBRE" in vis):
                if loc != vis:
                    partidos_finales.append({"local": loc, "visitante": vis})

    return partidos_finales, posiciones_finales


partidos, posiciones = scrapear_primera_v3()

print(f"--- TABLA DE POSICIONES (Clubes detectados: {len(posiciones)}) ---")
# Ordenar por ID para verificar
for club_id in sorted([p['club_id'] for p in posiciones.values()]):
    nombre = [n for n, id in MAPEO_CLUBES.items() if id == club_id][0]
    datos = posiciones[nombre]
    print(f"ID: {datos['club_id']} | {nombre.ljust(15)} | Pts: {datos['pts']}")