import requests
from bs4 import BeautifulSoup

URL = "https://www.ligaamateurdedeportes.com.ar/alineaciones.html"
response = requests.get(URL, timeout=30)
response.encoding = 'utf-8'
soup = BeautifulSoup(response.text, 'html.parser')

# Save to file
with open('alineaciones_debug.html', 'w', encoding='utf-8') as f:
    f.write(response.text)

print("HTML saved to alineaciones_debug.html")

# Find the main table
tablas = soup.find_all('table')
print(f"Total tables: {len(tablas)}")

# For each table, print first few rows
for i, tabla in enumerate(tablas[:3]):
    print(f"\n=== TABLA {i} ===")
    filas = tabla.find_all('tr')[:5]
    for fila in filas:
        cells = fila.find_all('td')
        row_text = [c.get_text(strip=True)[:30] for c in cells]
        print(row_text)