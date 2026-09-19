# -*- coding: utf-8 -*-
"""Propose or apply exact historical result corrections from the official fixture.

The default mode is a dry run. This script never inserts partidos, never updates
LIBRE rows, and never deletes posiciones. Categories whose competitive fixture
does not match the database exactly are reported and skipped.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence, Tuple

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


POSITION_FIELDS = ("pts", "pj", "pg", "pe", "pp", "gf", "gc", "dif")
POSITION_FIELD_LABELS = {
    "pts": "puntos",
    "pj": "partidos_jugados",
    "pg": "ganados",
    "pe": "empatados",
    "pp": "perdidos",
    "gf": "goles_favor",
    "gc": "goles_contra",
    "dif": "diferencia_goles",
}
MATCH_UPDATE_FIELDS = ("goles_local", "goles_visitante", "estado", "dia")
MatchKey = Tuple[int, int, int]


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Propone correcciones exactas desde el fixture oficial y recalcula posiciones. "
            "Por defecto no escribe en Supabase."
        )
    )
    parser.add_argument("--torneo-id", required=True, type=positive_int, help="ID positivo del torneo")
    parser.add_argument(
        "--competencia",
        required=True,
        choices=tuple(COMPETENCIA_FILES),
        help="competencia histórica oficial",
    )
    parser.add_argument("--categoria", choices=SOURCE_CATEGORIES, help="categoría; por defecto, todas")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="aplicar únicamente las actualizaciones informadas (sin esta opción es dry-run)",
    )
    parser.add_argument(
        "--include-dates",
        action="store_true",
        help="incluir cambios de dia; por defecto se ignoran incluso junto con otros cambios",
    )
    parser.add_argument("--json", action="store_true", help="emitir un informe JSON estructurado")
    return parser.parse_args(argv)


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


def read_db_positions(supabase: Any, torneo_id: int, category_id: int) -> List[Mapping[str, Any]]:
    response = (
        supabase.table("posiciones")
        .select("club_id,pts,pj,pg,pe,pp,gf,gc,dif")
        .eq("torneo_id", torneo_id)
        .eq("categoria_id", category_id)
        .limit(10000)
        .execute()
    )
    return list(getattr(response, "data", None) or [])


def _played_competitive(row: Mapping[str, Any]) -> bool:
    if match_key(row) is None:
        return False
    state = normalize_space(str(row.get("estado") or "")).lower()
    return (
        state == "jugado"
        and isinstance(integer_or_value(row.get("goles_local")), int)
        and isinstance(integer_or_value(row.get("goles_visitante")), int)
    )


def _db_matches_by_key(rows: Iterable[Mapping[str, Any]]) -> Dict[MatchKey, Mapping[str, Any]]:
    indexed: Dict[MatchKey, Mapping[str, Any]] = {}
    for row in rows:
        key = match_key(row)
        if key is not None:
            indexed[key] = row
    return indexed


def _display_match(row: Mapping[str, Any], labels: Mapping[int, str]) -> Dict[str, Any]:
    result = {
        key: integer_or_value(row.get(key))
        for key in ("fecha_id", "local_id", "visitante_id", "goles_local", "goles_visitante")
    }
    result.update({"dia": row.get("dia"), "estado": row.get("estado")})
    result["local"] = labels.get(result["local_id"], f"club_id={result['local_id']}")
    result["visitante"] = labels.get(
        result["visitante_id"], f"club_id={result['visitante_id']}"
    )
    return result


def compare_matches_for_correction(
    official: Mapping[str, Any],
    database: Sequence[Mapping[str, Any]],
    labels: Mapping[int, str],
) -> Dict[str, Any]:
    """Build the exact inventory/difference view needed by correction planning."""
    official_matches = list(official["matches"])
    official_by_key = {match_key(row): row for row in official_matches}
    db_competitive = [
        row
        for row in database
        if row.get("local_id") is not None and row.get("visitante_id") is not None
    ]
    db_by_key: Dict[MatchKey, Mapping[str, Any]] = {}
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
            mismatches.append({"key": list(key), "differences": differences})

    return {
        "missing_in_db": [
            _display_match(official_by_key[key], labels)
            for key in sorted(official_keys - database_keys)
        ],
        "extra_in_db": [
            _display_match(db_by_key[key], labels)
            for key in sorted(database_keys - official_keys)
        ],
        "mismatches": mismatches,
        "date_only_mismatches": [
            item for item in mismatches if set(item["differences"]) == {"dia"}
        ],
        "duplicate_official_keys": sorted(
            str(key) for key in duplicate_keys(match_key(row) for row in official_matches)
        ),
        "duplicate_db_keys": sorted(set(duplicate_db_keys)),
        "invalid_db_rows": invalid_db_rows,
    }


def build_match_corrections(
    official: Mapping[str, Any],
    database: Sequence[Mapping[str, Any]],
    comparison: Mapping[str, Any],
    include_dates: bool,
    labels: Mapping[int, str],
) -> List[Dict[str, Any]]:
    """Return corrections only for exact-key DB matches with an official played score."""
    official_by_key = {
        match_key(row): row
        for row in official["matches"]
        if row.get("estado") == "jugado" and match_key(row) is not None
    }
    db_by_key = _db_matches_by_key(database)
    corrections: List[Dict[str, Any]] = []

    for mismatch in comparison["mismatches"]:
        key = tuple(mismatch["key"])
        official_row = official_by_key.get(key)
        db_row = db_by_key.get(key)
        if official_row is None or db_row is None:
            continue

        changes: Dict[str, Dict[str, Any]] = {}
        for field in ("goles_local", "goles_visitante", "estado"):
            if field in mismatch["differences"]:
                changes[field] = {
                    "from": db_row.get(field),
                    "to": official_row.get(field),
                }
        if include_dates and "dia" in mismatch["differences"]:
            official_day = normalized_date(official_row.get("dia"))
            if official_day is not None:
                changes["dia"] = {"from": db_row.get("dia"), "to": official_day}
        if not changes:
            continue

        fecha_id, local_id, visitante_id = key
        corrections.append(
            {
                "key": {
                    "torneo_id": None,
                    "categoria_id": None,
                    "fecha_id": fecha_id,
                    "local_id": local_id,
                    "visitante_id": visitante_id,
                },
                "match": {
                    "fecha_id": fecha_id,
                    "local_id": local_id,
                    "local": labels.get(local_id, f"club_id={local_id}"),
                    "visitante_id": visitante_id,
                    "visitante": labels.get(visitante_id, f"club_id={visitante_id}"),
                },
                "changes": changes,
            }
        )
    return corrections


def corrected_matches(
    database: Sequence[Mapping[str, Any]], corrections: Sequence[Mapping[str, Any]]
) -> List[Dict[str, Any]]:
    """Apply proposed corrections to a detached snapshot for standings calculation."""
    changes_by_key: Dict[MatchKey, Mapping[str, Any]] = {}
    for correction in corrections:
        key_data = correction["key"]
        key = (
            int(key_data["fecha_id"]),
            int(key_data["local_id"]),
            int(key_data["visitante_id"]),
        )
        changes_by_key[key] = correction["changes"]

    result: List[Dict[str, Any]] = []
    for original in database:
        row = dict(original)
        key = match_key(row)
        for field, change in changes_by_key.get(key, {}).items():
            row[field] = change["to"]
        result.append(row)
    return result


def calculate_positions(
    matches: Iterable[Mapping[str, Any]], torneo_id: int, category_id: int
) -> List[Dict[str, int]]:
    """Calculate standings from played competitive DB matches only."""
    stats: Dict[int, Dict[str, int]] = {}

    for row in matches:
        if not _played_competitive(row):
            continue
        local_id = int(row["local_id"])
        visitor_id = int(row["visitante_id"])
        local_goals = int(row["goles_local"])
        visitor_goals = int(row["goles_visitante"])

        for club_id in (local_id, visitor_id):
            stats.setdefault(
                club_id,
                {"pts": 0, "pj": 0, "pg": 0, "pe": 0, "pp": 0, "gf": 0, "gc": 0},
            )

        local = stats[local_id]
        visitor = stats[visitor_id]
        local["pj"] += 1
        visitor["pj"] += 1
        local["gf"] += local_goals
        local["gc"] += visitor_goals
        visitor["gf"] += visitor_goals
        visitor["gc"] += local_goals

        if local_goals > visitor_goals:
            local["pts"] += 3
            local["pg"] += 1
            visitor["pp"] += 1
        elif local_goals < visitor_goals:
            visitor["pts"] += 3
            visitor["pg"] += 1
            local["pp"] += 1
        else:
            local["pts"] += 1
            visitor["pts"] += 1
            local["pe"] += 1
            visitor["pe"] += 1

    positions: List[Dict[str, int]] = []
    for club_id in sorted(stats):
        values = stats[club_id]
        positions.append(
            {
                "torneo_id": torneo_id,
                "categoria_id": category_id,
                "club_id": club_id,
                **values,
                "dif": values["gf"] - values["gc"],
            }
        )
    return positions


def _position_values(row: Mapping[str, Any]) -> Dict[str, Any]:
    return {field: integer_or_value(row.get(field)) for field in POSITION_FIELDS}


def build_position_actions(
    calculated: Sequence[Mapping[str, Any]],
    existing: Sequence[Mapping[str, Any]],
    labels: Mapping[int, str],
) -> Dict[str, Any]:
    existing_by_club: Dict[int, Mapping[str, Any]] = {}
    duplicate_club_ids: List[int] = []
    invalid_existing_rows: List[Dict[str, Any]] = []
    for row in existing:
        club_id = integer_or_value(row.get("club_id"))
        if not isinstance(club_id, int):
            invalid_existing_rows.append(dict(row))
            continue
        if club_id in existing_by_club:
            duplicate_club_ids.append(club_id)
        existing_by_club[club_id] = row

    calculated_ids = {int(row["club_id"]) for row in calculated}
    extras = [
        {"club_id": club_id, "club": labels.get(club_id, f"club_id={club_id}")}
        for club_id in sorted(set(existing_by_club) - calculated_ids)
    ]
    actions: List[Dict[str, Any]] = []

    for row in calculated:
        club_id = int(row["club_id"])
        current = existing_by_club.get(club_id)
        desired = _position_values(row)
        key = {
            "torneo_id": int(row["torneo_id"]),
            "categoria_id": int(row["categoria_id"]),
            "club_id": club_id,
        }
        if current is None:
            actions.append(
                {
                    "operation": "insert",
                    "key": key,
                    "club": labels.get(club_id, f"club_id={club_id}"),
                    "values": desired,
                }
            )
            continue

        current_values = _position_values(current)
        changes = {
            POSITION_FIELD_LABELS[field]: {"from": current_values[field], "to": desired[field]}
            for field in POSITION_FIELDS
            if current_values[field] != desired[field]
        }
        if changes:
            actions.append(
                {
                    "operation": "update",
                    "key": key,
                    "club": labels.get(club_id, f"club_id={club_id}"),
                    "changes": changes,
                    "values": desired,
                }
            )

    return {
        "actions": actions,
        "extra_existing": extras,
        "duplicate_club_ids": sorted(set(duplicate_club_ids)),
        "invalid_existing_rows": invalid_existing_rows,
    }


def analyze_category(
    supabase: Any,
    torneo_id: int,
    competencia: str,
    category: str,
    category_ids: Mapping[str, int],
    club_map: Mapping[str, int],
    labels: Mapping[int, str],
    include_dates: bool,
) -> Dict[str, Any]:
    category_id = int(category_ids[category])
    url = source_url(competencia, category)
    official = parse_official_fixture(fetch_rows(url), url, category, club_map)
    database = read_db_matches(supabase, torneo_id, category_id)
    comparison = compare_matches_for_correction(official, database, labels)

    detected_corrections = build_match_corrections(
        official, database, comparison, include_dates, labels
    )
    for correction in detected_corrections:
        correction["key"]["torneo_id"] = torneo_id
        correction["key"]["categoria_id"] = category_id

    skip_reasons: List[str] = []
    if comparison["missing_in_db"]:
        skip_reasons.append("faltan partidos competitivos en DB")
    if comparison["extra_in_db"]:
        skip_reasons.append("sobran partidos competitivos en DB")
    if comparison["duplicate_official_keys"]:
        skip_reasons.append("hay claves oficiales duplicadas")
    if comparison["duplicate_db_keys"]:
        skip_reasons.append("hay claves de partidos duplicadas en DB")
    if comparison["invalid_db_rows"]:
        skip_reasons.append("hay partidos competitivos no comparables en DB")

    position_result: Dict[str, Any] = {
        "actions": [],
        "extra_existing": [],
        "duplicate_club_ids": [],
        "invalid_existing_rows": [],
    }
    calculated_positions: List[Dict[str, int]] = []
    if not skip_reasons:
        in_memory_matches = corrected_matches(database, detected_corrections)
        calculated_positions = calculate_positions(in_memory_matches, torneo_id, category_id)
        existing_positions = read_db_positions(supabase, torneo_id, category_id)
        position_result = build_position_actions(calculated_positions, existing_positions, labels)
        if position_result["duplicate_club_ids"]:
            skip_reasons.append("hay posiciones duplicadas en DB")
        if position_result["invalid_existing_rows"]:
            skip_reasons.append("hay posiciones sin club_id válido en DB")

    skipped = bool(skip_reasons)
    return {
        "category": category,
        "categoria_id": category_id,
        "source_url": url,
        "skipped": skipped,
        "skip_reasons": skip_reasons,
        "missing_in_db": comparison["missing_in_db"],
        "extra_in_db": comparison["extra_in_db"],
        "date_only_differences_ignored": (
            comparison["date_only_mismatches"] if not include_dates else []
        ),
        "detected_match_corrections": detected_corrections,
        "calculated_position_count": len(calculated_positions),
        "extra_existing_positions": position_result["extra_existing"],
        "duplicate_position_club_ids": position_result["duplicate_club_ids"],
        "invalid_existing_positions": position_result["invalid_existing_rows"],
        "actions": {
            "partidos": [] if skipped else detected_corrections,
            "posiciones": [] if skipped else position_result["actions"],
        },
    }


def execute_category(supabase: Any, category: Mapping[str, Any]) -> Dict[str, int]:
    """Apply only scoped updates/inserts from a previously validated category plan."""
    if category["skipped"]:
        return {"partidos_updated": 0, "posiciones_updated": 0, "posiciones_inserted": 0}

    counts = {"partidos_updated": 0, "posiciones_updated": 0, "posiciones_inserted": 0}
    for action in category["actions"]["partidos"]:
        key = action["key"]
        payload = {
            field: change["to"]
            for field, change in action["changes"].items()
            if field in MATCH_UPDATE_FIELDS
        }
        (
            supabase.table("partidos")
            .update(payload)
            .eq("torneo_id", key["torneo_id"])
            .eq("categoria_id", key["categoria_id"])
            .eq("fecha_id", key["fecha_id"])
            .eq("local_id", key["local_id"])
            .eq("visitante_id", key["visitante_id"])
            .execute()
        )
        counts["partidos_updated"] += 1

    for action in category["actions"]["posiciones"]:
        key = action["key"]
        values = action["values"]
        if action["operation"] == "update":
            (
                supabase.table("posiciones")
                .update(values)
                .eq("torneo_id", key["torneo_id"])
                .eq("categoria_id", key["categoria_id"])
                .eq("club_id", key["club_id"])
                .execute()
            )
            counts["posiciones_updated"] += 1
        else:
            supabase.table("posiciones").insert({**key, **values}).execute()
            counts["posiciones_inserted"] += 1
    return counts


def _format_changes(changes: Mapping[str, Mapping[str, Any]]) -> str:
    return ", ".join(
        f"{field}: {values['from']!r} -> {values['to']!r}"
        for field, values in changes.items()
    )


def print_human_report(report: Mapping[str, Any]) -> None:
    mode = "EJECUCIÓN" if report["execute"] else "DRY-RUN"
    print(
        f"Corrección desde fuente oficial — {mode}: "
        f"torneo_id={report['torneo_id']} competencia={report['competencia']}"
    )
    if not report["include_dates"]:
        print("Las diferencias de dia se informan pero no se proponen para actualización.")

    for category in report["categories"]:
        print(f"\n=== {category['category'].upper()} ===")
        print(f"Fuente: {category['source_url']}")
        if category["missing_in_db"]:
            print(f"  Faltan en DB ({len(category['missing_in_db'])}):")
            for row in category["missing_in_db"]:
                print(f"    F{row['fecha_id']} {row['local']} - {row['visitante']}")
        if category["extra_in_db"]:
            print(f"  Sobran en DB ({len(category['extra_in_db'])}):")
            for row in category["extra_in_db"]:
                print(f"    F{row['fecha_id']} {row['local']} - {row['visitante']}")
        if category["skipped"]:
            print("  OMITIDA por seguridad: " + "; ".join(category["skip_reasons"]))
            continue

        partido_actions = category["actions"]["partidos"]
        print(f"  Correcciones de partidos: {len(partido_actions)}")
        for action in partido_actions:
            match = action["match"]
            print(
                f"    F{match['fecha_id']} {match['local']} - {match['visitante']}: "
                f"{_format_changes(action['changes'])}"
            )

        ignored_dates = category["date_only_differences_ignored"]
        if ignored_dates:
            print(f"  Diferencias solo de dia ignoradas: {len(ignored_dates)}")

        position_actions = category["actions"]["posiciones"]
        print(f"  Cambios de posiciones: {len(position_actions)}")
        for action in position_actions:
            if action["operation"] == "insert":
                values = ", ".join(
                    f"{POSITION_FIELD_LABELS[field]}={action['values'][field]}"
                    for field in POSITION_FIELDS
                )
                print(f"    INSERTAR {action['club']}: {values}")
            else:
                print(f"    ACTUALIZAR {action['club']}: {_format_changes(action['changes'])}")

        extras = category["extra_existing_positions"]
        if extras:
            print("  Posiciones extra sin partidos jugados (se dejan intactas): " + ", ".join(
                row["club"] for row in extras
            ))

        if report["execute"]:
            applied = category["applied"]
            print(
                "  Aplicado: "
                f"partidos={applied['partidos_updated']}, "
                f"posiciones actualizadas={applied['posiciones_updated']}, "
                f"posiciones insertadas={applied['posiciones_inserted']}"
            )

    if report["execute"]:
        print("\nEjecución finalizada sin deletes ni inserciones de partidos.")
    else:
        print("\nDRY-RUN: no se realizaron escrituras en Supabase.")


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    generated_at = datetime.now(timezone.utc).isoformat()
    categories = [args.categoria] if args.categoria else list(SOURCE_CATEGORIES)

    try:
        # Deliberately load config.py and Supabase only after argparse succeeds.
        supabase, club_map, category_ids = load_supabase_dependencies()
        missing_categories = [category for category in categories if category not in category_ids]
        if missing_categories:
            raise RuntimeError(f"Categorías sin identidad autoritativa: {missing_categories}")
        labels = club_labels(club_map)
        category_reports = [
            analyze_category(
                supabase,
                args.torneo_id,
                args.competencia,
                category,
                category_ids,
                club_map,
                labels,
                args.include_dates,
            )
            for category in categories
        ]
        report: MutableMapping[str, Any] = {
            "generated_at": generated_at,
            "mode": "execute" if args.execute else "dry-run",
            "execute": args.execute,
            "include_dates": args.include_dates,
            "torneo_id": args.torneo_id,
            "competencia": args.competencia,
            "source_directory": HISTORICAL_DIRECTORY,
            "categories": category_reports,
        }

        if args.execute:
            for category in category_reports:
                category["applied"] = execute_category(supabase, category)
    except Exception as exc:  # noqa: BLE001 - the CLI must fail closed on source/DB errors.
        message = f"No se pudo completar la corrección: {exc}"
        if args.json:
            print(json.dumps({"generated_at": generated_at, "error": message}, ensure_ascii=False, indent=2))
        else:
            print(f"ERROR: {message}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print_human_report(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
