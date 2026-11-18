"""Import complete COMET yellow-card reports for Primera."""

import argparse
from base64 import b64encode
from collections import Counter
from datetime import datetime, timedelta, timezone
import hashlib
from io import BytesIO
import json
from pathlib import Path
import re
import sys
import unicodedata

import requests

from operation_common import add_operation_arguments


SOURCE = "https://www.ligaamateurdedeportes.com.ar/amarillas%20acumuladas.pdf"
MAX_BYTES = 5_000_000
# COMET reuses the parent competition ID across phases. Check the phase too.
COMPETITIONS = {3: ("343121403", "PRIM/VER 2026 PRIMERA - 2026")}
CLUBS = {
    "ARGENTINO (LINCOLN)": (1, "Argentino"),
    "PASTEUR Y F.C.OESTE": (2, "Atl. Pasteur"),
    "ATLETICO ROBERTS": (3, "Atl. Roberts"),
    "PINTENSE": (4, "CA. Pintense"),
    "CASET": (5, "Caset"),
    "DEPORTIVO ARENAZA": (6, "Dep. Arenaza"),
    "DEPORTIVO PINTO": (7, "Dep. Gral Pinto"),
    "EL LINQUENO": (8, "El Linqueño"),
    "JUVENTUD UNIDA (LINCOLN)": (9, "Juventud Unida"),
    "SAN MARTIN (ROBERTS)": (10, "San Martin"),
    "SAN MARTIN": (10, "San Martin"),
    "VILLA FRANCIA": (11, "Villa Francia"),
}


def normalize(value):
    return "".join(
        char for char in unicodedata.normalize("NFD", value.upper())
        if not unicodedata.combining(char)
    )


def parse_report(text, torneo_id):
    if not re.search(r"(?m)^\s*Tarjetas Amarillas Acumuladas\s*$", text):
        raise ValueError("El PDF no es un informe de amarillas.")
    if not re.search(r"(?m)^Organizaci.n:\s*\(71675\)", text):
        raise ValueError("El informe no pertenece a la Liga de Lincoln.")
    competition = re.search(r"(?m)^Competici.n:\s*\((\d+)\).* / ([^\n]+)", text)
    if not competition or (competition[1], competition[2].strip()) != COMPETITIONS.get(torneo_id):
        raise ValueError("La competición del PDF no coincide con el torneo configurado.")
    issued = re.search(r"Fecha:\s*(\d{2}\.\d{2}\.\d{4})\s+Hora:\s*(\d{2}:\d{2}:\d{2})\s+ART", text)
    total = re.search(r"N.MERO TOTAL DE RESULTADOS:\s*(\d+)", text)
    if not issued or not total:
        raise ValueError("Faltan la fecha de emisión o el total de registros.")
    issued_at = datetime.strptime(" ".join(issued.groups()), "%d.%m.%Y %H:%M:%S")
    issued_at = issued_at.replace(tzinfo=timezone(timedelta(hours=-3))).isoformat()
    rows = []
    seen = set()
    club = group = None
    for line_number, raw in enumerate(text[total.end():].splitlines(), start=1):
        line = " ".join(raw.split())
        if not line or line.startswith("COMET - "):
            continue
        heading = re.fullmatch(r"(\d+) Tarjetas amarillas acumuladas", line, re.I)
        if heading:
            group = int(heading[1])
            club = None
            continue
        if normalize(line) in CLUBS:
            club = CLUBS[normalize(line)]
            continue
        player = re.fullmatch(r"(\d+) (.+?) \((Jugador|Cuerpo técnico)\)\s*(\d+)", line, re.I)
        if not player or club is None or int(player[4]) != group or not 1 <= group <= 32767:
            raise ValueError(f"Fila incompatible o club desconocido en el bloque de datos ({line_number}).")
        comet_id = int(player[1])
        role = "jugador" if player[3].lower() == "jugador" else "cuerpo_tecnico"
        key = (comet_id, club[0], role)
        if key in seen:
            raise ValueError("El informe repite una identidad en el mismo club y rol.")
        seen.add(key)
        rows.append(dict(comet_id=comet_id, nombre=player[2], rol=role,
                         club_id=club[0], club=club[1], amarillas=group))
    if len(rows) != int(total[1]) or not rows:
        raise ValueError(f"El PDF declara {total[1]} registros y se extrajeron {len(rows)}.")
    return issued_at, rows


def fetch_pdf():
    with requests.get(SOURCE, timeout=30, stream=True) as response:
        response.raise_for_status()
        content = bytearray()
        for chunk in response.iter_content(chunk_size=65536):
            content.extend(chunk)
            if len(content) > MAX_BYTES:
                raise ValueError("El PDF supera el tamaño máximo admitido.")
        return bytes(content)


def compare_reports(previous, current):
    def index(rows):
        return {(row["comet_id"], row["club_id"], row["rol"]): row for row in rows}

    before = index(previous)
    after = index(current)
    lines = []
    for key in sorted(before.keys() | after.keys()):
        old, new = before.get(key), after.get(key)
        row = new or old
        label = f'{row["nombre"]} · {row["club"]} · {row["rol"].replace("_", " ")}'
        if old is None:
            lines.append(f'{label}: aparece con {new["amarillas"]}')
        elif new is None:
            lines.append(f'{label}: ya no figura (antes {old["amarillas"]})')
        elif old["amarillas"] != new["amarillas"]:
            lines.append(f'{label}: {old["amarillas"]} → {new["amarillas"]}')
    return lines


def print_history_comparison(client, torneo_id):
    reports = (
        client.table("amarillas_importaciones")
        .select("emitido_en,filas")
        .eq("torneo_id", torneo_id)
        .order("emitido_en", desc=True)
        .order("importado_en", desc=True)
        .order("sha256", desc=True)
        .limit(2)
        .execute()
        .data
    )
    if len(reports) < 2:
        print("La comparación requiere dos informes archivados de este torneo.")
        return
    latest, previous = reports
    print(f'Comparación: {previous["emitido_en"]} → {latest["emitido_en"]}')
    changes = compare_reports(previous["filas"], latest["filas"])
    print("\n".join(changes) if changes else "Sin cambios en las amarillas informadas.")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    add_operation_arguments(parser, tournament_required=True)
    parser.add_argument("--source", type=Path, help="PDF local para previsualizar.")
    parser.add_argument("--preview-json", type=Path, help="Guardar una copia local para el frontend.")
    parser.add_argument("--compare-history", action="store_true",
                        help="Comparar las dos últimas versiones archivadas, en modo de solo lectura.")
    args = parser.parse_args(argv)
    if args.execute and (args.source or args.preview_json):
        parser.error("--execute requiere la fuente oficial y no se combina con --preview-json.")
    if args.compare_history and (args.execute or args.source or args.preview_json):
        parser.error("--compare-history se usa solo con --torneo-id.")
    try:
        if args.compare_history:
            from config import supabase

            print_history_comparison(supabase, args.torneo_id)
            return 0

        from pypdf import PdfReader

        if args.source:
            with args.source.open("rb") as file:
                pdf = file.read(MAX_BYTES + 1)
        else:
            pdf = fetch_pdf()
        if not pdf.startswith(b"%PDF-") or len(pdf) > MAX_BYTES:
            raise ValueError("El archivo no es un PDF válido dentro del tamaño admitido.")
        reader = PdfReader(BytesIO(pdf))
        if not 1 <= len(reader.pages) <= 50:
            raise ValueError("Cantidad de páginas inesperada.")
        issued_at, rows = parse_report(
            "\n".join(page.extract_text() or "" for page in reader.pages), args.torneo_id,
        )
        counts = Counter(row["amarillas"] for row in rows if row["rol"] == "jugador")
        print(f"Torneo {args.torneo_id} · informe {issued_at} · {len(rows)} registros")
        print(f"Jugadores por cantidad de amarillas: {dict(sorted(counts.items()))}")
        print(f"Cuerpo técnico: {len(rows) - sum(counts.values())}")
        if args.preview_json:
            public_rows = [{key: value for key, value in row.items() if key != "comet_id"} for row in rows]
            payload = dict(torneo_id=args.torneo_id, emitido_en=issued_at, filas=public_rows)
            args.preview_json.parent.mkdir(parents=True, exist_ok=True)
            args.preview_json.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        if args.execute:
            from config import supabase

            archived = supabase.table("amarillas_importaciones").upsert(
                dict(torneo_id=args.torneo_id, emitido_en=issued_at, filas=rows,
                     pdf_base64=b64encode(pdf).decode("ascii"),
                     sha256=hashlib.sha256(pdf).hexdigest()),
                on_conflict="torneo_id,sha256", ignore_duplicates=True,
            ).execute()
            print("PDF original archivado." if archived.data else "Ese PDF ya estaba archivado.")
        else:
            print("Previsualización sin escritura en Supabase.")
        return 0
    except Exception as exc:
        print(f"No se pudo procesar el informe: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
