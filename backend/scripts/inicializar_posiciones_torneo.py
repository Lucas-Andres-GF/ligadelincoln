"""Safely complete zeroed tournament standings from the stored fixture."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Optional, Sequence, TextIO

from fuente_fixture_actual import (
    SOURCE_PROFILES,
    CurrentFixtureSourceProfile,
    get_source_profile,
    validate_category_completeness,
    validate_source_profile,
)
from operation_common import (
    OperationContext,
    add_operation_arguments,
    load_backend_environment,
    operation_context_from_args,
    read_exact_paginated,
    validate_positive_tournament_id,
)


PAGE_SIZE = 200
FIXTURE_MAX_TOTAL = 2000
POSITION_MAX_TOTAL = 1000
FIXTURE_STATES = frozenset({"programado", "jugado", "postergado", "libre"})
STAT_FIELDS = ("pts", "pj", "pg", "pe", "pp", "gf", "gc", "dif")
PROFILE_CATEGORY_CHOICES = tuple(
    dict.fromkeys(
        category
        for profile in SOURCE_PROFILES.values()
        for category in profile.category_sources
    )
)


@dataclass(frozen=True)
class FixtureReadiness:
    rows: tuple[Mapping[str, Any], ...]
    participants: Mapping[int, frozenset[int]]
    has_played_or_results: bool


@dataclass(frozen=True)
class PositionInitializationPlan:
    tournament_id: int
    category_ids: tuple[int, ...]
    expected_count: int
    existing_count: int
    inserts: tuple[Mapping[str, Any], ...]
    issues: tuple[str, ...]

    @property
    def valid(self) -> bool:
        return self.expected_count > 0 and not self.issues

    @property
    def noop(self) -> bool:
        return self.valid and not self.inserts


def _positive(value: Any, label: str) -> int:
    try:
        return validate_positive_tournament_id(value, source=label)
    except ValueError as exc:
        raise RuntimeError(str(exc)) from exc


def _selected_categories(values: Sequence[int]) -> tuple[int, ...]:
    return tuple(sorted(set(values)))


def profile_category_ids(
    profile: CurrentFixtureSourceProfile,
    category_keys: Sequence[str] = (),
) -> dict[str, int]:
    """Resolve selected profile categories through authoritative configured IDs."""
    validate_source_profile(profile)
    selected = tuple(dict.fromkeys(category_keys or profile.category_sources.keys()))
    unknown = sorted(set(selected) - set(profile.category_sources))
    if unknown:
        raise ValueError(
            f"Categories are not available in profile {profile.key}: {', '.join(unknown)}"
        )

    from config import CATEGORIAS

    resolved: dict[str, int] = {}
    seen_ids: set[int] = set()
    for category in selected:
        if category not in CATEGORIAS:
            raise RuntimeError(f"Profile category {category} has no configured category ID")
        category_id = validate_positive_tournament_id(
            CATEGORIAS[category], source=f"category ID for {category}"
        )
        if category_id in seen_ids:
            raise RuntimeError(f"Configured category ID {category_id} is not unique")
        seen_ids.add(category_id)
        resolved[category] = category_id
    return resolved


def validate_readiness_completeness(
    readiness: FixtureReadiness,
    profile: CurrentFixtureSourceProfile,
    category_ids: Mapping[str, int],
) -> None:
    """Match a paginated DB fixture to exact profile category expectations."""
    expected_ids = set(category_ids.values())
    actual_ids = set(readiness.participants)
    if actual_ids != expected_ids:
        raise RuntimeError(
            f"Fixture category coverage mismatch: expected={sorted(expected_ids)} "
            f"actual={sorted(actual_ids)}"
        )
    for category_key, category_id in category_ids.items():
        category_rows = [
            row for row in readiness.rows if row.get("categoria_id") == category_id
        ]
        try:
            validate_category_completeness(
                profile,
                category_key,
                (row.get("fecha_id") for row in category_rows),
                len(category_rows),
            )
        except ValueError as exc:
            raise RuntimeError(str(exc)) from exc


def _read_inventory(
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
        raise RuntimeError(f"{label} contains a malformed row")
    return rows


def read_fixture_readiness(
    client: Any,
    tournament_id: int,
    category_ids: Sequence[int] = (),
) -> FixtureReadiness:
    """Read and validate the complete selected fixture and its participants."""
    tournament_id = validate_positive_tournament_id(tournament_id)
    selected = _selected_categories(category_ids)

    def scope(query: Any) -> Any:
        query = query.eq("torneo_id", tournament_id)
        if selected:
            query = query.in_("categoria_id", list(selected))
        return query

    rows = _read_inventory(
        client,
        table="partidos",
        columns=(
            "id,torneo_id,categoria_id,local_id,visitante_id,fecha_id,estado,"
            "goles_local,goles_visitante"
        ),
        label="Fixture inventory",
        maximum_total=FIXTURE_MAX_TOTAL,
        scope=scope,
    )
    if not rows:
        raise RuntimeError("Tournament fixture is empty")

    participants: dict[int, set[int]] = {}
    round_participants: dict[tuple[int, int], set[int]] = {}
    fixture_keys: set[tuple[int, int, int, Optional[int]]] = set()
    has_results = False
    for index, row in enumerate(rows, start=1):
        try:
            fixture_id = _positive(row.get("id"), "fixture id")
            row_tournament = _positive(row.get("torneo_id"), "fixture torneo_id")
            category_id = _positive(row.get("categoria_id"), "fixture categoria_id")
            round_id = _positive(row.get("fecha_id"), "fixture fecha_id")
            state_value = row.get("estado")
            if not isinstance(state_value, str) or not state_value.strip():
                raise RuntimeError("fixture estado is missing or malformed")
            state = state_value.strip().lower()
            if state not in FIXTURE_STATES:
                raise RuntimeError(f"fixture estado {state_value!r} is unsupported")
            local = row.get("local_id")
            visitor = row.get("visitante_id")
            if state == "libre":
                if (local is None) == (visitor is None):
                    raise RuntimeError("LIBRE fixture requires exactly one null team side")
                clubs = {_positive(local if local is not None else visitor, "fixture club id")}
            else:
                clubs = {
                    _positive(local, "fixture local_id"),
                    _positive(visitor, "fixture visitante_id"),
                }
                if len(clubs) != 2:
                    raise RuntimeError("fixture cannot contain the same club on both sides")
        except RuntimeError as exc:
            raise RuntimeError(f"Malformed fixture row {index}: {exc}") from exc
        if row_tournament != tournament_id or (selected and category_id not in selected):
            raise RuntimeError("Fixture inventory returned a row outside the selected scope")
        local_identity = local if local is not None else visitor
        visitor_identity = visitor if local is not None else None
        fixture_key = (category_id, round_id, int(local_identity), visitor_identity)
        if fixture_key in fixture_keys:
            raise RuntimeError(f"Duplicate fixture identity in row {index}")
        fixture_keys.add(fixture_key)
        seen_in_round = round_participants.setdefault((category_id, round_id), set())
        duplicated = sorted(seen_in_round & clubs)
        if duplicated:
            raise RuntimeError(
                f"Duplicate team participation in category {category_id} "
                f"round {round_id}: club IDs {duplicated}"
            )
        seen_in_round.update(clubs)
        participants.setdefault(category_id, set()).update(clubs)
        if state == "jugado" or row.get("goles_local") is not None or row.get("goles_visitante") is not None:
            has_results = True

    missing_categories = sorted(set(selected) - set(participants))
    if missing_categories:
        raise RuntimeError(
            f"Selected categories have no fixture rows: {missing_categories}"
        )
    return FixtureReadiness(
        rows=tuple(rows),
        participants={key: frozenset(value) for key, value in participants.items()},
        has_played_or_results=has_results,
    )


def read_positions(
    client: Any,
    tournament_id: int,
    category_ids: Sequence[int] = (),
) -> list[Mapping[str, Any]]:
    selected = _selected_categories(category_ids)

    def scope(query: Any) -> Any:
        query = query.eq("torneo_id", tournament_id)
        if selected:
            query = query.in_("categoria_id", list(selected))
        return query

    return _read_inventory(
        client,
        table="posiciones",
        columns=(
            "id,torneo_id,categoria_id,club_id,pts,pj,pg,pe,pp,gf,gc,dif,ultimos_5"
        ),
        label="Position inventory",
        maximum_total=POSITION_MAX_TOTAL,
        scope=scope,
    )


def _normalized_form(value: Any) -> list[str]:
    if value is None or value == "":
        return []
    parsed = value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as exc:
            raise RuntimeError("position ultimos_5 is malformed") from exc
    if not isinstance(parsed, (list, tuple)):
        raise RuntimeError("position ultimos_5 must be an array")
    form = [str(item) for item in parsed]
    if len(form) > 5 or any(item not in {"G", "E", "P"} for item in form):
        raise RuntimeError("position ultimos_5 contains invalid values")
    return form


def _position_values(row: Mapping[str, Any]) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for field in STAT_FIELDS:
        value = row.get(field)
        if isinstance(value, bool) or not isinstance(value, int):
            raise RuntimeError(f"position {field} must be an integer")
        values[field] = value
    values["ultimos_5"] = _normalized_form(row.get("ultimos_5"))
    return values


def zero_position_row(tournament_id: int, category_id: int, club_id: int) -> dict[str, Any]:
    return {
        "torneo_id": tournament_id,
        "categoria_id": category_id,
        "club_id": club_id,
        "pts": 0,
        "pj": 0,
        "pg": 0,
        "pe": 0,
        "pp": 0,
        "gf": 0,
        "gc": 0,
        "dif": 0,
        "ultimos_5": [],
    }


def build_initialization_plan(
    readiness: FixtureReadiness,
    existing_rows: Sequence[Mapping[str, Any]],
    tournament_id: int,
) -> PositionInitializationPlan:
    """Plan only safe completion of an untouched standings inventory."""
    tournament_id = validate_positive_tournament_id(tournament_id)
    expected = {
        (category_id, club_id)
        for category_id, clubs in readiness.participants.items()
        for club_id in clubs
    }
    issues: list[str] = []
    existing: dict[tuple[int, int], Mapping[str, Any]] = {}

    if readiness.has_played_or_results:
        issues.append("Fixture contains played or result-bearing rows")

    for index, row in enumerate(existing_rows, start=1):
        try:
            _positive(row.get("id"), "position id")
            row_tournament = _positive(row.get("torneo_id"), "position torneo_id")
            category_id = _positive(row.get("categoria_id"), "position categoria_id")
            club_id = _positive(row.get("club_id"), "position club_id")
            values = _position_values(row)
        except RuntimeError as exc:
            issues.append(f"Malformed position row {index}: {exc}")
            continue
        identity = (category_id, club_id)
        if row_tournament != tournament_id or identity not in expected:
            issues.append(f"Position row {index} is outside expected fixture participants")
            continue
        if identity in existing:
            issues.append(
                f"Duplicate position identity category_id={category_id} club_id={club_id}"
            )
            continue
        existing[identity] = row
        if any(values[field] != 0 for field in STAT_FIELDS) or values["ultimos_5"]:
            issues.append(
                f"Position category_id={category_id} club_id={club_id} is not zero/empty"
            )

    missing = sorted(expected - set(existing))
    inserts = tuple(
        zero_position_row(tournament_id, category_id, club_id)
        for category_id, club_id in missing
    )
    return PositionInitializationPlan(
        tournament_id=tournament_id,
        category_ids=tuple(sorted(readiness.participants)),
        expected_count=len(expected),
        existing_count=len(existing_rows),
        inserts=inserts,
        issues=tuple(issues),
    )


def execute_initialization(client: Any, plan: PositionInitializationPlan) -> int:
    if not plan.valid:
        raise ValueError("Refusing to execute an invalid positions initialization plan")
    if not plan.inserts:
        return 0
    client.table("posiciones").insert([dict(row) for row in plan.inserts]).execute()
    return len(plan.inserts)


def render_report(context: OperationContext, plan: PositionInitializationPlan) -> str:
    lines = [
        f"Position initialization: mode={context.mode} tournament_id={context.tournament_id}",
        f"Categories: {', '.join(map(str, plan.category_ids))}",
        f"Expected positions: {plan.expected_count}",
        f"Existing positions: {plan.existing_count}",
        f"Planned inserts: {len(plan.inserts)}",
    ]
    if plan.noop:
        lines.append("Plan: no-op; exact zeroed coverage already exists.")
    if plan.issues:
        lines.append(f"Blocking issues: {len(plan.issues)}")
        lines.extend(f"  ERROR: {issue}" for issue in plan.issues)
    else:
        lines.append("Blocking issues: 0")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Preview or safely complete zeroed standings from a tournament fixture."
    )
    parser.add_argument(
        "--profile",
        required=True,
        choices=tuple(SOURCE_PROFILES),
        help="Required versioned fixture profile used for completeness validation.",
    )
    add_operation_arguments(parser, tournament_required=True)
    parser.add_argument(
        "--category",
        action="append",
        choices=PROFILE_CATEGORY_CHOICES,
        default=[],
        help="Profile category key; repeat as needed (default: all profile categories).",
    )
    return parser


def _database_client() -> Any:
    from config import supabase

    return supabase


def main(
    argv: Optional[Sequence[str]] = None,
    *,
    client_factory: Optional[Callable[[], Any]] = None,
    stdout: Optional[TextIO] = None,
    stderr: Optional[TextIO] = None,
) -> int:
    args = build_parser().parse_args(argv)
    output = stdout or sys.stdout
    error_output = stderr or sys.stderr
    try:
        load_backend_environment()
        context = operation_context_from_args(args, environ={})
        profile = get_source_profile(args.profile)
        selected_categories = profile_category_ids(profile, args.category)
        category_ids = tuple(selected_categories.values())
        client = (client_factory or _database_client)()
        readiness = read_fixture_readiness(client, context.tournament_id, category_ids)
        validate_readiness_completeness(readiness, profile, selected_categories)
        positions = read_positions(client, context.tournament_id, category_ids)
        plan = build_initialization_plan(readiness, positions, context.tournament_id)
        print(render_report(context, plan), file=output)
        if not plan.valid:
            return 1
        if not context.execute:
            print("Dry run only; no database mutations were attempted.", file=output)
            return 0
        inserted = execute_initialization(client, plan)
        print(f"Applied position initialization: inserted={inserted}", file=output)
        return 0
    except Exception as exc:
        print(f"Position initialization failed: {exc}", file=error_output)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
