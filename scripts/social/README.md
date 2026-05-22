# Automatización social

MVP inicial para preparar publicaciones manuales en Facebook/Instagram sin cron.

## Tablas

Dry-run recomendado:

```bash
python scripts/social/subir_tablas.py --fecha 7 --dry-run
```

Preparar/generar imágenes faltantes:

```bash
python scripts/social/subir_tablas.py --fecha 7
```

Preparar sin subir a storage:

```bash
python scripts/social/subir_tablas.py --fecha 7 --skip-upload
```

Por seguridad, el modo real regenera siempre las imágenes de tablas para la fecha indicada, porque los archivos locales tienen nombres fijos y pueden haber quedado de una fecha anterior. Si querés usar exactamente lo que ya está en `tablas-images/`, usá:

```bash
python scripts/social/subir_tablas.py --fecha 7 --skip-generation
```

Orden del carrusel de tablas:

1. Portada (`tablas-images/portada_tabla_posiciones.png`)
2. Primera (`tablas-images/posiciones_primera.png`)
3. Séptima (`tablas-images/posiciones_septima.png`)
4. Octava (`tablas-images/posiciones_octava.png`)
5. Novena (`tablas-images/posiciones_novena.png`)
6. Décima (`tablas-images/posiciones_decima.png`)

## Registro anti-duplicados

`publicaciones.json` guarda las publicaciones realizadas. En este MVP todavía no se escribe automáticamente porque falta integrar storage público y Meta Graph API.

## Storage público

Instagram necesita URLs públicas para publicar carruseles. El MVP usa Supabase Storage.

Variables esperadas:

- `SUPABASE_URL`
- `SUPABASE_KEY`
- `SOCIAL_STORAGE_BUCKET` opcional; default: `social-images`

El bucket debe existir y ser público. Si el bucket no existe, crealo en Supabase como `social-images` o definí `SOCIAL_STORAGE_BUCKET` con otro nombre.

## Publicar en Meta

Variables requeridas para publicación real:

- `META_ACCESS_TOKEN`
- `META_PAGE_ACCESS_TOKEN` recomendado para Facebook; si falta, usa `META_ACCESS_TOKEN`
- `META_PAGE_ID` para Facebook
- `META_INSTAGRAM_BUSINESS_ID` para Instagram
- `META_GRAPH_VERSION` opcional; default: `v23.0`

Publicar tablas en ambas plataformas:

```bash
python scripts/social/subir_tablas.py --fecha 7 --publish
```

Solo Instagram:

```bash
python scripts/social/subir_tablas.py --fecha 7 --publish --only instagram
```

Solo Facebook:

```bash
python scripts/social/subir_tablas.py --fecha 7 --publish --only facebook
```

El comando pide confirmación antes de publicar. Para automatización futura se puede usar `--yes`.

## Captions automáticos con OpenRouter

Variables requeridas en `backend/.env`:

- `OPENROUTER_API_KEY`
- `OPENROUTER_MODEL` opcional; default: `openai/gpt-4o-mini`

Los scripts de publicación generan automáticamente un caption con IA si no pasás `--caption-file`.

Publicar tablas con caption automático:

```bash
python scripts/social/subir_tablas.py --fecha 8 --publish
```

Publicar resultados por categoría con caption automático:

```bash
python scripts/social/subir_resultados.py --fecha 8 --categoria decima --publish
```

Publicar fixture con caption automático:

```bash
python scripts/social/subir_fixture.py --fecha 9 --publish
```

El carrusel de fixture detecta automáticamente partidos postergados cargados para los mismos días de la fecha principal. Los agrega después de su división correspondiente, por ejemplo: Primera, Postergados Primera, Séptima, Postergados Séptima. El caption automático recibe ese contexto para mencionarlo. Si el carrusel supera 20 imágenes, Instagram no permite publicarlo completo.

Si querés forzar un texto manual, todavía podés usar `--caption-file`:

```bash
python scripts/social/subir_tablas.py --fecha 8 --publish --caption-file mi-caption.txt
```

Las imágenes se convierten automáticamente a JPEG antes de subirlas a Storage para cumplir los requisitos de Meta/Instagram.

## Próximos pasos

1. Probar publicación real con token de Meta.
2. Extender el mismo patrón a fixture y resultados.
