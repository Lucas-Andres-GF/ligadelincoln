# -*- coding: utf-8 -*-
from config import supabase

# Obtener todos los partidos con visitante_id nulo
r = supabase.table("partidos").select("id").is_("visitante_id", None).execute()
print(f"Libres encontrados: {len(r.data)}")

# Actualizar uno por uno
actualizados = 0
for p in r.data:
    try:
        supabase.table("partidos").update({"estado": "jugado"}).eq("id", p['id']).execute()
        actualizados += 1
    except:
        pass

print(f"Libres actualizados a 'jugado': {actualizados}")
