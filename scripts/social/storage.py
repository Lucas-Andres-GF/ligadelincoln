#!/usr/bin/env python3
import mimetypes
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional dependency in some envs
    load_dotenv = None

from supabase import create_client

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent.parent

if load_dotenv:
    load_dotenv(PROJECT_DIR / "backend" / ".env")

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
SOCIAL_STORAGE_BUCKET = os.environ.get("SOCIAL_STORAGE_BUCKET", "social-images")


class StorageConfigError(RuntimeError):
    pass


def get_storage_client():
    storage_key = SUPABASE_SERVICE_ROLE_KEY or SUPABASE_KEY
    if not SUPABASE_URL or not storage_key:
        raise StorageConfigError("Faltan SUPABASE_URL y una key de Supabase para subir imágenes")
    return create_client(SUPABASE_URL, storage_key)


def upload_public_image(local_path, remote_path, bucket=SOCIAL_STORAGE_BUCKET):
    local_path = Path(local_path)
    if not local_path.exists():
        raise FileNotFoundError(f"No existe la imagen: {local_path}")

    content_type = mimetypes.guess_type(local_path.name)[0] or "application/octet-stream"
    supabase = get_storage_client()

    with local_path.open("rb") as f:
        data = f.read()

    try:
        supabase.storage.from_(bucket).upload(
            remote_path,
            data,
            {"content-type": content_type, "upsert": "true"},
        )
    except Exception as exc:
        raise RuntimeError(
            f"No se pudo subir {local_path} al bucket '{bucket}'. "
            "Verificá que el bucket exista y sea público."
        ) from exc

    return supabase.storage.from_(bucket).get_public_url(remote_path)
