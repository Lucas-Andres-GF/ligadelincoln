# Tabla: alineaciones
#Jugadores por partido y equipo

from config import supabase

# Crear tabla alineaciones
tabla_alineaciones = """
CREATE TABLE IF NOT EXISTS alineaciones (
  id SERIAL PRIMARY KEY,
  created_at TIMESTAMP DEFAULT NOW(),
  partido_id INTEGER NOT NULL,
  equipo_id INTEGER NOT NULL,
  jugador TEXT NOT NULL,
  numero INTEGER NOT NULL,
  es_titular BOOLEAN DEFAULT true,
  tiempo TEXT DEFAULT 'PT',  -- PT (primer tiempo) o ST (segundo tiempo)
  FOREIGN KEY (partido_id) REFERENCES partidos(id),
  FOREIGN KEY (equipo_id) REFERENCES clubes(id)
);
"""

# Crear tabla goleadores_partido
tabla_goleadores = """
CREATE TABLE IF NOT EXISTS goleadores_partido (
  id SERIAL PRIMARY KEY,
  created_at TIMESTAMP DEFAULT NOW(),
  partido_id INTEGER NOT NULL,
  equipo_id INTEGER NOT NULL,
  jugador TEXT NOT NULL,
  tiempo TEXT,  -- PT o ST o null
  FOREIGN KEY (partido_id) REFERENCES partidos(id),
  FOREIGN KEY (equipo_id) REFERENCES clubes(id)
);
"""

print("Tablas creadas (o ya existentes)")
print("- alineaciones")
print("- goleadores_partido")