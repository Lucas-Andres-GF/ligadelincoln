# -*- coding: utf-8 -*-
"""Read-only standings audit against the shared historical official source."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

from fuente_oficial_historica import (
    COMPETENCIA_FILES,
    HISTORICAL_DIRECTORY,
    SOURCE_CATEGORIES,
    STAT_FIELDS,
    club_labels,
    fetch_rows,
    integer_or_value,
    load_supabase_dependencies,
    parse_official_standings,
    positive_int,
    source_url,
)


def read_db_positions(supabase: Any, torneo_id: int, category_id: int) -> List[Mapping[str, Any]]:
    response = (
        supabase.table("posiciones")
        .select("club_id,pts,pj,pg,pe,pp,gf,gc")
        .eq("torneo_id", torneo_id)
        .eq("categoria_id", category_id)
        .limit(10000)
        .execute()
    )
    return list(getattr(response, "data", None) or [])


def read_db_matches(supabase: Any, torneo_id: int, category_id: int) -> List[Mapping[str, Any]]:
    response = (
        supabase.table("partidos")
        .select("id,estado,local_id,visitante_id")
        .eq("torneo_id", torneo_id)
        .eq("categoria_id", category_id)
        .limit(10000)
        .execute()
    )
    return list(getattr(response, "data", None) or [])


def compare_positions(
    official: Sequence[Mapping[str, Any]],
    database: Sequence[Mapping[str, Any]],
    labels: Mapping[int, str],
) -> Dict[str, Any]:
    db_by_club: Dict[int, Dict[str, Any]] = {}
    duplicate_db_clubs: List[int] = []
    invalid_db_rows: List[Dict[str, Any]] = []
    for row in database:
        club_id = integer_or_value(row.get("club_id"))
        if not isinstance(club_id, int):
            invalid_db_rows.append(dict(row))
            continue
        if club_id in db_by_club:
            duplicate_db_clubs.append(club_id)
        db_by_club[club_id] = {field: integer_or_value(row.get(field)) for field in STAT_FIELDS}

    official_ids = {int(row["club_id"]) for row in official}
    missing_in_db = [
        {"club_id": row["club_id"], "team": row["team"]}
        for row in official
        if row["club_id"] not in db_by_club
    ]
    extra_in_db = [
        {"club_id": club_id, "team": labels.get(club_id, f"club_id={club_id}")}
        for club_id in sorted(set(db_by_club) - official_ids)
    ]
    differences: List[Dict[str, Any]] = []
    for row in official:
        club_id = int(row["club_id"])
        db_row = db_by_club.get(club_id)
        if db_row is None:
            continue
        field_differences = {
            field: {"official": row[field], "db": db_row[field]}
            for field in STAT_FIELDS
            if row[field] != db_row[field]
        }
        if field_differences:
            differences.append({"club_id": club_id, "team": row["team"], "fields": field_differences})

    return {
        "official_rows": [dict(row) for row in official],
        "db_rows": [
            {
                "club_id": integer_or_value(row.get("club_id")),
                **{field: integer_or_value(row.get(field)) for field in STAT_FIELDS},
            }
            for row in database
        ],
        "differences": differences,
        "missing_in_db": missing_in_db,
        "extra_in_db": extra_in_db,
        "duplicate_db_club_ids": sorted(set(duplicate_db_clubs)),
        "invalid_db_rows": invalid_db_rows,
    }


def match_inventory(
    matches: Iterable[Mapping[str, Any]], official_rows: Sequence[Mapping[str, Any]]
) -> Dict[str, Any]:
    rows = list(matches)
    competitive = [row for row in rows if row.get("local_id") is not None and row.get("visitante_id") is not None]
    played = [row for row in competitive if str(row.get("estado") or "").strip().lower() == "jugado"]
    pairings = set()
    for row in played:
        local_id = integer_or_value(row.get("local_id"))
        visitor_id = integer_or_value(row.get("visitante_id"))
        if isinstance(local_id, int) and isinstance(visitor_id, int):
            pairings.add(tuple(sorted((local_id, visitor_id))))
    official_pj_sum = sum(int(row["pj"]) for row in official_rows)
    return {
        "total": len(rows),
        "bye_rows": len(rows) - len(competitive),
        "competitive_total": len(competitive),
        "played": len(played),
        "scheduled_or_not_played": len(competitive) - len(played),
        "distinct_played_pairings": len(pairings),
        "official_pj_sum": official_pj_sum,
        "official_pj_implied_matches": official_pj_sum / 2,
        "official_pj_minus_db_played_twice": official_pj_sum - 2 * len(played),
    }


def audit_category(
    supabase: Any,
    torneo_id: int,
    competencia: str,
    category: str,
    category_ids: Mapping[str, int],
    club_map: Mapping[str, int],
    labels: Mapping[int, str],
) -> Dict[str, Any]:
    category_id = int(category_ids[category])
    url = source_url(competencia, category)
    official = parse_official_standings(fetch_rows(url), url, category, club_map)
    comparison = compare_positions(
        official,
        read_db_positions(supabase, torneo_id, category_id),
        labels,
    )
    comparison.update(
        {
            "category": category,
            "categoria_id": category_id,
            "source_url": url,
            "match_inventory": match_inventory(
                read_db_matches(supabase, torneo_id, category_id), official
            ),
        }
    )
    return comparison


def category_has_drift(category: Mapping[str, Any]) -> bool:
    inventory = category["match_inventory"]
    return bool(
        category["differences"]
        or category["missing_in_db"]
        or category["extra_in_db"]
        or category["duplicate_db_club_ids"]
        or category.get("invalid_db_rows")
        or inventory["official_pj_minus_db_played_twice"] != 0
    )


def report_has_drift(report: Mapping[str, Any]) -> bool:
    return any(category_has_drift(category) for category in report["categories"])


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audita posiciones y partidos de un torneo contra páginas oficiales históricas (solo lectura)."
    )
    parser.add_argument("--torneo-id", required=True, type=positive_int, help="ID positivo del torneo")
    parser.add_argument("--competencia", required=True, choices=tuple(COMPETENCIA_FILES), help="familia de URLs oficiales")
    parser.add_argument("--categoria", choices=SOURCE_CATEGORIES, help="auditar una categoría; por defecto, todas")
    parser.add_argument("--json", action="store_true", help="emitir el informe como JSON")
    return parser.parse_args(argv)


def print_human_report(report: Mapping[str, Any]) -> None:
    print(f"Auditoría oficial: torneo_id={report['torneo_id']} competencia={report['competencia']}")
    print(f"Generado: {report['generated_at']}")
    for category in report["categories"]:
        print(f"\n=== {category['category'].upper()} ===")
        print(f"Fuente: {category['source_url']}")
        print(
            "Posiciones: "
            f"{len(category['official_rows'])} oficiales, {len(category['db_rows'])} en DB, "
            f"{len(category['differences'])} equipos con diferencias"
        )
        if category["missing_in_db"]:
            print("  Faltan en DB: " + ", ".join(row["team"] for row in category["missing_in_db"]))
        if category["extra_in_db"]:
            print("  Sobran en DB: " + ", ".join(row["team"] for row in category["extra_in_db"]))
        if category["duplicate_db_club_ids"]:
            print(f"  ADVERTENCIA: club_id duplicados: {category['duplicate_db_club_ids']}")
        for difference in category["differences"]:
            details = ", ".join(
                f"{field} oficial={values['official']} DB={values['db']}"
                for field, values in difference["fields"].items()
            )
            print(f"  Diferencia {difference['team']}: {details}")
        inventory = category["match_inventory"]
        print(
            "Partidos DB: "
            f"total={inventory['total']}, jugados={inventory['played']}, "
            f"programados/no jugados={inventory['scheduled_or_not_played']}, "
            f"parejas jugadas distintas={inventory['distinct_played_pairings']}"
        )
        print(
            "  Referencia PJ oficial: "
            f"suma={inventory['official_pj_sum']} "
            f"(partidos implícitos={inventory['official_pj_implied_matches']}); "
            f"brecha PJ vs DB={inventory['official_pj_minus_db_played_twice']}"
        )
    print("\nModo solo lectura: no se realizaron escrituras en Supabase.")


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    generated_at = datetime.now(timezone.utc).isoformat()
    categories = [args.categoria] if args.categoria else list(SOURCE_CATEGORIES)
    try:
        supabase, club_map, category_ids = load_supabase_dependencies()
        missing_categories = [category for category in categories if category not in category_ids]
        if missing_categories:
            raise RuntimeError(f"Categorías sin identidad autoritativa: {missing_categories}")
        labels = club_labels(club_map)
        report = {
            "generated_at": generated_at,
            "torneo_id": args.torneo_id,
            "competencia": args.competencia,
            "source_directory": HISTORICAL_DIRECTORY,
            "source_urls": {category: source_url(args.competencia, category) for category in categories},
            "categories": [
                audit_category(
                    supabase, args.torneo_id, args.competencia, category, category_ids, club_map, labels
                )
                for category in categories
            ],
        }
    except Exception as exc:  # CLI boundary: source/config/DB failures are operational failures.
        message = f"No se pudo completar la auditoría: {exc}"
        if args.json:
            print(json.dumps({"generated_at": generated_at, "error": message}, ensure_ascii=False, indent=2))
        else:
            print(f"ERROR: {message}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print_human_report(report)
    return 1 if report_has_drift(report) else 0


if __name__ == "__main__":
    raise SystemExit(main())
