import subprocess
import sys

python_exe = sys.executable  # Esto apunta al Python del entorno actual

scripts = [
    [python_exe, "cargar_fixture_primera.py"],
    [python_exe, "cargar_fixture_septima.py"],
    [python_exe, "cargar_fixture_octava.py"],
    [python_exe, "cargar_fixture_decima.py"],
    # [python_exe, "cargar_fixture_novena.py"],
]

for cmd in scripts:
    print(f"\n--- Ejecutando: {' '.join(cmd)} ---")
    result = subprocess.run(cmd)
    if result.returncode != 0:
        print(f"Error al ejecutar: {' '.join(cmd)} (código {result.returncode})")
        break
    else:
        print(f"Finalizado: {' '.join(cmd)}")
print("\nTodos los scripts ejecutados.")