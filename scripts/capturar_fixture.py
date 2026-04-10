#!/usr/bin/env python3
import os
import sys
import time
import subprocess
import signal
import argparse
import base64
from playwright.sync_api import sync_playwright
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', 'backend', '.env'))

from supabase import create_client

supabase = create_client(os.environ.get('SUPABASE_URL'), os.environ.get('SUPABASE_KEY'))

OUTPUT_DIR = "/home/gallardo/Documentos/ligadelincoln/tablas-images"
FRONTEND_DIR = "/home/gallardo/Documentos/ligadelincoln/frontend"
ESCUDOS_FOLDER = "/home/gallardo/Documentos/ligadelincoln/frontend/public/escudos_hd"

from datetime import datetime

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

def get_fixture_dia(categoria_id, fecha_num):
    response = supabase.from_("partidos").select("dia").eq("categoria_id", categoria_id).eq("fecha_id", fecha_num).not_.is_("dia", "null").limit(1).execute()
    if response.data and response.data[0].get('dia'):
        return response.data[0]['dia']
    return None

def get_fixture(categoria_id, fecha_num):
    response = supabase.from_("partidos").select(
        "local_id, visitante_id, hora, estado, dia"
    ).eq("categoria_id", categoria_id).eq("fecha_id", fecha_num).not_.is_("local_id", "null").execute()
    
    if not response.data:
        return [], None
    
    # Buscar cualquier partido con día no nulo
    dia = None
    for p in response.data:
        if p.get('dia'):
            dia = p['dia']
            break
    
    local_ids = []
    for p in response.data:
        if p['local_id']:
            local_ids.append(p['local_id'])
        if p['visitante_id']:
            local_ids.append(p['visitante_id'])
    
    local_ids = list(set(local_ids))
    
    equipos_response = supabase.from_("clubes").select("id, nombre").in_("id", local_ids).execute()
    equipos_dict = {e['id']: e['nombre'] for e in equipos_response.data}
    
    partidos = []
    for p in response.data:
        if not p['local_id']:
            continue
            
        local_id = p['local_id']
        visitante_id = p.get('visitante_id')
        hora = p.get('hora', '')
        if hora:
            # Si termina en :00, quitar los segundos (últimos 3 caracteres)
            if hora.endswith(':00'):
                hora = hora[:-3]
        else:
            hora = '-'
        
        if p.get('dia'):
            dia = p['dia']
        else:
            dia = None
        
        if not dia and hora == '-':
            mostrar_fecha = False
        else:
            mostrar_fecha = True
        
        estado = p.get('estado', 'programado')
        
        if not visitante_id:
            partidos.append({
                'local': equipos_dict.get(local_id, 'Local'),
                'visitante': 'LIBRE',
                'hora': hora,
                'dia': dia,
                'mostrar_fecha': mostrar_fecha,
                'estado': estado
            })
        else:
            partidos.append({
                'local': equipos_dict.get(local_id, 'Local'),
                'visitante': equipos_dict.get(visitante_id, 'Visitante'),
                'hora': hora,
                'dia': dia,
                'mostrar_fecha': mostrar_fecha,
                'estado': estado
            })
    
    return partidos, dia

def generar_fixture_html(partidos, categoria_nombre, fecha_num, dia=None):
    if not partidos:
        return ""
    
    normales = [p for p in partidos if p['visitante'] != 'LIBRE']
    libres = [p for p in partidos if p['visitante'] == 'LIBRE']
    
    rows = ""
    
    for p in normales:
        escudo_local = get_escudo_filename(p['local'])
        escudo_visita = get_escudo_filename(p['visitante'])
        escudo_local_b64 = get_escudo_base64(escudo_local)
        escudo_visita_b64 = get_escudo_base64(escudo_visita)
        
        fecha_html = ""
        if p.get('mostrar_fecha') and p.get('dia'):
            fecha_obj = datetime.strptime(p['dia'], "%Y-%m-%d")
            dias = ['LUN', 'MAR', 'MIÉ', 'JUE', 'VIE', 'SÁB', 'DOM']
            fecha_html = f"{dias[fecha_obj.weekday()]} {fecha_obj.day}"
        
        rows += f"""
        <div class="partido">
            <div class="equipo local">
                <img class="escudo" src="data:image/png;base64,{escudo_local_b64}">
                <span class="nombre">{p['local']}</span>
            </div>
            <div class="vs">VS</div>
            <div class="equipo visitante">
                <span class="nombre">{p['visitante']}</span>
                <img class="escudo" src="data:image/png;base64,{escudo_visita_b64}">
            </div>
            <div class="datetime">
                {fecha_html if fecha_html else ''}
                <span class="hora">{p['hora']}</span>
            </div>
        </div>
        """
    
    for p in libres:
        escudo_local = get_escudo_filename(p['local'])
        escudo_local_b64 = get_escudo_base64(escudo_local)
        
        fecha_html = ""
        if p.get('mostrar_fecha') and p.get('dia'):
            fecha_obj = datetime.strptime(p['dia'], "%Y-%m-%d")
            dias = ['LUN', 'MAR', 'MIÉ', 'JUE', 'VIE', 'SÁB', 'DOM']
            fecha_html = f"{dias[fecha_obj.weekday()]} {fecha_obj.day}"
        
        rows += f"""
        <div class="partido libre">
            <div class="equipo-center">
                <img class="escudo" src="data:image/png;base64,{escudo_local_b64}">
                <span class="nombre">{p['local']}</span>
                <span class="libre-text">LIBRE</span>
            </div>
            <div class="datetime">
                {fecha_html if fecha_html else ''}
                <span class="hora">{p['hora']}</span>
            </div>
        </div>
        """
    
    return f"""
    <div class="fixture-container">
        {rows}
    </div>
    """

PORTADA_FIXTURE_HTML = """
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
        <div class="titulo-principal">Fixture</div>
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
        
        .fixture-container {{
            width: 100%;
            max-width: 900px;
            display: flex;
            flex-direction: column;
            gap: 12px;
        }}
        
        .fecha-info {{
            background: linear-gradient(135deg, #1a4a1a 0%, #143814 100%);
            padding: 16px 24px;
            border-radius: 12px;
            border: 1px solid rgba(34, 197, 94, 0.3);
            text-align: center;
            margin-bottom: 20px;
            font-size: 20px;
            font-weight: 700;
            color: #22c55e;
            letter-spacing: 2px;
        }}
        
        .partido {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            background: rgba(20, 56, 20, 0.6);
            border: 1px solid rgba(34, 197, 94, 0.2);
            border-radius: 12px;
            padding: 16px 24px;
        }}
        
        .partido.libre {{
            background: rgba(34, 197, 94, 0.05);
        }}
        
        .equipo-center {{
            display: flex;
            align-items: center;
            gap: 12px;
            justify-content: center;
            flex: 1;
        }}
        
        .libre-text {{
            background: rgba(34, 197, 94, 0.2);
            border: 1px solid #22c55e;
            padding: 4px 12px;
            border-radius: 6px;
            font-size: 12px;
            font-weight: 700;
            color: #22c55e;
            text-transform: uppercase;
            letter-spacing: 1px;
        }}
        
        .equipo {{
            display: flex;
            align-items: center;
            gap: 12px;
            flex: 1;
        }}
        
        .equipo.local {{
            justify-content: flex-end;
        }}
        
        .equipo.visitante {{
            justify-content: flex-start;
        }}
        
        .escudo {{
            width: 48px;
            height: 48px;
            object-fit: contain;
        }}
        
        .nombre {{
            font-size: 18px;
            font-weight: 700;
            color: white;
            white-space: nowrap;
        }}
        
        .vs {{
            font-size: 20px;
            font-weight: 900;
            color: #22c55e;
            margin: 0 20px;
        }}
        
        .hora {{
            font-size: 14px;
            color: rgba(255, 255, 255, 0.5);
            width: 60px;
            text-align: center;
        }}
        
        .datetime {{
            display: flex;
            flex-direction: column;
            align-items: flex-end;
            gap: 2px;
            min-width: 80px;
        }}
        
        .datetime .dia {{
            font-size: 10px;
            color: #22c55e;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 1px;
        }}
        
        .datetime .hora {{
            font-size: 14px;
            color: rgba(255, 255, 255, 0.7);
        }}
        
        .libre-badge {{
            background: rgba(34, 197, 94, 0.2);
            border: 1px solid #22c55e;
            padding: 8px 24px;
            border-radius: 8px;
            font-size: 14px;
            font-weight: 700;
            color: #22c55e;
            text-transform: uppercase;
            letter-spacing: 2px;
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
    </style>
</head>
<body>
    <div class="header">
        <div class="liga-text">Liga De Lincoln</div>
        <div class="categoria-badge">{categoria_nombre}</div>
    </div>
    
    <div class="main-content">
        <div class="fixture-container">
            {fixture_html}
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

def capturar_fixture(fecha_num, categorias=None):
    if categorias is None:
        categorias = CATEGORIAS
    
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
    
    print(f"📅 Generando fixture Fecha {fecha_num}...")
    
    total_generados = 0
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        
        # Generar portada general
        print(f"📸 Generando portada general Fixture Fecha {fecha_num}...")
        try:
            html_content = PORTADA_FIXTURE_HTML.format(fecha_num=fecha_num)
            
            page = browser.new_page(viewport={"width": 1080, "height": 1080})
            page.set_content(html_content)
            time.sleep(1)
            
            output_path = os.path.join(OUTPUT_DIR, f"portada_fixture.png")
            page.screenshot(path=output_path)
            page.close()
            
            print(f"   ✅ Portada: {output_path}")
            total_generados += 1
        except Exception as e:
            print(f"   ❌ Error portada: {e}")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        
        for cat_id, cat_slug, cat_nombre in categorias:
            print(f"📸 Generando fixture {cat_nombre}...")
            
            try:
                partidos, dia = get_fixture(cat_id, fecha_num)
                
                if not partidos:
                    print(f"   ⚠️ No hay partidos para esta categoría")
                    continue
                
                fecha_info = ""
                if dia:
                    fecha_obj = datetime.strptime(dia, "%Y-%m-%d")
                    dias = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']
                    fecha_info = f"{dias[fecha_obj.weekday()]} {fecha_obj.day}"
                
                fixture_html = generar_fixture_html(partidos, cat_nombre, fecha_num, dia)
                
                html_content = HTML_TEMPLATE.format(
                    categoria_nombre=cat_nombre,
                    fixture_html=fixture_html,
                    fecha_info=""
                )
                
                cat_folder = os.path.join(OUTPUT_DIR, cat_slug, f"fecha_{fecha_num}")
                os.makedirs(cat_folder, exist_ok=True)
                
                output_path = os.path.join(cat_folder, "fixture.png")
                
                page = browser.new_page(viewport={"width": 1080, "height": 1080})
                page.set_content(html_content)
                time.sleep(1)
                
                page.screenshot(path=output_path)
                page.close()
                
                print(f"   ✅ {output_path}")
                total_generados += 1
                
            except Exception as e:
                print(f"   ❌ Error: {e}")
        
        browser.close()
    
    os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
    
    print(f"\n🎉 Listo! {total_generados} imágenes generadas en {OUTPUT_DIR}")
    return total_generados

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Generar imágenes de fixture')
    parser.add_argument('--fecha', type=int, required=True, help='Número de fecha')
    parser.add_argument('--categoria', type=str, default=None, help='Categoría específica (opcional)')
    args = parser.parse_args()
    
    categorias = None
    if args.categoria:
        cat_map = {
            "primera": (1, "primera", "PRIMERA DIVISIÓN"),
            "septima": (2, "septima", "SÉPTIMA DIVISIÓN"),
            "octava": (3, "octava", "OCTAVA DIVISIÓN"),
            "novena": (4, "novena", "NOVENA DIVISIÓN"),
            "decima": (5, "decima", "DÉCIMA DIVISIÓN"),
        }
        if args.categoria in cat_map:
            categorias = [cat_map[args.categoria]]
    
    capturar_fixture(fecha_num=args.fecha, categorias=categorias)