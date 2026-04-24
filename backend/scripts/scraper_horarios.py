# -*- coding: utf-8 -*-
import os
from dotenv import load_dotenv
from supabase import create_client
import requests
from bs4 import BeautifulSoup
import re

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

URL = "https://www.ligaamateurdedeportes.com.ar/horarios.html"

DURACION_MINUTOS = {
    "primera": 105,
    "septima": 95,
    "octava": 85,
    "novena": 75,
    "decima": 65,
}

MAPEO_CATEGORIA = {
    "primera": 1,
    "septima": 2,
    "octava": 3,
    "novena": 4,
    "decima": 5,
}

MAPEO_EQUIPOS = {
    "CASET": 5,
    "JUVENTUD UNIDA": 9,
    "DEP GRAL PINTO": 7,
    "DEP. GRAL PINTO": 7,
    "C A PINTENSE": 4,
    "CA. PINTENSE": 4,
    "EL LINQUEÑO": 8,
    "ARGENTINO": 1,
    "ATL PASTEUR": 2,
    "ATL ROBERTS": 3,
    "DEP ARENAZA": 6,
    "CAEL": 12,
    "SAN MARTIN": 10,
    "VILLA FRANCIA": 11,
}

def normalizar_equipo(nombre):
    if not nombre:
        return ""
    return nombre.strip().upper()

def normalizar_categoria(cat):
    if not cat:
        return None
    cat = cat.lower().strip()
    cat = cat.replace("décima", "decima").replace("séptima", "septima")
    if cat in MAPEO_CATEGORIA:
        return cat
    return None

def buscar_equipo_id(nombre):
    if not nombre:
        return None
    nombre_norm = normalizar_equipo(nombre)
    for eq, id_eq in MAPEO_EQUIPOS.items():
        if eq in nombre_norm:
            return id_eq
    return None

def scrape():
    print("Fetching horarios...")
    response = requests.get(URL, timeout=30)
    response.encoding = 'utf-8'
    soup = BeautifulSoup(response.text, 'html.parser')
    
    resultados = []
    fecha_actual = None
    ultima_hora = None
    ultima_cancha = None
    
    tablas = soup.find_all('table')
    tabla = None
    for t in tablas:
        if 'CRONOGRAMA' in t.get_text():
            tabla = t
            break
    
    if not tabla:
        print("ERROR: No se encontró tabla de cronograma")
        return []
    
    filas = tabla.find_all('tr')
    postergados_encontrado = False
    
    for fila in filas:
        celdas = [c.get_text(strip=True) for c in fila.find_all('td')]
        if not celdas:
            celdas = [c.get_text(strip=True) for c in fila.find_all('th')]
        
        if not celdas:
            continue
        
        texto = ' '.join(celdas)
        
        if 'Postergados' in celdas[0] and len(celdas) < 3:
            postergados_encontrado = True
            continue
        
        if postergados_encontrado:
            continue
        
        match = re.search(r'((?:Lunes|Martes|Miércoles|Jueves|Viernes|Sábado|Domingo)\s+\d{1,2}\s+de\s+\w+\s+de\s+\d{4})', texto, re.IGNORECASE)
        if match:
            fecha_str = match.group(1)
            fecha_match = re.search(r'(\d{1,2})\s+de\s+(\w+)\s+de\s+(\d{4})', fecha_str)
            if fecha_match:
                dia, mes, anio = fecha_match.groups()
                meses = {
                    "enero": "01", "febrero": "02", "marzo": "03", "abril": "04",
                    "mayo": "05", "junio": "06", "julio": "07", "agosto": "08",
                    "septiembre": "09", "octubre": "10", "noviembre": "11", "diciembre": "12"
                }
                fecha_actual = f"{anio}-{meses.get(mes.lower(), '04')}-{dia.zfill(2)}"
                ultima_hora = None
                ultima_cancha = None
            continue
        
        if 'Division' in celdas[0] or 'ligaamateurdedeportes' in celdas[0].lower():
            continue
        
        cat = normalizar_categoria(celdas[0])
        if not cat:
            continue
        
        if len(celdas) < 4:
            continue
        
        local = normalizar_equipo(celdas[1]) if celdas[1] else ""
        vs = celdas[2] if len(celdas) > 2 else ""
        visitante = normalizar_equipo(celdas[3]) if len(celdas) > 3 else ""
        
        if vs not in ["vs", "vs."]:
            continue
        
        if not local or not visitante:
            continue
        
        hora = None
        cancha = None
        hora_heredada = False
        
        if len(celdas) >= 6:
            hora_str = celdas[4].replace('.', ':').strip()
            if re.match(r'\d{1,2}:\d{2}', hora_str):
                hora = hora_str
                if not ultima_hora:
                    ultima_hora = hora
                if celdas[5]:
                    campo = celdas[5].strip()
                    if campo:
                        ultima_cancha = campo
            elif celdas[5]:
                campo = celdas[5].strip()
                if campo:
                    ultima_cancha = campo
        
        if not hora and ultima_hora:
            hora = ultima_hora
            hora_heredada = True
        
        resultados.append({
            "fecha": fecha_actual,
            "categoria_id": MAPEO_CATEGORIA[cat],
            "categoria": cat,
            "local": local,
            "local_id": buscar_equipo_id(local),
            "visitante": visitante,
            "visitante_id": buscar_equipo_id(visitante),
            "hora": hora,
            "hora_heredada": hora_heredada,
            "cancha": ultima_cancha if ultima_cancha else "",
        })
    
    return resultados

def calcular_horarios(partidos):
    seen = set()
    unique = []
    for p in partidos:
        key = (p['fecha'], p['categoria'], p['local'], p['visitante'])
        if key not in seen:
            seen.add(key)
            unique.append(p)
    
    cronograma = {}
    for p in unique:
        key = (p['fecha'], p['cancha'])
        if key not in cronograma:
            cronograma[key] = []
        cronograma[key].append(p)
    
    resultado_final = []
    
    for (fecha, campo), lista in sorted(cronograma.items()):
        hora_actual = None
        cat_anterior = None
        
        for p in lista:
            if p.get('hora_heredada'):
                if hora_actual and cat_anterior:
                    h, m = map(int, hora_actual.split(':'))
                    minutos = h * 60 + m
                    minutos += DURACION_MINUTOS.get(cat_anterior, 80)
                    nueva_hora = f"{minutos // 60:02d}:{minutos % 60:02d}"
                    resultado_final.append({**p, "hora_calc": nueva_hora, "hora_original": p['hora']})
                    hora_actual = nueva_hora
                    cat_anterior = p['categoria']
                else:
                    hora_actual = p['hora']
                    cat_anterior = p['categoria']
                    resultado_final.append({**p, "hora_calc": hora_actual, "hora_original": p['hora']})
            else:
                hora_actual = p['hora']
                cat_anterior = p['categoria']
                resultado_final.append({**p, "hora_calc": p['hora'], "hora_original": p['hora']})
    
    return resultado_final

def actualizar_db(partidos_con_hora):
    print(f"\n=== Actualizando {len(partidos_con_hora)} partidos en la DB ===\n")
    
    actualizados = 0
    errores = 0
    
    for p in partidos_con_hora:
        if not p['local_id'] or not p['visitante_id']:
            print(f"  SKIP: {p['categoria']} {p['local']} vs {p['visitante']} (equipo no encontrado)")
            continue
        
        try:
            result = supabase.table("partidos").select("id").eq("categoria_id", p['categoria_id']).eq("local_id", p['local_id']).eq("visitante_id", p['visitante_id']).execute()
            
            if result.data:
                supabase.table("partidos").update({
                    "dia": p['fecha'],
                    "hora": p['hora_calc']
                }).eq("id", result.data[0]['id']).execute()
                
                print(f"  OK: {p['fecha']} {p['hora_calc']} | {p['categoria']:8} | {p['local']} vs {p['visitante']}")
                actualizados += 1
            else:
                print(f"  NOT FOUND: {p['categoria']} {p['local']} vs {p['visitante']}")
        
        except Exception as e:
            print(f"  ERROR: {p['local']} vs {p['visitante']}: {e}")
            errores += 1
    
    print(f"\n=== Resumen: {actualizados} actualizados, {errores} errores ===")

if __name__ == "__main__":
    resultados = scrape()
    partidos_con_hora = calcular_horarios(resultados)
    
    print(f"\n=== Partidos con hora: {len(partidos_con_hora)} ===\n")
    for p in partidos_con_hora:
        print(f"{p['fecha']} {p['hora_calc']:6} | {p['categoria']:8} | {p['local']:15} vs {p['visitante']:15}")
    
    print("\n--- Actualizando la base de datos ---\n")
    actualizar_db(partidos_con_hora)