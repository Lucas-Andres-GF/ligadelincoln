import requests
from bs4 import BeautifulSoup

# Textos que NO son equipos pero aparecen en celdas similares
EXCLUIR = {
    'local', 'visitante', 'observaciones', 'equipos', 'pts', 'libre:',
    'fecha:', 'día:', 'primera división', 'primera division',
    'www.ligaamateurdedeportes.com.ar', 'torneo apertura',
    'últimos encuentros', 'fixture completo', 'tablas y resultados',
    'próxima:', 'segunda fecha',
}

def es_nombre_equipo(texto):
    """Detecta si un texto parece nombre de equipo (mayúsculas, no número, no header)."""
    if not texto or len(texto) < 3:
        return False
    if texto.lower() in EXCLUIR:
        return False
    if any(excl in texto.lower() for excl in EXCLUIR):
        return False
    # Debe tener letras y estar en mayúsculas
    if not any(c.isalpha() for c in texto):
        return False
    if texto != texto.upper():
        return False
    # No puede ser solo números
    if texto.replace(' ', '').isdigit():
        return False
    return True

def scrapear_equipos_del_fixture():
    url = "https://www.ligaamateurdedeportes.com.ar/primera.html"
    
    try:
        respuesta = requests.get(url)
        
        contenido_decodificado = respuesta.content.decode('utf-8')
        
        soup = BeautifulSoup(contenido_decodificado, 'html.parser')
        
        nombres_vistos = set()
        
        for celda in soup.find_all('td'):
            texto = celda.get_text().strip()
            if es_nombre_equipo(texto):
                # Convertimos a Título (Ej: EL LINQUEÑO -> El Linqueño)
                nombre_lindo = texto.title()
                
                # Ajustes estéticos
                nombre_lindo = nombre_lindo.replace("Atl ", "Atl. ")
                nombre_lindo = nombre_lindo.replace("Dep ", "Dep. ")
                nombre_lindo = nombre_lindo.replace("C A ", "CA. ")
                
                nombres_vistos.add(nombre_lindo)
        return sorted(list(nombres_vistos))
    
    except Exception as e:
        print(f"Error crítico de codificación: {e}")
        return []

if __name__ == "__main__":
    clubes = scrapear_equipos_del_fixture()
    print(f"✅ Lista procesada ({len(clubes)} equipos):")
    for c in clubes:
        print(f" - {c}")