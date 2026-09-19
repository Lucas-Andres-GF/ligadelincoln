# Comandos útiles - Liga de Lincoln

## Ver próximas ejecuciones de los timers

```bash
systemctl --user list-timers --all
```

## Ver historial de ejecuciones (systemd)

```bash
# Ver todas las ejecuciones recientes
journalctl --user -u scraper-resultados.service --no-pager -r | head -30

# Solo ver inicio/fin de cada ejecución
journalctl --user -u scraper-resultados.service --no-pager | grep -E "(Started|Finished|Failed)"

# Ver logs del generador de placas
journalctl --user -u generador-placas.service --no-pager -r | head -20
```

## Ver log del script (archivo)

```bash
# Ver todo el log
cat /home/gallardo/logs/scraper_resultados.log

# Ver últimas líneas (tiempo real)
tail -f /home/gallardo/logs/scraper_resultados.log

# Ver solo timestamps
grep "^===" /home/gallardo/logs/scraper_resultados.log

# Ver log del generador de placas de resultados
tail -f /home/gallardo/logs/generador_placas.log
```

## Estado de los servicios

```bash
# Ver estado del timer
systemctl --user status scraper-resultados.timer

# Ver estado del servicio
systemctl --user status scraper-resultados.service
```

## Reiniciar si hay problemas

```bash
# Recargar configuración
systemctl --user daemon-reload

# Reiniciar timer
systemctl --user restart scraper-resultados.timer
```

## Horarios de ejecución automática

| Servicio | Frecuencia | Horario Argentina |
|----------|------------|-------------------|
| scraper-resultados | cada 15 min | Sáb/Dom 14-21hs |
| placas-resultados | semanal | Domingos 22:15hs |

---

## Scripts manuales (corrida operativa)

### Scraper de horarios (inicio de semana)

Previsualiza cambios de fecha, hora y cancha para un torneo explícito:

```bash
cd /home/gallardo/Documentos/ligadelincoln
backend/venv/bin/python backend/scripts/scraper_horarios.py --torneo-id 2
```

Para aplicar la actualización después de revisar el reporte:

```bash
backend/venv/bin/python backend/scripts/scraper_horarios.py --torneo-id 2 --execute
```

### Scraper de resultados

Previsualiza resultados y posiciones para todas las categorías del torneo:

```bash
cd /home/gallardo/Documentos/ligadelincoln
backend/venv/bin/python backend/scripts/scraper_resultados.py --torneo-id 2
```

Se puede limitar la previsualización a una categoría con `--category primera`. Para escribir realmente:

```bash
backend/venv/bin/python backend/scripts/scraper_resultados.py --torneo-id 2 --category primera --execute
```

### Scraper de alineaciones (cuando la web ya esté actualizada)

El scraper reemplaza alineaciones de **Primera** y actualiza únicamente sus metadatos de DT local, DT visitante y árbitro. No actualiza resultados, estado del partido ni posiciones.

La invocación predeterminada es una previsualización sin escrituras y requiere torneo y fecha explícitos:

```bash
cd /home/gallardo/Documentos/ligadelincoln
backend/venv/bin/python backend/scripts/scraper_alineaciones.py --torneo-id 2 --fecha 7
```

Después de revisar un plan válido, la escritura real requiere `--execute`:

```bash
backend/venv/bin/python backend/scripts/scraper_alineaciones.py --torneo-id 2 --fecha 7 --execute
```

**Cuándo correrlo**

- Cuando la web `alineaciones.html` ya muestre la fecha correcta y sus jugadores.
- También sirve para la fecha completa cuando la Liga publica todas las alineaciones de Primera.

**Importante**

- `alineaciones.html` muestra la **fecha actual**; no es una fuente histórica estable.
- Verificar visualmente la fecha y los partidos antes de previsualizar.
- Una previsualización válida informa qué alineaciones y metadatos reemplazaría sin mutar la base.
- Si la web cambia de fecha, esa misma URL ya no permite reconstruir alineaciones anteriores.
- La ingesta no ejecuta despliegues. El despliegue manual documentado más abajo es una acción separada.

### Capturar fixture (inicio de semana)
Genera imágenes PNG del fixture por categoría y fecha.

```bash
python3 /home/gallardo/Documentos/ligadelincoln/scripts/capturar_fixture.py
```

### Capturar tablas (opcional)
Genera imágenes PNG de las tablas de posiciones.

```bash
python3 /home/gallardo/Documentos/ligadelincoln/scripts/capturar_tablas.py
```

### Generar placas de resultados (manual, si no funciona el timer)
Genera las placas de resultado final. Si no indicás fecha, usa la última fecha jugada.

```bash
/home/gallardo/Documentos/ligadelincoln/scripts/generar_placas_resultados.sh
```

Para una fecha concreta:

```bash
/home/gallardo/Documentos/ligadelincoln/scripts/generar_placas_resultados.sh --fecha 11
```

Para una categoría concreta:

```bash
/home/gallardo/Documentos/ligadelincoln/scripts/generar_placas_resultados.sh --fecha 11 --categoria primera
```

---

## Workflow semanal

| Día | Acción | Comando |
|-----|--------|---------|
| Inicio de semana | Previsualizar y luego ejecutar horarios del torneo | `backend/venv/bin/python backend/scripts/scraper_horarios.py --torneo-id 2 [--execute]` |
| Inicio de semana | Capturar fixture | `python3 capturar_fixture.py` |
| Cuando la web ya fue actualizada | Previsualizar y luego reemplazar alineaciones/metadatos de Primera | `backend/venv/bin/python backend/scripts/scraper_alineaciones.py --torneo-id 2 --fecha 7 [--execute]` |
| Después de actualizar datos, si corresponde | Deploy manual y separado del frontend | `pnpm run deploy` |
| Sábados | Resultados (automático) | Timer systemd cada 15min (14-21hs) |
| Domingos 22:15 | Generar placas de resultados (automático) | Timer systemd |

---

## Flujo recomendado de trabajo

### 1) Inicio de semana

```bash
cd /home/gallardo/Documentos/ligadelincoln
backend/venv/bin/python backend/scripts/scraper_horarios.py --torneo-id 2
# Después de revisar el reporte:
backend/venv/bin/python backend/scripts/scraper_horarios.py --torneo-id 2 --execute
python3 scripts/capturar_fixture.py
```

### 2) Durante el fin de semana

- Los resultados se actualizan automáticamente con el timer `scraper-resultados`.
- Si querés revisar que esté corriendo:

```bash
systemctl --user status scraper-resultados.timer
systemctl --user status scraper-resultados.service
```

### 3) Cuando la Liga sube alineaciones de un partido o de la fecha

```bash
cd /home/gallardo/Documentos/ligadelincoln
backend/venv/bin/python backend/scripts/scraper_alineaciones.py --torneo-id 2 --fecha 7
# Después de revisar el reporte:
backend/venv/bin/python backend/scripts/scraper_alineaciones.py --torneo-id 2 --fecha 7 --execute
```

Eso reemplaza únicamente:

- alineaciones de Primera para la fecha seleccionada
- `dt_local`
- `dt_visitante`
- `arbitro`

No modifica resultados, estado del partido ni posiciones.

### 4) Después de una corrida manual importante

Si corresponde regenerar el frontend, el despliegue se ejecuta manualmente y por separado:

```bash
cd /home/gallardo/Documentos/ligadelincoln/frontend
pnpm run deploy
```

### 5) Precaución con alineaciones

- No asumir que `alineaciones.html` conserva semanas anteriores.
- Si la página todavía no muestra el partido correcto, **no correr** `scraper_alineaciones.py`.
- Si querés conservar histórico confiable, conviene exportar o respaldar antes de corridas importantes.

---

## Deploy a Vercel

El frontend está desplegado en Vercel. Para hacer deploy manual:

```bash
cd /home/gallardo/Documentos/ligadelincoln/frontend
pnpm run deploy
```

O conectar desde GitHub (main branch → auto-deploy).

---

## Estructura de directorios

```
ligadelincoln/
├── backend/scripts/          # Scripts de scraping
│   ├── scraper_resultados.py
│   ├── scraper_horarios.py
│   └── scraper_alineaciones.py
├── scripts/                   # Scripts runners y timers systemd
│   ├── run_scraper_resultados.sh
│   ├── generar_placas_resultados.sh
│   ├── scraper-resultados.timer
│   └── scraper-resultados.service
├── frontend/                  # App Astro desplegada en Vercel
│   └── src/pages/partido/     # Páginas de partido individual
└── tablas-images/             # Imágenes de tablas de posiciones
```
