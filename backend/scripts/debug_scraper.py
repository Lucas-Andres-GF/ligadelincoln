# -*- coding: utf-8 -*-
import requests
from bs4 import BeautifulSoup
import re

url = "https://www.ligaamateurdedeportes.com.ar/primera.html"
response = requests.get(url, timeout=30)
response.encoding = 'utf-8'
html = response.text

soup = BeautifulSoup(html, 'html.parser')

tablas = soup.find_all('table')
print(f"Total tablas: {len(tablas)}")

for i, tabla in enumerate(tablas[:3]):
    texto = tabla.get_text()[:200]
    print(f"\n--- Tabla {i} (primeros 200 chars) ---")
    print(texto)
    print("---")
