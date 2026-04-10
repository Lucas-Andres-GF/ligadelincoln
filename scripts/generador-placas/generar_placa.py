import os
from playwright.sync_api import sync_playwright
import base64
import sys

ESCUDOS_FOLDER = "/app/escudos"
OUTPUT_BASE = os.environ.get("OUTPUT_FOLDER", "/app/salida")
OUTPUT_FOLDER = OUTPUT_BASE  # Compatibilidad

os.makedirs(OUTPUT_FOLDER, exist_ok=True)

def get_image_base64(club_filename):
    path = os.path.join(ESCUDOS_FOLDER, club_filename)
    if not os.path.exists(path):
        default_path = os.path.join(ESCUDOS_FOLDER, "default.png")
        path = default_path if os.path.exists(default_path) else None
    
    if path:
        with open(path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')
    return ""

def get_escudo_filename(nombre_club):
    if not nombre_club:
        return "default.png"
    
    mapa = {
        "ARGENTINO": "argentino.png",
        "ATL. PASTEUR": "atl.pasteur.png",
        "ATL PASTEUR": "atl.pasteur.png",
        "ATL. ROBERTS": "atl.roberts.png",
        "ATL ROBERTS": "atl.roberts.png",
        "CA. PINTENSE": "ca.pintense.png",
        "C A PINTENSE": "ca.pintense.png",
        "CASET": "caset.png",
        "DEP. ARENAZA": "dep.arenaza.png",
        "DEP ARENAZA": "dep.arenaza.png",
        "DEP. GRAL PINTO": "dep.pinto.png",
        "DEP GRAL PINTO": "dep.pinto.png",
        "EL LINQUEÑO": "el.linqueño.png",
        "JUVENTAD UNIDA": "juventud.unida.png",
        "JUVENTUD UNIDA": "juventud.unida.png",
        "SAN MARTIN": "san.martin.png",
        "VILLA FRANCIA": "villa.francia.png",
        "CAEL": "el.linqueño.png",
    }
    
    nombre_upper = nombre_club.upper().strip()
    return mapa.get(nombre_upper, "default.png")

def get_categoria_nombre(categoria_id):
    categorias = {
        1: "PRIMERA",
        2: "SÉPTIMA",
        3: "OCTAVA",
        4: "NOVENA",
        5: "DÉCIMA"
    }
    return categorias.get(categoria_id, "LIGA DE LINCOLN")

def generar_placa_portada(categoria_id, fecha_num):
    """Genera imagen de portada para una categoría y fecha"""
    categoria_nombre = get_categoria_nombre(categoria_id)
    fecha_str = f"FECHA {fecha_num}" if fecha_num else ""
    
    html_content = f"""
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
            }}
            
            .liga-tag {{
                display: flex;
                align-items: center;
                gap: 12px;
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
                flex-direction: column;
                justify-content: center;
                align-items: center;
            }}
            
            .titulo {{
                font-size: 60px;
                font-weight: 900;
                text-transform: uppercase;
                letter-spacing: 6px;
                margin-bottom: 10px;
                color: white;
            }}
            
            .categoria-titulo {{
                font-size: 90px;
                font-weight: 900;
                text-transform: uppercase;
                letter-spacing: 10px;
                margin-bottom: 30px;
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
                letter-spacing: 4px;
            }}
            
            .footer {{
                padding: 30px 40px;
                text-align: center;
                border-top: 1px solid rgba(34, 197, 94, 0.15);
                width: 100%;
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
            <div class="liga-tag">
                <span class="liga-text">Liga De Lincoln</span>
            </div>
            <div class="categoria-badge">{categoria_nombre}</div>
        </div>
        
        <div class="main-content">
            <div class="categoria-titulo">{categoria_nombre}</div>
            <div class="titulo">Resultados</div>
            <div class="fecha-badge">{fecha_str}</div>
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
    
    filename = f"portada_{categoria_nombre.lower()}_fecha_{fecha_num}.png"
    output_path = os.path.join(OUTPUT_BASE, filename)
    
    print(f"🎨 Generando portada: {categoria_nombre} - {fecha_str}")
    
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={'width': 1080, 'height': 1080})
        page.set_content(html_content)
        page.wait_for_load_state("networkidle")
        page.screenshot(path=output_path)
        browser.close()
    
    print(f"✅ Portada guardada en: {output_path}")
    return output_path

def generar_placa_libre(categoria_id, club_nombre, fecha_num=None):
    """Genera imagen para equipo libre"""
    img_b64 = get_image_base64(get_escudo_filename(club_nombre))
    name_club = club_nombre.title() if club_nombre else "Club"
    
    categoria_nombre = get_categoria_nombre(categoria_id)
    fecha_str = f"FECHA {fecha_num}" if fecha_num else ""
    
    html_content = f"""
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
            }}
            
            .header {{
                background: linear-gradient(135deg, #143814 0%, #1a4a1a 100%);
                padding: 30px 40px;
                border-bottom: 2px solid rgba(34, 197, 94, 0.3);
                display: flex;
                align-items: center;
                justify-content: space-between;
            }}
            
            .liga-tag {{
                display: flex;
                align-items: center;
                gap: 12px;
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
                flex-direction: column;
                justify-content: center;
                align-items: center;
                padding: 40px;
            }}
            
            .libre-badge {{
                background: rgba(34, 197, 94, 0.15);
                border: 2px solid rgba(34, 197, 94, 0.5);
                padding: 20px 60px;
                border-radius: 16px;
                font-size: 80px;
                font-weight: 900;
                color: #22c55e;
                text-transform: uppercase;
                letter-spacing: 8px;
                margin-bottom: 40px;
            }}
            
            .escudo {{
                width: 250px;
                height: 250px;
                object-fit: contain;
                filter: drop-shadow(0 8px 20px rgba(0,0,0,0.5));
            }}
            
            .club-name {{
                font-size: 48px;
                font-weight: 700;
                text-transform: uppercase;
                color: #f0fdf4;
                text-shadow: 0 2px 4px rgba(0,0,0,0.3);
                margin-top: 30px;
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
            
            .date-badge {{
                position: absolute;
                top: 130px;
                right: 40px;
                background: rgba(34, 197, 94, 0.1);
                border: 1px solid rgba(34, 197, 94, 0.3);
                padding: 8px 16px;
                border-radius: 6px;
                font-size: 14px;
                font-weight: 600;
                color: #22c55e;
                letter-spacing: 1px;
            }}
            
            .gradient-bar {{
                position: absolute;
                bottom: 0;
                left: 0;
                right: 0;
                height: 6px;
                background: linear-gradient(90deg, #22c55e, #4ade80, #22c55e);
            }}
            
            body {{
                position: relative;
            }}
        </style>
    </head>
    <body>
        <div class="header">
            <div class="liga-tag">
                <span class="liga-text">Liga De Lincoln</span>
            </div>
            <div class="categoria-badge">{categoria_nombre}</div>
        </div>
        
        <div class="main-content">
            {f'<div class="date-badge">{fecha_str}</div>' if fecha_str else ''}
            <div class="libre-badge">LIBRE</div>
            <img src="data:image/png;base64,{img_b64}" class="escudo">
            <div class="club-name">{name_club}</div>
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
    
    filename = f"libre_{name_club.replace(' ', '_')}.png"
    output_path = os.path.join(OUTPUT_BASE, filename)
    
    print(f"🎨 Generando Libre: {name_club}")
    
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={'width': 1080, 'height': 1080})
        page.set_content(html_content)
        page.wait_for_load_state("networkidle")
        page.screenshot(path=output_path)
        browser.close()
    
    print(f"✅ Imagen libre guardada en: {output_path}")
    return output_path

def generar_placa_resultado(categoria_id, club_local_nombre, goles_local, club_visita_nombre, goles_visita, fecha_num=None):
    
    club_local_file = get_escudo_filename(club_local_nombre)
    club_visita_file = get_escudo_filename(club_visita_nombre)
    
    img_local_b64 = get_image_base64(club_local_file)
    img_visita_b64 = get_image_base64(club_visita_file)

    name_local = club_local_nombre.title() if club_local_nombre else "Local"
    name_visita = club_visita_nombre.title() if club_visita_nombre else "Visita"
    
    categoria_nombre = get_categoria_nombre(categoria_id)
    fecha_str = f"FECHA {fecha_num}" if fecha_num else ""

    html_content = f"""
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
            }}
            
            .header {{
                background: linear-gradient(135deg, #143814 0%, #1a4a1a 100%);
                padding: 30px 40px;
                border-bottom: 2px solid rgba(34, 197, 94, 0.3);
                display: flex;
                align-items: center;
                justify-content: space-between;
            }}
            
            .liga-tag {{
                display: flex;
                align-items: center;
                gap: 12px;
            }}
            
            .liga-logo {{
                width: 50px;
                height: 50px;
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
                flex-direction: column;
                justify-content: center;
                align-items: center;
                padding: 40px;
            }}
            
            .marcador-container {{
                display: flex;
                justify-content: center;
                align-items: center;
                gap: 30px;
                width: 100%;
                max-width: 900px;
                background: rgba(20, 56, 20, 0.5);
                padding: 50px 40px;
                border-radius: 24px;
                border: 1px solid rgba(34, 197, 94, 0.2);
                backdrop-filter: blur(10px);
            }}
            
            .club-block {{
                display: flex;
                flex-direction: column;
                align-items: center;
                flex: 1;
            }}
            
            .escudo {{
                width: 180px;
                height: 180px;
                object-fit: contain;
                margin-bottom: 20px;
                filter: drop-shadow(0 8px 20px rgba(0,0,0,0.5));
            }}
            
            .club-name {{
                font-size: 28px;
                font-weight: 700;
                text-align: center;
                text-transform: uppercase;
                color: #f0fdf4;
                text-shadow: 0 2px 4px rgba(0,0,0,0.3);
                max-width: 220px;
                line-height: 1.2;
            }}
            
            .score-container {{
                display: flex;
                flex-direction: column;
                align-items: center;
                gap: 8px;
            }}
            
            .goles {{
                font-size: 120px;
                font-weight: 900;
                color: #22c55e;
                line-height: 1;
                text-shadow: 0 4px 20px rgba(34, 197, 94, 0.4);
            }}
            
            .vs {{
                font-size: 24px;
                font-weight: 500;
                color: rgba(34, 197, 94, 0.5);
                text-transform: uppercase;
                letter-spacing: 4px;
            }}
            
            .divider {{
                width: 80px;
                height: 3px;
                background: linear-gradient(90deg, transparent, #22c55e, transparent);
                margin: 30px 0;
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
            
            .date-badge {{
                position: absolute;
                top: 130px;
                right: 40px;
                background: rgba(34, 197, 94, 0.1);
                border: 1px solid rgba(34, 197, 94, 0.3);
                padding: 8px 16px;
                border-radius: 6px;
                font-size: 14px;
                font-weight: 600;
                color: #22c55e;
                letter-spacing: 1px;
            }}
            
            .gradient-bar {{
                position: absolute;
                bottom: 0;
                left: 0;
                right: 0;
                height: 6px;
                background: linear-gradient(90deg, #22c55e, #4ade80, #22c55e);
            }}
            
            body {{
                position: relative;
            }}
        </style>
    </head>
    <body>
        <div class="header">
            <div class="liga-tag">
                <span class="liga-text">Liga De Lincoln</span>
            </div>
            <div class="categoria-badge">{categoria_nombre}</div>
        </div>
        
        <div class="main-content">
            {f'<div class="date-badge">{fecha_str}</div>' if fecha_str else ''}
            
            <div class="marcador-container">
                <div class="club-block">
                    <img src="data:image/png;base64,{img_local_b64}" class="escudo">
                    <div class="club-name">{name_local}</div>
                </div>
                
                <div class="score-container">
                    <div class="goles">{goles_local}</div>
                    <div class="vs">VS</div>
                    <div class="goles">{goles_visita}</div>
                </div>
                
                <div class="club-block">
                    <img src="data:image/png;base64,{img_visita_b64}" class="escudo">
                    <div class="club-name">{name_visita}</div>
                </div>
            </div>
            
            <div class="divider"></div>
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

    filename = f"resultado_{name_local.replace(' ', '_')}_{goles_local}_vs_{goles_visita}_{name_visita.replace(' ', '_')}.png"
    output_path = os.path.join(OUTPUT_BASE, filename)

    print(f"🚀 Generando placa: {name_local} {goles_local} - {goles_visita} {name_visita}")
    print(f"   Categoría: {categoria_nombre}")
    
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={'width': 1080, 'height': 1080})
        page.set_content(html_content)
        page.wait_for_load_state("networkidle")
        page.screenshot(path=output_path)
        browser.close()

    print(f"✅ Imagen guardada en: {output_path}")
    return output_path

if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "--portada":
        categoria_id = int(sys.argv[2])
        fecha_num = int(sys.argv[3]) if len(sys.argv) > 3 else None
        generar_placa_portada(categoria_id, fecha_num)
    elif len(sys.argv) >= 2 and sys.argv[1] == "--libre":
        categoria_id = int(sys.argv[2])
        club = sys.argv[3]
        fecha_num = int(sys.argv[4]) if len(sys.argv) > 4 else None
        generar_placa_libre(categoria_id, club, fecha_num)
    elif len(sys.argv) >= 6:
        categoria_id = int(sys.argv[1])
        club_local = sys.argv[2]
        goles_local = int(sys.argv[3])
        club_visita = sys.argv[4]
        goles_visita = int(sys.argv[5])
        fecha_num = int(sys.argv[6]) if len(sys.argv) > 6 else None
        generar_placa_resultado(categoria_id, club_local, goles_local, club_visita, goles_visita, fecha_num)
    else:
        generar_placa_resultado(1, "San Martin", 3, "Villa Francia", 0, 15)