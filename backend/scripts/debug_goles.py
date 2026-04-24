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
        for i, fila in enumerate(filas[:40]):
            cells = fila.find_all('td')
            if len(cells) >= 2:
                vals = []
                for c in cells:
                    vals.append(limpiar(c.get_text())[:25])
                print(f"Row {i}: {vals}")
        break