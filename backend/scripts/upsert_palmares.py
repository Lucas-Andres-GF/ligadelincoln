# -*- coding: utf-8 -*-
"""Preview or safely write one explicit official champion record."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Optional, Sequence, TextIO

from operation_common import (
    OperationContext,
    add_operation_arguments,
    load_backend_environment,
    operation_context_from_args,
    read_exact_paginated,
    validate_positive_tournament_id,
)


PAGE_SIZE = 100
REFERENCE_MAX_TOTAL = 2
PALMARES_MAX_TOTAL = 2


class PalmaresError(RuntimeError):
    """The requested palmares operation is unsafe or cannot be validated."""


@dataclass(frozen=True)
class PalmaresPlan:
    tournament_id: int
    category_id: int
    payload: Mapping[str, Any]
    references: Mapping[str, Mapping[str, Any]]
    existing: Optional[Mapping[str, Any]]
    action: str
    issues: tuple[str, ...]

    @property
    def valid(self) -> bool:
        return self.action in {"insert", "noop", "update"} and not self.issues

    @property
    def noop(self) -> bool:
        return self.valid and self.action == "noop"


def _positive(value: Any, label: str) -> int:
    try:
        return validate_positive_tournament_id(value, source=label)
    except ValueError as exc:
        raise PalmaresError(str(exc)) from exc


def non_empty_string(value: str) -> str:
    parsed = value.strip()
    if not parsed:
        raise argparse.ArgumentTypeError("must not be empty")
    return parsed


def _read_exact(
    client: Any,
    *,
    table: str,
    columns: str,
    label: str,
    maximum_total: int,
    scope: Callable[[Any], Any],
) -> list[Mapping[str, Any]]:
    def fetch_page(start: int, end: int) -> Any:
        query = client.table(table).select(columns, count="exact")
        return scope(query).order("id").range(start, end).execute()

    rows = read_exact_paginated(
        fetch_page,
        label=label,
        maximum_total=maximum_total,
        page_size=PAGE_SIZE,
        identity=lambda row: _positive(
            row.get("id") if isinstance(row, Mapping) else None,
            f"{label} row id",
        ),
        identity_name="row id",
    )
    if not all(isinstance(row, Mapping) for row in rows):
        raise PalmaresError(f"{label} contains a malformed row")
    return rows


def require_reference(client: Any, table: str, row_id: int, label: str) -> Mapping[str, Any]:
    row_id = validate_positive_tournament_id(row_id, source=f"{label} id")
    rows = _read_exact(
        client,
        table=table,
        columns="id,nombre",
        label=f"{label} reference",
        maximum_total=REFERENCE_MAX_TOTAL,
        scope=lambda query: query.eq("id", row_id),
    )
    if not rows:
        raise PalmaresError(f"Missing {label} reference id={row_id}")
    if len(rows) != 1:
        raise PalmaresError(f"Duplicate {label} reference id={row_id}")
    row = rows[0]
    if _positive(row.get("id"), f"{label} reference id") != row_id:
        raise PalmaresError(f"{label} reference returned an out-of-scope row")
    name = row.get("nombre")
    if not isinstance(name, str) or not name.strip():
        raise PalmaresError(f"{label} reference has malformed nombre")
    return row


def find_existing(client: Any, tournament_id: int, category_id: int) -> Optional[Mapping[str, Any]]:
    rows = _read_exact(
        client,
        table="palmares",
        columns="id,nombre,temporada,club_id,torneo_id,categoria_id",
        label="Palmares inventory",
        maximum_total=PALMARES_MAX_TOTAL,
        scope=lambda query: query.eq("torneo_id", tournament_id).eq(
            "categoria_id", category_id
        ),
    )
    if len(rows) > 1:
        raise PalmaresError(
            "Duplicate palmares records for the requested tournament/category"
        )
    if not rows:
        return None
    row = rows[0]
    _positive(row.get("id"), "palmares row id")
    if _positive(row.get("torneo_id"), "palmares torneo_id") != tournament_id:
        raise PalmaresError("Palmares inventory returned an out-of-scope tournament")
    if _positive(row.get("categoria_id"), "palmares categoria_id") != category_id:
        raise PalmaresError("Palmares inventory returned an out-of-scope category")
    _positive(row.get("club_id"), "palmares club_id")
    for field in ("nombre", "temporada"):
        value = row.get(field)
        if not isinstance(value, str) or not value.strip():
            raise PalmaresError(f"Existing palmares {field} is malformed")
    return row


def build_plan(
    client: Any,
    context: OperationContext,
    *,
    category_id: int,
    club_id: int,
    name: str,
    season: str,
    replace_existing: bool,
) -> PalmaresPlan:
    tournament_id = validate_positive_tournament_id(context.tournament_id)
    category_id = validate_positive_tournament_id(category_id, source="--categoria-id")
    club_id = validate_positive_tournament_id(club_id, source="--club-id")
    payload = {
        "nombre": name.strip(),
        "temporada": season.strip(),
        "club_id": club_id,
        "torneo_id": tournament_id,
        "categoria_id": category_id,
    }
    references = {
        "torneo": require_reference(client, "torneos", tournament_id, "tournament"),
        "categoria": require_reference(client, "categorias", category_id, "category"),
        "club": require_reference(client, "clubes", club_id, "club"),
    }
    existing = find_existing(client, tournament_id, category_id)
    if existing is None:
        action = "insert"
        issues: tuple[str, ...] = ()
    elif all(existing.get(key) == value for key, value in payload.items()):
        action = "noop"
        issues = ()
    elif replace_existing:
        action = "update"
        issues = ()
    else:
        action = "blocked"
        issues = (
            "Existing champion or metadata conflicts with the explicit request; "
            "use --replace-existing to permit one narrow update",
        )
    return PalmaresPlan(
        tournament_id=tournament_id,
        category_id=category_id,
        payload=payload,
        references=references,
        existing=existing,
        action=action,
        issues=issues,
    )


def execute_plan(client: Any, plan: PalmaresPlan) -> list[Mapping[str, Any]]:
    if not plan.valid:
        raise ValueError("Refusing to execute an invalid palmares plan")
    if plan.noop:
        return []
    if plan.action == "insert":
        response = client.table("palmares").insert(dict(plan.payload)).execute()
    elif plan.action == "update" and plan.existing is not None:
        existing_id = _positive(plan.existing.get("id"), "palmares row id")
        response = (
            client.table("palmares")
            .update(dict(plan.payload))
            .eq("id", existing_id)
            .eq("torneo_id", plan.tournament_id)
            .eq("categoria_id", plan.category_id)
            .execute()
        )
    else:
        raise ValueError(f"Unsupported palmares action: {plan.action}")
    rows = list(getattr(response, "data", None) or [])
    if len(rows) != 1:
        raise PalmaresError(
            f"Database reported {len(rows)} changed rows; expected exactly one"
        )
    return rows


def render_report(context: OperationContext, plan: PalmaresPlan) -> dict[str, Any]:
    return {
        "mode": context.mode,
        "action": plan.action,
        "scope": {
            "torneo_id": plan.tournament_id,
            "categoria_id": plan.category_id,
        },
        "validated_references": {
            key: dict(value) for key, value in plan.references.items()
        },
        "existing": dict(plan.existing) if plan.existing else None,
        "values": dict(plan.payload),
        "issues": list(plan.issues),
    }


def print_human_report(report: Mapping[str, Any], output: TextIO = sys.stdout) -> None:
    print(
        f"Official palmares: mode={report['mode']} action={report['action']}",
        file=output,
    )
    scope = report["scope"]
    print(
        f"Scope: tournament_id={scope['torneo_id']} category_id={scope['categoria_id']}",
        file=output,
    )
    print(
        f"Values: {json.dumps(report['values'], ensure_ascii=False, sort_keys=True)}",
        file=output,
    )
    for issue in report["issues"]:
        print(f"  ERROR: {issue}", file=output)
    if report["action"] == "noop":
        print("Plan: no-op; the exact record already exists.", file=output)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Preview or safely write one explicitly supplied official champion."
    )
    add_operation_arguments(parser, tournament_required=True)
    parser.add_argument("--categoria-id", required=True, type=lambda value: _cli_id(value, "--categoria-id"))
    parser.add_argument("--club-id", required=True, type=lambda value: _cli_id(value, "--club-id"))
    parser.add_argument("--nombre", required=True, type=non_empty_string)
    parser.add_argument("--temporada", required=True, type=non_empty_string)
    parser.add_argument(
        "--replace-existing",
        action="store_true",
        help="Permit one narrow update when the existing record conflicts.",
    )
    parser.add_argument("--json", action="store_true", help="Emit the plan as JSON.")
    return parser


def _cli_id(value: str, source: str) -> int:
    try:
        return validate_positive_tournament_id(value, source=source)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    return build_parser().parse_args(argv)


def load_supabase() -> Any:
    from config import supabase

    return supabase


def main(
    argv: Optional[Sequence[str]] = None,
    *,
    client_factory: Optional[Callable[[], Any]] = None,
    stdout: Optional[TextIO] = None,
    stderr: Optional[TextIO] = None,
) -> int:
    args = parse_args(argv)
    output = stdout or sys.stdout
    error_output = stderr or sys.stderr
    try:
        load_backend_environment()
        context = operation_context_from_args(args, environ={})
        client = (client_factory or load_supabase)()
        plan = build_plan(
            client,
            context,
            category_id=args.categoria_id,
            club_id=args.club_id,
            name=args.nombre,
            season=args.temporada,
            replace_existing=args.replace_existing,
        )
        report = render_report(context, plan)
        if args.json:
            print(json.dumps(report, ensure_ascii=False, indent=2), file=output)
        else:
            print_human_report(report, output)
        if not plan.valid:
            return 1
        if not context.execute:
            print("Dry run only; no database mutations were attempted.", file=output)
            return 0
        rows = execute_plan(client, plan)
        print(f"Applied palmares operation: changed={len(rows)}", file=output)
        return 0
    except Exception as exc:
        message = f"Palmares operation failed: {exc}"
        if getattr(args, "json", False):
            print(json.dumps({"error": message}, ensure_ascii=False), file=error_output)
        else:
            print(message, file=error_output)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
