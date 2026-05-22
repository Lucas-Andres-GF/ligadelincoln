#!/usr/bin/env python3
import argparse
import os
import subprocess
import sys
from pathlib import Path

from registry import get_publication, publication_key
from registry import record_publication
from caption_ai import CaptionConfigError, CaptionGenerationError, generate_captions
from meta_client import MetaConfigError, publish_facebook_carousel, publish_instagram_carousel
from image_prepare import prepare_image_for_meta
from storage import SOCIAL_STORAGE_BUCKET, upload_public_image

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent.parent
TABLAS_DIR = PROJECT_DIR / "tablas-images"
CAPTURAR_TABLAS = PROJECT_DIR / "scripts" / "capturar_tablas.py"

CATEGORIAS_ORDEN_TABLAS = [
    ("primera", "Primera"),
    ("septima", "Séptima"),
    ("octava", "Octava"),
    ("novena", "Novena"),
    ("decima", "Décima"),
]


def expected_images():
    images = [("Portada", TABLAS_DIR / "portada_tabla_posiciones.png")]
    images.extend(
        (label, TABLAS_DIR / f"posiciones_{slug}.png")
        for slug, label in CATEGORIAS_ORDEN_TABLAS
    )
    return images


def run_generation(fecha):
    cmd = [sys.executable, str(CAPTURAR_TABLAS), "--fecha", str(fecha)]
    print(f"🚀 Generando imágenes: {' '.join(cmd)}")
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    subprocess.run(cmd, cwd=str(PROJECT_DIR), check=True, env=env)


def print_carousel_plan(fecha, images, missing, already_published):
    key = publication_key("tablas", fecha)
    print(f"\n📌 Carrusel Tablas - Fecha {fecha}")
    print(f"🔑 Registry key: {key}")

    if already_published:
        print("\n⚠️  Esta fecha ya figura como publicada:")
        print(f"   Registrado: {already_published.get('recorded_at', '-')}")
        if already_published.get("facebook_post_id"):
            print(f"   Facebook: {already_published['facebook_post_id']}")
        if already_published.get("instagram_media_id"):
            print(f"   Instagram: {already_published['instagram_media_id']}")
        print("   Usá --force cuando implementemos publicación real si querés republicar.")

    print("\n🖼️  Orden del carrusel:")
    for index, (label, path) in enumerate(images, start=1):
        status = "✅" if path.exists() else "❌"
        print(f"   {index}. {status} {label}: {path}")

    if missing:
        print("\n⚠️  Faltan imágenes:")
        for label, path in missing:
            print(f"   - {label}: {path}")
    else:
        print("\n✅ Todas las imágenes del carrusel están disponibles.")


def remote_image_path(fecha, index, label, path):
    safe_label = label.lower().replace("é", "e").replace("è", "e").replace(" ", "-")
    return f"tablas/fecha-{fecha}/{index:02d}-{safe_label}{path.suffix.lower()}"


def upload_carousel_images(fecha, images):
    uploaded = []
    print(f"\n☁️  Subiendo imágenes a Supabase Storage bucket '{SOCIAL_STORAGE_BUCKET}'...")
    for index, (label, path) in enumerate(images, start=1):
        prepared_path = prepare_image_for_meta(path, f"tablas-fecha-{fecha}")
        remote_path = remote_image_path(fecha, index, label, prepared_path)
        url = upload_public_image(prepared_path, remote_path)
        uploaded.append({"label": label, "local_path": str(path), "prepared_path": str(prepared_path), "remote_path": remote_path, "url": url})
        print(f"   ✅ {index}. {label}: {url}")
    return uploaded


def build_caption(fecha):
    return (
        f"📊 Tabla de posiciones - Fecha {fecha}\n\n"
        "Torneo Apertura 2026\n"
        "Liga Deportiva Amateur de Lincoln\n\n"
        "#LigaDeLincoln #FutbolLocal #Lincoln"
    )


def read_caption_file(path):
    caption_path = Path(path)
    if not caption_path.exists():
        raise FileNotFoundError(f"No existe el archivo de caption: {caption_path}")
    content = caption_path.read_text(encoding="utf-8").strip()
    if "## Opción" not in content:
        return content

    lines = content.splitlines()
    selected = []
    inside_option = False
    for line in lines:
        if line.startswith("## Opción"):
            if inside_option and selected:
                break
            inside_option = True
            selected = []
            continue
        if inside_option:
            selected.append(line)

    caption = "\n".join(selected).strip()
    if not caption:
        raise ValueError(f"No se pudo extraer un caption de {caption_path}")
    return caption


def build_ai_caption(fecha):
    print("\n🤖 Generando caption con IA...")
    try:
        captions = generate_captions("tablas", fecha, variantes=1)
    except (CaptionConfigError, CaptionGenerationError) as exc:
        print(f"⛔ No se pudo generar caption con IA: {exc}")
        sys.exit(1)

    return captions[0]


def confirm_or_abort(message):
    answer = input(f"{message} [y/N]: ").strip().lower()
    if answer not in {"y", "yes", "s", "si", "sí"}:
        print("⛔ Abortado por el usuario.")
        sys.exit(0)


def parse_args():
    parser = argparse.ArgumentParser(description="Prepara/publica carrusel de tablas en redes sociales")
    parser.add_argument("--fecha", type=int, required=True, help="Fecha editorial de las tablas")
    parser.add_argument("--dry-run", action="store_true", help="Muestra el plan sin publicar ni registrar")
    parser.add_argument("--force", action="store_true", help="Regenera imágenes aunque existan y permite republicar en el futuro")
    parser.add_argument("--skip-generation", action="store_true", help="No regenera imágenes antes de subirlas")
    parser.add_argument("--skip-upload", action="store_true", help="Prepara imágenes pero no las sube a storage")
    parser.add_argument("--publish", action="store_true", help="Publica el carrusel en Meta después de subir imágenes")
    parser.add_argument("--only", choices=["instagram", "facebook", "both"], default="both", help="Plataforma a publicar")
    parser.add_argument("--caption-file", help="Archivo .txt/.md con el pie de publicación aprobado")
    parser.add_argument("--yes", action="store_true", help="No pedir confirmación antes de publicar")
    return parser.parse_args()


def main():
    args = parse_args()
    images = expected_images()
    missing = [(label, path) for label, path in images if not path.exists()]
    already_published = get_publication("tablas", args.fecha)

    print_carousel_plan(args.fecha, images, missing, already_published)

    if args.dry_run:
        print("\n🧪 DRY RUN: no se generan imágenes, no se publica y no se registra nada.")
        if missing:
            print(f"   Para generar: python {CAPTURAR_TABLAS} --fecha {args.fecha}")
        return

    if already_published and not args.force:
        print("\n⛔ Abortado: la fecha ya figura publicada. Usá --force cuando quieras republicar.")
        return

    if args.skip_generation:
        print("\n⏭️  Generación omitida por --skip-generation. Usando imágenes locales existentes.")
    else:
        # Las imágenes de tablas tienen nombres fijos sin fecha. Si no regeneramos,
        # podemos subir una portada vieja (por ejemplo Fecha 6) a una ruta nueva
        # (por ejemplo fecha-7). Por eso el modo real regenera siempre.
        run_generation(args.fecha)
        images = expected_images()
        missing = [(label, path) for label, path in images if not path.exists()]

    if missing:
        print("\n⛔ Abortado: siguen faltando imágenes después de generar.")
        for label, path in missing:
            print(f"   - {label}: {path}")
        sys.exit(1)

    print("\n✅ Carrusel listo para publicar.")
    uploaded = []
    if args.skip_upload:
        print("⏭️  Upload omitido por --skip-upload.")
    else:
        uploaded = upload_carousel_images(args.fecha, images)
        print(f"\n✅ {len(uploaded)} imágenes subidas y con URL pública.")

    if not args.publish:
        print("⏭️  Próximo paso: publicar con --publish cuando estén las credenciales Meta.")
        print("   Por ahora este comando preparó/subió imágenes; NO publicó en redes.")
        return

    if args.skip_upload:
        print("⛔ No se puede publicar con --skip-upload porque Meta necesita URLs públicas.")
        sys.exit(1)

    if args.caption_file:
        caption = read_caption_file(args.caption_file)
    else:
        caption = build_ai_caption(args.fecha)
    image_urls = [item["url"] for item in uploaded]

    print("\n📝 Caption:")
    print(caption)

    if not args.yes:
        confirm_or_abort(f"¿Publicar carrusel de tablas fecha {args.fecha} en {args.only}?")

    result = {"caption": caption, "images": uploaded}
    try:
        if args.only in {"instagram", "both"}:
            print("\n📲 Publicando en Instagram...")
            result["instagram"] = publish_instagram_carousel(image_urls, caption)
            print(f"   ✅ Instagram media_id: {result['instagram'].get('media_id')}")

        if args.only in {"facebook", "both"}:
            print("\n📘 Publicando en Facebook...")
            result["facebook"] = publish_facebook_carousel(image_urls, caption)
            print(f"   ✅ Facebook post_id: {result['facebook'].get('post_id')}")
    except MetaConfigError as exc:
        print(f"⛔ {exc}")
        sys.exit(1)

    key = record_publication("tablas", args.fecha, result)
    print(f"\n✅ Publicación registrada en {key}")


if __name__ == "__main__":
    main()
