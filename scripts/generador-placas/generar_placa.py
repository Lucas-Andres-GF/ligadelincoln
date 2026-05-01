import os
from playwright.sync_api import sync_playwright
import base64
import sys

SCRIPT_DIR = os.path.dirname(__file__)
PROJECT_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))

ESCUDOS_FOLDER = os.environ.get(
    "ESCUDOS_FOLDER",
    os.environ.get("ESCUDOS_HOST", os.path.join(PROJECT_DIR, "frontend", "public", "escudos_hd")),
)
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
                position: relative;
                overflow: hidden;
            }}

            body::before {{
                content: '';
                position: absolute;
                inset: 0;
                background: radial-gradient(circle at 20% 15%, rgba(250, 204, 21, .18), transparent 22%), radial-gradient(circle at 85% 82%, rgba(34, 197, 94, .22), transparent 24%);
                mix-blend-mode: screen;
                pointer-events: none;
            }}

            body::after {{
                content: '';
                position: absolute;
                inset: 0;
                opacity: .13;
                background-image: repeating-linear-gradient(135deg, rgba(255,255,255,.32) 0 1px, transparent 1px 7px);
                pointer-events: none;
            }}
            
            .header {{
                background: rgba(3, 23, 12, .74);
                padding: 28px 44px;
                border-bottom: 4px solid #facc15;
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
                padding: 10px 26px;
                border-radius: 999px;
                font-size: 24px;
                font-weight: 900;
                color: #052e16;
                text-transform: uppercase;
                letter-spacing: 2px;
                box-shadow: 6px 6px 0 rgba(0,0,0,.28);
            }}
            
            .main-content {{
                flex: 1;
                display: flex;
                flex-direction: column;
                justify-content: center;
                align-items: center;
            }}
            
            .titulo {{
                font-family: 'Bebas Neue', sans-serif;
                font-size: 108px;
                font-weight: 400;
                text-transform: uppercase;
                letter-spacing: 4px;
                margin-bottom: 10px;
                color: #f8fafc;
                text-shadow: 6px 6px 0 #052e16;
            }}
            
            .categoria-titulo {{
                font-size: 76px;
                font-weight: 900;
                text-transform: uppercase;
                letter-spacing: 6px;
                margin-bottom: 18px;
                color: #bbf7d0;
            }}
            
            .fecha-badge {{
                background: #f8fafc;
                border: 4px solid #052e16;
                padding: 18px 64px;
                border-radius: 999px;
                font-size: 48px;
                font-weight: 900;
                color: #14532d;
                letter-spacing: 4px;
                box-shadow: 8px 8px 0 rgba(0,0,0,.28);
            }}
            
            .footer {{
                padding: 30px 40px;
                text-align: center;
                border-top: 1px solid rgba(250, 204, 21, .28);
                width: 100%;
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
            }}
            
            .header {{
                background: rgba(3, 23, 12, .74);
                padding: 28px 44px;
                border-bottom: 4px solid #facc15;
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
                font-size: 34px;
                font-weight: 800;
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
            
            .main-content {{
                flex: 1;
                display: flex;
                flex-direction: column;
                justify-content: center;
                align-items: center;
                padding: 40px;
            }}
            
            .libre-badge {{
                background: #facc15;
                border: 4px solid #052e16;
                padding: 20px 60px;
                border-radius: 999px;
                font-size: 80px;
                font-weight: 900;
                color: #052e16;
                text-transform: uppercase;
                letter-spacing: 8px;
                margin-bottom: 40px;
            }}
            
            .escudo {{
                width: 250px;
                height: 250px;
                object-fit: contain;
                filter: drop-shadow(10px 12px 0 rgba(0,0,0,.28)) drop-shadow(0 8px 24px rgba(0,0,0,.48));
            }}
            
            .club-name {{
                font-size: 58px;
                font-weight: 900;
                text-transform: uppercase;
                color: #f8fafc;
                text-shadow: 5px 5px 0 #052e16;
                margin-top: 30px;
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
            
            .date-badge {{
                position: absolute;
                top: 130px;
                right: 40px;
                background: #f8fafc;
                border: 2px solid #052e16;
                padding: 8px 16px;
                border-radius: 6px;
                font-size: 14px;
                font-weight: 600;
                color: #14532d;
                letter-spacing: 1px;
            }}
            
            .gradient-bar {{
                position: absolute;
                bottom: 0;
                left: 0;
                right: 0;
                height: 10px;
                background: repeating-linear-gradient(90deg, #facc15 0 42px, #f8fafc 42px 84px, #16a34a 84px 126px);
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
            @import url('https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@500;600;700;800;900&family=Bebas+Neue&display=swap');
            
            * {{ margin: 0; padding: 0; box-sizing: border-box; }}
            
            body {{
                width: 1080px; height: 1080px;
                background:
                    radial-gradient(circle at 50% 50%, rgba(255,255,255,.10) 0 18%, transparent 18.4%),
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
                background: rgba(248, 250, 252, .94);
                padding: 54px 42px;
                border-radius: 34px;
                border: 5px solid #052e16;
                box-shadow: 18px 18px 0 rgba(0,0,0,.30), inset 0 0 0 3px rgba(250,204,21,.85);
                transform: rotate(-1.1deg);
            }}
            
            .club-block {{
                display: flex;
                flex-direction: column;
                align-items: center;
                flex: 1;
            }}
            
            .escudo {{
                width: 205px;
                height: 205px;
                object-fit: contain;
                margin-bottom: 20px;
                filter: drop-shadow(9px 10px 0 rgba(20,83,45,.22)) drop-shadow(0 8px 22px rgba(0,0,0,.32));
            }}
            
            .club-name {{
                font-size: 34px;
                font-weight: 900;
                text-align: center;
                text-transform: uppercase;
                color: #052e16;
                text-shadow: none;
                max-width: 220px;
                line-height: 1.2;
            }}
            
            .score-container {{
                display: flex;
                flex-direction: row;
                align-items: center;
                gap: 18px;
            }}
            
            .goles {{
                font-family: 'Bebas Neue', sans-serif;
                font-size: 158px;
                font-weight: 400;
                color: #052e16;
                line-height: 1;
                text-shadow: 5px 5px 0 #facc15;
            }}
            
            .vs {{
                font-family: 'Bebas Neue', sans-serif;
                font-size: 112px;
                font-weight: 400;
                color: #16a34a;
                text-transform: uppercase;
                letter-spacing: 0;
            }}
            
            .divider {{
                width: 80px;
                height: 3px;
                background: repeating-linear-gradient(90deg, #facc15 0 22px, #f8fafc 22px 44px, #16a34a 44px 66px);
                margin: 30px 0;
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
            
            .date-badge {{
                position: absolute;
                top: 130px;
                right: 40px;
                background: #f8fafc;
                border: 2px solid #052e16;
                padding: 8px 16px;
                border-radius: 6px;
                font-size: 14px;
                font-weight: 600;
                color: #14532d;
                letter-spacing: 1px;
            }}
            
            .gradient-bar {{
                position: absolute;
                bottom: 0;
                left: 0;
                right: 0;
                height: 10px;
                background: repeating-linear-gradient(90deg, #facc15 0 42px, #f8fafc 42px 84px, #16a34a 84px 126px);
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
                    <div class="vs">-</div>
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
