#!/usr/bin/env python3
import json
from datetime import datetime, timezone
from pathlib import Path

REGISTRY_PATH = Path(__file__).with_name("publicaciones.json")


def load_registry():
    if not REGISTRY_PATH.exists():
        return {}

    with REGISTRY_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_registry(registry):
    REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with REGISTRY_PATH.open("w", encoding="utf-8") as f:
        json.dump(registry, f, ensure_ascii=False, indent=2)
        f.write("\n")


def publication_key(kind, fecha, category=None):
    parts = [kind, f"fecha-{fecha}"]
    if category:
        parts.append(category)
    return ":".join(parts)


def get_publication(kind, fecha, category=None):
    return load_registry().get(publication_key(kind, fecha, category))


def record_publication(kind, fecha, payload, category=None):
    registry = load_registry()
    key = publication_key(kind, fecha, category)
    registry[key] = {
        **payload,
        "kind": kind,
        "fecha": fecha,
        "category": category,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }
    save_registry(registry)
    return key
