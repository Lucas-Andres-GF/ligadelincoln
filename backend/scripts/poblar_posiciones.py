import subprocess
import sys

python_exe = sys.executable

scripts = [
    [python_exe, "cargar_posiciones_primera.py"],
    [python_exe, "cargar_posiciones_septima.py"],
    [python_exe, "cargar_posiciones_octava.py"],
    [python_exe, "cargar_posiciones_decima.py"],
    # [python_exe, "cargar_posiciones_novena.py"],
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
