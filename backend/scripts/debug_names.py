import requests
from bs4 import BeautifulSoup
import re
import unicodedata

URL = "https://www.ligaamateurdedeportes.com.ar/alineaciones.html"

def normalizar(t):
    if not t: return ""
    t = unicodedata.normalize('NFD', t)
    t = ''.join(c for c in t if unicodedata.category(c) != 'Mn')
    return re.sub(r'\s+', ' ', t.replace(".", "").replace(",", "").strip().upper())

def limpiar(t):
    return t.replace('\xa0', ' ').replace('\n', ' ').strip() if t else ""

response = requests.get(URL, timeout=30)
response.encoding = 'utf-8'
soup = BeautifulSoup(response.text, 'html.parser')

# Find the first table with Juventud Unida vs Dep Gral Pinto
tablas = soup.find_all('table')
for tabla in tablas:
    txt = normalizar(tabla.get_text())
    if 'JUVENTUD UNIDA' in txt and 'DEP GRAL PINTO' in txt:
        print("=== FOUND TABLE ===")
        filas = tabla.find_all('tr')
        for i, fila in enumerate(filas[:20]):
            cells = fila.find_all('td')
            if len(cells) >= 2:
                c0 = limpiar(cells[0].get_text())
                c1 = limpiar(cells[1].get_text()) if len(cells) > 1 else ""
                c2 = limpiar(cells[2].get_text()) if len(cells) > 2 else ""
                c3 = limpiar(cells[3].get_text()) if len(cells) > 3 else ""
                c4 = limpiar(cells[4].get_text()) if len(cells) > 4 else ""
                print(f"Row {i}: |{c0[:15]}| |{c1[:20]}| |{c2[:10]}| |{c3[:15]}| |{c4[:20]}|")
        break