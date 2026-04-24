from supabase import create_client
import os
from dotenv import load_dotenv
load_dotenv()

url = os.getenv('SUPABASE_URL')
key = os.getenv('SUPABASE_KEY')
supabase = create_client(url, key)

# Check how many alineaciones have each partido
result = supabase.table('alineaciones').select('partido_id').execute()
from collections import Counter
partidos_count = Counter(r['partido_id'] for r in result.data)

print("Partidos con alineaciones (>0):")
for pid, count in sorted(partidos_count.items()):
    print(f"  Partido {pid}: {count} alineaciones")