# Panel local de operaciones

Dashboard local para ejecutar scripts del proyecto sin usar la consola.

## Ejecutar

Desde la raíz del repo:

```bash
python scripts/control-panel/app.py
```

En Linux, también se puede usar el lanzador de la raíz del proyecto:

```bash
./abrir-panel-liga.sh
```

Abre:

```txt
http://127.0.0.1:8765
```

Para cambiar puerto:

```bash
CONTROL_PANEL_PORT=8766 python scripts/control-panel/app.py
```

Para evitar que abra el navegador automáticamente:

```bash
CONTROL_PANEL_OPEN=0 python scripts/control-panel/app.py
```

## Acciones incluidas

- Actualizar resultados (`backend/scripts/scraper_resultados.py`)
- Actualizar horarios (`backend/scripts/scraper_horarios.py`)
- Alineaciones dry-run (`scraper_alineaciones.py --fecha N --dry-run`)
- Alineaciones real (`scraper_alineaciones.py --fecha N`)
- Generar tablas (`scripts/capturar_tablas.py --fecha N`)
- Generar fixture (`scripts/capturar_fixture.py --fecha N`)
- Generar placas de resultados (`scripts/generador-placas/generar_placas_resultados.py`)
- Subir tablas dry-run (`scripts/social/subir_tablas.py --fecha N --dry-run`)
- Subir tablas a Supabase Storage (`scripts/social/subir_tablas.py --fecha N`)
- Publicar tablas con caption automático (`scripts/social/subir_tablas.py --fecha N --publish`)
- Publicar resultados por división con caption automático (`scripts/social/subir_resultados.py --fecha N --categoria decima --publish`)
- Publicar fixture con caption automático (`scripts/social/subir_fixture.py --fecha N --publish`)

## Flujo recomendado para publicar contenido social

Las acciones de publicación generan un caption con IA, convierten imágenes a JPEG, suben a Storage y publican en la plataforma elegida.

1. Verificar/generar primero las imágenes necesarias (resultados, tablas o fixture).
2. Ejecutar **Publicar resultados**, **Publicar tablas** o **Publicar fixture**.
3. Confirmar escribiendo `S` o `Y`.
4. Elegir `both`, `instagram` o `facebook`.

## Flujo recomendado para publicar resultados

Orden editorial recomendado en el feed: **Décima → Novena → Octava → Séptima → Primera**, después tablas y fixture.

Para resultados, publicar una división por vez en ese orden.

## Seguridad

- Corre solo en `127.0.0.1`.
- No expone credenciales en el frontend.
- Las acciones que escriben en DB o publican afuera están marcadas por riesgo.
- Alineaciones real exige escribir `ESCRIBIR` antes de ejecutar.
- Las acciones de publicación exigen escribir `S` o `Y` antes de ejecutar; el panel pasa `--yes` al script para que no quede esperando entrada interactiva.

Este panel es local/privado. No desplegar en Vercel ni exponer públicamente.
