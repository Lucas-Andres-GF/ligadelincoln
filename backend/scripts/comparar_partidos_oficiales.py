# -*- coding: utf-8 -*-
"""Compare official historical fixtures with Supabase partidos (read-only)."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from fuente_oficial_historica import (
    COMPETENCIA_FILES,
    HISTORICAL_DIRECTORY,
    SOURCE_CATEGORIES,
    club_labels,
    duplicate_keys,
    fetch_rows,
    integer_or_value,
    load_supabase_dependencies,
    match_key,
    normalize_space,
    normalized_date,
    parse_official_fixture,
    positive_int,
    source_url,
)


def read_db_matches(supabase: Any, torneo_id: int, category_id: int) -> List[Mapping[str, Any]]:
    response = (
        supabase.table("partidos")
        .select("fecha_id,local_id,visitante_id,goles_local,goles_visitante,estado,dia")
        .eq("torneo_id", torneo_id)
        .eq("categoria_id", category_id)
        .limit(10000)
        .execute()
    )
    return list(getattr(response, "data", None) or [])


def display_match(row: Mapping[str, Any], labels: Mapping[int, str]) -> Dict[str, Any]:
    result = {
        key: integer_or_value(row.get(key))
        for key in ("fecha_id", "local_id", "visitante_id", "goles_local", "goles_visitante")
    }
    result.update({"dia": row.get("dia"), "estado": row.get("estado")})
    for field in ("local_id", "visitante_id"):
        club_id = result[field]
        result[field.replace("_id", "")] = labels.get(club_id, f"club_id={club_id}")
    return result


def compare_matches(
    official: Mapping[str, Any],
    database: Iterable[Mapping[str, Any]],
    labels: Mapping[int, str],
) -> Dict[str, Any]:
    official_matches = list(official["matches"])
    official_by_key = {match_key(row): row for row in official_matches}
    # The shared parser rejects duplicate official keys before comparison. Keep
    # this field because correction reports already consume it as a safety flag.
    duplicate_official = sorted(
        str(key) for key in duplicate_keys(match_key(row) for row in official_matches)
    )

    db_rows = list(database)
    db_competitive = [
        row for row in db_rows if row.get("local_id") is not None and row.get("visitante_id") is not None
    ]
    db_byes = [
        row for row in db_rows if row.get("local_id") is None or row.get("visitante_id") is None
    ]
    db_by_key: Dict[Tuple[int, int, int], Mapping[str, Any]] = {}
    duplicate_db_keys: List[str] = []
    invalid_db_rows: List[Dict[str, Any]] = []
    for row in db_competitive:
        key = match_key(row)
        if key is None:
            invalid_db_rows.append(dict(row))
            continue
        if key in db_by_key:
            duplicate_db_keys.append(str(key))
        db_by_key[key] = row

    official_keys = {key for key in official_by_key if key is not None}
    database_keys = set(db_by_key)
    missing = [display_match(official_by_key[key], labels) for key in sorted(official_keys - database_keys)]
    extra = [display_match(db_by_key[key], labels) for key in sorted(database_keys - official_keys)]

    mismatches: List[Dict[str, Any]] = []
    for key in sorted(official_keys & database_keys):
        official_row = official_by_key[key]
        db_row = db_by_key[key]
        differences: Dict[str, Dict[str, Any]] = {}
        for field in ("goles_local", "goles_visitante"):
            expected = official_row[field]
            actual = integer_or_value(db_row.get(field))
            if expected != actual:
                differences[field] = {"oficial": expected, "db": actual}
        expected_state = official_row["estado"]
        actual_state = normalize_space(str(db_row.get("estado") or "")).lower()
        if expected_state != actual_state:
            differences["estado"] = {"oficial": expected_state, "db": db_row.get("estado")}
        expected_day = normalized_date(official_row.get("dia"))
        actual_day = normalized_date(db_row.get("dia"))
        if expected_day is not None and expected_day != actual_day:
            differences["dia"] = {"oficial": expected_day, "db": db_row.get("dia")}
        if differences:
            mismatches.append(
                {"key": list(key), "match": display_match(official_row, labels), "differences": differences}
            )

    score_or_state_fields = {"goles_local", "goles_visitante", "estado"}
    return {
        "official_match_count": len(official_matches),
        "official_scheduled_without_score": sum(row["estado"] == "programado" for row in official_matches),
        "db_match_count": len(db_competitive),
        "db_bye_row_count": len(db_byes),
        "missing_in_db": missing,
        "extra_in_db": extra,
        "mismatches": mismatches,
        "score_or_state_mismatches": [
            item for item in mismatches if score_or_state_fields.intersection(item["differences"])
        ],
        "date_only_mismatches": [item for item in mismatches if set(item["differences"]) == {"dia"}],
        "duplicate_official_keys": duplicate_official,
        "duplicate_db_keys": sorted(set(duplicate_db_keys)),
        "invalid_db_rows": invalid_db_rows,
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
    official = parse_official_fixture(fetch_rows(url), url, category, club_map)
    comparison = compare_matches(
        official,
        read_db_matches(supabase, torneo_id, category_id),
        labels,
    )
    comparison.update(
        {
            "category": category,
            "categoria_id": category_id,
            "source_url": url,
            "official_participants": official["participants"],
            "official_byes": official["byes"],
            "official_final_standings": official["final_standings"],
            "final_standings_source": official["final_standings_source"],
            "final_table_omissions": official["final_table_omissions"],
            "fixture_dates": official["date_numbers"],
            "bye_count_difference": len(official["byes"]) - comparison["db_bye_row_count"],
        }
    )
    return comparison


def category_has_drift(category: Mapping[str, Any]) -> bool:
    return bool(
        category["missing_in_db"]
        or category["extra_in_db"]
        or category["mismatches"]
        or category["duplicate_official_keys"]
        or category["duplicate_db_keys"]
        or category["invalid_db_rows"]
        or category.get("bye_count_difference", 0)
    )


def report_has_drift(report: Mapping[str, Any]) -> bool:
    return any(category_has_drift(category) for category in report["categories"])


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compara partidos oficiales históricos con Supabase, sin realizar escrituras."
    )
    parser.add_argument("--torneo-id", required=True, type=positive_int, help="ID positivo del torneo")
    parser.add_argument("--competencia", required=True, choices=tuple(COMPETENCIA_FILES), help="competencia histórica")
    parser.add_argument("--categoria", choices=SOURCE_CATEGORIES, help="categoría; por defecto, todas")
    parser.add_argument("--json", action="store_true", help="emitir el informe como JSON")
    return parser.parse_args(argv)


def print_human_report(report: Mapping[str, Any]) -> None:
    print(f"Comparación oficial de partidos: torneo_id={report['torneo_id']} competencia={report['competencia']}")
    for category in report["categories"]:
        print(f"\n=== {category['category'].upper()} ===")
        print(f"Fuente: {category['source_url']}")
        print(
            f"Participantes oficiales (fixture completo): {len(category['official_participants'])}; "
            f"fechas: {len(category['fixture_dates'])}; partidos oficiales: {category['official_match_count']}"
        )
        if category["final_table_omissions"]:
            print(
                "  Omitidos de la tabla final, pero presentes en el fixture: "
                + ", ".join(row["team"] for row in category["final_table_omissions"])
            )
        print(
            f"  Sin resultado oficial: {category['official_scheduled_without_score']}; "
            f"LIBRE oficiales: {len(category['official_byes'])}; LIBRE DB: {category['db_bye_row_count']}"
        )
        if category["missing_in_db"]:
            print(
                f"  Faltan en DB ({len(category['missing_in_db'])}): "
                + ", ".join(
                    f"F{row['fecha_id']} {row['local']} - {row['visitante']}"
                    for row in category["missing_in_db"]
                )
            )
        if category["extra_in_db"]:
            print(
                f"  Sobran en DB ({len(category['extra_in_db'])}): "
                + ", ".join(
                    f"F{row['fecha_id']} {row['local']} - {row['visitante']}"
                    for row in category["extra_in_db"]
                )
            )
        print(
            "  Diferencias: "
            f"resultado/estado={len(category['score_or_state_mismatches'])}, "
            f"solo fecha={len(category['date_only_mismatches'])}, total={len(category['mismatches'])}"
        )
        for mismatch in category["score_or_state_mismatches"]:
            match = mismatch["match"]
            details = ", ".join(
                f"{field} oficial={values['oficial']} DB={values['db']}"
                for field, values in mismatch["differences"].items()
            )
            print(
                f"    F{match['fecha_id']} {match['local']} "
                f"{match['goles_local']}-{match['goles_visitante']} {match['visitante']}: {details}"
            )
        if category["duplicate_db_keys"]:
            print(f"  ADVERTENCIA: claves duplicadas en DB: {', '.join(category['duplicate_db_keys'])}")
        if category["invalid_db_rows"]:
            print(f"  ADVERTENCIA: filas DB no comparables: {len(category['invalid_db_rows'])}")
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
    except Exception as exc:
        message = f"No se pudo completar la comparación: {exc}"
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
