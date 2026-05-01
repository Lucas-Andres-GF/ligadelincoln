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
Actualiza fecha, hora y cancha de los partidos desde la web de la Liga.

```bash
cd /home/gallardo/Documentos/ligadelincoln/backend/scripts
python3 scraper_horarios.py
```

### Scraper de alineaciones (cuando la web ya esté actualizada)
Extrae alineaciones, goleadores, DTs, árbitro y también actualiza el resultado/estado del partido en `partidos`.

```bash
cd /home/gallardo/Documentos/ligadelincoln/backend/scripts
python3 scraper_alineaciones.py
```

**Cuándo correrlo**

- Cuando termine un partido y la web `alineaciones.html` ya muestre ese partido con sus jugadores.
- También sirve para la fecha completa, cuando la Liga sube todas las alineaciones.

**Importante**

- `alineaciones.html` muestra la **fecha actual**; no es una fuente histórica estable.
- Antes de correrlo, verificar visualmente que la página tenga la fecha y los partidos correctos.
- El script trabaja sobre la fecha detectada en la web y vuelve a guardar las alineaciones de esos partidos.
- Si la web cambia de fecha, ya no se pueden reconstruir alineaciones viejas desde esa misma URL.

**Importante:** Después de ejecutar, hacer deploy manual a Vercel para regenerar las páginas de partido:

```bash
cd /home/gallardo/Documentos/ligadelincoln/frontend
npm run deploy
```

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
| Inicio de semana | Actualizar horarios de la semana | `python3 scraper_horarios.py` |
| Inicio de semana | Capturar fixture | `python3 capturar_fixture.py` |
| Cuando termina un partido y la web ya fue actualizada | Scrapear alineaciones / goleadores / DT / árbitro / resultado | `python3 scraper_alineaciones.py` |
| Después de actualizar datos manualmente | Deploy del frontend | `npm run deploy` |
| Sábados | Resultados (automático) | Timer systemd cada 15min (14-21hs) |
| Domingos 22:15 | Generar placas de resultados (automático) | Timer systemd |

---

## Flujo recomendado de trabajo

### 1) Inicio de semana

```bash
cd /home/gallardo/Documentos/ligadelincoln/backend/scripts
python3 scraper_horarios.py
python3 /home/gallardo/Documentos/ligadelincoln/scripts/capturar_fixture.py
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
cd /home/gallardo/Documentos/ligadelincoln/backend/scripts
python3 scraper_alineaciones.py
```

Eso actualiza:

- `alineaciones`
- goleadores
- `dt_local`
- `dt_visitante`
- `arbitro`
- `goles_local`
- `goles_visitante`
- `estado = jugado`

### 4) Después de una corrida manual importante

Regenerar el frontend en Vercel:

```bash
cd /home/gallardo/Documentos/ligadelincoln/frontend
npm run deploy
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
npm run deploy
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
