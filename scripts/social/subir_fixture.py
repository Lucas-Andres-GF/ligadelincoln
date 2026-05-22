#!/usr/bin/env python3
import argparse
import os
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv
from supabase import create_client

from caption_ai import CaptionConfigError, CaptionGenerationError, generate_captions
from image_prepare import prepare_image_for_meta
from meta_client import MetaConfigError, publish_facebook_carousel_from_files, publish_instagram_carousel
from registry import get_publication, publication_key, record_publication
from storage import SOCIAL_STORAGE_BUCKET, upload_public_image

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent.parent
FIXTURE_DIR = PROJECT_DIR / "tablas-images"
CAPTURAR_FIXTURE = PROJECT_DIR / "scripts" / "capturar_fixture.py"

load_dotenv(PROJECT_DIR / "backend" / ".env")
supabase = create_client(os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_KEY"))

CATEGORIAS_ORDEN_FIXTURE = [
    ("primera", "Primera"),
    ("septima", "Séptima"),
    ("octava", "Octava"),
    ("novena", "Novena"),
    ("decima", "Décima"),
]
CATEGORIAS_BY_ID = {
    1: ("primera", "Primera"),
    2: ("septima", "Séptima"),
    3: ("octava", "Octava"),
    4: ("novena", "Novena"),
    5: ("decima", "Décima"),
}


def get_fixture_dates(fecha):
    response = (
        supabase.table("partidos")
        .select("dia")
        .eq("fecha_id", fecha)
        .not_.is_("dia", "null")
        .execute()
    )
    return sorted({row["dia"] for row in response.data or [] if row.get("dia")})


def discover_postponed_items(fecha):
    dates = get_fixture_dates(fecha)
    if not dates:
        return []

    response = (
        supabase.table("partidos")
        .select("fecha_id, categoria_id, dia")
        .in_("dia", dates)
        .neq("fecha_id", fecha)
        .not_.is_("visitante_id", "null")
        .execute()
    )

    seen = set()
    items = []
    for row in response.data or []:
        categoria = CATEGORIAS_BY_ID.get(row.get("categoria_id"))
        fecha_postergada = row.get("fecha_id")
        dia = row.get("dia")
        if not categoria or not fecha_postergada or not dia:
            continue

        slug, label = categoria
        key = (slug, fecha_postergada, dia)
        if key in seen:
            continue
        seen.add(key)
        items.append({"slug": slug, "label": label, "fecha": fecha_postergada, "dia": dia})

    category_order = {slug: index for index, (slug, _) in enumerate(CATEGORIAS_ORDEN_FIXTURE)}
    return sorted(items, key=lambda item: (category_order[item["slug"]], item["fecha"], item["dia"]))


def expected_images(fecha, postponed_items=None):
    postponed_items = postponed_items or []
    images = [("Portada", FIXTURE_DIR / "portada_fixture.png")]
    postponed_by_slug = {}
    for item in postponed_items:
        postponed_by_slug.setdefault(item["slug"], []).append(item)

    for slug, label in CATEGORIAS_ORDEN_FIXTURE:
        images.append((label, FIXTURE_DIR / slug / f"fecha_{fecha}" / "fixture.png"))
        for item in postponed_by_slug.get(slug, []):
            images.append((
                f"Postergados {label} Fecha {item['fecha']}",
                FIXTURE_DIR / slug / f"postergados_fecha_{item['fecha']}" / "fixture.png",
            ))
    return images


def run_generation(fecha, postponed_items=None):
    postponed_items = postponed_items or []
    cmd = [sys.executable, str(CAPTURAR_FIXTURE), "--fecha", str(fecha)]
    print(f"🚀 Generando fixture: {' '.join(cmd)}")
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    subprocess.run(cmd, cwd=str(PROJECT_DIR), check=True, env=env)

    for item in postponed_items:
        cmd = [
            sys.executable,
            str(CAPTURAR_FIXTURE),
            "--fecha",
            str(item["fecha"]),
            "--postergados-fecha",
            str(item["fecha"]),
            "--dia",
            item["dia"],
            "--categoria",
            item["slug"],
            "--skip-portada",
        ]
        print(f"🚀 Generando fixture postergado: {' '.join(cmd)}")
        subprocess.run(cmd, cwd=str(PROJECT_DIR), check=True, env=env)


def remote_image_path(fecha, index, label, path):
    safe_label = label.lower().replace("é", "e").replace(" ", "-")
    return f"fixture/fecha-{fecha}/{index:02d}-{safe_label}{path.suffix.lower()}"


def upload_carousel_images(fecha, images):
    uploaded = []
    print(f"\n☁️  Subiendo imágenes a Supabase Storage bucket '{SOCIAL_STORAGE_BUCKET}'...")
    for index, (label, path) in enumerate(images, start=1):
        prepared_path = prepare_image_for_meta(path, f"fixture-fecha-{fecha}")
        remote_path = remote_image_path(fecha, index, label, prepared_path)
        url = upload_public_image(prepared_path, remote_path)
        uploaded.append({"label": label, "local_path": str(path), "prepared_path": str(prepared_path), "remote_path": remote_path, "url": url})
        print(f"   ✅ {index}. {label}: {url}")
    return uploaded


def build_caption(fecha, postponed_items=None):
    postponed_items = postponed_items or []
    postergados_text = ""
    if postponed_items:
        partes = [f"{item['label']} de Fecha {item['fecha']}" for item in postponed_items]
        postergados_text = "\n\nAdemás, este carrusel incluye partidos postergados: " + ", ".join(partes) + "."

    return (
        f"FIXTURE FECHA {fecha} 🗓️⚽\n\n"
        f"¡La pelota no para! Te presentamos el cronograma de partidos para la Fecha {fecha} de la Liga de Lincoln. "
        "Repasá todos los cruces y horarios para no perderte nada de una nueva jornada del fútbol regional. 🏟️🔥"
        f"{postergados_text}\n\n"
        "Toda la programación oficial y la información de las canchas la encontrás acá. ¡Nos vemos alentando a los clubes de nuestra liga! 🙌⚽\n\n"
        f"#LigaDeLincoln #ligadelincolncom #Fixture #Fecha{fecha} #Fútbol #FútbolRegional #PróximaFecha #AgendaDeportiva #Lincoln #PasiónFutbolera"
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


def build_ai_caption(fecha, postponed_items=None):
    print("\n🤖 Generando caption con IA...")
    extra_context = None
    if postponed_items:
        partes = [f"{item['label']} - postergados Fecha {item['fecha']} ({item['dia']})" for item in postponed_items]
        extra_context = "El carrusel incluye también estas placas de partidos postergados, ubicadas después de su división principal: " + "; ".join(partes) + ". Mencionalo de forma clara en el pie de publicación."

    try:
        captions = generate_captions("fixture", fecha, variantes=1, extra_context=extra_context)
    except (CaptionConfigError, CaptionGenerationError) as exc:
        print(f"⛔ No se pudo generar caption con IA: {exc}")
        sys.exit(1)

    return captions[0]


def print_carousel_plan(fecha, images, missing, already_published):
    key = publication_key("fixture", fecha)
    print(f"\n📌 Carrusel Fixture - Fecha {fecha}")
    print(f"🔑 Registry key: {key}")

    if already_published:
        print("\n⚠️  Esta fecha ya figura publicada:")
        print(f"   Registrado: {already_published.get('recorded_at', '-')}")

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


def confirm_or_abort(message):
    answer = input(f"{message} [y/N]: ").strip().lower()
    if answer not in {"y", "yes", "s", "si", "sí"}:
        print("⛔ Abortado por el usuario.")
        sys.exit(0)


def parse_args():
    parser = argparse.ArgumentParser(description="Prepara/publica carrusel de fixture")
    parser.add_argument("--fecha", type=int, required=True)
    parser.add_argument("--dry-run", action="store_true", help="Muestra el plan sin publicar ni registrar")
    parser.add_argument("--force", action="store_true", help="Regenera imágenes y permite republicar")
    parser.add_argument("--skip-generation", action="store_true", help="No regenera imágenes antes de subirlas")
    parser.add_argument("--skip-upload", action="store_true", help="No sube imágenes a Storage")
    parser.add_argument("--publish", action="store_true", help="Publica el carrusel en Meta")
    parser.add_argument("--only", choices=["instagram", "facebook", "both"], default="both")
    parser.add_argument("--caption-file", help="Archivo .txt/.md con el pie de publicación aprobado")
    parser.add_argument("--yes", action="store_true", help="No pedir confirmación antes de publicar")
    return parser.parse_args()


def main():
    args = parse_args()
    postponed_items = discover_postponed_items(args.fecha)
    images = expected_images(args.fecha, postponed_items)
    missing = [(label, path) for label, path in images if not path.exists()]
    already_published = get_publication("fixture", args.fecha)

    print_carousel_plan(args.fecha, images, missing, already_published)

    if postponed_items:
        print("\n📌 Postergados incluidos:")
        for item in postponed_items:
            print(f"   - {item['label']}: Fecha {item['fecha']} ({item['dia']})")

    if args.dry_run:
        print("\n🧪 DRY RUN: no se generan imágenes, no se publica y no se registra nada.")
        return

    if already_published and not args.force:
        print("\n⛔ Abortado: la fecha ya figura publicada. Usá --force si querés republicar.")
        return

    if args.skip_generation:
        print("\n⏭️  Generación omitida por --skip-generation. Usando imágenes locales existentes.")
    else:
        run_generation(args.fecha, postponed_items)
        images = expected_images(args.fecha, postponed_items)
        missing = [(label, path) for label, path in images if not path.exists()]

    if missing:
        print("\n⛔ Abortado: siguen faltando imágenes después de generar.")
        for label, path in missing:
            print(f"   - {label}: {path}")
        sys.exit(1)

    if args.publish and args.only in {"instagram", "both"} and len(images) > 20:
        print("\n⛔ Abortado: Instagram permite hasta 20 imágenes por carrusel.")
        print(f"   Este carrusel tiene {len(images)} imágenes. Publicá por partes o usá --only facebook.")
        sys.exit(1)

    print("\n✅ Carrusel listo para publicar.")
    uploaded = []
    if args.skip_upload:
        print("⏭️  Upload omitido por --skip-upload.")
    else:
        uploaded = upload_carousel_images(args.fecha, images)
        print(f"\n✅ {len(uploaded)} imágenes subidas y con URL pública.")

    if not args.publish:
        print("⏭️  Próximo paso: publicar con --publish usando un caption aprobado.")
        return

    if args.skip_upload:
        print("⛔ No se puede publicar con --skip-upload porque Meta necesita URLs públicas.")
        sys.exit(1)

    caption = read_caption_file(args.caption_file) if args.caption_file else build_ai_caption(args.fecha, postponed_items)
    image_urls = [item["url"] for item in uploaded]

    print("\n📝 Caption:")
    print(caption)

    if not args.yes:
        confirm_or_abort(f"¿Publicar fixture fecha {args.fecha} en {args.only}?")

    result = {"caption": caption, "images": uploaded}
    try:
        if args.only in {"instagram", "both"}:
            print("\n📲 Publicando en Instagram...")
            result["instagram"] = publish_instagram_carousel(image_urls, caption)
            print(f"   ✅ Instagram media_id: {result['instagram'].get('media_id')}")

        if args.only in {"facebook", "both"}:
            print("\n📘 Publicando en Facebook...")
            image_paths = [item["prepared_path"] for item in uploaded]
            result["facebook"] = publish_facebook_carousel_from_files(image_paths, caption)
            print(f"   ✅ Facebook post_id: {result['facebook'].get('post_id')}")
    except MetaConfigError as exc:
        print(f"⛔ {exc}")
        sys.exit(1)

    key = record_publication("fixture", args.fecha, result)
    print(f"\n✅ Publicación registrada en {key}")


if __name__ == "__main__":
    main()
