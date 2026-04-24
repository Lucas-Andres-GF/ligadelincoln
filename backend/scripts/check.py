from config import supabase

# Check alineaciones
r = supabase.table('alineaciones').select('*').execute()
print(f'Total alineaciones: {len(r.data)}')

# Verificar que tenga partido_id correcto
if r.data:
    # Ver un ejemplo
    print('\nEjemplo (último):')
    for a in r.data[-5:]:
        print(f'  Partido {a["partido_id"]}: Equipo {a["equipo_id"]}, #{a["numero"]}, titular={a["es_titular"]}')