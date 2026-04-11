# Comandos úteis - Liga de Lincoln

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

## Horarios de ejecución

| Servicio | Frecuencia | Horario Argentina |
|----------|------------|------------------|
| scraper-resultados | cada 15 min | Sáb/Dom 14-21hs |
| generador-placas | semanal | Domingos 22:15hs |