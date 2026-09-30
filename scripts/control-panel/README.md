# Panel local de operaciones

Dashboard local para ejecutar scripts del proyecto sin usar la consola. Escucha únicamente en `127.0.0.1`.

## Ejecutar con el entorno del proyecto

Desde la raíz del repositorio, usá el lanzador:

```bash
./abrir-panel-liga.sh
```

El lanzador y el panel usan solamente el intérprete del entorno virtual del backend:

- `backend/venv/bin/python`
- `backend/venv/Scripts/python.exe`
- la ruta indicada por `LIGA_PYTHON`, si se define explícitamente

No hay fallback a `python` o `python3` del sistema. Si el entorno no existe, el lanzamiento falla con un mensaje visible.

Ejemplo con override:

```bash
LIGA_PYTHON=/ruta/al/venv/bin/python ./abrir-panel-liga.sh
```

Abre `http://127.0.0.1:8765`. Para cambiar el puerto o evitar que se abra el navegador:

```bash
CONTROL_PANEL_PORT=8766 CONTROL_PANEL_OPEN=0 ./abrir-panel-liga.sh
```

## Operaciones de scrapers

Cada scraper tiene dos acciones explícitas. Todas exigen un **ID de torneo positivo**; alineaciones también exige una **fecha positiva**.

| Acción | Alcance | Comportamiento |
|---|---|---|
| Previsualizar horarios | Torneo | No pasa `--execute`; no escribe en DB |
| Ejecutar horarios | Torneo | Pasa `--execute`; exige `ESCRIBIR` |
| Previsualizar resultados | Torneo y categoría opcional | No pasa `--execute`; no escribe en DB |
| Ejecutar resultados | Torneo y categoría opcional | Pasa `--execute`; exige `ESCRIBIR` |
| Previsualizar alineaciones | Torneo y fecha; solo Primera | No pasa `--execute`; no escribe en DB |
| Ejecutar alineaciones | Torneo y fecha; solo Primera | Pasa `--execute`; exige `ESCRIBIR` |

La previsualización es el comportamiento predeterminado de los scripts backend. Una escritura real requiere tanto elegir la acción **Ejecutar** como confirmar `ESCRIBIR`; el servidor vuelve a validar torneo, fecha, categoría y confirmación antes de crear el proceso.

La ingesta de horarios, resultados o alineaciones no construye ni despliega el frontend. Cualquier despliegue es una operación manual y separada.

## Programaciones especiales en Linux Mint

La sección **Programador** permite crear una ventana adicional para resultados, alineaciones o ambos procesos. Está pensada para partidos postergados o jornadas fuera de la programación habitual de sábados y domingos.

Se puede elegir:

- Una fecha puntual o un día semanal.
- Hora de inicio y de finalización.
- Frecuencia de 5, 10, 15, 20, 30 o 60 minutos.
- ID de torneo, categoría opcional para resultados y número de fecha para alineaciones.

Guardar exige confirmar `ESCRIBIR`. El backend valida todos los campos, genera unidades persistentes de `systemd --user` y las activa sin usar una shell intermedia. Las programaciones se guardan en `~/.local/share/ligadelincoln/schedules` y sus unidades en `~/.config/systemd/user`; cerrar el navegador o el panel no las cancela. Cada tarjeta activa se puede eliminar desde el mismo dashboard.

Esta función debe usarse abriendo el panel desde Mint. No reemplaza ni modifica los timers globales ya instalados para el fin de semana. Los timers de usuario vuelven a estar disponibles al iniciar sesión; si necesitás que corran antes del login, el administrador del equipo puede habilitar *linger* una sola vez para ese usuario.

Para auditar lo programado desde una terminal de Mint:

```bash
systemctl --user list-timers 'liga-panel-*'
```

## Otras acciones

Las operaciones de medios y redes conservan su comportamiento:

- Generar tablas, fixture y placas de resultados.
- Validar tablas sociales en modo dry-run.
- Subir tablas a Supabase Storage.
- Publicar tablas, resultados o fixture en Instagram/Facebook.

Las publicaciones externas exigen su confirmación propia (`S` o `Y`) y el panel pasa `--yes` al script para evitar una espera interactiva.

## Flujo recomendado para contenido social

1. Verificar o generar las imágenes necesarias.
2. Ejecutar **Publicar resultados**, **Publicar tablas** o **Publicar fixture**.
3. Confirmar escribiendo `S` o `Y`.
4. Elegir `both`, `instagram` o `facebook`.

Para resultados, el orden editorial recomendado es **Décima → Novena → Octava → Séptima → Primera**, seguido por tablas y fixture.

## Seguridad

- El panel corre solamente en `127.0.0.1`.
- Las credenciales no se envían al frontend.
- Las previsualizaciones están marcadas como seguras.
- Las acciones que escriben en DB o publican externamente están marcadas por riesgo.
- Los parámetros también se validan en el servidor; los atributos HTML no son la única barrera.
- Este panel es local y privado: no debe exponerse públicamente.
