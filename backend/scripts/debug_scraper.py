import requests
from bs4 import BeautifulSoup
import re
import unicodedata
import os
from dotenv import load_dotenv
load_dotenv()
from supabase import create_client
supabase = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])

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

MAPEO_CLUBES = {
    "ARGENTINO": 1, "ATL. PASTEUR": 2, "ATL PASTEUR": 2,
    "ATL. ROBERTS": 3, "ATL ROBERTS": 3,
    "CA. PINTENSE": 4, "C A PINTENSE": 4,
    "CASET": 5,
    "DEP. ARENAZA": 6, "DEP ARENAZA": 6,
    "DEP. GRAL PINTO": 7, "DEP GRAL PINTO": 7,
    "EL LINQUEÑO": 8, "EL LINQUENO": 8,
    "JUVENTUD UNIDA": 9,
    "SAN MARTIN": 10,
    "VILLA FRANCIA": 11,
}

response = requests.get(URL, timeout=30)
response.encoding = 'utf-8'
soup = BeautifulSoup(response.text, 'html.parser')

tablas = soup.find_all('table')
equipos_norm = {normalizar(k): v for k, v in MAPEO_CLUBES.items()}

print("=== ANALIZANDO TODAS LAS TABLAS ===\n")

for idx, tabla in enumerate(tablas):
    print(f"--- TABLA {idx+1} ---")
    filas = tabla.find_all('tr')
    
    # Buscar fila con equipos
    for f_idx, f in enumerate(filas[:10]):
        cells = f.find_all('td')
        if len(cells) >= 4:
            c0 = limpiar(cells[0].get_text())
            c3 = limpiar(cells[3].get_text())
            print(f"  Fila {f_idx}: '{c0[:25]}' vs '{c3[:25]}'")
    
    # Buscar equipos_fila
    equipos_fila = None
    for f in filas[:8]:
        cells = f.find_all('td')
        if len(cells) >= 4:
            texto = ' '.join([limpiar(c.get_text()) for c in cells])
            if 'PRIMER TIEMPO' in texto.upper():
                equipos_fila = f
                print(f"  -> Equipos encontrados en fila con 'PRIMER TIEMPO'")
                break
    
    if not equipos_fila:
        print(f"  -> NO HAY FILA CON 'PRIMER TIEMPO'\n")
        continue
        
    cells = equipos_fila.find_all('td')
    if len(cells) < 4:
        print(f"  -> MENOS DE 4 CELDAS\n")
        continue
    
    eq_local = normalizar(limpiar(cells[0].get_text()))
    eq_visita = normalizar(limpiar(cells[3].get_text()))
    print(f"  eq_local: '{eq_local}'")
    print(f"  eq_visita: '{eq_visita}'\n")