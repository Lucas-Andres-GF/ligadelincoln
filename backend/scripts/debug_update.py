# -*- coding: utf-8 -*-
from config import supabase

# INSERTar nuevo registro
result = supabase.table("partidos").insert({
    "torneo_id": 1,
    "categoria_id": 1,
    "fecha_id": 99,
    "local_id": 1,
    "visitante_id": 2,
    "goles_local": 5,
    "goles_visitante": 3,
    "estado": "jugado",
    "dia": "2026-03-22"
}).execute()

print("Insert result:", result.data)
print("Error:", result.error)
