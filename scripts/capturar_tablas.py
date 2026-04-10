#!/usr/bin/env python3
import os
import sys
import time
import subprocess
import signal
import argparse
import base64
import json
from playwright.sync_api import sync_playwright
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', 'backend', '.env'))

from supabase import create_client

supabase = create_client(os.environ.get('SUPABASE_URL'), os.environ.get('SUPABASE_KEY'))

OUTPUT_DIR = "/home/gallardo/Documentos/ligadelincoln/tablas-images"
FRONTEND_DIR = "/home/gallardo/Documentos/ligadelincoln/frontend"
ESCUDOS_FOLDER = "/home/gallardo/Documentos/ligadelincoln/frontend/public/escudos_hd"

CATEGORIAS = [
    (1, "primera", "PRIMERA DIVISIÓN"),
    (2, "septima", "SÉPTIMA DIVISIÓN"),
    (3, "octava", "OCTAVA DIVISIÓN"),
    (4, "novena", "NOVENA DIVISIÓN"),
    (5, "decima", "DÉCIMA DIVISIÓN"),
]

os.makedirs(OUTPUT_DIR, exist_ok=True)

def get_escudo_base64(filename):
    path = os.path.join(ESCUDOS_FOLDER, filename)
    if os.path.exists(path):
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode('utf-8')
    return ""

def get_escudo_filename(nombre_club):
    if not nombre_club:
        return "argentino.png"
    
    nombre = nombre_club.lower().strip()
    nombre_sin_espacios = nombre.replace(" ", "")
    
    mapa = {
        "argentino": "argentino.png",
        "atl.pasteur": "atl.pasteur.png",
        "atl pasteur": "atl.pasteur.png",
        "atl.roberts": "atl.roberts.png",
        "atl roberts": "atl.roberts.png",
        "ca.pintense": "ca.pintense.png",
        "c a pintense": "ca.pintense.png",
        "capintense": "ca.pintense.png",
        "pintense": "ca.pintense.png",
        "caset": "caset.png",
        "dep.arenaza": "dep.arenaza.png",
        "deparenaza": "dep.arenaza.png",
        "dep. gral pinto": "dep.pinto.png",
        "dep gral pinto": "dep.pinto.png",
        "depgralpinto": "dep.pinto.png",
        "el linqueño": "el.linqueño.png",
        "ellinqueño": "el.linqueño.png",
        "juventad-unida": "juventud.unida.png",
        "juventadunida": "juventud.unida.png",
        "juventud-unida": "juventud.unida.png",
        "juventudunida": "juventud.unida.png",
        "juventudunida": "juventud.unida.png",
        "sanmartin": "san.martin.png",
        "san martin": "san.martin.png",
        "villafricia": "villa.francia.png",
        "villa francia": "villa.francia.png",
        "cael": "el.linqueño.png",
    }
    
    if nombre in mapa:
        return mapa[nombre]
    if nombre_sin_espacios in mapa:
        return mapa[nombre_sin_espacios]
    return mapa.get(nombre, "argentino.png")

def get_fecha_actual():
    response = supabase.from_("partidos").select("fecha_id").eq("estado", "jugado").order("fecha_id", desc=True).limit(1).execute()
    if response.data:
        return response.data[0].get('fecha_id', 1)
    return 1

def get_posiciones(categoria_id):
    response = supabase.from_("posiciones").select(
        "pts, pj, pg, pe, pp, gf, gc, dif, ultimos_5, clubes(nombre)"
    ).eq("categoria_id", categoria_id).order("pts", desc=True).order("dif", desc=True).execute()
    return response.data or []

def generar_tabla_html(posiciones):
    rows = ""
    for i, pos in enumerate(posiciones, 1):
        club = pos.get('clubes', {})
        club_nombre = club.get('nombre', 'Club') if isinstance(club, dict) else 'Club'
        escudo_file = get_escudo_filename(club_nombre)
        escudo_b64 = get_escudo_base64(escudo_file)
        
        ultimos = pos.get('ultimos_5', [])
        if isinstance(ultimos, str):
            try:
                ultimos = json.loads(ultimos)
            except:
                ultimos = []
        
        ultimos_html = ""
        for r in ultimos:
            ultimos_html += f'<span class="{r}">{r}</span>'
        
        rows += f"""
        <tr>
            <td class="pos">{i}</td>
            <td class="club-cell">
                <img class="club-escudo" src="data:image/png;base64,{escudo_b64}">
                <span>{club_nombre}</span>
            </td>
            <td class="pts">{pos.get('pts', 0)}</td>
            <td class="stat">{pos.get('pj', 0)}</td>
            <td class="stat">{pos.get('pg', 0)}</td>
            <td class="stat">{pos.get('pe', 0)}</td>
            <td class="stat">{pos.get('pp', 0)}</td>
            <td class="stat">{pos.get('gf', 0)}</td>
            <td class="stat">{pos.get('gc', 0)}</td>
            <td class="stat">{pos.get('dif', 0)}</td>
            <td class="ultimos5">{ultimos_html}</td>
        </tr>
        """
    
    return f"""
    <table class="standings-table">
        <thead>
            <tr>
                <th>Pos</th>
                <th>Club</th>
                <th>PTS</th>
                <th>PJ</th>
                <th>PG</th>
                <th>PE</th>
                <th>PP</th>
                <th>GF</th>
                <th>GC</th>
                <th>DIF</th>
                <th>Últ. 5</th>
            </tr>
        </thead>
        <tbody>
            {rows}
        </tbody>
    </table>
    """

PORTADA_GENERAL_HTML = """
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap');
        
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        
        body {{
            width: 1080px; height: 1080px;
            background: linear-gradient(180deg, #0f2d0f 0%, #143814 50%, #0f2d0f 100%);
            font-family: 'Inter', sans-serif;
            color: white;
            display: flex;
            flex-direction: column;
            justify-content: center;
            align-items: center;
        }}
        
        .header {{
            background: linear-gradient(135deg, #143814 0%, #1a4a1a 100%);
            padding: 30px 40px;
            border-bottom: 2px solid rgba(34, 197, 94, 0.3);
            display: flex;
            align-items: center;
            justify-content: space-between;
            width: 100%;
            position: absolute;
            top: 0;
        }}
        
        .liga-text {{
            font-size: 24px;
            font-weight: 800;
            letter-spacing: 2px;
            text-transform: uppercase;
            background: linear-gradient(90deg, #22c55e, #4ade80);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }}
        
        .main-content {{
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            flex: 1;
        }}
        
        .titulo-principal {{
            font-size: 90px;
            font-weight: 900;
            text-transform: uppercase;
            letter-spacing: 8px;
            margin-bottom: 30px;
            text-align: center;
            background: linear-gradient(90deg, #22c55e, #4ade80);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }}
        
        .fecha-badge {{
            background: rgba(34, 197, 94, 0.15);
            border: 2px solid rgba(34, 197, 94, 0.5);
            padding: 20px 60px;
            border-radius: 16px;
            font-size: 48px;
            font-weight: 800;
            color: #22c55e;
            letter-spacing: 6px;
            margin-bottom: 30px;
        }}
        
        .torneo-badge {{
            background: rgba(34, 197, 94, 0.1);
            border: 1px solid rgba(34, 197, 94, 0.3);
            padding: 12px 36px;
            border-radius: 8px;
            font-size: 24px;
            font-weight: 600;
            color: #22c55e;
            letter-spacing: 2px;
        }}
        
        .footer {{
            padding: 30px 40px;
            text-align: center;
            border-top: 1px solid rgba(34, 197, 94, 0.15);
            width: 100%;
            position: absolute;
            bottom: 0;
        }}
        
        .footer-text {{
            font-size: 18px;
            color: rgba(255, 255, 255, 0.5);
            font-weight: 400;
        }}
        
        .footer-link {{
            color: #22c55e;
            font-weight: 600;
            text-decoration: none;
        }}
        
        .gradient-bar {{
            position: absolute;
            bottom: 0;
            left: 0;
            right: 0;
            height: 6px;
            background: linear-gradient(90deg, #22c55e, #4ade80, #22c55e);
        }}
    </style>
</head>
<body>
    <div class="header">
        <div class="liga-text">Liga De Lincoln</div>
    </div>
    
    <div class="main-content">
        <div class="titulo-principal">Tabla de Posiciones</div>
        <div class="fecha-badge">FECHA {fecha_num}</div>
        <div class="torneo-badge">TORNEO APERTURA 2026</div>
    </div>
    
    <div class="footer">
        <div class="footer-text">
            Seguí toda la info en <span class="footer-link">ligadelincoln.com</span>
        </div>
    </div>
    
    <div class="gradient-bar"></div>
</body>
</html>
"""

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap');
        
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        
        body {{
            width: 1080px;
            height: 1080px;
            background: linear-gradient(180deg, #0f2d0f 0%, #143814 50%, #0f2d0f 100%);
            font-family: 'Inter', sans-serif;
            color: white;
            display: flex;
            flex-direction: column;
        }}
        
        .header {{
            background: linear-gradient(135deg, #143814 0%, #1a4a1a 100%);
            padding: 30px 40px;
            border-bottom: 2px solid rgba(34, 197, 94, 0.3);
            display: flex;
            align-items: center;
            justify-content: space-between;
        }}
        
        .liga-text {{
            font-size: 24px;
            font-weight: 800;
            letter-spacing: 2px;
            text-transform: uppercase;
            background: linear-gradient(90deg, #22c55e, #4ade80);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }}
        
        .categoria-badge {{
            background: rgba(34, 197, 94, 0.15);
            border: 1px solid rgba(34, 197, 94, 0.4);
            padding: 10px 24px;
            border-radius: 8px;
            font-size: 20px;
            font-weight: 700;
            color: #22c55e;
            text-transform: uppercase;
            letter-spacing: 3px;
        }}
        
        .main-content {{
            flex: 1;
            display: flex;
            justify-content: center;
            align-items: flex-start;
            padding: 40px;
        }}
        
        .table-container {{
            background: #143814;
            border-radius: 16px;
            border: 1px solid rgba(34, 197, 94, 0.3);
            overflow: hidden;
            width: 100%;
            max-width: 800px;
            margin: 0 auto;
        }}
        
        .footer {{
            padding: 30px 40px;
            text-align: center;
            border-top: 1px solid rgba(34, 197, 94, 0.15);
        }}
        
        .footer-text {{
            font-size: 18px;
            color: rgba(255, 255, 255, 0.5);
            font-weight: 400;
        }}
        
        .footer-link {{
            color: #22c55e;
            font-weight: 600;
            text-decoration: none;
        }}
        
        .gradient-bar {{
            position: absolute;
            bottom: 0;
            left: 0;
            right: 0;
            height: 6px;
            background: linear-gradient(90deg, #22c55e, #4ade80, #22c55e);
        }}
        
        body {{ position: relative; }}
        
        .standings-table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 14px;
        }}
        
        .standings-table th {{
            background: linear-gradient(135deg, #1a4a1a 0%, #143814 100%);
            padding: 18px 12px;
            text-align: left;
            color: rgba(34, 197, 94, 0.7);
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 1px;
            font-size: 12px;
            border-bottom: 2px solid rgba(34, 197, 94, 0.3);
            vertical-align: middle;
        }}
        
        .standings-table td {{
            padding: 12px;
            border-bottom: 1px solid rgba(34, 197, 94, 0.1);
            color: white;
            vertical-align: middle;
        }}
        
        .standings-table tr:nth-child(even) {{
            background: rgba(34, 197, 94, 0.05);
        }}
        
        .standings-table tr:hover {{
            background: rgba(34, 197, 94, 0.1);
        }}
        
        .club-cell {{
            display: flex;
            align-items: center;
            gap: 10px;
            font-weight: 600;
            color: white;
            height: 100%;
        }}
        
        .club-escudo {{
            width: 28px;
            height: 28px;
            object-fit: contain;
            flex-shrink: 0;
        }}
        
        .pos {{
            color: rgba(34, 197, 94, 0.6);
            font-weight: 600;
            font-size: 14px;
            width: 30px;
        }}
        
        .pts {{
            font-weight: 900;
            color: #22c55e;
            font-size: 18px;
            text-align: center;
        }}
        
        .stat {{
            color: rgba(255, 255, 255, 0.7);
            font-size: 13px;
            text-align: center;
        }}
        
        .ultimos5 {{
            display: flex;
            gap: 4px;
            justify-content: center;
        }}
        
        .ultimos5 span {{
            width: 24px;
            height: 24px;
            display: flex;
            align-items: center;
            justify-content: center;
            border-radius: 6px;
            font-size: 12px;
            font-weight: bold;
        }}
        
        .ultimos5 .G {{
            background: rgba(34, 197, 94, 0.25);
            color: #22c55e;
            border: 1px solid #22c55e;
        }}
        
        .ultimos5 .P {{
            background: rgba(239, 68, 68, 0.25);
            color: #ef4444;
            border: 1px solid #ef4444;
        }}
        
        .ultimos5 .E {{
            background: rgba(234, 179, 8, 0.25);
            color: #eab308;
            border: 1px solid #eab308;
        }}
    </style>
</head>
<body>
    <div class="header">
        <div class="liga-text">Liga De Lincoln</div>
        <div class="categoria-badge">{categoria_nombre}</div>
    </div>
    
    <div class="main-content">
        <div class="table-container">
            {tabla_html}
        </div>
    </div>
    
    <div class="footer">
        <div class="footer-text">
            Seguí toda la info en <span class="footer-link">ligadelincoln.com</span>
        </div>
    </div>
    
    <div class="gradient-bar"></div>
</body>
</html>
"""

def capturar_tablas(fecha_num=None):
    print("🚀 Iniciando frontend...")
    
    proc = subprocess.Popen(
        ["npm", "run", "dev", "--", "--host"],
        cwd=FRONTEND_DIR,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        preexec_fn=os.setsid
    )
    
    print("⏳ Esperando que el frontend esté listo...")
    time.sleep(15)
    
    if fecha_num is None:
        fecha_num = get_fecha_actual()
        print(f"📅 Fecha última jugado: {fecha_num}")
    else:
        print(f"📅 Fecha proporcionada: {fecha_num}")
    
    print("🚀 Generando imágenes...")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        
        # Generar portada general
        print(f"📸 Generando portada general Fecha {fecha_num}...")
        try:
            html_content = PORTADA_GENERAL_HTML.format(fecha_num=fecha_num)
            
            page = browser.new_page(viewport={"width": 1080, "height": 1080})
            page.set_content(html_content)
            time.sleep(1)
            
            output_path = os.path.join(OUTPUT_DIR, f"portada_tabla_posiciones.png")
            page.screenshot(path=output_path)
            page.close()
            
            print(f"   ✅ Portada general: {output_path}")
        except Exception as e:
            print(f"   ❌ Error portada general: {e}")
        
        for cat_id, cat_slug, cat_nombre in CATEGORIAS:
            print(f"📸 Generando tabla {cat_nombre}...")
            try:
                posiciones = get_posiciones(cat_id)
                tabla_html = generar_tabla_html(posiciones)
                
                html_content = HTML_TEMPLATE.format(
                    categoria_nombre=cat_nombre,
                    tabla_html=tabla_html
                )
                
                page = browser.new_page(viewport={"width": 1080, "height": 1080})
                page.set_content(html_content)
                time.sleep(1)
                
                output_path = os.path.join(OUTPUT_DIR, f"posiciones_{cat_slug}.png")
                page.screenshot(path=output_path)
                page.close()
                
                print(f"   ✅ Tabla: {output_path}")
                
            except Exception as e:
                print(f"   ❌ Error tabla: {e}")
        
        browser.close()
    
    os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
    
    total = 1 + len(CATEGORIAS)
    print(f"\n🎉 Listo! {total} imágenes generadas en {OUTPUT_DIR}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Generar imágenes de tablas de posiciones')
    parser.add_argument('--fecha', type=int, default=None, help='Número de fecha (opcional)')
    args = parser.parse_args()
    
    capturar_tablas(fecha_num=args.fecha)