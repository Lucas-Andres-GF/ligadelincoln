# Operar el backend de forma segura

Esta es la **fuente canónica** para importar, verificar y actualizar datos del backend. Empezá siempre por una previsualización, revisá el alcance y recién después repetí el mismo comando con `--execute`.

> **Reemplazá todos los marcadores** como `<TORNEO_ID>`, `<FECHA>`, `<COMPETENCIA>`, `<CATEGORIA>`, `<CLUB_ID>` y `<RUTA_PROYECTO>` antes de ejecutar. Los ejemplos los mantienen entre `<...>` para que un valor de producción nunca quede implícito.

## Reglas de seguridad

1. **Sin `--execute` no hay escritura.** Nueve comandos escritores previsualizan por defecto. Comparación y auditoría son siempre de solo lectura.
2. **Usá un torneo explícito.** Los comandos de alta, historia y palmarés exigen `--torneo-id`. Los tres scrapers recurrentes pueden tomar un `ACTIVE_TORNEO_ID` positivo y validado, pero el panel y los runners pasan el ID explícitamente.
3. **No confundas identidad con estado activo.** El ID del torneo es inmutable: no se recicla, renumera ni se deduce desde un nombre, slug o perfil.
4. **No ejecutes un plan bloqueado o inesperado.** Un código `1`, una categoría omitida, una diferencia no explicada o un conteo distinto al esperado requiere investigación.
5. **Las escrituras son secuenciales y no transaccionales.** Una falla puede dejar cambios parciales. Leé el estado resultante y recuperá solamente el alcance afectado.
6. **No hagas borrados amplios ni reintentos ciegos.** Respaldá, volvé a previsualizar y aplicá una reparación estrecha. Usá SQL manual solo con una consulta explícitamente revisada.
7. **La ingesta no despliega el frontend ni publica contenido.** Deploy, placas, medios y redes sociales son operaciones separadas.
8. **RLS no se administra desde estas CLI.** Todo cambio de políticas o permisos SQL se realiza manualmente en SQL Editor, con revisión independiente.

## Camino rápido

### Torneo actual nuevo

1. Confirmá intérprete, variables y respaldo.
2. Previsualizá e importá el fixture.
3. Previsualizá e inicializá posiciones.
4. Previsualizá y activá el torneo.
5. Verificá fixture, posiciones y unicidad del torneo activo.

Orden obligatorio:

```text
importar fixture -> inicializar posiciones -> activar
```

La importación **nunca activa** el torneo.

### Operación recurrente

Cuando las fuentes oficiales correspondan al torneo y fecha esperados:

```text
horarios -> resultados -> alineaciones de Primera
```

Alineaciones se ejecuta únicamente cuando la página oficial muestra la fecha correcta. No es una fuente histórica estable.

### Torneo histórico

```text
importar inactivo -> comparar y auditar -> corregir solo un plan válido -> cargar palmarés explícito
```

Nunca actives una importación histórica por inferencia y nunca deduzcas el campeón desde posiciones o resultados.

## Alcance de esta guía

| Incluye | No incluye |
|---|---|
| Fixture actual e histórico | Deploy del frontend |
| Posiciones, horarios y resultados | Generación de placas o capturas |
| Alineaciones de Primera | Publicación en Instagram/Facebook |
| Activación explícita de torneos | Cambios RLS o migraciones SQL |
| Comparación, auditoría y corrección | Instalación de runtime o dependencias |
| Palmarés explícito | Operaciones externas implícitas |

Para panel, systemd, medios, redes y deploy manual, usá [`../COMANDOS.md`](../COMANDOS.md). Para el panel en detalle, consultá [`../scripts/control-panel/README.md`](../scripts/control-panel/README.md).

## Preparar el entorno existente

Trabajá desde la raíz del repositorio. Esta guía **no instala** Python, paquetes ni navegadores: el entorno virtual del proyecto debe existir y estar aprovisionado.

### Linux

```bash
cd "<RUTA_PROYECTO>"
PYTHON_PROYECTO="./backend/venv/bin/python"
"$PYTHON_PROYECTO" --version
```

### Windows PowerShell

```powershell
Set-Location "<RUTA_PROYECTO>"
$PYTHON_PROYECTO = ".\backend\venv\Scripts\python.exe"
& $PYTHON_PROYECTO --version
```

Los ejemplos siguientes usan sintaxis de shell Linux con `"$PYTHON_PROYECTO"`. En PowerShell, reemplazá ese prefijo por `& $PYTHON_PROYECTO`; los nombres y opciones de cada CLI no cambian.

### Variables y credenciales

El backend carga `backend/.env` sin sobrescribir variables ya presentes en el proceso.

- `SUPABASE_URL` y `SUPABASE_KEY` son obligatorias para acceder a la base.
- `ACTIVE_TORNEO_ID` es opcional para invocaciones manuales de los scrapers recurrentes; debe ser un entero positivo.
- Los runners programados requieren un `ACTIVE_TORNEO_ID` válido y pasan luego `--torneo-id` explícitamente.
- No pegues valores de credenciales en comandos, documentación, logs o tickets.
- Verificá que las credenciales correspondan al ambiente esperado antes de una previsualización.

## Identidad y perfiles de torneo

- Elegí un `<TORNEO_ID>` positivo y único antes del alta. Ese ID queda asociado para siempre al mismo torneo.
- Nombre, slug, temporada y estado activo son atributos; ninguno reemplaza al ID.
- Los comandos de setup e historia requieren `--torneo-id` explícito y no consultan `ACTIVE_TORNEO_ID`.
- Los scrapers `horarios`, `resultados` y `alineaciones` aceptan `ACTIVE_TORNEO_ID` como alternativa validada para uso directo. Para una intervención humana, preferí igualmente `--torneo-id` visible.
- El perfil de fuente describe formato, URLs, metadatos y completitud. **No contiene ningún ID de base de datos.**
- El perfil incorporado `primavera-verano-2026` representa el estado soportado actual: fechas 1 a 11 y 307 filas en total (`66/56/63/56/66` para Primera/Séptima/Octava/Novena/Décima). Es una referencia versionada, no un default de identidad.
- Un torneo futuro necesita un perfil de fuente nuevo y versionado; no reutilices ni modifiques silenciosamente el perfil existente para otra competencia.

## Matriz de las 11 CLI

Todas las categorías admitidas son `primera`, `septima`, `octava`, `novena` y `decima`. Cuando una opción de categoría es repetible, omitida significa todas las categorías soportadas por esa fuente/perfil.

| CLI | Modo | Alcance/opciones obligatorias | Comportamiento por defecto | Escrituras que posee | Salida/cautela |
|---|---|---|---|---|---|
| `importar_fixture_torneo.py` | Escritura protegida | `--profile`, `--torneo-id`; opcionales repetibles `--category`, `--source`; `--torneo-nombre`, `--slug`, `--replace-existing`, `--timeout` | Previsualiza todas las categorías del perfil | `torneos` (alta/metadatos) y `partidos`; con reemplazo elimina solo partidos de categorías seleccionadas | `0/1/2`; nunca agrega sobre fixture existente |
| `inicializar_posiciones_torneo.py` | Escritura protegida | `--profile`, `--torneo-id`; `--category` repetible | Previsualiza posiciones cero faltantes | Inserta filas cero en `posiciones` | `0/1/2`; bloquea fixture con resultados o posiciones no-cero |
| `activar_torneo.py` | Escritura protegida | `--profile`, `--torneo-id` | Valida fixture y posiciones; no activa | `torneos.activo`, objetivo primero y luego desactivaciones | `0/1/2`; puede dejar múltiples activos ante falla parcial |
| `scraper_horarios.py` | Escritura protegida | `--torneo-id` o `ACTIVE_TORNEO_ID`; opcionales `--source`, `--timeout` | Previsualiza coincidencias del cronograma | Actualiza `partidos.dia`, `hora`, `cancha` | `0/1/2`; plan completo y targets únicos |
| `scraper_resultados.py` | Escritura protegida | `--torneo-id` o `ACTIVE_TORNEO_ID`; `--category` y `--source` repetibles; `--timeout` | Previsualiza todas las categorías y posiciones proyectadas | Actualiza resultados/estado en `partidos`; actualiza o inserta `posiciones` | `0/1/2`; resultados se escriben antes que posiciones |
| `scraper_alineaciones.py` | Escritura protegida | `--fecha`; `--torneo-id` o `ACTIVE_TORNEO_ID`; opcionales `--source`, `--timeout` | Previsualiza reemplazo de Primera | Borra/inserta `alineaciones`; actualiza `dt_local`, `dt_visitante`, `arbitro` en `partidos` | `0/1/2`; fuente actual, no archivo histórico |
| `importar_torneo_historico_oficial.py` | Escritura protegida | `--torneo-id`, `--nombre`, `--competencia`; opcionales `--slug`, `--categoria`, `--force`, `--json` | Previsualiza todas las categorías; torneo inactivo | Alta/actualiza torneo inactivo e inserta `partidos`/`posiciones`; `--force` reemplaza alcance seleccionado | `0/1`; puede continuar por categorías y quedar parcial |
| `comparar_partidos_oficiales.py` | Solo lectura | `--torneo-id`, `--competencia`; opcionales `--categoria`, `--json` | Compara todas las categorías | Ninguna | `0` limpio, `1` diferencias, `2` falla operacional |
| `auditar_torneo_oficial.py` | Solo lectura | `--torneo-id`, `--competencia`; opcionales `--categoria`, `--json` | Audita todas las categorías | Ninguna | `0` limpio, `1` diferencias, `2` falla operacional |
| `corregir_resultados_desde_oficial.py` | Escritura protegida | `--torneo-id`, `--competencia`; opcionales `--categoria`, `--include-dates`, `--json` | Propone correcciones; ignora cambios de fecha salvo pedido explícito | Actualiza partidos existentes y actualiza/inserta posiciones; no inserta partidos ni borra posiciones | `0/1`; omite categorías cuya estructura no coincide exactamente |
| `upsert_palmares.py` | Escritura protegida | `--torneo-id`, `--categoria-id`, `--club-id`, `--nombre`, `--temporada`; opcionales `--replace-existing`, `--json` | Valida referencias y propone inserción/no-op | Inserta o actualiza un registro de `palmares` | `0/1/2`; conflicto requiere reemplazo estrecho explícito |

`argparse` usa código `2` para opciones inválidas o faltantes antes de entrar a la lógica de cada comando.

## Recetas: siempre previsualizar y luego ejecutar

Los pares siguientes deben conservar exactamente el mismo alcance entre pasos. Si cambió la fuente, la base o el plan, no ejecutes: previsualizá otra vez.

### 1. Importar fixture actual

Previsualización completa del perfil:

```bash
"$PYTHON_PROYECTO" backend/scripts/importar_fixture_torneo.py \
  --profile primavera-verano-2026 \
  --torneo-id "<TORNEO_ID>"
```

Ejecución del mismo plan:

```bash
"$PYTHON_PROYECTO" backend/scripts/importar_fixture_torneo.py \
  --profile primavera-verano-2026 \
  --torneo-id "<TORNEO_ID>" \
  --execute
```

Para limitar una recuperación, repetí `--category` solo por las categorías revisadas. Para una fuente local o alternativa revisada, repetí `--source <CATEGORIA>=<URL_O_RUTA>` junto con la categoría seleccionada.

#### Política de reemplazo actual

La importación no hace append. Si ya hay partidos en una categoría seleccionada, bloquea salvo que agregues `--replace-existing`. Aun con esa opción, bloquea el reemplazo cuando encuentra:

- partidos jugados o con goles;
- posiciones en las categorías seleccionadas;
- alineaciones asociadas a los partidos seleccionados;
- estados de fixture no reemplazables o inventarios incompletos/malformados.

Previsualización de reemplazo estrecho:

```bash
"$PYTHON_PROYECTO" backend/scripts/importar_fixture_torneo.py \
  --profile primavera-verano-2026 \
  --torneo-id "<TORNEO_ID>" \
  --category "<CATEGORIA>" \
  --replace-existing
```

Solo si el plan es válido y el respaldo fue confirmado:

```bash
"$PYTHON_PROYECTO" backend/scripts/importar_fixture_torneo.py \
  --profile primavera-verano-2026 \
  --torneo-id "<TORNEO_ID>" \
  --category "<CATEGORIA>" \
  --replace-existing \
  --execute
```

### 2. Inicializar posiciones

```bash
# Previsualizar
"$PYTHON_PROYECTO" backend/scripts/inicializar_posiciones_torneo.py \
  --profile primavera-verano-2026 \
  --torneo-id "<TORNEO_ID>"

# Ejecutar el mismo alcance
"$PYTHON_PROYECTO" backend/scripts/inicializar_posiciones_torneo.py \
  --profile primavera-verano-2026 \
  --torneo-id "<TORNEO_ID>" \
  --execute
```

El comando solo completa posiciones cero faltantes para participantes derivados del fixture. No sirve para reiniciar una tabla empezada.

### 3. Activar el torneo actual

```bash
# Previsualizar
"$PYTHON_PROYECTO" backend/scripts/activar_torneo.py \
  --profile primavera-verano-2026 \
  --torneo-id "<TORNEO_ID>"

# Ejecutar el mismo alcance
"$PYTHON_PROYECTO" backend/scripts/activar_torneo.py \
  --profile primavera-verano-2026 \
  --torneo-id "<TORNEO_ID>" \
  --execute
```

La activación valida perfil, fixture y posiciones. Es objetivo-primero: activa el elegido y después desactiva los IDs activos previamente inventariados.

### 4. Actualizar horarios

```bash
# Previsualizar
"$PYTHON_PROYECTO" backend/scripts/scraper_horarios.py \
  --torneo-id "<TORNEO_ID>"

# Ejecutar
"$PYTHON_PROYECTO" backend/scripts/scraper_horarios.py \
  --torneo-id "<TORNEO_ID>" \
  --execute
```

### 5. Actualizar resultados y una categoría

Sin `--category`, procesa todas las categorías. La opción es repetible.

```bash
# Previsualizar una categoría
"$PYTHON_PROYECTO" backend/scripts/scraper_resultados.py \
  --torneo-id "<TORNEO_ID>" \
  --category "<CATEGORIA>"

# Ejecutar el mismo alcance
"$PYTHON_PROYECTO" backend/scripts/scraper_resultados.py \
  --torneo-id "<TORNEO_ID>" \
  --category "<CATEGORIA>" \
  --execute
```

### 6. Reemplazar alineaciones de Primera

Confirmá visualmente que la fuente oficial muestra `<FECHA>` y los partidos esperados.

```bash
# Previsualizar
"$PYTHON_PROYECTO" backend/scripts/scraper_alineaciones.py \
  --torneo-id "<TORNEO_ID>" \
  --fecha "<FECHA>"

# Ejecutar
"$PYTHON_PROYECTO" backend/scripts/scraper_alineaciones.py \
  --torneo-id "<TORNEO_ID>" \
  --fecha "<FECHA>" \
  --execute
```

Solo reemplaza alineaciones de Primera y los metadatos de DT/árbitro. No modifica marcador, estado ni posiciones.

### 7. Importar un torneo histórico inactivo

`<COMPETENCIA>` debe ser una elección admitida por `--help`. El torneo queda inactivo.

```bash
# Previsualizar
"$PYTHON_PROYECTO" backend/scripts/importar_torneo_historico_oficial.py \
  --torneo-id "<TORNEO_ID>" \
  --nombre "<NOMBRE_TORNEO>" \
  --slug "<SLUG_TORNEO>" \
  --competencia "<COMPETENCIA>"

# Ejecutar
"$PYTHON_PROYECTO" backend/scripts/importar_torneo_historico_oficial.py \
  --torneo-id "<TORNEO_ID>" \
  --nombre "<NOMBRE_TORNEO>" \
  --slug "<SLUG_TORNEO>" \
  --competencia "<COMPETENCIA>" \
  --execute
```

No hace append sobre categorías con partidos o posiciones. `--force` elimina y reemplaza **solo** `partidos` y `posiciones` del torneo/categoría seleccionados; no omite validaciones de integridad. Para usarlo, agregá también `--categoria "<CATEGORIA>"`, hacé respaldo y revisá primero la previsualización exacta.

### 8. Comparar partidos históricos

Siempre es solo lectura; no existe paso de ejecución.

```bash
"$PYTHON_PROYECTO" backend/scripts/comparar_partidos_oficiales.py \
  --torneo-id "<TORNEO_ID>" \
  --competencia "<COMPETENCIA>" \
  --categoria "<CATEGORIA>"
```

Omití `--categoria` para comparar todas.

### 9. Auditar torneo histórico

Siempre es solo lectura; contrasta posiciones y el inventario de partidos.

```bash
"$PYTHON_PROYECTO" backend/scripts/auditar_torneo_oficial.py \
  --torneo-id "<TORNEO_ID>" \
  --competencia "<COMPETENCIA>" \
  --categoria "<CATEGORIA>"
```

### 10. Corregir resultados históricos

Primero exigí inventario competitivo exacto y un plan sin categorías omitidas.

```bash
# Previsualizar
"$PYTHON_PROYECTO" backend/scripts/corregir_resultados_desde_oficial.py \
  --torneo-id "<TORNEO_ID>" \
  --competencia "<COMPETENCIA>" \
  --categoria "<CATEGORIA>"

# Ejecutar
"$PYTHON_PROYECTO" backend/scripts/corregir_resultados_desde_oficial.py \
  --torneo-id "<TORNEO_ID>" \
  --competencia "<COMPETENCIA>" \
  --categoria "<CATEGORIA>" \
  --execute
```

Por defecto informa pero no corrige diferencias solo de fecha. `--include-dates` debe aparecer tanto en la previsualización como en la ejecución si el cambio de `dia` fue revisado. El comando nunca inserta partidos ni elimina posiciones.

### 11. Registrar palmarés explícito

El operador debe aportar campeón, categoría, nombre y temporada desde evidencia oficial. No los infieras.

```bash
# Previsualizar
"$PYTHON_PROYECTO" backend/scripts/upsert_palmares.py \
  --torneo-id "<TORNEO_ID>" \
  --categoria-id "<CATEGORIA_ID>" \
  --club-id "<CLUB_ID>" \
  --nombre "<NOMBRE_CAMPEONATO>" \
  --temporada "<TEMPORADA>"

# Ejecutar
"$PYTHON_PROYECTO" backend/scripts/upsert_palmares.py \
  --torneo-id "<TORNEO_ID>" \
  --categoria-id "<CATEGORIA_ID>" \
  --club-id "<CLUB_ID>" \
  --nombre "<NOMBRE_CAMPEONATO>" \
  --temporada "<TEMPORADA>" \
  --execute
```

Si existe un registro conflictivo, `--replace-existing` permite únicamente esa actualización estrecha y debe incluirse en ambos pasos.

## Checklist antes de escribir

- [ ] Estoy en la raíz correcta y uso el intérprete de `backend/venv`.
- [ ] Reemplacé cada marcador y verifiqué el `<TORNEO_ID>` contra la base.
- [ ] Las credenciales apuntan al ambiente correcto sin exponer sus valores.
- [ ] La fuente oficial corresponde a competencia, categoría y fecha esperadas.
- [ ] Guardé un respaldo verificable del alcance que puede mutar.
- [ ] Ejecuté la previsualización inmediatamente antes de escribir.
- [ ] El plan no tiene bloqueos, omisiones inesperadas ni targets ambiguos.
- [ ] Conteos, categorías, fechas y acciones coinciden con mi intención.
- [ ] Entiendo el orden secuencial de escrituras y el playbook de recuperación aplicable.
- [ ] Para historia, el torneo seguirá inactivo y el campeón se cargará por separado.

## Checklist después de escribir

- [ ] Guardé salida, código de proceso y hora de la operación.
- [ ] Repetí la previsualización o una lectura equivalente para confirmar no-op/estado esperado.
- [ ] Verifiqué solamente el torneo, categorías, fecha y tablas afectadas.
- [ ] Para resultados, confirmé tanto `partidos` como `posiciones`.
- [ ] Para alineaciones, confirmé filas y metadatos de cada partido objetivo.
- [ ] Para activación, confirmé que existe exactamente un torneo activo.
- [ ] Para historia, ejecuté comparación y auditoría; ambos terminaron en `0`.
- [ ] No hubo deploy, publicación social ni cambio RLS implícito.

## Recuperación de escrituras parciales

> Regla común: detené nuevas escrituras, conservá la salida, identificá la última acción confirmada y leé el alcance exacto. No uses borrados generales, no cambies de torneo y no repitas `--execute` sin una nueva previsualización. Si la CLI no puede expresar la reparación estrecha, restaurá el respaldo o prepará SQL manual explícitamente revisado.

### Activación dejó múltiples torneos activos

La activación escribe el objetivo primero y desactiva después.

1. Leé el objetivo y el inventario de torneos activos.
2. Confirmá que el objetivo conserva fixture y posiciones válidos.
3. Volvé a previsualizar `activar_torneo.py` con el mismo perfil e ID.
4. Ejecutá solo si el nuevo plan enumera exactamente los IDs extra que debés desactivar.
5. Verificá que quede un único activo. Si el inventario no coincide, no improvises una desactivación masiva: revisá SQL estrecho o respaldo.

### Resultado escrito antes de posiciones

`resultados` actualiza partidos antes de actualizar/insertar posiciones.

1. Leé los partidos reportados como actualizados y las posiciones de las categorías seleccionadas.
2. Volvé a previsualizar la misma categoría: la proyección se recalcula desde el fixture completo ya persistido.
3. Ejecutá solo si el plan ahora propone exclusivamente la sincronización esperada de posiciones y no contiene drift estructural.
4. Confirmá resultados y tabla. Ante filas stale o identidades ambiguas, frená y revisá una reparación manual acotada.

### Alineaciones fallaron entre delete, insert y update

Cada partido pasa secuencialmente por borrado de alineaciones, inserción y actualización de metadatos.

1. Identificá el último `fixture` procesado y leé sus alineaciones y campos `dt_local`, `dt_visitante`, `arbitro`.
2. Conservá la fuente exacta usada; si la página oficial ya cambió, usá un archivo local respaldado, no la fuente actual.
3. Previsualizá otra vez el torneo/fecha y comprobá que todos los partidos jugados esperados estén presentes.
4. Si una eliminación quedó sin reinserción, restaurá el respaldo o ejecutá un reemplazo completo solo después de validar el nuevo plan exacto. No insertes filas a ciegas.
5. Verificá partido por partido.

### Importación histórica quedó parcial por categorías

El importador puede continuar después de una falla de categoría y dejar el torneo inactivo con otras categorías importadas.

1. Leé `torneos`, `partidos` y `posiciones` por torneo y categoría; registrá cuáles quedaron completas.
2. Ejecutá comparación/auditoría de las categorías existentes.
3. Previsualizá únicamente la categoría incompleta con `--categoria "<CATEGORIA>"`.
4. Si existen filas parciales, usá `--force` solo para esa categoría, con respaldo y después de confirmar que el plan oficial es íntegro.
5. Repetí comparación y auditoría. No actives el torneo histórico.

### Corrección dejó diferencias

1. Volvé a ejecutar comparación y auditoría de solo lectura.
2. Separá drift restante, diferencias de fecha ignoradas y fallas operacionales.
3. Previsualizá la corrección de una categoría. Usá `--include-dates` únicamente si esas fechas fueron revisadas.
4. No repitas la ejecución si faltan/sobran partidos o hay duplicados: esas categorías se omiten por seguridad y requieren otra reparación acotada.
5. Cerrá con comparación y auditoría en `0`.

### Importación actual parcial o reemplazo bloqueado

1. Leé metadatos del torneo, inventario de partidos, posiciones y alineaciones por categoría seleccionada.
2. Compará los conteos contra el perfil y la salida guardada; no asumas que una categoría se insertó completa.
3. Si el reemplazo está bloqueado por resultados, posiciones o alineaciones, preservá esos datos y escalá una reparación revisada; no fuerces un append ni borres dependencias.
4. Solo cuando el alcance sea reemplazable y esté respaldado, previsualizá `--replace-existing` por una categoría y ejecutá ese mismo plan.
5. Después, reiniciá el flujo normal desde verificación de fixture; no actives hasta completar posiciones.

## Scheduler de resultados y alineaciones: systemd de sistema

Los únicos schedulers de ingesta son `scraper-resultados.timer` y `scraper-alineaciones.timer`, ambos a nivel sistema. `scripts/crontab` conserva solamente automatización de medios y **no debe** invocar los runners de ingesta.

Ambos timers disparan cada 5 minutos los sábados y domingos de 13:00 a 21:55 (ventana 13-22 hs Argentina), según la zona horaria local del host. Cada runner vuelve a validar `13 <= hora < 22` y sábado/domingo antes de ejecutar. El unit no fija `Timezone=`: verificá la zona del host con `timedatectl` antes de confiar en el horario.

Para excepciones entre semana (partidos reprogramados), forzá una corrida manual ignorando día/hora con `LIGA_FORCE=1`:

```bash
LIGA_FORCE=1 /home/gallardo/Documentos/ligadelincoln/scripts/run_scraper_resultados.sh
LIGA_FORCE=1 /home/gallardo/Documentos/ligadelincoln/scripts/run_scraper_alineaciones.sh
```

El scraper de alineaciones no exige `--fecha`: toma la fecha actual desde la propia página oficial, y si todavía no publicaron alineaciones termina como no-op sin error.

```bash
# Estado e inventario
systemctl status scraper-resultados.timer scraper-alineaciones.timer
systemctl list-timers --all

# Logs del unit y del runner
journalctl -u scraper-resultados.service --no-pager -r
journalctl -u scraper-alineaciones.service --no-pager -r
tail -f "<SCRAPER_LOG_DIR>/scraper_resultados.log"
tail -f "<SCRAPER_LOG_DIR>/scraper_alineaciones.log"

# Recargar unidades revisadas y reiniciar los timers
sudo systemctl daemon-reload
sudo systemctl restart scraper-resultados.timer scraper-alineaciones.timer

# Instalar las unidades versionadas y habilitar los timers
sudo ./scripts/install_scraper_systemd.sh
```

La instalación versionada copia `scraper-resultados.{service,timer}` y `scraper-alineaciones.{service,timer}` a `/etc/systemd/system/`, ejecuta `systemctl daemon-reload` y `systemctl enable --now` para ambos timers. No agregues un segundo cron, timer de usuario o scheduler externo para resultados ni alineaciones.

## Panel local

El panel usa el intérprete del proyecto y escucha en `127.0.0.1`. Expone previsualización y ejecución para horarios, resultados y alineaciones; no cubre el flujo completo de setup/historia.

- La acción **Previsualizar** no pasa `--execute`.
- La acción **Ejecutar** pasa `--execute` y exige escribir `ESCRIBIR`.
- El servidor valida nuevamente torneo, fecha, categoría y confirmación.
- El panel no construye ni despliega el frontend.
- El panel no convierte medios/publicaciones en parte de la ingesta backend.

Lanzamiento y opciones: [`../scripts/control-panel/README.md`](../scripts/control-panel/README.md).

## Códigos de salida

| Código | Significado operativo | Acción |
|---|---|---|
| `0` | Plan válido/ejecución terminada; en auditoría y comparación, sin drift | Hacer verificación posterior; no asumir atomicidad |
| `1` | Plan inválido o bloqueado; en auditoría/comparación, drift; en importador histórico/corrector, también falla operacional capturada | Leer el reporte, acotar causa y volver a previsualizar |
| `2` | Falla operacional en la mayoría de CLI; también error de uso de `argparse` | Corregir entorno/opciones; no ejecutar a ciegas |

Particularidades:

- `comparar_partidos_oficiales.py` y `auditar_torneo_oficial.py`: `0` limpio, `1` drift, `2` operacional.
- La mayoría de comandos seguros: `0` éxito, `1` plan inválido/bloqueado, `2` operacional.
- `corregir_resultados_desde_oficial.py` e `importar_torneo_historico_oficial.py`: la lógica del comando usa `0/1`; una invocación inválida todavía puede terminar en `2` por `argparse`.

## Diagnóstico rápido

| Síntoma | Revisar primero | Respuesta segura |
|---|---|---|
| Falta intérprete | `backend/venv/Scripts/python.exe` o `backend/venv/bin/python` | Detenerse; aprovisionar fuera de esta guía, sin fallback al Python del sistema |
| Faltan credenciales | Presencia de `SUPABASE_URL` y `SUPABASE_KEY`, sin imprimir valores | Corregir ambiente y repetir previsualización |
| Falta ID de torneo | `--torneo-id` o, solo en scrapers recurrentes directos, `ACTIVE_TORNEO_ID` positivo | Pasar alcance explícito |
| Plan bloqueado | `Blocking issues`, categorías `skipped` o `manual_review_required` | No agregar `--execute`; resolver la causa |
| Fuente no coincide | Competencia, categoría, fecha, equipos y conteos | No escribir; esperar/corregir fuente revisada |
| Diferencias solo de fecha | Reporte del corrector | Mantenerlas informativas o revisar `--include-dates` en ambos pasos |
| Timer fuera de hora | `timedatectl`, `systemctl list-timers --all`, gate del runner | Corregir zona/configuración; no sumar otro scheduler |
| Drift después de escritura | Comparación/auditoría y readback acotado | Seguir el playbook correspondiente |
| Cambio RLS necesario | Política SQL requerida | Ejecutarlo manualmente en SQL Editor tras revisión; ninguna CLI de esta guía lo aplica |
