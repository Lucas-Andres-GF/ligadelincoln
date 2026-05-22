#!/usr/bin/env python3
import argparse
import os
import subprocess
import sys
from pathlib import Path

from caption_ai import CaptionConfigError, CaptionGenerationError, generate_captions
from meta_client import MetaConfigError, publish_facebook_carousel, publish_instagram_carousel
from image_prepare import prepare_image_for_meta
from registry import get_publication, publication_key, record_publication
from storage import SOCIAL_STORAGE_BUCKET, upload_public_image

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent.parent
RESULTADOS_DIR = PROJECT_DIR / "placares_generados"
GENERADOR_RESULTADOS = PROJECT_DIR / "scripts" / "generador-placas" / "generar_placas_resultados.py"

CATEGORIAS = {
    "primera": "Primera",
    "septima": "Séptima",
    "octava": "Octava",
    "novena": "Novena",
    "decima": "Décima",
}


def categoria_label(slug):
    return CATEGORIAS[slug]


def categoria_hashtag(slug):
    return categoria_label(slug).replace("é", "e").replace("É", "E") + "Division"


def resultados_dir(fecha, categoria):
    return RESULTADOS_DIR / categoria / f"fecha_{fecha}"


def expected_images(fecha, categoria):
    folder = resultados_dir(fecha, categoria)
    if not folder.exists():
        return []

    portada = sorted(folder.glob("portada_*.png"))
    resultados = sorted(folder.glob("resultado_*.png"))
    libres = sorted(folder.glob("libre_*.png"))
    return [("Portada", path) for path in portada[:1]] + [("Resultado", path) for path in resultados] + [("Libre", path) for path in libres]


def run_generation(fecha, categoria, force=False):
    cmd = [sys.executable, str(GENERADOR_RESULTADOS), "--fecha", str(fecha), "--categoria", categoria]
    if force:
        cmd.append("--force")
    print(f"🚀 Generando placas: {' '.join(cmd)}")
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    subprocess.run(cmd, cwd=str(PROJECT_DIR), check=True, env=env)


def safe_label(label, path):
    stem = path.stem.lower()
    replacements = {
        "á": "a", "é": "e", "í": "i", "ó": "o", "ú": "u", "ñ": "n",
        ".": "", " ": "-", "_": "-",
    }
    for source, target in replacements.items():
        stem = stem.replace(source, target)
    return f"{label.lower()}-{stem}"


def remote_image_path(fecha, categoria, index, label, path):
    return f"resultados/fecha-{fecha}/{categoria}/{index:02d}-{safe_label(label, path)}{path.suffix.lower()}"


def upload_carousel_images(fecha, categoria, images):
    uploaded = []
    print(f"\n☁️  Subiendo imágenes a Supabase Storage bucket '{SOCIAL_STORAGE_BUCKET}'...")
    for index, (label, path) in enumerate(images, start=1):
        prepared_path = prepare_image_for_meta(path, f"resultados-fecha-{fecha}-{categoria}")
        remote_path = remote_image_path(fecha, categoria, index, label, prepared_path)
        url = upload_public_image(prepared_path, remote_path)
        uploaded.append({"label": label, "local_path": str(path), "prepared_path": str(prepared_path), "remote_path": remote_path, "url": url})
        print(f"   ✅ {index}. {label}: {url}")
    return uploaded


def build_caption(fecha, categoria):
    label = categoria_label(categoria)
    return (
        f"FECHA {fecha} - {label.upper()} DIVISIÓN ⚽\n\n"
        f"¡Resultados de la {label}! Ya están disponibles los marcadores oficiales de la Fecha {fecha} de la Liga de Lincoln. "
        "Deslizá para repasar cada encuentro y seguir toda la acción del fútbol regional. 🏟️🔥\n\n"
        f"#LigaDeLincoln #ligadelincolncom #{categoria_hashtag(categoria)} #Fútbol #Fecha{fecha} #Resultados #FútbolRegional #Lincoln"
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


def build_ai_caption(fecha, categoria):
    print("\n🤖 Generando caption con IA...")
    try:
        captions = generate_captions("resultados", fecha, variantes=1, categoria=categoria)
    except (CaptionConfigError, CaptionGenerationError) as exc:
        print(f"⛔ No se pudo generar caption con IA: {exc}")
        sys.exit(1)

    return captions[0]


def print_carousel_plan(fecha, categoria, images, missing, already_published):
    key = publication_key("resultados", fecha, categoria)
    print(f"\n📌 Carrusel Resultados - Fecha {fecha} - {categoria_label(categoria)}")
    print(f"🔑 Registry key: {key}")

    if already_published:
        print("\n⚠️  Esta categoría ya figura publicada:")
        print(f"   Registrado: {already_published.get('recorded_at', '-')}")
        if already_published.get("facebook", {}).get("post_id"):
            print(f"   Facebook: {already_published['facebook']['post_id']}")
        if already_published.get("instagram", {}).get("media_id"):
            print(f"   Instagram: {already_published['instagram']['media_id']}")

    print("\n🖼️  Orden del carrusel:")
    for index, (label, path) in enumerate(images, start=1):
        status = "✅" if path.exists() else "❌"
        print(f"   {index}. {status} {label}: {path}")

    if missing:
        print("\n⚠️  Faltan imágenes:")
        for label, path in missing:
            print(f"   - {label}: {path}")
    elif images:
        print("\n✅ Todas las imágenes del carrusel están disponibles.")
    else:
        print("\n⚠️  No se encontraron imágenes para esta categoría/fecha.")


def confirm_or_abort(message):
    answer = input(f"{message} [y/N]: ").strip().lower()
    if answer not in {"y", "yes", "s", "si", "sí"}:
        print("⛔ Abortado por el usuario.")
        sys.exit(0)


def parse_args():
    parser = argparse.ArgumentParser(description="Prepara/publica carrusel de resultados por categoría")
    parser.add_argument("--fecha", type=int, required=True)
    parser.add_argument("--categoria", choices=list(CATEGORIAS), required=True)
    parser.add_argument("--dry-run", action="store_true", help="Muestra el plan sin generar, subir ni publicar")
    parser.add_argument("--force", action="store_true", help="Regenera placas y permite republicar")
    parser.add_argument("--skip-generation", action="store_true", help="No regenera placas antes de subirlas")
    parser.add_argument("--skip-upload", action="store_true", help="No sube imágenes a Storage")
    parser.add_argument("--publish", action="store_true", help="Publica el carrusel en Meta")
    parser.add_argument("--only", choices=["instagram", "facebook", "both"], default="both")
    parser.add_argument("--caption-file", help="Archivo .txt/.md con el pie de publicación aprobado")
    parser.add_argument("--yes", action="store_true", help="No pedir confirmación antes de publicar")
    return parser.parse_args()


def main():
    args = parse_args()
    images = expected_images(args.fecha, args.categoria)
    missing = [] if images else [("Carpeta de resultados", resultados_dir(args.fecha, args.categoria))]
    already_published = get_publication("resultados", args.fecha, args.categoria)

    print_carousel_plan(args.fecha, args.categoria, images, missing, already_published)

    if args.dry_run:
        print("\n🧪 DRY RUN: no se generan placas, no se sube a Storage y no se publica.")
        return

    if already_published and not args.force:
        print("\n⛔ Abortado: esta categoría/fecha ya figura publicada. Usá --force si querés republicar.")
        return

    if args.skip_generation:
        print("\n⏭️  Generación omitida por --skip-generation. Usando placas locales existentes.")
    else:
        run_generation(args.fecha, args.categoria, args.force)
        images = expected_images(args.fecha, args.categoria)

    if not images:
        print("\n⛔ Abortado: no hay imágenes para publicar.")
        sys.exit(1)

    print("\n✅ Carrusel listo para publicar.")
    uploaded = []
    if args.skip_upload:
        print("⏭️  Upload omitido por --skip-upload.")
    else:
        uploaded = upload_carousel_images(args.fecha, args.categoria, images)
        print(f"\n✅ {len(uploaded)} imágenes subidas y con URL pública.")

    if not args.publish:
        print("⏭️  Próximo paso: publicar con --publish usando un caption aprobado.")
        return

    if args.skip_upload:
        print("⛔ No se puede publicar con --skip-upload porque Meta necesita URLs públicas.")
        sys.exit(1)

    caption = read_caption_file(args.caption_file) if args.caption_file else build_ai_caption(args.fecha, args.categoria)
    image_urls = [item["url"] for item in uploaded]

    print("\n📝 Caption:")
    print(caption)

    if not args.yes:
        confirm_or_abort(f"¿Publicar resultados fecha {args.fecha} {categoria_label(args.categoria)} en {args.only}?")

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

    key = record_publication("resultados", args.fecha, result, args.categoria)
    print(f"\n✅ Publicación registrada en {key}")


if __name__ == "__main__":
    main()
