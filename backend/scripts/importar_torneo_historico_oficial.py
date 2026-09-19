# -*- coding: utf-8 -*-
"""Import a complete official historical tournament into Supabase safely.

The default mode is a dry run. Official fixtures and final standings are parsed
with the shared historical comparator, and every category is validated before it
is eligible for insertion. Execute mode never activates the historical tournament.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, MutableMapping, Optional, Sequence, Tuple

from fuente_oficial_historica import (
    COMPETENCIA_FILES,
    SOURCE_CATEGORIES,
    club_labels,
    fetch_rows,
    load_supabase_dependencies,
    parse_official_fixture,
    positive_int,
    source_url,
)


COMPETENCIAS = tuple(COMPETENCIA_FILES)
POSITION_FIELDS = ("pts", "pj", "pg", "pe", "pp", "gf", "gc")


@dataclass
class CategoryPlan:
    """Validated report plus the exact rows eligible for a category import."""

    report: MutableMapping[str, Any]
    partido_rows: List[Dict[str, Any]]
    posicion_rows: List[Dict[str, Any]]


def non_empty_string(value: str) -> str:
    parsed = value.strip()
    if not parsed:
        raise argparse.ArgumentTypeError("no puede estar vacío")
    return parsed


def slug_from_name(value: str) -> str:
    folded = unicodedata.normalize("NFD", value.strip().lower())
    ascii_value = "".join(char for char in folded if unicodedata.category(char) != "Mn")
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_value).strip("-")
    if not slug:
        raise ValueError("no se pudo generar un slug válido desde --nombre")
    return slug


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Importa fixture, resultados y posiciones finales de un torneo histórico oficial. "
            "Por defecto realiza un dry-run sin escrituras."
        )
    )
    parser.add_argument("--torneo-id", required=True, type=positive_int, help="ID positivo del torneo")
    parser.add_argument("--nombre", required=True, type=non_empty_string, help="nombre del torneo")
    parser.add_argument("--slug", type=non_empty_string, help="slug; por defecto se deriva de --nombre")
    parser.add_argument(
        "--competencia",
        required=True,
        choices=COMPETENCIAS,
        help="competencia histórica oficial",
    )
    parser.add_argument("--categoria", choices=SOURCE_CATEGORIES, help="categoría; por defecto, todas")
    parser.add_argument("--execute", action="store_true", help="escribir el plan validado en Supabase")
    parser.add_argument(
        "--force",
        action="store_true",
        help=(
            "reemplazar exclusivamente partidos y posiciones del torneo/categoría seleccionados; "
            "no omite validaciones de integridad de la fuente"
        ),
    )
    parser.add_argument("--json", action="store_true", help="emitir el informe como JSON")
    return parser.parse_args(argv)


def existing_rows(supabase: Any, table: str, torneo_id: int, category_id: int) -> bool:
    response = (
        supabase.table(table)
        .select("id")
        .eq("torneo_id", torneo_id)
        .eq("categoria_id", category_id)
        .limit(1)
        .execute()
    )
    return bool(getattr(response, "data", None))


def inspect_existing_rows(supabase: Any, torneo_id: int, category_id: int) -> Dict[str, bool]:
    return {
        "partidos": existing_rows(supabase, "partidos", torneo_id, category_id),
        "posiciones": existing_rows(supabase, "posiciones", torneo_id, category_id),
    }


def build_partido_rows(
    official: Mapping[str, Any], torneo_id: int, category_id: int
) -> List[Dict[str, Any]]:
    rows = [
        {
            "torneo_id": torneo_id,
            "categoria_id": category_id,
            "fecha_id": int(match["fecha_id"]),
            "local_id": int(match["local_id"]),
            "visitante_id": int(match["visitante_id"]),
            "goles_local": match["goles_local"],
            "goles_visitante": match["goles_visitante"],
            "estado": match["estado"],
            "dia": match.get("dia"),
        }
        for match in official["matches"]
    ]
    rows.extend(
        {
            "torneo_id": torneo_id,
            "categoria_id": category_id,
            "fecha_id": int(bye["fecha_id"]),
            "local_id": int(bye["club_id"]),
            "visitante_id": None,
            "goles_local": None,
            "goles_visitante": None,
            "estado": "libre",
            "dia": bye.get("dia"),
        }
        for bye in official["byes"]
    )
    return rows


def build_posicion_rows(
    official: Mapping[str, Any], torneo_id: int, category_id: int
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for standing in official["final_standings"]:
        values = {field: int(standing[field]) for field in POSITION_FIELDS}
        rows.append(
            {
                "torneo_id": torneo_id,
                "categoria_id": category_id,
                "club_id": int(standing["club_id"]),
                **values,
                "dif": values["gf"] - values["gc"],
            }
        )
    return rows


def analyze_category(
    supabase: Any,
    torneo_id: int,
    competencia: str,
    category: str,
    category_ids: Mapping[str, int],
    club_map: Mapping[str, int],
    labels: Mapping[int, str],
    force: bool,
) -> CategoryPlan:
    category_id = int(category_ids[category])
    url = source_url(competencia, category)
    base_report: MutableMapping[str, Any] = {
        "category": category,
        "categoria_id": category_id,
        "source_url": url,
        "status": "error",
        "official_participants_count": 0,
        "official_match_count": 0,
        "official_bye_count": 0,
        "official_standings_count": 0,
        "final_table_omissions": [],
        "existing_rows": {"partidos": False, "posiciones": False},
        "manual_review_required": False,
        "skip_reasons": [],
    }

    try:
        official = parse_official_fixture(fetch_rows(url), url, category, club_map)
        omissions = [
            {
                "club_id": int(row["club_id"]),
                "club": labels.get(int(row["club_id"]), row["team"]),
                "official_name": row["team"],
            }
            for row in official["final_table_omissions"]
        ]
        base_report.update(
            {
                "official_participants_count": len(official["participants"]),
                "official_match_count": len(official["matches"]),
                "official_bye_count": len(official["byes"]),
                "official_standings_count": len(official["final_standings"]),
                "final_table_omissions": omissions,
            }
        )
        existing = inspect_existing_rows(supabase, torneo_id, category_id)
        base_report["existing_rows"] = existing

        skip_reasons: List[str] = []
        if not official["final_standings"]:
            skip_reasons.append("la tabla final oficial está vacía")
        if omissions:
            skip_reasons.append("la tabla final oficial omite participantes del fixture")
        if (existing["partidos"] or existing["posiciones"]) and not force:
            skip_reasons.append(
                "ya existen partidos o posiciones para este torneo/categoría; use --force para reemplazarlos"
            )

        source_integrity_failure = not official["final_standings"] or bool(omissions)
        base_report["manual_review_required"] = source_integrity_failure
        base_report["skip_reasons"] = skip_reasons
        base_report["status"] = (
            "manual_review_required"
            if source_integrity_failure
            else "skipped"
            if skip_reasons
            else "ready"
        )

        if skip_reasons:
            return CategoryPlan(base_report, [], [])
        return CategoryPlan(
            base_report,
            build_partido_rows(official, torneo_id, category_id),
            build_posicion_rows(official, torneo_id, category_id),
        )
    except Exception as exc:  # noqa: BLE001 - one source/category failure must be reported safely.
        base_report["skip_reasons"] = [str(exc)]
        return CategoryPlan(base_report, [], [])


def upsert_inactive_tournament(
    supabase: Any, torneo_id: int, nombre: str, slug: str
) -> str:
    values = {
        "nombre": nombre,
        "slug": slug,
        "temporada": 2026,
        "activo": False,
    }
    response = supabase.table("torneos").select("id").eq("id", torneo_id).limit(1).execute()
    if getattr(response, "data", None):
        supabase.table("torneos").update(values).eq("id", torneo_id).execute()
        return "updated"
    supabase.table("torneos").insert({"id": torneo_id, **values}).execute()
    return "inserted"


def delete_category_rows(supabase: Any, torneo_id: int, category_id: int) -> None:
    for table in ("partidos", "posiciones"):
        (
            supabase.table(table)
            .delete()
            .eq("torneo_id", torneo_id)
            .eq("categoria_id", category_id)
            .execute()
        )


def execute_category(
    supabase: Any,
    plan: CategoryPlan,
    torneo_id: int,
    force: bool,
) -> Dict[str, int]:
    category_id = int(plan.report["categoria_id"])
    if plan.report["status"] != "ready":
        return {"partidos_inserted": 0, "posiciones_inserted": 0}

    # Recheck immediately before mutation so a concurrent import cannot silently
    # create duplicate rows after the dry-run analysis.
    current = inspect_existing_rows(supabase, torneo_id, category_id)
    if (current["partidos"] or current["posiciones"]) and not force:
        raise RuntimeError("aparecieron filas existentes después del análisis; categoría no modificada")
    if force:
        delete_category_rows(supabase, torneo_id, category_id)

    if plan.partido_rows:
        supabase.table("partidos").insert(plan.partido_rows).execute()
    if plan.posicion_rows:
        supabase.table("posiciones").insert(plan.posicion_rows).execute()
    return {
        "partidos_inserted": len(plan.partido_rows),
        "posiciones_inserted": len(plan.posicion_rows),
    }


def print_human_report(report: Mapping[str, Any]) -> None:
    mode = "EJECUCIÓN" if report["execute"] else "DRY-RUN"
    print(
        f"Importación histórica oficial — {mode}: torneo_id={report['torneo_id']} "
        f"nombre={report['nombre']!r} competencia={report['competencia']}"
    )
    print(f"Slug: {report['slug']}; el torneo histórico permanecerá inactivo.")

    for category in report["categories"]:
        print(f"\n=== {category['category'].upper()} — {category['status']} ===")
        print(f"Fuente: {category['source_url']}")
        print(
            "  Oficial: "
            f"participantes={category['official_participants_count']}, "
            f"partidos={category['official_match_count']}, "
            f"LIBRE={category['official_bye_count']}, "
            f"posiciones={category['official_standings_count']}, "
            f"omisiones_tabla_final={len(category['final_table_omissions'])}"
        )
        if category["final_table_omissions"]:
            print(
                "  REVISIÓN MANUAL: la tabla final omite a "
                + ", ".join(row["club"] for row in category["final_table_omissions"])
            )
        existing = category["existing_rows"]
        print(
            "  Existentes: "
            f"partidos={'sí' if existing['partidos'] else 'no'}, "
            f"posiciones={'sí' if existing['posiciones'] else 'no'}"
        )
        for reason in category["skip_reasons"]:
            print(f"  OMITIDA: {reason}")
        if "applied" in category:
            applied = category["applied"]
            print(
                f"  Insertados: partidos/LIBRE={applied['partidos_inserted']}, "
                f"posiciones={applied['posiciones_inserted']}"
            )

    if report["execute"]:
        print("\nLa ejecución nunca activó el torneo ni modificó otros torneos/categorías.")
    else:
        print("\nDRY-RUN: no se realizaron escrituras en Supabase.")


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    generated_at = datetime.now(timezone.utc).isoformat()
    slug = args.slug or slug_from_name(args.nombre)
    categories = [args.categoria] if args.categoria else list(SOURCE_CATEGORIES)

    try:
        # Config and Supabase are deliberately loaded only after argparse succeeds.
        supabase, club_map, category_ids = load_supabase_dependencies()
        missing_categories = [category for category in categories if category not in category_ids]
        if missing_categories:
            raise RuntimeError(f"Categorías sin identidad autoritativa: {missing_categories}")
        labels = club_labels(club_map)
        plans = [
            analyze_category(
                supabase,
                args.torneo_id,
                args.competencia,
                category,
                category_ids,
                club_map,
                labels,
                args.force,
            )
            for category in categories
        ]
        report: MutableMapping[str, Any] = {
            "generated_at": generated_at,
            "mode": "execute" if args.execute else "dry-run",
            "execute": args.execute,
            "force": args.force,
            "torneo_id": args.torneo_id,
            "nombre": args.nombre,
            "slug": slug,
            "temporada": 2026,
            "activo": False,
            "competencia": args.competencia,
            "categories": [plan.report for plan in plans],
        }

        ready_plans = [plan for plan in plans if plan.report["status"] == "ready"]
        if args.execute and ready_plans:
            report["tournament_action"] = upsert_inactive_tournament(
                supabase, args.torneo_id, args.nombre, slug
            )
            for plan in ready_plans:
                try:
                    plan.report["applied"] = execute_category(
                        supabase, plan, args.torneo_id, args.force
                    )
                    plan.report["status"] = "imported"
                except Exception as exc:  # noqa: BLE001 - preserve other category plans and report partial writes.
                    plan.report["status"] = "failed"
                    plan.report["skip_reasons"] = [str(exc)]
        elif args.execute:
            report["tournament_action"] = "not_written_no_ready_categories"
    except Exception as exc:  # noqa: BLE001 - CLI must fail closed on config/global failures.
        message = f"No se pudo preparar la importación: {exc}"
        if args.json:
            print(json.dumps({"generated_at": generated_at, "error": message}, ensure_ascii=False, indent=2))
        else:
            print(f"ERROR: {message}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print_human_report(report)

    failed_statuses = {"error", "skipped", "manual_review_required", "failed"}
    return 1 if any(category["status"] in failed_statuses for category in report["categories"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
