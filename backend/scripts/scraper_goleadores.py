"""Importar la tabla acumulada de goleadores publicada por la Liga."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from pathlib import Path
import re
import sys

from bs4 import BeautifulSoup

from operation_common import add_operation_arguments, load_backend_environment, operation_context_from_args
from scraper_horarios import MONTHS
from scraper_resultados import _identity_text, fetch_result_html, resolve_category, resolve_club_id


SOURCE = "https://www.ligaamateurdedeportes.com.ar/goleadoresprimavera.html"
UPDATED_AT = re.compile(
    r"Actualizado al:\s*\w+\s*,\s*(\d{1,2})\s+(\w+)\s*,\s*(\d{4})\s+(\d{1,2}):(\d{2})",
    re.IGNORECASE,
)


def parse_report(html: str) -> tuple[str, str, list[dict]]:
    soup = BeautifulSoup(html, "html.parser")
    heading = None
    issued_at = None
    category = None
    columns = None
    divisions = set()
    players = set()
    scores = []

    for number, row in enumerate(soup.find_all("tr"), start=1):
        if row.find("table") is not None:
            continue
        cells = [" ".join(cell.get_text(" ", strip=True).split())
                 for cell in row.find_all(("td", "th"), recursive=False)]
        while cells and not cells[-1]:
            cells.pop()
        if not cells:
            continue
        cells = cells[next(i for i, value in enumerate(cells) if value):]
        if len(cells) == 1:
            label = _identity_text(cells[0])
            if label.startswith("ACTUALIZADO AL"):
                stamp = UPDATED_AT.fullmatch(cells[0])
                if stamp is None or stamp[2].lower() not in MONTHS:
                    raise ValueError("No se pudo interpretar la hora de publicación de la Liga.")
                issued_at = datetime(
                    int(stamp[3]), MONTHS[stamp[2].lower()], int(stamp[1]),
                    int(stamp[4]), int(stamp[5]), tzinfo=timezone(timedelta(hours=-3)),
                ).isoformat()
            if label.startswith("GOLEADORES DEL TORNEO "):
                heading = label.removeprefix("GOLEADORES DEL TORNEO ")
            if label.endswith(" DIVISION"):
                category = resolve_category(label.removesuffix(" DIVISION"))[1]
                if category is None or category in divisions:
                    raise ValueError(f"División desconocida o repetida en la fila {number}.")
                divisions.add(category)
                columns = None
            continue

        if category is None:
            continue
        if cells[:2] == ["APELLIDO Y NOMBRE", "CLUB"]:
            if "TOT" not in cells or columns is not None:
                raise ValueError(f"Encabezado de goleadores inesperado en la fila {number}.")
            columns = (len(cells), cells.index("TOT"))
            continue

        if columns is None or len(cells) != columns[0]:
            raise ValueError(f"Fila incompleta en la tabla de goleadores: {number}.")
        name, club = cells[:2]
        club_id = resolve_club_id(club)
        total = cells[columns[1]]
        if not name or club_id is None or not re.fullmatch(r"[0-9]{1,3}", total) or int(total) == 0:
            raise ValueError(f"Jugador, club o total inválido en la fila {number}: {name}, {club}, {total}.")
        key = (category, club_id, _identity_text(name))
        if key in players:
            raise ValueError(f"Jugador duplicado en la fila {number}: {name}, {club}.")
        players.add(key)
        scores.append(dict(categoria_id=category, club_id=club_id, nombre=name, goles=int(total)))

    if not heading or not issued_at or {row["categoria_id"] for row in scores} != set(range(1, 6)):
        raise ValueError("La publicación debe identificar el torneo, la actualización y las cinco divisiones.")
    return heading, issued_at, scores


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    add_operation_arguments(parser)
    parser.add_argument("--source", default=SOURCE, help="Tabla de goleadores o archivo HTML local de prueba.")
    parser.add_argument("--preview-json", type=Path, help="Guardar los datos para la vista previa local.")
    args = parser.parse_args(argv)
    if args.execute and (args.source != SOURCE or args.preview_json):
        parser.error("--execute requiere la página oficial y no se combina con --preview-json.")

    try:
        load_backend_environment()
        context = operation_context_from_args(args)
        heading, issued_at, scores = parse_report(fetch_result_html(args.source))
        counts = Counter(row["categoria_id"] for row in scores)
        print(f"Torneo {context.tournament_id} · {heading} · {issued_at} · {len(scores)} jugadores")
        for label in ("Primera", "Séptima", "Octava", "Novena", "Décima"):
            category = resolve_category(label)[1]
            leader = max(row["goles"] for row in scores if row["categoria_id"] == category)
            print(f"{label}: {counts[category]} jugadores, máximo {leader} goles")

        report = dict(torneo_id=context.tournament_id, emitido_en=issued_at, filas=scores)
        if args.execute or args.preview_json:
            from config import supabase

            tournaments = supabase.table("torneos").select("nombre").eq("id", context.tournament_id).execute().data
            if not tournaments or _identity_text(tournaments[0]["nombre"]) != heading:
                raise ValueError("El campeonato de la publicación no coincide con el torneo seleccionado.")

        if args.preview_json:
            args.preview_json.parent.mkdir(parents=True, exist_ok=True)
            club_ids = sorted({row["club_id"] for row in scores})
            clubs = supabase.table("clubes").select("id,nombre").in_("id", club_ids).execute().data
            club_names = {club["id"]: club["nombre"] for club in clubs}
            preview = {**report, "filas": [
                {**row, "club": club_names[row["club_id"]]} for row in scores
            ]}
            args.preview_json.write_text(json.dumps(preview, ensure_ascii=False), encoding="utf-8")

        if context.execute:
            digest = sha256(json.dumps(report, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
            imported = supabase.table("goleadores_importaciones").upsert(
                {**report, "sha256": digest}, on_conflict="torneo_id,sha256", ignore_duplicates=True,
            ).execute()
            print("Tabla oficial importada." if imported.data else "Esta publicación ya estaba importada.")
        else:
            print("Previsualización sin escritura en Supabase.")
        return 0
    except Exception as exc:
        print(f"No se pudo importar la tabla de goleadores: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
