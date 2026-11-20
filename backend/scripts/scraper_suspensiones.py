"""Import match-specific suspension notices from the league's home page."""

from __future__ import annotations

import argparse
import re
import sys
from datetime import date

from bs4 import BeautifulSoup

from operation_common import (
    A_REPROGRAMAR,
    add_operation_arguments,
    argentina_today,
    load_backend_environment,
    operation_context_from_args,
)
from scraper_resultados import fetch_result_html, read_fixture_inventory, resolve_category, resolve_club_id


DEFAULT_SOURCE = "https://www.ligaamateurdedeportes.com.ar/"
NOTICE = re.compile(
    r"^(?P<day>\d{1,2})[/-](?P<month>\d{1,2})[/-](?P<year>\d{4}|\d{2})\s+"
    r".*?\bhoy\s+deb[ií]an\s+disputarse\s+entre\s+(?P<club>.+?)\s+y\s+"
    r"(?P<opponent>.+?),?\s+en\s+(?P<divisions>.+?)\s+divisi[oó]n(?:es)?,?\s+"
    r"han\s+sido\s+suspendid[oa]s?\b",
    re.IGNORECASE,
)


def parse_notices(html: str) -> tuple[set[tuple[str, int, int, int]], list[str]]:
    notices: set[tuple[str, int, int, int]] = set()
    warnings: list[str] = []
    for box in BeautifulSoup(html, "html.parser").select(".cajablancayroja100"):
        message = " ".join(box.get_text(" ", strip=True).split())
        if not re.search(r"\bsuspendid[oa]s?\b", message, re.IGNORECASE):
            continue
        match = NOTICE.match(message)
        if not match:
            warnings.append(f"Aviso de suspensión sin formato reconocido: {message[:180]}")
            continue
        year = int(match["year"])
        try:
            day = date(year + 2000 if year < 100 else year, int(match["month"]), int(match["day"]))
        except ValueError:
            warnings.append(f"Fecha inválida en aviso de suspensión: {message[:180]}")
            continue

        club = resolve_club_id(match["club"])
        opponent = resolve_club_id(match["opponent"])
        categories = [
            resolve_category(name.strip())[1]
            for name in re.split(r"\s*(?:,|\by\b|\be\b)\s*", match["divisions"], flags=re.IGNORECASE)
        ]
        if club is None or opponent is None or club == opponent or None in categories:
            warnings.append(f"Clubes o divisiones sin identificar en aviso: {message[:180]}")
            continue
        first, second = sorted((club, opponent))
        notices.update(
            (day.isoformat(), category, first, second)
            for category in categories if category is not None
        )
    return notices, warnings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    add_operation_arguments(parser)
    parser.add_argument("--source", default=DEFAULT_SOURCE)
    args = parser.parse_args(argv)

    try:
        load_backend_environment()
        context = operation_context_from_args(args)
        today = argentina_today()
        from config import supabase

        print(f"Suspensiones: {context.mode}, torneo {context.tournament_id}")
        reprogramar = {"estado": A_REPROGRAMAR, "dia": None, "hora": None}
        table = supabase.table("partidos")
        expired = table.update(reprogramar) if context.execute else table.select("id")
        expired = (
            expired.eq("torneo_id", context.tournament_id)
            .eq("estado", "suspendido").lt("dia", today)
            .is_("goles_local", "null").is_("goles_visitante", "null").execute()
        )
        for match in expired.data or []:
            print(f'Partido {match["id"]}: suspensión de un día anterior, pasa a {A_REPROGRAMAR}.')

        notices, warnings = parse_notices(fetch_result_html(args.source))
        for warning in warnings:
            print(f"AVISO: {warning}")
        if not notices:
            print("Sin avisos de suspensión con partidos identificados.")
            return 0

        fixtures = read_fixture_inventory(supabase, context.tournament_id, sorted({key[1] for key in notices}))
        updates = len(expired.data or [])
        for day, category, club, opponent in sorted(notices):
            matches = [
                fixture for fixture in fixtures
                if fixture.date == day and fixture.category_id == category
                and {fixture.local_id, fixture.visitor_id} == {club, opponent}
            ]
            if len(matches) != 1:
                print(f"AVISO: {day}, división {category}, clubes {club} y {opponent}: {len(matches)} partidos coincidentes.")
                continue

            target = matches[0]
            if target.state != "programado" or target.local_goals is not None or target.visitor_goals is not None:
                continue
            values = reprogramar if day < today else {"estado": "suspendido", "hora": None}
            print(f'Partido {target.id}: {day}, división {category}, clubes {club} y {opponent}: {values["estado"]}.')
            if context.execute:
                response = (
                    supabase.table("partidos").update(values)
                    .eq("id", target.id).eq("torneo_id", context.tournament_id)
                    .eq("dia", day).eq("estado", "programado")
                    .is_("goles_local", "null").is_("goles_visitante", "null").execute()
                )
                updates += len(response.data or [])
            else:
                updates += 1
        print(f"{'Actualizaciones aplicadas' if context.execute else 'Actualizaciones previstas'}: {updates}")
        return 0
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"Error al consultar suspensiones: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
