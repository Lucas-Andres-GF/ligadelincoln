import os
import re
import unicodedata
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent.parent
SOCIAL_IMAGES_DIR = PROJECT_DIR / "social-images"
SOCIAL_GENERATOR = PROJECT_DIR / "scripts" / "generar_contenido_social.py"


def slugify(value):
    normalized = unicodedata.normalize("NFKD", str(value or "").strip().lower())
    ascii_value = "".join(char for char in normalized if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", "-", ascii_value).strip("-")


def active_tournament_id():
    value = str(os.environ.get("ACTIVE_TORNEO_ID", "")).strip()
    if not value.isdigit() or int(value) <= 0:
        raise RuntimeError("ACTIVE_TORNEO_ID debe ser un entero positivo")
    return int(value)


def active_tournament_name():
    return str(os.environ.get("ACTIVE_TORNEO_NAME", "Torneo actual")).strip() or "Torneo actual"


def publication_dir(fecha):
    return SOCIAL_IMAGES_DIR / slugify(active_tournament_name()) / f"fecha_{int(fecha)}" / "publicacion"

