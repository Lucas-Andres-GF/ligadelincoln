# config.py
from supabase import create_client

# Credenciales de Supabase
SUPABASE_URL = "https://orrimhgwimzbgzicnlcc.supabase.co"
SUPABASE_KEY = "sb_publishable_FtAEpnKNqCYoIF5sFOqaVQ_Xom0Cf37"

# Conexión global
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# Mapeo oficial verificado con tus fotos
MAPEO_CLUBES = {
    "ARGENTINO": 1, 
    "ATL. PASTEUR": 2, 
    "ATL PASTEUR": 2, # Por si el HTML varía
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
    "CAEL": 8 # Usado a veces para El Linqueño
}

# IDs de Categorías según tu foto
CATEGORIAS = {
    "primera": 1,
    "septima": 2,
    "octava": 3,
    "novena": 4,
    "decima": 5
}