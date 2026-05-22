#!/usr/bin/env python3
import argparse
import sys
from pathlib import Path

from caption_ai import CaptionConfigError, CaptionGenerationError, generate_captions

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SCRIPT_DIR = Path(__file__).resolve().parent
DRAFTS_DIR = SCRIPT_DIR / "drafts"


def parse_args():
    parser = argparse.ArgumentParser(description="Genera borradores de captions con OpenRouter")
    parser.add_argument("--tipo", choices=["tablas", "fixture", "resultados"], required=True)
    parser.add_argument("--fecha", type=int, required=True)
    parser.add_argument("--categoria", choices=["primera", "septima", "octava", "novena", "decima"], help="Categoría para captions de resultados")
    parser.add_argument("--variantes", type=int, default=1)
    return parser.parse_args()


def main():
    args = parse_args()
    DRAFTS_DIR.mkdir(parents=True, exist_ok=True)
    suffix = f"-{args.categoria}" if args.categoria else ""
    output = DRAFTS_DIR / f"{args.tipo}-fecha-{args.fecha}{suffix}.md"

    try:
        captions = generate_captions(args.tipo, args.fecha, args.variantes, args.categoria)
    except (CaptionConfigError, CaptionGenerationError) as exc:
        print(f"⛔ {exc}")
        sys.exit(1)

    lines = [
        f"# Borradores {args.tipo} - Fecha {args.fecha}",
        "",
        "Elegí una opción, editala si hace falta y dejá el texto final en este archivo o copialo a otro.",
        "",
    ]
    for index, caption in enumerate(captions, start=1):
        lines.extend([f"## Opción {index}", "", caption, ""])

    output.write_text("\n".join(lines), encoding="utf-8")
    print(f"✅ Borradores generados: {output}")


if __name__ == "__main__":
    main()
