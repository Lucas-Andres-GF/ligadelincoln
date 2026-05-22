#!/usr/bin/env python3
from pathlib import Path

from PIL import Image


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent.parent
PREPARED_DIR = PROJECT_DIR / "scripts" / "social" / "prepared-images"


def prepare_image_for_meta(local_path, namespace):
    """Convierte imágenes a JPEG RGB para cumplir requisitos de Instagram Graph API."""
    local_path = Path(local_path)
    target_dir = PREPARED_DIR / namespace
    target_dir.mkdir(parents=True, exist_ok=True)

    try:
        relative = local_path.resolve().relative_to(PROJECT_DIR.resolve())
        safe_stem = "-".join(relative.with_suffix("").parts)
    except ValueError:
        safe_stem = local_path.stem

    target_path = target_dir / f"{safe_stem}.jpg"

    with Image.open(local_path) as image:
        if image.mode in ("RGBA", "LA"):
            background = Image.new("RGB", image.size, (255, 255, 255))
            background.paste(image, mask=image.getchannel("A"))
            image = background
        else:
            image = image.convert("RGB")

        image.save(target_path, "JPEG", quality=95, optimize=True)

    return target_path
