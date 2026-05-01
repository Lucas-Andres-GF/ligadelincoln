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

SCRIPT_DIR = os.path.dirname(__file__)
PROJECT_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, '..'))
OUTPUT_DIR = os.environ.get('OUTPUT_DIR', os.path.join(PROJECT_DIR, 'tablas-images'))
FRONTEND_DIR = os.environ.get('FRONTEND_DIR', os.path.join(PROJECT_DIR, 'frontend'))
ESCUDOS_FOLDER = os.environ.get('ESCUDOS_FOLDER', os.path.join(PROJECT_DIR, 'frontend', 'public', 'escudos_hd'))

from datetime import datetime

CATEGORIAS = [
    (1, "primera", "PRIMERA DIVISIÓN"),
    (2, "septima", "SÉPTIMA DIVISIÓN"),
    (3, "octava", "OCTAVA DIVISIÓN"),
    (4, "novena", "NOVENA DIVISIÓN"),
    (5, "decima", "DÉCIMA DIVISIÓN"),
]

os.makedirs(OUTPUT_DIR, exist_ok=True)

def start_frontend():
    if os.environ.get('CAPTURE_START_FRONTEND', '0') != '1':
        return None

    kwargs = {
        'cwd': FRONTEND_DIR,
        'stdout': subprocess.DEVNULL,
        'stderr': subprocess.DEVNULL,
    }
    if os.name == 'nt':
        kwargs['creationflags'] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs['preexec_fn'] = os.setsid

    return subprocess.Popen(["npm", "run", "dev", "--", "--host"], **kwargs)

def stop_frontend(proc):
    if not proc:
        return
    if os.name == 'nt':
        proc.terminate()
    else:
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)

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
            fecha_html = f'<span class="dia">{dias[fecha_obj.weekday()]} {fecha_obj.day}</span>'
        hora_html = f'<span class="hora">{p["hora"]}</span>' if p.get('hora') and p['hora'] != '-' else ''
        datetime_html = f"""
            <div class="datetime">
                {fecha_html if fecha_html else ''}
                {hora_html}
            </div>
        """ if fecha_html or hora_html else ""
        
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
            {datetime_html}
        </div>
        """
    
    for p in libres:
        escudo_local = get_escudo_filename(p['local'])
        escudo_local_b64 = get_escudo_base64(escudo_local)
        
        fecha_html = ""
        if p.get('mostrar_fecha') and p.get('dia'):
            fecha_obj = datetime.strptime(p['dia'], "%Y-%m-%d")
            dias = ['LUN', 'MAR', 'MIÉ', 'JUE', 'VIE', 'SÁB', 'DOM']
            fecha_html = f'<span class="dia">{dias[fecha_obj.weekday()]} {fecha_obj.day}</span>'
        hora_html = f'<span class="hora">{p["hora"]}</span>' if p.get('hora') and p['hora'] != '-' else ''
        datetime_html = f"""
            <div class="datetime">
                {fecha_html if fecha_html else ''}
                {hora_html}
            </div>
        """ if fecha_html or hora_html else ""
        
        rows += f"""
        <div class="partido libre">
            <div class="equipo-center">
                <img class="escudo" src="data:image/png;base64,{escudo_local_b64}">
                <span class="nombre">{p['local']}</span>
                <span class="libre-text">LIBRE</span>
            </div>
            {datetime_html}
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
        @import url('https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@500;600;700;800;900&family=Bebas+Neue&display=swap');
        
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        
        body {{
            width: 1080px; height: 1080px;
            background:
                radial-gradient(circle at 50% 52%, rgba(255,255,255,.09) 0 18%, transparent 18.4%),
                linear-gradient(90deg, transparent 0 11%, rgba(255,255,255,.10) 11.2% 11.55%, transparent 11.8% 88%, rgba(255,255,255,.10) 88.2% 88.55%, transparent 88.8%),
                repeating-linear-gradient(0deg, rgba(255,255,255,.028) 0 2px, transparent 2px 84px),
                linear-gradient(135deg, #052e16 0%, #14532d 48%, #03170c 100%);
            font-family: 'Barlow Condensed', sans-serif;
            color: white;
            display: flex;
            flex-direction: column;
            justify-content: center;
            align-items: center;
        }}
        
        .header {{
            background: rgba(3, 23, 12, .74);
            padding: 28px 44px;
            border-bottom: 4px solid #facc15;
            display: flex;
            align-items: center;
            justify-content: space-between;
            width: 100%;
            position: absolute;
            top: 0;
        }}
        
        .liga-text {{
            font-size: 34px;
            font-weight: 900;
            letter-spacing: 1.5px;
            text-transform: uppercase;
            color: #f8fafc;
            text-shadow: 3px 3px 0 #052e16;
        }}
        
        .main-content {{
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            flex: 1;
        }}
        
        .titulo-principal {{
            font-family: 'Bebas Neue', sans-serif;
            font-size: 138px;
            font-weight: 400;
            text-transform: uppercase;
            letter-spacing: 5px;
            margin-bottom: 30px;
            text-align: center;
            color: #f8fafc;
            text-shadow: 7px 7px 0 #052e16;
        }}
        
        .fecha-badge {{
            background: #facc15;
            border: 4px solid #052e16;
            padding: 20px 60px;
            border-radius: 999px;
            font-size: 48px;
            font-weight: 800;
            color: #052e16;
            letter-spacing: 6px;
            margin-bottom: 30px;
        }}
        
        .torneo-badge {{
            background: #f8fafc;
            border: 3px solid #052e16;
            padding: 12px 36px;
            border-radius: 999px;
            font-size: 24px;
            font-weight: 600;
            color: #14532d;
            letter-spacing: 2px;
        }}
        
        .footer {{
            padding: 30px 40px;
            text-align: center;
            border-top: 1px solid rgba(250, 204, 21, .28);
            width: 100%;
            position: absolute;
            bottom: 0;
        }}
        
        .footer-text {{
            font-size: 18px;
            color: rgba(255, 255, 255, 0.72);
            font-weight: 600;
        }}
        
        .footer-link {{
            color: #facc15;
            font-weight: 900;
            text-decoration: none;
        }}
        
        .gradient-bar {{
            position: absolute;
            bottom: 0;
            left: 0;
            right: 0;
            height: 10px;
            background: repeating-linear-gradient(90deg, #facc15 0 42px, #f8fafc 42px 84px, #16a34a 84px 126px);
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
        @import url('https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@500;600;700;800;900&family=Bebas+Neue&display=swap');
        
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        
        body {{
            width: 1080px;
            height: 1080px;
            background:
                radial-gradient(circle at 50% 52%, rgba(255,255,255,.09) 0 18%, transparent 18.4%),
                linear-gradient(90deg, transparent 0 11%, rgba(255,255,255,.10) 11.2% 11.55%, transparent 11.8% 88%, rgba(255,255,255,.10) 88.2% 88.55%, transparent 88.8%),
                repeating-linear-gradient(0deg, rgba(255,255,255,.028) 0 2px, transparent 2px 84px),
                linear-gradient(135deg, #052e16 0%, #14532d 48%, #03170c 100%);
            font-family: 'Barlow Condensed', sans-serif;
            color: white;
            display: flex;
            flex-direction: column;
        }}
        
        .header {{
            background: rgba(3, 23, 12, .74);
            padding: 28px 44px;
            border-bottom: 4px solid #facc15;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }}
        
        .liga-text {{
            font-size: 34px;
            font-weight: 900;
            letter-spacing: 1.5px;
            text-transform: uppercase;
            color: #f8fafc;
            text-shadow: 3px 3px 0 #052e16;
        }}
        
        .categoria-badge {{
            background: #facc15;
            border: 3px solid #052e16;
            padding: 10px 24px;
            border-radius: 999px;
            font-size: 24px;
            font-weight: 900;
            color: #052e16;
            text-transform: uppercase;
            letter-spacing: 2px;
            box-shadow: 6px 6px 0 rgba(0,0,0,.28);
        }}

        .header-meta {{
            display: flex;
            align-items: center;
            gap: 16px;
        }}

        .fecha-chip {{
            background: #f8fafc;
            border: 3px solid #052e16;
            border-radius: 999px;
            color: #14532d;
            font-size: 22px;
            font-weight: 900;
            letter-spacing: 2px;
            padding: 10px 22px;
            text-transform: uppercase;
            box-shadow: 6px 6px 0 rgba(0,0,0,.20);
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
            gap: 14px;
        }}
        
        .fecha-info {{
            background: #facc15;
            padding: 16px 24px;
            border-radius: 999px;
            border: 3px solid #052e16;
            text-align: center;
            margin-bottom: 20px;
            font-size: 20px;
            font-weight: 700;
            color: #052e16;
            letter-spacing: 2px;
        }}
        
        .partido {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            background: rgba(248, 250, 252, .94);
            border: 3px solid #052e16;
            border-radius: 20px;
            padding: 14px 22px;
            box-shadow: 8px 8px 0 rgba(0,0,0,.24);
        }}
        
        .partido.libre {{
            background: rgba(250, 204, 21, .92);
        }}
        
        .equipo-center {{
            display: flex;
            align-items: center;
            gap: 12px;
            justify-content: center;
            flex: 1;
        }}
        
        .libre-text {{
            background: #052e16;
            border: 1px solid #052e16;
            padding: 4px 12px;
            border-radius: 6px;
            font-size: 12px;
            font-weight: 700;
            color: #facc15;
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
            width: 56px;
            height: 56px;
            object-fit: contain;
            filter: drop-shadow(3px 4px 0 rgba(20,83,45,.18));
        }}
        
        .nombre {{
            font-size: 24px;
            font-weight: 900;
            color: #052e16;
            white-space: nowrap;
        }}
        
        .vs {{
            font-size: 22px;
            font-weight: 900;
            color: #16a34a;
            margin: 0 20px;
        }}
        
        .hora {{
            font-size: 20px;
            color: #14532d;
            width: 60px;
            text-align: center;
            font-weight: 900;
        }}
        
        .datetime {{
            display: flex;
            flex-direction: column;
            align-items: flex-end;
            gap: 2px;
            min-width: 94px;
        }}
        
        .datetime .dia {{
            font-size: 16px;
            color: #14532d;
            font-weight: 900;
            text-transform: uppercase;
            letter-spacing: 1px;
        }}
        
        .datetime .hora {{
            font-size: 22px;
            color: #052e16;
            font-weight: 800;
        }}
        
        .libre-badge {{
            background: #052e16;
            border: 1px solid #052e16;
            padding: 8px 24px;
            border-radius: 8px;
            font-size: 14px;
            font-weight: 700;
            color: #facc15;
            text-transform: uppercase;
            letter-spacing: 2px;
        }}
        
        .footer {{
            padding: 30px 40px;
            text-align: center;
            border-top: 1px solid rgba(250, 204, 21, .28);
        }}
        
        .footer-text {{
            font-size: 18px;
            color: rgba(255, 255, 255, 0.72);
            font-weight: 600;
        }}
        
        .footer-link {{
            color: #facc15;
            font-weight: 900;
            text-decoration: none;
        }}
        
        .gradient-bar {{
            position: absolute;
            bottom: 0;
            left: 0;
            right: 0;
            height: 10px;
            background: repeating-linear-gradient(90deg, #facc15 0 42px, #f8fafc 42px 84px, #16a34a 84px 126px);
        }}
        
        body {{ position: relative; }}
    </style>
</head>
<body>
    <div class="header">
        <div class="liga-text">Liga De Lincoln</div>
        <div class="header-meta">
            <div class="fecha-chip">FECHA {fecha_num}</div>
            <div class="categoria-badge">{categoria_nombre}</div>
        </div>
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
    
    proc = start_frontend()
    if proc:
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
                    fecha_num=fecha_num,
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
    
    stop_frontend(proc)
    
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
