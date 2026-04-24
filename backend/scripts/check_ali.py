from config import supabase

r = supabase.table('alineaciones').select('*').execute()
print(f'Jugadores guardados: {len(r.data)}')

if r.data:
    # Ver ultimo equipo
    eq9 = [a for a in r.data if a['equipo_id'] == 9]
    print(f'Equipo 9 (Juventud Unida): {len(eq9)} jugadores')
    for a in eq9[:5]:
        print(f'  #{a["numero"]}: es_titular={a["es_titular"]}')