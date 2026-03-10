import os
from datetime import date, timedelta
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()
supabase = create_client(os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_KEY"))

# Fecha 1 = Domingo 22/03/2026, luego cada domingo
INICIO = date(2026, 3, 22)
TOTAL_FECHAS = 11

print("📅 Calculando fechas del campeonato...\n")

for i in range(TOTAL_FECHAS):
    fecha_num = i + 1
    dia = INICIO + timedelta(weeks=i)
    dia_str = dia.strftime("%d/%m")

    print(f"  Fecha {fecha_num}: Dom {dia_str}")

    supabase.table("fixture") \
        .update({"dia": dia_str, "hora": "15:00"}) \
        .eq("fecha", fecha_num) \
        .execute()

print("\n✅ Todas las fechas y horarios actualizados.")
