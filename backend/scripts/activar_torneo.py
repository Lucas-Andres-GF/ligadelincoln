"""Preview or safely activate one fully initialized tournament."""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Optional, Sequence, TextIO

from fuente_fixture_actual import SOURCE_PROFILES, CurrentFixtureSourceProfile, get_source_profile
from inicializar_posiciones_torneo import (
    POSITION_MAX_TOTAL,
    STAT_FIELDS,
    _normalized_form,
    _positive,
    profile_category_ids,
    read_fixture_readiness,
    read_positions,
    validate_readiness_completeness,
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
ACTIVE_TOURNAMENT_MAX_TOTAL = 100


@dataclass(frozen=True)
class ActivationPlan:
    tournament_id: int
    profile_key: str
    target: Mapping[str, Any]
    active_tournament_ids: tuple[int, ...]
    deactivate_ids: tuple[int, ...]
    fixture_count: int
    position_count: int
    issues: tuple[str, ...]

    @property
    def valid(self) -> bool:
        return not self.issues

    @property
    def noop(self) -> bool:
        return self.valid and self.active_tournament_ids == (self.tournament_id,)


def _read_exact_query(
    client: Any,
    *,
    table: str,
    columns: str,
    label: str,
    maximum_total: int,
    scope: Callable[[Any], Any],
    page_size: int = PAGE_SIZE,
) -> list[Mapping[str, Any]]:
    def fetch_page(start: int, end: int) -> Any:
        query = client.table(table).select(columns, count="exact")
        return scope(query).order("id").range(start, end).execute()

    rows = read_exact_paginated(
        fetch_page,
        label=label,
        maximum_total=maximum_total,
        page_size=page_size,
        identity=lambda row: _positive(
            row.get("id") if isinstance(row, Mapping) else None,
            f"{label} row id",
        ),
        identity_name="row id",
    )
    if not all(isinstance(row, Mapping) for row in rows):
        raise RuntimeError(f"{label} contains a malformed row")
    return rows


def read_target_tournament(client: Any, tournament_id: int) -> Mapping[str, Any]:
    tournament_id = validate_positive_tournament_id(tournament_id)
    rows = _read_exact_query(
        client,
        table="torneos",
        columns="id,nombre,slug,temporada,activo",
        label="Target tournament inventory",
        maximum_total=2,
        page_size=2,
        scope=lambda query: query.eq("id", tournament_id),
    )
    if not rows:
        raise RuntimeError(f"Tournament id={tournament_id} does not exist")
    if len(rows) != 1:
        raise RuntimeError(f"Tournament inventory returned duplicate id {tournament_id}")
    row = rows[0]
    if _positive(row.get("id"), "target tournament id") != tournament_id:
        raise RuntimeError("Target tournament inventory returned an out-of-scope row")
    if not isinstance(row.get("activo"), bool):
        raise RuntimeError("Target tournament activo must be boolean")
    return row


def read_active_tournaments(client: Any) -> list[Mapping[str, Any]]:
    rows = _read_exact_query(
        client,
        table="torneos",
        columns="id,activo",
        label="Active tournament inventory",
        maximum_total=ACTIVE_TOURNAMENT_MAX_TOTAL,
        scope=lambda query: query.eq("activo", True),
    )
    identities: set[int] = set()
    for index, row in enumerate(rows, start=1):
        row_id = _positive(row.get("id"), f"active tournament row {index} id")
        if row.get("activo") is not True:
            raise RuntimeError("Active tournament inventory returned an out-of-scope row")
        if row_id in identities:
            raise RuntimeError(f"Active tournament inventory contains duplicate id {row_id}")
        identities.add(row_id)
    return rows


def _validate_progressed_positions(
    rows: Sequence[Mapping[str, Any]],
    tournament_id: int,
    participants: Mapping[int, frozenset[int]],
) -> tuple[str, ...]:
    expected = {
        (category_id, club_id)
        for category_id, clubs in participants.items()
        for club_id in clubs
    }
    actual: set[tuple[int, int]] = set()
    issues: list[str] = []
    for index, row in enumerate(rows, start=1):
        try:
            _positive(row.get("id"), "position id")
            row_tournament = _positive(row.get("torneo_id"), "position torneo_id")
            category_id = _positive(row.get("categoria_id"), "position categoria_id")
            club_id = _positive(row.get("club_id"), "position club_id")
            values: dict[str, int] = {}
            for field in STAT_FIELDS:
                value = row.get(field)
                if isinstance(value, bool) or not isinstance(value, int):
                    raise RuntimeError(f"position {field} must be an integer")
                values[field] = value
            form = _normalized_form(row.get("ultimos_5"))
        except RuntimeError as exc:
            issues.append(f"Malformed position row {index}: {exc}")
            continue
        identity = (category_id, club_id)
        if row_tournament != tournament_id or identity not in expected:
            issues.append(f"Position row {index} is outside expected fixture participants")
            continue
        if identity in actual:
            issues.append(
                f"Duplicate position identity category_id={category_id} club_id={club_id}"
            )
            continue
        actual.add(identity)
        if any(values[field] < 0 for field in ("pts", "pj", "pg", "pe", "pp", "gf", "gc")):
            issues.append(f"Position row {index} contains negative statistics")
        if values["pj"] != values["pg"] + values["pe"] + values["pp"]:
            issues.append(f"Position row {index} has incoherent played totals")
        if values["dif"] != values["gf"] - values["gc"]:
            issues.append(f"Position row {index} has incoherent goal difference")
        if len(form) > min(5, values["pj"]):
            issues.append(f"Position row {index} has incoherent recent form")

    missing = sorted(expected - actual)
    if missing:
        issues.append(f"Missing position identities: {missing}")
    extra = sorted(actual - expected)
    if extra:
        issues.append(f"Extra position identities: {extra}")
    return tuple(issues)


def build_activation_plan(
    target: Mapping[str, Any],
    active_rows: Sequence[Mapping[str, Any]],
    fixture_count: int,
    participants: Mapping[int, frozenset[int]],
    position_rows: Sequence[Mapping[str, Any]],
    tournament_id: int,
    profile: CurrentFixtureSourceProfile,
) -> ActivationPlan:
    tournament_id = validate_positive_tournament_id(tournament_id)
    issues: list[str] = []
    if fixture_count <= 0 or not participants:
        issues.append("Target tournament fixture is empty")
    issues.extend(
        _validate_progressed_positions(position_rows, tournament_id, participants)
    )

    active_ids: list[int] = []
    seen: set[int] = set()
    for index, row in enumerate(active_rows, start=1):
        try:
            row_id = _positive(row.get("id"), f"active tournament row {index} id")
        except RuntimeError as exc:
            issues.append(str(exc))
            continue
        if row.get("activo") is not True:
            issues.append(f"Active tournament row {index} is outside active scope")
        if row_id in seen:
            issues.append(f"Duplicate active tournament id {row_id}")
        else:
            seen.add(row_id)
            active_ids.append(row_id)

    target_id = target.get("id")
    target_active = target.get("activo")
    if target_id != tournament_id or not isinstance(target_active, bool):
        issues.append("Target tournament row is malformed or out of scope")
    if target.get("nombre") != profile.display_name:
        issues.append("Target tournament nombre does not match the selected profile")
    if target.get("slug") != profile.slug:
        issues.append("Target tournament slug does not match the selected profile")
    if target.get("temporada") != profile.season:
        issues.append("Target tournament temporada does not match the selected profile")
    if target_active and tournament_id not in seen:
        issues.append("Target active state disagrees with active tournament inventory")
    if not target_active and tournament_id in seen:
        issues.append("Target inactive state disagrees with active tournament inventory")

    active_tuple = tuple(sorted(active_ids))
    return ActivationPlan(
        tournament_id=tournament_id,
        profile_key=profile.key,
        target=target,
        active_tournament_ids=active_tuple,
        deactivate_ids=tuple(value for value in active_tuple if value != tournament_id),
        fixture_count=fixture_count,
        position_count=len(position_rows),
        issues=tuple(issues),
    )


def inspect_activation(
    client: Any,
    tournament_id: int,
    profile: CurrentFixtureSourceProfile,
) -> ActivationPlan:
    target = read_target_tournament(client, tournament_id)
    active_rows = read_active_tournaments(client)
    expected_categories = profile_category_ids(profile)
    readiness = read_fixture_readiness(client, tournament_id)
    validate_readiness_completeness(readiness, profile, expected_categories)
    positions = read_positions(client, tournament_id)
    return build_activation_plan(
        target,
        active_rows,
        len(readiness.rows),
        readiness.participants,
        positions,
        tournament_id,
        profile,
    )


def execute_activation(client: Any, plan: ActivationPlan) -> dict[str, int]:
    if not plan.valid:
        raise ValueError("Refusing to execute an invalid tournament activation plan")
    if plan.noop:
        return {"activated": 0, "deactivated": 0}

    client.table("torneos").update({"activo": True}).eq(
        "id", plan.tournament_id
    ).execute()
    deactivated = 0
    for tournament_id in plan.deactivate_ids:
        client.table("torneos").update({"activo": False}).eq(
            "id", tournament_id
        ).execute()
        deactivated += 1
    return {"activated": 1, "deactivated": deactivated}


def render_report(context: OperationContext, plan: ActivationPlan) -> str:
    lines = [
        f"Tournament activation: mode={context.mode} tournament_id={context.tournament_id}",
        f"Profile: {plan.profile_key}",
        f"Validated fixtures: {plan.fixture_count}",
        f"Validated positions: {plan.position_count}",
        f"Currently active tournament IDs: {list(plan.active_tournament_ids)}",
        f"Planned deactivation IDs: {list(plan.deactivate_ids)}",
    ]
    if plan.noop:
        lines.append("Plan: no-op; target is already the sole active tournament.")
    elif plan.valid:
        lines.append("Plan: activate target first, then deactivate prevalidated IDs.")
    if plan.issues:
        lines.append(f"Blocking issues: {len(plan.issues)}")
        lines.extend(f"  ERROR: {issue}" for issue in plan.issues)
    else:
        lines.append("Blocking issues: 0")
    lines.append(
        "Execution risk: writes are sequential; if deactivation fails, multiple tournaments "
        "may temporarily remain active. Target-first ordering avoids leaving none active."
    )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Preview or activate one fixture-complete, standings-ready tournament."
    )
    parser.add_argument(
        "--profile",
        required=True,
        choices=tuple(SOURCE_PROFILES),
        help="Required versioned fixture profile used for readiness validation.",
    )
    add_operation_arguments(parser, tournament_required=True)
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
        client = (client_factory or _database_client)()
        plan = inspect_activation(client, context.tournament_id, profile)
        print(render_report(context, plan), file=output)
        if not plan.valid:
            return 1
        if not context.execute:
            print("Dry run only; no database mutations were attempted.", file=output)
            return 0
        counts = execute_activation(client, plan)
        print(
            f"Applied tournament activation: activated={counts['activated']} "
            f"deactivated={counts['deactivated']}",
            file=output,
        )
        return 0
    except Exception as exc:
        print(f"Tournament activation failed: {exc}", file=error_output)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
