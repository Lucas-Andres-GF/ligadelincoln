# Entrada de operaciones del host

La guía canónica para fixture, posiciones, activación, scrapers, historia, correcciones, recuperación y códigos de salida es **[`backend/README_OPERACIONES.md`](backend/README_OPERACIONES.md)**. No uses este archivo como un segundo manual de ingesta.

> Reemplazá marcadores como `<RUTA_PROYECTO>` antes de ejecutar. La ingesta backend, los medios, la publicación social y el deploy del frontend son flujos separados.

## Intérprete del proyecto y panel local

No hay fallback al Python del sistema ni instalación de dependencias en runtime. El entorno virtual debe existir.

```bash
cd "<RUTA_PROYECTO>"
./backend/venv/bin/python --version
./abrir-panel-liga.sh
```

En Windows PowerShell:

```powershell
Set-Location "<RUTA_PROYECTO>"
& ".\backend\venv\Scripts\python.exe" --version
.\abrir-panel-liga.bat
```

El panel escucha en `127.0.0.1`. Las acciones backend **Previsualizar** no escriben; las acciones **Ejecutar** pasan `--execute` y exigen `ESCRIBIR`. El panel no construye ni despliega el frontend. Más detalles: [`scripts/control-panel/README.md`](scripts/control-panel/README.md).

## Resultados automáticos: un solo scheduler

El único scheduler de resultados es el timer **systemd de sistema** `scraper-resultados.timer`. `scripts/crontab` conserva únicamente medios y no debe programar resultados, directa ni indirectamente.

El timer versionado dispara cada 5 minutos, sábados y domingos de 13:00 a 22:55 en la hora local del host. El runner vuelve a exigir sábado/domingo y `13 <= hora < 23`. Como el unit no fija una zona horaria, verificá el host:

```bash
timedatectl
systemctl list-timers --all
systemctl status scraper-resultados.timer
systemctl status scraper-resultados.service
```

### Logs

```bash
journalctl -u scraper-resultados.service --no-pager -r
journalctl -u scraper-resultados.service --no-pager | grep -E "Started|Finished|Failed"
tail -f "<SCRAPER_LOG_DIR>/scraper_resultados.log"
```

### Recargar o reiniciar

```bash
sudo systemctl daemon-reload
sudo systemctl restart scraper-resultados.timer
```

### Instalar las unidades versionadas

Desde la raíz del proyecto:

```bash
sudo ./scripts/install_scraper_systemd.sh
```

El instalador copia los units a `/etc/systemd/system/`, recarga systemd y ejecuta `systemctl enable --now scraper-resultados.timer`. No agregues cron, un timer de usuario ni otro scheduler externo para resultados.

## Medios y publicación social

Estos flujos están fuera de las garantías de ingesta backend:

- Capturas: `scripts/capturar_fixture.py` y `scripts/capturar_tablas.py`.
- Generadores de placas: `scripts/generador-placas/`.
- Flujo social: [`scripts/social/README.md`](scripts/social/README.md).
- Cron de medios: `scripts/crontab`.

`scripts/generar_placas_resultados.sh` es **tooling legacy de medios**. Puede instalar navegador o dependencias durante la ejecución; no comparte el contrato de entorno fijo, previsualización ni seguridad de las CLI de ingesta backend.

## Deploy manual del frontend

La ingesta y el panel no hacen deploy. Si el operador decide desplegar, es una acción manual, explícita y separada:

```bash
cd "<RUTA_PROYECTO>/frontend"
pnpm run deploy
```

Antes de desplegar, seguí el proceso de revisión y autorización propio del frontend. Ningún éxito de backend implica que haya que desplegar o publicar contenido.
