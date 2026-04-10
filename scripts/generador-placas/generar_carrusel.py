#!/usr/bin/env python3
"""
Genera carrusel de Instagram/Facebook para una categoría y fecha.
Orden: Portada → Resultados → Libres
Usage: python3 generar_carrusel.py <categoria> <fecha_id>
Categorías: 1=primera, 2=septima, 3=octava, 4=novena, 5=decima
"""
import os
import sys
from PIL import Image

OUTPUT_HOST = "/home/gallardo/Documentos/ligadelincoln/placares_generados"

MAPEO_CATEGORIAS = {
    1: "primera",
    2: "septima",
    3: "octava",
    4: "novena",
    5: "decima"
}

MAPEO_CATEGORIAS_INV = {
    "primera": 1,
    "septima": 2,
    "octava": 3,
    "novena": 4,
    "decima": 5
}

def obtener_nombre_categoria(categoria_id):
    nombres = {
        1: "PRIMERA",
        2: "SÉPTIMA",
        3: "OCTAVA",
        4: "NOVENA",
        5: "DÉCIMA"
    }
    return nombres.get(categoria_id, "CATEGORÍA")

def obtener_carrusel(categoria, fecha_id):
    fecha_folder = f"fecha_{fecha_id}"
    target_dir = os.path.join(OUTPUT_HOST, categoria, fecha_folder)
    
    if not os.path.exists(target_dir):
        print(f"❌ Carpeta no existe: {target_dir}")
        return []
    
    archivos = sorted(os.listdir(target_dir))
    
    imagenes = []
    
    # 1. Portada (primera)
    cat_id = MAPEO_CATEGORIAS_INV.get(categoria, 1)
    cat_nombre = obtener_nombre_categoria(cat_id).lower()
    portada = [f for f in archivos if f.startswith(f"portada_{cat_nombre}_fecha")]
    imagenes.extend(portada)
    
    # 2. Resultados (resultado_*.png pero no libres)
    resultados = [f for f in archivos if f.startswith("resultado_")]
    imagenes.extend(resultados)
    
    # 3. Libres (libre_*.png)
    libres = [f for f in archivos if f.startswith("libre_")]
    imagenes.extend(libres)
    
    return imagenes

def generar_carrusel(categoria, fecha_id):
    fecha_folder = f"fecha_{fecha_id}"
    target_dir = os.path.join(OUTPUT_HOST, categoria, fecha_folder)
    
    imagenes = obtener_carrusel(categoria, fecha_id)
    
    if not imagenes:
        print(f"⚠️  No hay imágenes en {target_dir}")
        return
    
    print(f"📊 {len(imagenes)} imágenes para carrusel")
    
    # Cargar imágenes
    pil_images = []
    for img_name in imagenes:
        img_path = os.path.join(target_dir, img_name)
        try:
            img = Image.open(img_path)
            pil_images.append(img)
            print(f"   ✅ {img_name}")
        except Exception as e:
            print(f"   ❌ Error cargando {img_name}: {e}")
    
    if not pil_images:
        print("❌ No se pudieron cargar imágenes")
        return
    
    # Crear carrusel vertical
    ancho = pil_images[0].width
    alto_total = sum(img.height for img in pil_images)
    
    carrusel = Image.new('RGB', (ancho, alto_total))
    
    y_offset = 0
    for img in pil_images:
        carrusel.paste(img, (0, y_offset))
        y_offset += img.height
    
    # Guardar
    cat_nombre = obtener_nombre_categoria(MAPEO_CATEGORIAS_INV.get(categoria, 1))
    output_name = f"carrusel_{categoria}_fecha_{fecha_id}.png"
    output_path = os.path.join(target_dir, output_name)
    carrusel.save(output_path)
    
    print(f"\n✅ Carrusel guardado: {output_path}")
    print(f"   Dimensiones: {ancho}x{alto_total} px")

def main():
    if len(sys.argv) < 3:
        print("Usage: python3 generar_carrusel.py <categoria> <fecha_id>")
        print("Categorías: primera, septima, octava, novena, decima")
        sys.exit(1)
    
    categoria = sys.argv[1].lower()
    fecha_id = sys.argv[2]
    
    if categoria not in MAPEO_CATEGORIAS_INV:
        print(f"❌ Categoría inválida: {categoria}")
        sys.exit(1)
    
    print(f"🎨 Generando carrusel: {categoria.upper()} - Fecha {fecha_id}")
    generar_carrusel(categoria, fecha_id)

if __name__ == "__main__":
    main()