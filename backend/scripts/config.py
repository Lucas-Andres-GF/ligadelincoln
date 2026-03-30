# config.py
import os
from supabase import create_client

# Credenciales de Supabase (desde variables de entorno)
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("Faltan credenciales de Supabase. Definir SUPABASE_URL y SUPABASE_KEY")

# Conexión global
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# Mapeo de equipos (todos los equipos posibles)
MAPEO_CLUBES = {
    "ARGENTINO": 1, 
    "ATL. PASTEUR": 2, 
    "ATL PASTEUR": 2,
    "ATL. ROBERTS": 3,
    "ATL ROBERTS": 3,
    "CA. PINTENSE": 4, 
    "C A PINTENSE": 4,
    "CASET": 5,
    "DEP. ARENAZA": 6,
    "DEP ARENAZA": 6,
    "DEP. GRAL PINTO": 7,
    "DEP GRAL PINTO": 7,
    "EL LINQUEÑO": 8,
    "JUVENTUD UNIDA": 9,
    "SAN MARTIN": 10,
    "VILLA FRANCIA": 11,
    "CAEL": 12,  # El Linqueño B (novena)
}

# Equipos por categoría (los que participan en cada división)
EQUIPOS_POR_CATEGORIA = {
    1: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11],  # Primera: todos
    2: [8, 2, 4, 7, 5, 9, 1, 3],  # Séptima
    3: [1, 7, 6, 11, 4, 10, 8, 9, 2],  # Octava (agregado ATL PASTEUR)
    4: [1, 12, 4, 7, 8, 10],  # Novena (usa CAEL)
    5: [8, 6, 4, 5, 2, 10, 1, 9, 7, 11, 3],  # Décima
}

# IDs de Categorías
CATEGORIAS = {
    "primera": 1,
    "septima": 2,
    "octava": 3,
    "novena": 4,
    "decima": 5
}
