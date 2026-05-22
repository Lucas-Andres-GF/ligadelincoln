#!/usr/bin/env python3
import json
import os
from pathlib import Path

import requests

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional dependency in local scripts
    load_dotenv = None


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent.parent

if load_dotenv:
    load_dotenv(PROJECT_DIR / "backend" / ".env")

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")
OPENROUTER_MODEL = os.environ.get("OPENROUTER_MODEL", "openai/gpt-4o-mini")
OPENROUTER_REFERER = os.environ.get("OPENROUTER_REFERER", "https://ligadelincoln.com")
OPENROUTER_APP_NAME = os.environ.get("OPENROUTER_APP_NAME", "Liga de Lincoln Social")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


class CaptionConfigError(RuntimeError):
    pass


class CaptionGenerationError(RuntimeError):
    pass


STYLE_GUIDE = """
Estilo editorial de Liga de Lincoln:
- Español rioplatense/neutro para redes, cercano y deportivo.
- Títulos en mayúsculas: "TABLAS DE POSICIONES - FECHA N 📈⚽", "FIXTURE FECHA N 🗓️⚽" o "FECHA N - DÉCIMA DIVISIÓN 👶🏟️".
- Primer párrafo con energía: "¡Se actualizan los números!", "¡La pelota no para!", "¡Resultados de la jornada!".
- Mencionar Liga de Lincoln, fecha y tipo de publicación sin inventar datos específicos.
- Usar emojis deportivos con moderación: ⚽ 🏆 🔥 🏟️ 🙌 📈 🗓️.
- Cierre breve institucional/comunitario.
- Hashtags al final, similares a los ejemplos.
- No inventar nombres de clubes, posiciones, goleadores, resultados ni horarios si no están en el contexto.
- No usar comillas ni markdown. Devolver texto listo para Instagram/Facebook.
""".strip()


EXAMPLES = """
TABLAS DE POSICIONES - FECHA 7 📈⚽

¡Se actualizan los números! Así quedaron las tablas de posiciones después de completarse la séptima jornada de la Liga de Lincoln. Deslizá para encontrar tu categoría y ver quién manda en la clasificación y cómo quedó la pelea por los primeros puestos. 🏆🔥

Toda la estadística oficial del fútbol regional está en un solo lugar. 🏟️🙌

#LigaDeLincoln #ligadelincolncom #TablasDePosiciones #Fútbol #Fecha7 #Estadísticas #Posiciones #FútbolRegional #Lincoln #PuntoAPunto

FIXTURE FECHA 8 🗓️⚽

¡La pelota no para! Te presentamos el cronograma de partidos para la Fecha 8 de la Liga de Lincoln. Repasá todos los cruces y horarios para no perderte nada de una jornada que empieza a definir cosas importantes en todas las categorías. 🏟️🔥

Toda la programación oficial y la información de las canchas la encontrás acá. ¡Nos vemos alentando a los clubes de nuestra liga! 🙌⚽

#LigaDeLincoln #ligadelincolncom #Fixture #Fecha8 #Fútbol #FútbolRegional #PróximaFecha #AgendaDeportiva #Lincoln #PasiónFutbolera

FECHA 7 - DÉCIMA DIVISIÓN 👶🏟️

¡El fútbol de la Décima! Ya tenemos los resultados oficiales de la séptima jornada para la categoría más pequeña de la Liga. Así terminó el fin de semana para nuestro semillero. 🙌⚽

#LigaDeLincoln #ligadelincolncom #DécimaDivisión #Fútbol #LosMasChicos #Fecha7 #FútbolInfantil #Resultados #Lincoln
""".strip()


def validate_caption_config():
    if not OPENROUTER_API_KEY:
        raise CaptionConfigError("Falta OPENROUTER_API_KEY en backend/.env")


def build_prompt(tipo, fecha, variantes, categoria=None, extra_context=None):
    tipo_label = {
        "tablas": "tablas de posiciones",
        "fixture": "fixture",
        "resultados": "resultados",
    }.get(tipo, tipo)

    return f"""
Generá {variantes} opciones de pie de publicación para redes sociales.

Contexto:
- Institución: Liga de Lincoln
- Tipo de publicación: {tipo_label}
- Fecha: {fecha}
- Categoría/división: {categoria or 'todas las categorías'}
- Plataformas: Instagram y Facebook
- Formato visual: carrusel, con portada primero
{f'- Contexto adicional: {extra_context}' if extra_context else ''}

Guía de estilo:
{STYLE_GUIDE}

Ejemplos del cliente:
{EXAMPLES}

Requisitos de salida:
- Devolvé SOLO JSON válido.
- Forma exacta: {{"captions": ["caption 1", "caption 2"]}}
- Cada caption debe estar completo y listo para copiar/pegar.
- Usá #Fecha{fecha} y hashtags relevantes.
- Si hay categoría, el título debe ser "FECHA {fecha} - {categoria} DIVISIÓN" respetando acentos y mayúsculas.
- No inventes información no incluida en el contexto.
""".strip()


def generate_captions(tipo, fecha, variantes=3, categoria=None, extra_context=None):
    validate_caption_config()

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": OPENROUTER_REFERER,
        "X-Title": OPENROUTER_APP_NAME,
    }
    payload = {
        "model": OPENROUTER_MODEL,
        "messages": [
            {"role": "system", "content": "Sos un redactor deportivo para redes sociales de una liga regional de fútbol."},
            {"role": "user", "content": build_prompt(tipo, fecha, variantes, categoria, extra_context)},
        ],
        "temperature": 0.8,
    }

    response = requests.post(OPENROUTER_URL, headers=headers, json=payload, timeout=60)
    body = response.json() if response.content else {}
    if response.status_code >= 400:
        raise CaptionGenerationError(str(body.get("error") or body))

    content = body.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
    if content.startswith("```"):
        content = content.strip("`")
        if content.lower().startswith("json"):
            content = content[4:].strip()

    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        raise CaptionGenerationError(f"OpenRouter no devolvió JSON válido: {content}") from exc

    captions = parsed.get("captions") or []
    if not captions:
        raise CaptionGenerationError("OpenRouter no devolvió captions")

    return [str(caption).strip() for caption in captions if str(caption).strip()]
