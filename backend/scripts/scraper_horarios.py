# -*- coding: utf-8 -*-
"""Tournament-scoped schedule ingestion with a dry-run-first CLI."""

from __future__ import annotations

import argparse
import re
import sys
import unicodedata
from dataclasses import dataclass, replace
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Optional, Sequence, TextIO
from urllib.parse import urlparse
from urllib.request import urlopen

from operation_common import (
    OperationContext,
    add_operation_arguments,
    load_backend_environment,
    operation_context_from_args,
    validate_positive_tournament_id,
)


DEFAULT_SOURCE_URL = "https://www.ligaamateurdedeportes.com.ar/horarios.html"
INVENTORY_LIMIT = 1000

DURATION_MINUTES = {
    "primera": 105,
    "septima": 95,
    "octava": 85,
    "novena": 75,
    "decima": 65,
}

MONTHS = {
    "enero": 1,
    "febrero": 2,
    "marzo": 3,
    "abril": 4,
    "mayo": 5,
    "junio": 6,
    "julio": 7,
    "agosto": 8,
    "septiembre": 9,
    "octubre": 10,
    "noviembre": 11,
    "diciembre": 12,
}

DATE_PATTERN = re.compile(
    r"(?:lunes|martes|miércoles|miercoles|jueves|viernes|sábado|sabado|domingo)"
    r"\s+(\d{1,2})\s+de\s+([A-Za-zÁÉÍÓÚáéíóúÑñ]+)\s+de\s+(\d{4})",
    re.IGNORECASE,
)
ROUND_PATTERN = re.compile(r"fecha\s*(\d+)", re.IGNORECASE)
TIME_PATTERN = re.compile(r"(\d{1,2})[:.](\d{2})")


class ScheduleParseError(ValueError):
    """Raised when the official schedule structure cannot be interpreted."""


@dataclass(frozen=True)
class ScheduleRow:
    source_row: int
    date: Optional[str]
    round_id: Optional[int]
    category_raw: str
    category_key: Optional[str]
    category_id: Optional[int]
    local: str
    local_id: Optional[int]
    visitor: str
    visitor_id: Optional[int]
    scheduled_time: Optional[str]
    inherited_time: bool
    venue: str
    calculated_time: Optional[str] = None


@dataclass(frozen=True)
class FixtureRecord:
    id: int
    tournament_id: int
    category_id: int
    local_id: int
    visitor_id: Optional[int]
    round_id: Optional[int]

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "FixtureRecord":
        return cls(
            id=int(value["id"]),
            tournament_id=int(value["torneo_id"]),
            category_id=int(value["categoria_id"]),
            local_id=int(value["local_id"]),
            visitor_id=(
                int(value["visitante_id"])
                if value.get("visitante_id") is not None
                else None
            ),
            round_id=(int(value["fecha_id"]) if value.get("fecha_id") is not None else None),
        )


@dataclass(frozen=True)
class UpdatePlanEntry:
    target_id: int
    row: ScheduleRow
    values: Mapping[str, Any]


@dataclass(frozen=True)
class UpdatePlan:
    tournament_id: int
    entries: tuple[UpdatePlanEntry, ...]
    issues: tuple[str, ...]

    @property
    def valid(self) -> bool:
        return bool(self.entries) and not self.issues


class _ScheduleTableParser(HTMLParser):
    """Table extractor that preserves nested tables, sufficient for the official schedule markup."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[list[list[str]]] = []
        self._stack: list[dict[str, Any]] = []

    def _frame(self) -> Optional[dict[str, Any]]:
        return self._stack[-1] if self._stack else None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, Optional[str]]]) -> None:
        del attrs
        tag = tag.lower()
        if tag == "table":
            self._stack.append({"rows": [], "row": None, "cell": None})
            return
        frame = self._frame()
        if frame is None:
            return
        if tag == "tr":
            frame["row"] = []
        elif tag in {"td", "th"} and frame["row"] is not None:
            frame["cell"] = []
        elif tag == "br" and frame["cell"] is not None:
            frame["cell"].append(" ")

    def handle_data(self, data: str) -> None:
        frame = self._frame()
        if frame is not None and frame["cell"] is not None:
            frame["cell"].append(data)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        frame = self._frame()
        if frame is None:
            return
        if tag in {"td", "th"} and frame["cell"] is not None:
            text = " ".join("".join(frame["cell"]).split())
            if frame["row"] is not None:
                frame["row"].append(text)
            frame["cell"] = None
        elif tag == "tr":
            if frame["row"]:
                frame["rows"].append(frame["row"])
            frame["row"] = None
            frame["cell"] = None
        elif tag == "table":
            finished = self._stack.pop()
            if finished["rows"]:
                self.tables.append(finished["rows"])


def _identity_text(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    without_accents = "".join(char for char in decomposed if not unicodedata.combining(char))
    alphanumeric = re.sub(r"[^A-Za-z0-9]+", " ", without_accents)
    return " ".join(alphanumeric.upper().split())


def _identity_indexes() -> tuple[dict[str, int], dict[str, tuple[str, int]]]:
    # Importing config is intentionally deferred until parsing needs identities.
    # This keeps module import and --help independent from credentials and DB clients.
    from config import CATEGORIAS, MAPEO_CLUBES

    clubs: dict[str, int] = {}
    for source_name, club_id in MAPEO_CLUBES.items():
        key = _identity_text(source_name)
        existing = clubs.get(key)
        if existing is not None and existing != club_id:
            raise RuntimeError(f"Conflicting authoritative club identity for {source_name!r}")
        clubs[key] = club_id

    categories = {
        _identity_text(source_name): (source_name, category_id)
        for source_name, category_id in CATEGORIAS.items()
    }
    return clubs, categories


def normalize_team_name(name: str) -> str:
    return " ".join(name.strip().upper().split())


def resolve_club_id(name: str) -> Optional[int]:
    clubs, _ = _identity_indexes()
    return clubs.get(_identity_text(name))


def resolve_category(category: str) -> tuple[Optional[str], Optional[int]]:
    _, categories = _identity_indexes()
    normalized = _identity_text(category)
    resolved = categories.get(normalized)
    if resolved is None:
        return None, None
    return resolved


def _parse_date(match: re.Match[str]) -> str:
    day, raw_month, year = match.groups()
    month = MONTHS.get(_identity_text(raw_month).lower())
    if month is None:
        raise ScheduleParseError(f"Unknown Spanish month: {raw_month}")
    return f"{int(year):04d}-{month:02d}-{int(day):02d}"


def _parse_time(value: str) -> Optional[str]:
    match = TIME_PATTERN.fullmatch(value.strip())
    if match is None:
        return None
    hour, minute = (int(part) for part in match.groups())
    if hour > 23 or minute > 59:
        return None
    return f"{hour:02d}:{minute:02d}"


def parse_schedule_html(html: str) -> list[ScheduleRow]:
    """Parse fixture-like rows from the official schedule table."""
    parser = _ScheduleTableParser()
    parser.feed(html)
    table = next(
        (rows for rows in parser.tables if "CRONOGRAMA" in _identity_text(" ".join(sum(rows, [])))),
        None,
    )
    if table is None:
        raise ScheduleParseError("Schedule table containing CRONOGRAMA was not found")

    rows: list[ScheduleRow] = []
    current_date: Optional[str] = None
    current_round: Optional[int] = None
    last_time: Optional[str] = None
    last_venue = ""
    ignore_postponed_block = False

    for source_row, cells in enumerate(table, start=1):
        text = " ".join(cells)
        normalized_text = _identity_text(text).lower()
        date_match = DATE_PATTERN.search(text)
        if date_match is not None:
            current_date = _parse_date(date_match)
            round_match = ROUND_PATTERN.search(text)
            is_postponed = "postergado" in normalized_text
            current_round = int(round_match.group(1)) if round_match else None
            ignore_postponed_block = is_postponed and current_round is None
            last_time = None
            last_venue = ""
            continue

        if "postergado" in normalized_text and len(cells) < 3:
            ignore_postponed_block = True
            current_date = None
            current_round = None
            last_time = None
            last_venue = ""
            continue
        if ignore_postponed_block or len(cells) < 4:
            continue
        if len(cells) < 3 or cells[2].strip().lower() not in {"vs", "vs."}:
            continue

        local = normalize_team_name(cells[1])
        visitor = normalize_team_name(cells[3])
        if not local or not visitor:
            continue

        category_raw = cells[0].strip()
        category_key, category_id = resolve_category(category_raw)
        explicit_time = _parse_time(cells[4].replace(".", ":")) if len(cells) >= 5 else None
        inherited_time = explicit_time is None and last_time is not None
        scheduled_time = explicit_time or last_time
        if explicit_time is not None:
            last_time = explicit_time
        if len(cells) >= 6 and cells[5].strip():
            last_venue = cells[5].strip()

        rows.append(
            ScheduleRow(
                source_row=source_row,
                date=current_date,
                round_id=current_round,
                category_raw=category_raw,
                category_key=category_key,
                category_id=category_id,
                local=local,
                local_id=resolve_club_id(local),
                visitor=visitor,
                visitor_id=resolve_club_id(visitor),
                scheduled_time=scheduled_time,
                inherited_time=inherited_time,
                venue=last_venue,
            )
        )

    return rows


def _add_minutes(value: str, minutes: int) -> str:
    hour, minute = (int(part) for part in value.split(":"))
    total = hour * 60 + minute + minutes
    return f"{total // 60:02d}:{total % 60:02d}"


def calculate_schedule_times(rows: Iterable[ScheduleRow]) -> list[ScheduleRow]:
    """Deduplicate source rows and calculate inherited kickoff times per date/venue."""
    unique: list[ScheduleRow] = []
    seen: set[tuple[Any, ...]] = set()
    for row in rows:
        key = (
            row.date,
            row.round_id,
            row.category_raw,
            row.local,
            row.visitor,
        )
        if key not in seen:
            seen.add(key)
            unique.append(row)

    groups: dict[tuple[Optional[str], str], list[ScheduleRow]] = {}
    for row in unique:
        groups.setdefault((row.date, row.venue), []).append(row)

    calculated: list[ScheduleRow] = []
    for group in groups.values():
        current_time: Optional[str] = None
        previous_category: Optional[str] = None
        for row in group:
            if row.inherited_time and current_time is not None:
                duration = DURATION_MINUTES.get(previous_category or "", 80)
                current_time = _add_minutes(current_time, duration)
            else:
                current_time = row.scheduled_time
            calculated.append(replace(row, calculated_time=current_time))
            previous_category = row.category_key
    return calculated


def fetch_schedule_html(source: str = DEFAULT_SOURCE_URL, timeout: float = 30.0) -> str:
    """Read schedule HTML from a local recovery file or an HTTP(S) source."""
    local_path = Path(source)
    if local_path.is_file():
        return local_path.read_text(encoding="utf-8")

    parsed = urlparse(source)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError(f"Schedule source is not a readable file or HTTP(S) URL: {source}")

    with urlopen(source, timeout=timeout) as response:  # noqa: S310 - operator-selected URL
        encoding = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(encoding)


def read_fixture_inventory(client: Any, tournament_id: int) -> list[FixtureRecord]:
    """Read one bounded, tournament-scoped fixture inventory."""
    tournament_id = validate_positive_tournament_id(tournament_id)
    response = (
        client.table("partidos")
        .select("id,torneo_id,categoria_id,local_id,visitante_id,fecha_id")
        .eq("torneo_id", tournament_id)
        .limit(INVENTORY_LIMIT)
        .execute()
    )
    data = response.data or []
    if len(data) >= INVENTORY_LIMIT:
        raise RuntimeError(
            f"Fixture inventory reached the safety limit of {INVENTORY_LIMIT}; refusing a partial plan"
        )
    return [FixtureRecord.from_mapping(item) for item in data]


def _row_label(row: ScheduleRow) -> str:
    return f"row {row.source_row}: {row.category_raw} | {row.local} vs {row.visitor}"


def build_update_plan(
    rows: Iterable[ScheduleRow],
    fixtures: Iterable[FixtureRecord],
    tournament_id: int,
) -> UpdatePlan:
    """Match every schedule row to exactly one fixture before any mutation."""
    tournament_id = validate_positive_tournament_id(tournament_id)
    schedule_rows = list(rows)
    scoped_fixtures = [item for item in fixtures if item.tournament_id == tournament_id]
    entries: list[UpdatePlanEntry] = []
    issues: list[str] = []
    claimed_targets: set[int] = set()

    if not schedule_rows:
        issues.append("No schedule rows were parsed")

    for row in schedule_rows:
        label = _row_label(row)
        row_issues: list[str] = []
        if row.category_id is None:
            row_issues.append(f"Unknown category at {label}")
        if row.local_id is None:
            row_issues.append(f"Unknown local club at {label}")
        if row.visitor_id is None:
            row_issues.append(f"Unknown visiting club at {label}")
        if row.date is None:
            row_issues.append(f"Missing date at {label}")
        if row.calculated_time is None:
            row_issues.append(f"Missing kickoff time at {label}")
        if row_issues:
            issues.extend(row_issues)
            continue

        matches = [
            fixture
            for fixture in scoped_fixtures
            if fixture.category_id == row.category_id
            and fixture.local_id == row.local_id
            and fixture.visitor_id == row.visitor_id
            and (row.round_id is None or fixture.round_id == row.round_id)
        ]
        if not matches:
            issues.append(f"Missing fixture target for {label}")
            continue
        if len(matches) > 1:
            issues.append(f"Ambiguous fixture target ({len(matches)} matches) for {label}")
            continue

        target = matches[0]
        if target.id in claimed_targets:
            issues.append(f"Fixture target {target.id} was matched more than once ({label})")
            continue
        claimed_targets.add(target.id)
        entries.append(
            UpdatePlanEntry(
                target_id=target.id,
                row=row,
                values={
                    "dia": row.date,
                    "hora": row.calculated_time,
                    "cancha": row.venue or None,
                },
            )
        )

    return UpdatePlan(
        tournament_id=tournament_id,
        entries=tuple(entries),
        issues=tuple(issues),
    )


def render_report(context: OperationContext, plan: UpdatePlan) -> str:
    """Render a deterministic preview suitable for operators and tests."""
    lines = [
        f"Schedule operation: mode={context.mode} tournament_id={context.tournament_id}",
        f"Planned updates: {len(plan.entries)}",
    ]
    for entry in plan.entries:
        row = entry.row
        lines.append(
            f"  TARGET {entry.target_id}: {row.date} {row.calculated_time} | "
            f"{row.category_raw} | {row.local} vs {row.visitor} | {row.venue or '-'}"
        )
    if plan.issues:
        lines.append(f"Blocking issues: {len(plan.issues)}")
        lines.extend(f"  ERROR: {issue}" for issue in plan.issues)
    else:
        lines.append("Blocking issues: 0")
    return "\n".join(lines)


def execute_update_plan(client: Any, plan: UpdatePlan) -> int:
    """Apply only prevalidated target IDs, retaining defensive tournament scope."""
    if not plan.valid:
        raise ValueError("Refusing to execute an invalid or empty schedule plan")

    for entry in plan.entries:
        (
            client.table("partidos")
            .update(dict(entry.values))
            .eq("id", entry.target_id)
            .eq("torneo_id", plan.tournament_id)
            .execute()
        )
    return len(plan.entries)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Preview or apply tournament-scoped schedule updates.",
    )
    add_operation_arguments(parser)
    parser.add_argument(
        "--source",
        default=DEFAULT_SOURCE_URL,
        help="Official schedule URL or a local HTML recovery file.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="HTTP source timeout in seconds (default: 30).",
    )
    return parser


def _database_client() -> Any:
    from config import supabase

    return supabase


def main(
    argv: Optional[Sequence[str]] = None,
    *,
    client_factory: Optional[Callable[[], Any]] = None,
    fetcher: Optional[Callable[[str, float], str]] = None,
    stdout: Optional[TextIO] = None,
    stderr: Optional[TextIO] = None,
) -> int:
    """Run the schedule operation and return a process-compatible exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)
    output = stdout or sys.stdout
    error_output = stderr or sys.stderr

    try:
        load_backend_environment()
        context = operation_context_from_args(args)
        html = (fetcher or fetch_schedule_html)(args.source, args.timeout)
        parsed_rows = parse_schedule_html(html)
        calculated_rows = calculate_schedule_times(parsed_rows)
        client = (client_factory or _database_client)()
        inventory = read_fixture_inventory(client, context.tournament_id)
        plan = build_update_plan(calculated_rows, inventory, context.tournament_id)
        print(render_report(context, plan), file=output)
        if not plan.valid:
            return 1
        if context.execute:
            applied = execute_update_plan(client, plan)
            print(f"Applied updates: {applied}", file=output)
        else:
            print("Dry run only; no database mutations were attempted.", file=output)
        return 0
    except Exception as exc:
        print(f"Schedule operation failed: {exc}", file=error_output)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
