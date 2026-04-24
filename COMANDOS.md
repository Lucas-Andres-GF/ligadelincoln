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

# Ver log del generador de placas
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
| generador-placas | semanal | Domingos 22:15hs |

---

## Scripts manuales (corrida semanal)

### Scraper de horarios (lunes)
Actualiza fecha, hora y cancha de los partidos desde la web de la Liga.

```bash
cd /home/gallardo/Documentos/ligadelincoln/backend/scripts
python3 scraper_horarios.py
```

### Scraper de alineaciones (lunes/martes)
Extrae alineaciones, goleadores, DTs y árbitros desde la web de la Liga.

```bash
cd /home/gallardo/Documentos/ligadelincoln/backend/scripts
python3 scraper_alineaciones.py
```

**Importante:** Después de ejecutar, hacer deploy manual a Vercel para regenerar las páginas de partido:

```bash
cd /home/gallardo/Documentos/ligadelincoln/frontend
npm run deploy
```

### Capturar tablas (opcional)
Genera imágenes PNG de las tablas de posiciones.

```bash
python3 /home/gallardo/Documentos/ligadelincoln/scripts/capturar_tablas.py
```

### Generar placas (manual, si no funciona el timer)
Genera las placas de resultado final.

```bash
/home/gallardo/Documentos/ligadelincoln/scripts/run_generador_placas.sh
```

---

## Workflow semanal

| Día | Acción | Comando |
|-----|--------|---------|
| Lunes | Actualizar horarios de la semana | `python3 scraper_horarios.py` |
| Lunes/Martes | Scrapear alineaciones + deploy | `python3 scraper_alineaciones.py` + `npm run deploy` |
| Sábados | Resultados (automático) | Timer systemd cada 15min (14-21hs) |
| Domingos 22:15 | Generar placas (automático) | Timer systemd |

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
│   ├── run_generador_placas.sh
│   ├── scraper-resultados.timer
│   └── scraper-resultados.service
├── frontend/                  # App Astro desplegada en Vercel
│   └── src/pages/partido/     # Páginas de partido individual
└── tablas-images/             # Imágenes de tablas de posiciones
```