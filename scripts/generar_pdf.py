#!/usr/bin/env python3
import os
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', 'backend', '.env'))

from supabase import create_client
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

MAPEO_CATEGORIAS = {
    1: "PRIMERA",
    2: "SÉPTIMA", 
    3: "OCTAVA",
    4: "NOVENA",
    5: "DÉCIMA"
}

MAPEO_EQUIPOS = {
    1: "Argentino",
    2: "Atl. Pasteur",
    3: "Atl. Roberts",
    4: "CA. Pintense",
    5: "Caset",
    6: "Dep. Arenaza",
    7: "Dep. Gral Pinto",
    8: "El Linqueño",
    9: "Juventud Unida",
    10: "San Martin",
    11: "Villa Francia",
    12: "CAEL",
}

def obtener_partidos():
    response = supabase.table("partidos").select("*").order("categoria_id").order("fecha_id").execute()
    return response.data or []

def obtener_posiciones():
    response = supabase.table("posiciones").select("*").order("categoria_id").order("pts", desc=True).execute()
    return response.data or []

def crear_pdf(partidos, posiciones, output_path="liga_lincoln.pdf"):
    doc = SimpleDocTemplate(output_path, pagesize=A4)
    story = []
    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        spaceAfter=30,
        alignment=1
    )
    
    subtitle_style = ParagraphStyle(
        'CustomSubtitle',
        parent=styles['Heading2'],
        fontSize=16,
        spaceBefore=20,
        spaceAfter=15
    )
    
    story.append(Paragraph("LIGA DE LINCOLN", title_style))
    story.append(Paragraph(f"Fecha de generación: 10/04/2026", styles['Normal']))
    story.append(Spacer(1, 20))
    
    story.append(Paragraph("POSICIONES POR CATEGORÍA", subtitle_style))
    
    posiciones_por_cat = {}
    for pos in posiciones:
        cat_id = pos['categoria_id']
        if cat_id not in posiciones_por_cat:
            posiciones_por_cat[cat_id] = []
        posiciones_por_cat[cat_id].append(pos)
    
    for cat_id in posiciones_por_cat:
        posiciones_por_cat[cat_id].sort(key=lambda x: x.get('pts', 0), reverse=True)
    
    for cat_id in sorted(posiciones_por_cat.keys()):
        story.append(Paragraph(f"{MAPEO_CATEGORIAS.get(cat_id, str(cat_id))}", styles['Heading3']))
        
        posiciones_cat = posiciones_por_cat[cat_id]
        data = [["#", "Equipo", "PJ", "PG", "PE", "PP", "GF", "GC", "DG", "Pts"]]
        
        for i, pos in enumerate(posiciones_cat[:15], 1):
            equipo = MAPEO_EQUIPOS.get(pos['club_id'], f"Club {pos['club_id']}")
            data.append([
                str(i),
                equipo,
                str(pos.get('pj', 0)),
                str(pos.get('pg', 0)),
                str(pos.get('pe', 0)),
                str(pos.get('pp', 0)),
                str(pos.get('gf', 0)),
                str(pos.get('gc', 0)),
                str(pos.get('dif', 0)),
                str(pos.get('pts', 0))
            ])
        
        table = Table(data, colWidths=[25, 120, 25, 25, 25, 25, 25, 25, 25, 25])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.darkgreen),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
            ('BACKGROUND', (0, 1), (-1, -1), colors.whitesmoke),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.whitesmoke, colors.white]),
        ]))
        story.append(table)
    
    story.append(Spacer(1, 20))
    story.append(Paragraph("PARTIDOS", subtitle_style))
    
    partidos_por_cat = {}
    for p in partidos:
        cat_id = p['categoria_id']
        if cat_id not in partidos_por_cat:
            partidos_por_cat[cat_id] = []
        partidos_por_cat[cat_id].append(p)
    
    for cat_id in sorted(partidos_por_cat.keys()):
        story.append(Paragraph(f"{MAPEO_CATEGORIAS.get(cat_id, str(cat_id))}", styles['Heading3']))
        
        partidos_cat = partidos_por_cat[cat_id]
        
        for p in sorted(partidos_cat, key=lambda x: x.get('fecha_id', 0)):
            local = MAPEO_EQUIPOS.get(p['local_id'], f"Local {p['local_id']}")
            visita = MAPEO_EQUIPOS.get(p['visitante_id'], f"Visitante {p['visitante_id']}")
            fecha = p.get('fecha_id', 'N/A')
            estado = p.get('estado', 'N/A')
            
            if estado == 'jugado':
                gl = p.get('goles_local', '-')
                gv = p.get('goles_visitante', '-')
                resultado = f"{local} {gl} - {gv} {visita}"
            else:
                resultado = f"{local} vs {visita} ({estado})"
            
            story.append(Paragraph(f"Fecha {fecha}: {resultado}", styles['Normal']))
    
    doc.build(story)
    print(f"PDF generado: {output_path}")

if __name__ == "__main__":
    print("Obteniendo datos de Supabase...")
    partidos = obtener_partidos()
    posiciones = obtener_posiciones()
    
    print(f"Partidos: {len(partidos)}")
    print(f"Posiciones: {len(posiciones)}")
    
    crear_pdf(partidos, posiciones, "liga_lincoln.pdf")