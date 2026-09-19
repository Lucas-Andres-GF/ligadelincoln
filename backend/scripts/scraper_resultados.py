# -*- coding: utf-8 -*-
"""Safe tournament-scoped result ingestion and projected standings refresh."""

from __future__ import annotations

import argparse
import json
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


DEFAULT_CATEGORY_SOURCES = {
    "primera": "https://www.ligaamateurdedeportes.com.ar/primera.html",
    "septima": "https://www.ligaamateurdedeportes.com.ar/septima.html",
    "octava": "https://www.ligaamateurdedeportes.com.ar/octava.html",
    "novena": "https://www.ligaamateurdedeportes.com.ar/novena.html",
    "decima": "https://www.ligaamateurdedeportes.com.ar/decima.html",
}
FIXTURE_INVENTORY_LIMIT = 2000
POSITION_INVENTORY_LIMIT = 1000
SCORE_PATTERN = re.compile(r"\d+")
ROUND_PATTERN = re.compile(r"\bFECHA\s*:?\s*(\d+)\b", re.IGNORECASE)
DATE_PATTERN = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{2}|\d{4})\b")
POSITION_FIELDS = ("pts", "pj", "pg", "pe", "pp", "gf", "gc", "dif", "ultimos_5")


class ResultParseError(ValueError):
    """Raised when the supported official result table cannot be found."""


@dataclass(frozen=True)
class OfficialResult:
    source_row: int
    category_raw: str
    category_key: Optional[str]
    category_id: Optional[int]
    round_id: Optional[int]
    date: Optional[str]
    local: str
    local_id: Optional[int]
    visitor: str
    visitor_id: Optional[int]
    local_goals: Optional[int]
    visitor_goals: Optional[int]
    score_raw: str


@dataclass(frozen=True)
class FixtureRecord:
    id: int
    tournament_id: int
    category_id: int
    local_id: Optional[int]
    visitor_id: Optional[int]
    round_id: Optional[int]
    date: Optional[str]
    state: str
    local_goals: Optional[int]
    visitor_goals: Optional[int]

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "FixtureRecord":
        return cls(
            id=_required_int(value.get("id"), "fixture id"),
            tournament_id=_required_int(value.get("torneo_id"), "fixture torneo_id"),
            category_id=_required_int(value.get("categoria_id"), "fixture categoria_id"),
            local_id=_optional_int(value.get("local_id"), "fixture local_id"),
            visitor_id=_optional_int(value.get("visitante_id"), "fixture visitante_id"),
            round_id=_optional_int(value.get("fecha_id"), "fixture fecha_id"),
            date=_optional_text(value.get("dia")),
            state=str(value.get("estado") or ""),
            local_goals=_optional_int(value.get("goles_local"), "fixture goles_local"),
            visitor_goals=_optional_int(value.get("goles_visitante"), "fixture goles_visitante"),
        )


@dataclass(frozen=True)
class ResultUpdate:
    target_id: int
    row: OfficialResult
    values: Mapping[str, Any]


@dataclass(frozen=True)
class ResultPlan:
    tournament_id: int
    official_row_count: int
    matched_target_ids: tuple[int, ...]
    entries: tuple[ResultUpdate, ...]
    issues: tuple[str, ...]

    @property
    def valid(self) -> bool:
        return self.official_row_count > 0 and not self.issues


@dataclass(frozen=True)
class StandingRow:
    tournament_id: int
    category_id: int
    club_id: int
    pts: int
    pj: int
    pg: int
    pe: int
    pp: int
    gf: int
    gc: int
    dif: int
    ultimos_5: tuple[str, ...]

    def values(self) -> dict[str, Any]:
        return {
            "pts": self.pts,
            "pj": self.pj,
            "pg": self.pg,
            "pe": self.pe,
            "pp": self.pp,
            "gf": self.gf,
            "gc": self.gc,
            "dif": self.dif,
            "ultimos_5": list(self.ultimos_5),
        }


@dataclass(frozen=True)
class StandingsProjection:
    rows: tuple[StandingRow, ...]
    issues: tuple[str, ...]


@dataclass(frozen=True)
class PositionAction:
    operation: str
    tournament_id: int
    category_id: int
    club_id: int
    values: Mapping[str, Any]
    existing_id: Optional[int] = None

    def __post_init__(self) -> None:
        if self.operation == "update":
            if (
                isinstance(self.existing_id, bool)
                or not isinstance(self.existing_id, int)
                or self.existing_id <= 0
            ):
                raise ValueError("Position update actions require a positive existing row ID")
        elif self.operation == "insert":
            if self.existing_id is not None:
                raise ValueError("Position insert actions cannot have an existing row ID")
        else:
            raise ValueError(f"Unsupported position operation: {self.operation}")


@dataclass(frozen=True)
class PositionPlan:
    actions: tuple[PositionAction, ...]
    issues: tuple[str, ...]


@dataclass(frozen=True)
class OperationPlan:
    tournament_id: int
    category_keys: tuple[str, ...]
    result_plan: ResultPlan
    projected_fixtures: tuple[FixtureRecord, ...]
    standings: tuple[StandingRow, ...]
    position_actions: tuple[PositionAction, ...]
    issues: tuple[str, ...]

    @property
    def valid(self) -> bool:
        return self.result_plan.valid and not self.issues


class _TableParser(HTMLParser):
    """Extract table rows while preserving independently nested tables."""

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


def _required_int(value: Any, label: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{label} must be an integer")
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be an integer") from exc
    return result


def _required_positive_int(value: Any, label: str) -> int:
    result = _required_int(value, label)
    if result <= 0:
        raise ValueError(f"{label} must be a positive integer")
    return result


def _optional_int(value: Any, label: str) -> Optional[int]:
    if value is None or value == "":
        return None
    return _required_int(value, label)


def _optional_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _identity_text(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    without_accents = "".join(char for char in decomposed if not unicodedata.combining(char))
    return " ".join(re.sub(r"[^A-Za-z0-9]+", " ", without_accents).upper().split())


def _identity_indexes() -> tuple[dict[str, int], dict[str, tuple[str, int]]]:
    # Config owns numeric identities. Import is deferred so module import and --help
    # do not load credentials or construct a database client.
    from config import CATEGORIAS, MAPEO_CLUBES

    clubs: dict[str, int] = {}
    for source_name, club_id in MAPEO_CLUBES.items():
        normalized = _identity_text(source_name)
        existing = clubs.get(normalized)
        if existing is not None and existing != club_id:
            raise RuntimeError(f"Conflicting authoritative club identity for {source_name!r}")
        clubs[normalized] = int(club_id)

    categories = {
        _identity_text(source_name): (source_name, int(category_id))
        for source_name, category_id in CATEGORIAS.items()
    }
    return clubs, categories


def resolve_club_id(name: str) -> Optional[int]:
    clubs, _ = _identity_indexes()
    return clubs.get(_identity_text(name))


def resolve_category(name: str) -> tuple[Optional[str], Optional[int]]:
    _, categories = _identity_indexes()
    resolved = categories.get(_identity_text(name))
    return resolved if resolved is not None else (None, None)


def parse_score(value: str) -> Optional[int]:
    """Return a non-negative integer score, rejecting mixed or signed text."""
    stripped = value.strip()
    if SCORE_PATTERN.fullmatch(stripped) is None:
        return None
    return int(stripped)


def _parse_date(value: str) -> Optional[str]:
    match = DATE_PATTERN.search(value)
    if match is None:
        return None
    day, month, year = match.groups()
    full_year = int(year) + 2000 if len(year) == 2 else int(year)
    day_number = int(day)
    month_number = int(month)
    if not 1 <= month_number <= 12 or not 1 <= day_number <= 31:
        return None
    return f"{full_year:04d}-{month_number:02d}-{day_number:02d}"


def _looks_like_incomplete_result_row(cells: Sequence[str]) -> bool:
    """Identify incomplete match rows after the official result header."""
    nonempty = [cell.strip() for cell in cells if cell.strip()]
    if not nonempty:
        return False
    if any(resolve_club_id(cell) is not None for cell in nonempty):
        return True
    score_cells = sum(parse_score(cell) is not None for cell in nonempty)
    return len(nonempty) >= 2 and score_cells > 0


def parse_results_html(html: str, category_name: str) -> list[OfficialResult]:
    """Parse the first supported latest-results block for one category page."""
    category_key, category_id = resolve_category(category_name)
    if category_id is None:
        raise ValueError(f"Unknown configured category: {category_name}")

    parser = _TableParser()
    parser.feed(html)
    table = next(
        (
            rows
            for rows in parser.tables
            if "ULTIMOS ENCUENTROS" in _identity_text(" ".join(sum(rows, [])))
        ),
        None,
    )
    if table is None:
        raise ResultParseError("Result table containing ULTIMOS ENCUENTROS was not found")

    current_round: Optional[int] = None
    current_date: Optional[str] = None
    active_round: Optional[int] = None
    headers_seen = False
    results: list[OfficialResult] = []

    for source_row, cells in enumerate(table, start=1):
        text = " ".join(cells)
        if headers_seen and "PROXIMA" in _identity_text(text):
            break

        round_match = ROUND_PATTERN.search(text)
        if round_match is not None:
            next_round = int(round_match.group(1))
            if results and active_round is not None and next_round != active_round:
                break
            current_round = next_round
            active_round = active_round if active_round is not None else next_round

        parsed_date = _parse_date(text)
        if parsed_date is not None:
            current_date = parsed_date

        normalized_cells = [_identity_text(cell) for cell in cells]
        if "LOCAL" in normalized_cells and "VISITANTE" in normalized_cells:
            headers_seen = True
            continue
        if not headers_seen:
            continue
        if len(cells) < 4:
            if _looks_like_incomplete_result_row(cells):
                raise ResultParseError(
                    f"Incomplete result row {source_row} in category {category_name}: {cells!r}"
                )
            continue
        if not any(cell.strip() for cell in cells[:4]):
            continue

        local = " ".join(cells[0].upper().split())
        visitor = " ".join(cells[3].upper().split())
        if not local or not visitor:
            raise ResultParseError(
                f"Result row {source_row} is missing a local or visiting team "
                f"in category {category_name}"
            )
        if "LIBRE" in _identity_text(local) or "LIBRE" in _identity_text(visitor):
            continue

        results.append(
            OfficialResult(
                source_row=source_row,
                category_raw=category_name,
                category_key=category_key,
                category_id=category_id,
                round_id=current_round,
                date=current_date,
                local=local,
                local_id=resolve_club_id(local),
                visitor=visitor,
                visitor_id=resolve_club_id(visitor),
                local_goals=parse_score(cells[1]),
                visitor_goals=parse_score(cells[2]),
                score_raw=f"{cells[1]}-{cells[2]}",
            )
        )

    return results


def fetch_result_html(source: str, timeout: float = 30.0) -> str:
    """Read one result page from a local recovery file or HTTP(S)."""
    local_path = Path(source)
    if local_path.is_file():
        return local_path.read_text(encoding="utf-8")

    parsed = urlparse(source)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError(f"Result source is not a readable file or HTTP(S) URL: {source}")
    with urlopen(source, timeout=timeout) as response:  # noqa: S310 - operator-selected URL
        encoding = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(encoding)


def _validate_category_ids(category_ids: Sequence[int]) -> tuple[int, ...]:
    values = tuple(sorted({validate_positive_tournament_id(item, source="category ID") for item in category_ids}))
    if not values:
        raise ValueError("At least one category must be selected")
    return values


def read_fixture_inventory(
    client: Any,
    tournament_id: int,
    category_ids: Sequence[int],
) -> list[FixtureRecord]:
    """Read a bounded fixture snapshot scoped to one tournament and selected categories."""
    tournament_id = validate_positive_tournament_id(tournament_id)
    selected = _validate_category_ids(category_ids)
    response = (
        client.table("partidos")
        .select(
            "id,torneo_id,categoria_id,local_id,visitante_id,fecha_id,dia,estado,"
            "goles_local,goles_visitante"
        )
        .eq("torneo_id", tournament_id)
        .in_("categoria_id", list(selected))
        .limit(FIXTURE_INVENTORY_LIMIT)
        .execute()
    )
    data = list(response.data or [])
    if len(data) >= FIXTURE_INVENTORY_LIMIT:
        raise RuntimeError(
            f"Fixture inventory reached the safety limit of {FIXTURE_INVENTORY_LIMIT}; "
            "refusing a possibly partial plan"
        )

    fixtures = [FixtureRecord.from_mapping(item) for item in data]
    seen_ids: set[int] = set()
    for fixture in fixtures:
        if fixture.tournament_id != tournament_id or fixture.category_id not in selected:
            raise RuntimeError("Fixture inventory returned a row outside the requested scope")
        if fixture.id in seen_ids:
            raise RuntimeError(f"Fixture inventory contains duplicate id {fixture.id}")
        seen_ids.add(fixture.id)
    return fixtures


def read_position_inventory(
    client: Any,
    tournament_id: int,
    category_ids: Sequence[int],
) -> list[Mapping[str, Any]]:
    """Read bounded existing standings rows for deterministic synchronization."""
    tournament_id = validate_positive_tournament_id(tournament_id)
    selected = _validate_category_ids(category_ids)
    response = (
        client.table("posiciones")
        .select("id,torneo_id,categoria_id,club_id,pts,pj,pg,pe,pp,gf,gc,dif,ultimos_5")
        .eq("torneo_id", tournament_id)
        .in_("categoria_id", list(selected))
        .limit(POSITION_INVENTORY_LIMIT)
        .execute()
    )
    data = list(response.data or [])
    if len(data) >= POSITION_INVENTORY_LIMIT:
        raise RuntimeError(
            f"Position inventory reached the safety limit of {POSITION_INVENTORY_LIMIT}; "
            "refusing a possibly partial plan"
        )
    for index, row in enumerate(data, start=1):
        try:
            _required_positive_int(row.get("id"), "position id")
            row_tournament = _required_int(row.get("torneo_id"), "position torneo_id")
            row_category = _required_int(row.get("categoria_id"), "position categoria_id")
        except ValueError as exc:
            raise RuntimeError(f"Malformed position inventory row {index}: {exc}") from exc
        if row_tournament != tournament_id or row_category not in selected:
            raise RuntimeError("Position inventory returned a row outside the requested scope")
    return data


def _result_label(row: OfficialResult) -> str:
    return (
        f"row {row.source_row}: {row.category_raw} round={row.round_id or '-'} "
        f"date={row.date or '-'} | {row.local} {row.score_raw} {row.visitor}"
    )


def build_result_plan(
    rows: Iterable[OfficialResult],
    fixtures: Iterable[FixtureRecord],
    tournament_id: int,
) -> ResultPlan:
    """Match each official row uniquely before creating any result mutation."""
    tournament_id = validate_positive_tournament_id(tournament_id)
    official_rows = list(rows)
    scoped_fixtures = [item for item in fixtures if item.tournament_id == tournament_id]
    issues: list[str] = []
    entries: list[ResultUpdate] = []
    matched_targets: list[int] = []
    claimed: dict[int, OfficialResult] = {}

    if not official_rows:
        issues.append("No official result rows were parsed")

    source_groups: dict[tuple[Any, ...], list[OfficialResult]] = {}
    for row in official_rows:
        source_groups.setdefault(
            (row.category_id, row.round_id, row.date, row.local_id, row.visitor_id), []
        ).append(row)
    conflicting_rows: set[int] = set()
    for grouped in source_groups.values():
        scores = {(item.local_goals, item.visitor_goals) for item in grouped}
        if len(grouped) > 1 and len(scores) > 1:
            labels = "; ".join(_result_label(item) for item in grouped)
            issues.append(f"Conflicting official rows: {labels}")
            conflicting_rows.update(id(item) for item in grouped)

    for row in official_rows:
        label = _result_label(row)
        row_issues: list[str] = []
        if row.category_id is None:
            row_issues.append(f"Unknown category at {label}")
        if row.local_id is None:
            row_issues.append(f"Unknown local club at {label}")
        if row.visitor_id is None:
            row_issues.append(f"Unknown visiting club at {label}")
        if row.local_goals is None or row.visitor_goals is None:
            row_issues.append(f"Malformed score at {label}")
        if row.local_goals is not None and row.local_goals < 0:
            row_issues.append(f"Malformed score at {label}")
        if row.visitor_goals is not None and row.visitor_goals < 0:
            row_issues.append(f"Malformed score at {label}")
        if row_issues:
            issues.extend(row_issues)
            continue
        if id(row) in conflicting_rows:
            continue

        matches = [
            fixture
            for fixture in scoped_fixtures
            if fixture.category_id == row.category_id
            and fixture.local_id == row.local_id
            and fixture.visitor_id == row.visitor_id
            and (row.round_id is None or fixture.round_id == row.round_id)
            and (row.date is None or fixture.date == row.date)
        ]
        if not matches:
            issues.append(f"Missing fixture target for {label}")
            continue
        if len(matches) > 1:
            issues.append(f"Ambiguous fixture target ({len(matches)} matches) for {label}")
            continue

        target = matches[0]
        previous = claimed.get(target.id)
        if previous is not None:
            previous_score = (previous.local_goals, previous.visitor_goals)
            current_score = (row.local_goals, row.visitor_goals)
            if previous_score != current_score:
                issues.append(
                    f"Conflicting official rows for fixture target {target.id}: "
                    f"{_result_label(previous)}; {label}"
                )
            else:
                issues.append(f"Fixture target {target.id} was matched more than once ({label})")
            continue

        claimed[target.id] = row
        matched_targets.append(target.id)
        desired = {
            "goles_local": row.local_goals,
            "goles_visitante": row.visitor_goals,
            "estado": "jugado",
        }
        if (
            target.state.strip().lower() != "jugado"
            or target.local_goals != row.local_goals
            or target.visitor_goals != row.visitor_goals
        ):
            entries.append(ResultUpdate(target_id=target.id, row=row, values=desired))

    return ResultPlan(
        tournament_id=tournament_id,
        official_row_count=len(official_rows),
        matched_target_ids=tuple(matched_targets),
        entries=tuple(entries),
        issues=tuple(issues),
    )


def overlay_planned_results(
    fixtures: Iterable[FixtureRecord],
    plan: ResultPlan,
) -> list[FixtureRecord]:
    """Apply result changes to a detached fixture snapshot."""
    changes = {entry.target_id: entry for entry in plan.entries}
    projected: list[FixtureRecord] = []
    for fixture in fixtures:
        entry = changes.get(fixture.id)
        if entry is None:
            projected.append(fixture)
            continue
        projected.append(
            replace(
                fixture,
                state="jugado",
                local_goals=int(entry.values["goles_local"]),
                visitor_goals=int(entry.values["goles_visitante"]),
            )
        )
    return projected


def derive_participants(
    fixtures: Iterable[FixtureRecord],
    category_ids: Sequence[int],
) -> dict[int, set[int]]:
    """Derive standings participants exclusively from the selected fixture."""
    selected = _validate_category_ids(category_ids)
    participants = {category_id: set() for category_id in selected}
    for fixture in fixtures:
        if fixture.category_id not in participants:
            continue
        for club_id in (fixture.local_id, fixture.visitor_id):
            if club_id is not None:
                participants[fixture.category_id].add(club_id)
    return participants


def _fixture_sort_key(fixture: FixtureRecord) -> tuple[Any, ...]:
    return (
        fixture.round_id is None,
        fixture.round_id if fixture.round_id is not None else 0,
        fixture.date or "",
        fixture.id,
    )


def calculate_projected_standings(
    fixtures: Iterable[FixtureRecord],
    tournament_id: int,
    category_ids: Sequence[int],
) -> StandingsProjection:
    """Calculate deterministic standings and recent form from a projected snapshot."""
    tournament_id = validate_positive_tournament_id(tournament_id)
    selected = _validate_category_ids(category_ids)
    fixture_rows = [
        fixture
        for fixture in fixtures
        if fixture.tournament_id == tournament_id and fixture.category_id in selected
    ]
    participants = derive_participants(fixture_rows, selected)
    issues: list[str] = []
    standings: list[StandingRow] = []

    for category_id in selected:
        club_ids = participants[category_id]
        if not club_ids:
            issues.append(f"Category {category_id} has no fixture participants")
            continue
        stats = {
            club_id: {
                "pts": 0,
                "pj": 0,
                "pg": 0,
                "pe": 0,
                "pp": 0,
                "gf": 0,
                "gc": 0,
                "form": [],
            }
            for club_id in club_ids
        }

        matches = sorted(
            (fixture for fixture in fixture_rows if fixture.category_id == category_id),
            key=_fixture_sort_key,
        )
        for fixture in matches:
            if fixture.state.strip().lower() != "jugado":
                continue
            if fixture.local_id is None or fixture.visitor_id is None:
                issues.append(f"Played fixture {fixture.id} has a missing participant identity")
                continue
            if fixture.local_id == fixture.visitor_id:
                issues.append(f"Fixture {fixture.id} has the same local and visiting club")
                continue
            if (
                fixture.local_goals is None
                or fixture.visitor_goals is None
                or fixture.local_goals < 0
                or fixture.visitor_goals < 0
            ):
                issues.append(f"Played fixture {fixture.id} has an invalid score")
                continue

            local = stats[fixture.local_id]
            visitor = stats[fixture.visitor_id]
            local["pj"] += 1
            visitor["pj"] += 1
            local["gf"] += fixture.local_goals
            local["gc"] += fixture.visitor_goals
            visitor["gf"] += fixture.visitor_goals
            visitor["gc"] += fixture.local_goals

            if fixture.local_goals > fixture.visitor_goals:
                local["pts"] += 3
                local["pg"] += 1
                visitor["pp"] += 1
                local["form"].append("G")
                visitor["form"].append("P")
            elif fixture.local_goals < fixture.visitor_goals:
                visitor["pts"] += 3
                visitor["pg"] += 1
                local["pp"] += 1
                visitor["form"].append("G")
                local["form"].append("P")
            else:
                local["pts"] += 1
                visitor["pts"] += 1
                local["pe"] += 1
                visitor["pe"] += 1
                local["form"].append("E")
                visitor["form"].append("E")

        category_rows = [
            StandingRow(
                tournament_id=tournament_id,
                category_id=category_id,
                club_id=club_id,
                pts=int(values["pts"]),
                pj=int(values["pj"]),
                pg=int(values["pg"]),
                pe=int(values["pe"]),
                pp=int(values["pp"]),
                gf=int(values["gf"]),
                gc=int(values["gc"]),
                dif=int(values["gf"]) - int(values["gc"]),
                ultimos_5=tuple(values["form"][-5:]),
            )
            for club_id, values in stats.items()
        ]
        category_rows.sort(key=lambda row: (-row.pts, -row.dif, -row.gf, row.club_id))
        standings.extend(category_rows)

    return StandingsProjection(rows=tuple(standings), issues=tuple(issues))


def _normalize_form(value: Any) -> list[str]:
    if value is None or value == "":
        return []
    parsed = value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError("ultimos_5 must be a JSON array or array value") from exc
    if not isinstance(parsed, (list, tuple)):
        raise ValueError("ultimos_5 must be an array")
    form = [str(item) for item in parsed]
    if len(form) > 5 or any(item not in {"G", "E", "P"} for item in form):
        raise ValueError("ultimos_5 contains invalid recent-form values")
    return form


def _existing_position_values(row: Mapping[str, Any]) -> dict[str, Any]:
    values = {
        field: _required_int(row.get(field), f"position {field}")
        for field in POSITION_FIELDS
        if field != "ultimos_5"
    }
    values["ultimos_5"] = _normalize_form(row.get("ultimos_5"))
    return values


def build_position_plan(
    standings: Sequence[StandingRow],
    existing_rows: Sequence[Mapping[str, Any]],
    tournament_id: int,
    category_ids: Sequence[int],
) -> PositionPlan:
    """Plan exact updates/inserts and block stale or malformed existing rows."""
    tournament_id = validate_positive_tournament_id(tournament_id)
    selected = _validate_category_ids(category_ids)
    desired = {(row.category_id, row.club_id): row for row in standings}
    existing: dict[tuple[int, int], Mapping[str, Any]] = {}
    issues: list[str] = []

    for index, row in enumerate(existing_rows, start=1):
        try:
            _required_positive_int(row.get("id"), "position id")
            row_tournament = _required_int(row.get("torneo_id"), "position torneo_id")
            category_id = _required_int(row.get("categoria_id"), "position categoria_id")
            club_id = _required_int(row.get("club_id"), "position club_id")
        except ValueError as exc:
            issues.append(f"Malformed existing position row {index}: {exc}")
            continue
        if row_tournament != tournament_id or category_id not in selected:
            issues.append(f"Existing position row {index} is outside the requested scope")
            continue
        key = (category_id, club_id)
        if key in existing:
            issues.append(
                f"Duplicate existing position target for category {category_id}, club {club_id}"
            )
            continue
        existing[key] = row

    stale = sorted(set(existing) - set(desired))
    for category_id, club_id in stale:
        issues.append(
            f"Stale position row for category {category_id}, club {club_id}; "
            "automatic removal is not safe"
        )

    actions: list[PositionAction] = []
    for key in sorted(desired):
        standing = desired[key]
        values = standing.values()
        current = existing.get(key)
        if current is None:
            actions.append(
                PositionAction(
                    operation="insert",
                    tournament_id=tournament_id,
                    category_id=standing.category_id,
                    club_id=standing.club_id,
                    values=values,
                )
            )
            continue
        try:
            current_values = _existing_position_values(current)
        except ValueError as exc:
            issues.append(
                f"Malformed existing position for category {standing.category_id}, "
                f"club {standing.club_id}: {exc}"
            )
            continue
        if current_values != values:
            existing_id = _required_positive_int(current.get("id"), "position id")
            actions.append(
                PositionAction(
                    operation="update",
                    tournament_id=tournament_id,
                    category_id=standing.category_id,
                    club_id=standing.club_id,
                    values=values,
                    existing_id=existing_id,
                )
            )

    return PositionPlan(actions=tuple(actions), issues=tuple(issues))


def build_operation_plan(
    rows: Iterable[OfficialResult],
    fixtures: Sequence[FixtureRecord],
    existing_positions: Sequence[Mapping[str, Any]],
    tournament_id: int,
    category_keys: Sequence[str],
    category_ids: Sequence[int],
) -> OperationPlan:
    """Build the complete result and standings synchronization plan before writes."""
    result_plan = build_result_plan(rows, fixtures, tournament_id)
    projected = overlay_planned_results(fixtures, result_plan)
    projection = calculate_projected_standings(projected, tournament_id, category_ids)
    position_plan = (
        PositionPlan(actions=(), issues=())
        if projection.issues
        else build_position_plan(
            projection.rows,
            existing_positions,
            tournament_id,
            category_ids,
        )
    )
    issues = tuple((*result_plan.issues, *projection.issues, *position_plan.issues))
    return OperationPlan(
        tournament_id=tournament_id,
        category_keys=tuple(category_keys),
        result_plan=result_plan,
        projected_fixtures=tuple(projected),
        standings=projection.rows,
        position_actions=position_plan.actions,
        issues=issues,
    )


def render_report(context: OperationContext, plan: OperationPlan) -> str:
    """Render a deterministic operator preview."""
    lines = [
        f"Result operation: mode={context.mode} tournament_id={context.tournament_id}",
        f"Categories: {', '.join(plan.category_keys)}",
        f"Official rows: {plan.result_plan.official_row_count}",
        f"Matched fixtures: {len(plan.result_plan.matched_target_ids)}",
        f"Planned result updates: {len(plan.result_plan.entries)}",
    ]
    for entry in plan.result_plan.entries:
        lines.append(
            f"  RESULT target={entry.target_id}: {entry.row.local} "
            f"{entry.values['goles_local']}-{entry.values['goles_visitante']} "
            f"{entry.row.visitor}"
        )
    lines.append(f"Projected standings rows: {len(plan.standings)}")
    lines.append(f"Planned position actions: {len(plan.position_actions)}")
    for action in plan.position_actions:
        lines.append(
            f"  POSITION {action.operation} category={action.category_id} club={action.club_id}"
        )
    if plan.issues:
        lines.append(f"Blocking issues: {len(plan.issues)}")
        lines.extend(f"  ERROR: {issue}" for issue in plan.issues)
    else:
        lines.append("Blocking issues: 0")
    return "\n".join(lines)


def execute_operation_plan(client: Any, plan: OperationPlan) -> dict[str, int]:
    """Apply a fully validated plan with defensive row-level scope filters."""
    if not plan.valid:
        raise ValueError("Refusing to execute an invalid result operation plan")

    counts = {"results_updated": 0, "positions_updated": 0, "positions_inserted": 0}
    for entry in plan.result_plan.entries:
        (
            client.table("partidos")
            .update(dict(entry.values))
            .eq("id", entry.target_id)
            .eq("torneo_id", plan.tournament_id)
            .execute()
        )
        counts["results_updated"] += 1

    for action in plan.position_actions:
        if action.operation == "update":
            (
                client.table("posiciones")
                .update(dict(action.values))
                .eq("id", action.existing_id)
                .eq("torneo_id", action.tournament_id)
                .eq("categoria_id", action.category_id)
                .eq("club_id", action.club_id)
                .execute()
            )
            counts["positions_updated"] += 1
        elif action.operation == "insert":
            client.table("posiciones").insert(
                {
                    "torneo_id": action.tournament_id,
                    "categoria_id": action.category_id,
                    "club_id": action.club_id,
                    **dict(action.values),
                }
            ).execute()
            counts["positions_inserted"] += 1
        else:
            raise ValueError(f"Unsupported position operation: {action.operation}")
    return counts


def _parse_source_overrides(values: Sequence[str]) -> dict[str, str]:
    overrides: dict[str, str] = {}
    for value in values:
        category, separator, source = value.partition("=")
        if not separator or category not in DEFAULT_CATEGORY_SOURCES or not source.strip():
            raise ValueError("--source must use CATEGORY=URL_OR_PATH for a supported category")
        if category in overrides:
            raise ValueError(f"Duplicate --source override for category {category}")
        overrides[category] = source.strip()
    return overrides


def _selected_sources(
    categories: Sequence[str],
    source_overrides: Sequence[str],
) -> dict[str, str]:
    selected = list(dict.fromkeys(categories or DEFAULT_CATEGORY_SOURCES.keys()))
    overrides = _parse_source_overrides(source_overrides)
    unselected = sorted(set(overrides) - set(selected))
    if unselected:
        raise ValueError(
            "Source override provided for unselected category: " + ", ".join(unselected)
        )
    return {category: overrides.get(category, DEFAULT_CATEGORY_SOURCES[category]) for category in selected}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Preview or apply tournament-scoped official results and standings.",
    )
    add_operation_arguments(parser)
    parser.add_argument(
        "--category",
        action="append",
        choices=tuple(DEFAULT_CATEGORY_SOURCES),
        default=[],
        help="Category to process; repeat as needed (default: all official categories).",
    )
    parser.add_argument(
        "--source",
        action="append",
        default=[],
        metavar="CATEGORY=URL_OR_PATH",
        help="Override one selected category source with an HTTP(S) URL or local HTML file.",
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
    """Run result ingestion and return a process-compatible exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)
    output = stdout or sys.stdout
    error_output = stderr or sys.stderr

    try:
        load_backend_environment()
        context = operation_context_from_args(args)
        sources = _selected_sources(args.category, args.source)
        identities = [resolve_category(category) for category in sources]
        category_ids = [category_id for _, category_id in identities if category_id is not None]
        if len(category_ids) != len(sources):
            raise RuntimeError("A selected category is missing an authoritative numeric identity")

        official_rows: list[OfficialResult] = []
        source_fetcher = fetcher or fetch_result_html
        for category, source in sources.items():
            html = source_fetcher(source, args.timeout)
            parsed = parse_results_html(html, category)
            if not parsed:
                raise ResultParseError(f"No result rows found for category {category}")
            official_rows.extend(parsed)

        client = (client_factory or _database_client)()
        fixtures = read_fixture_inventory(client, context.tournament_id, category_ids)
        positions = read_position_inventory(client, context.tournament_id, category_ids)
        plan = build_operation_plan(
            official_rows,
            fixtures,
            positions,
            context.tournament_id,
            tuple(sources),
            category_ids,
        )
        print(render_report(context, plan), file=output)
        if not plan.valid:
            return 1
        if not context.execute:
            print("Dry run only; no database mutations were attempted.", file=output)
            return 0

        counts = execute_operation_plan(client, plan)
        print(
            "Applied updates: "
            f"results={counts['results_updated']} "
            f"positions_updated={counts['positions_updated']} "
            f"positions_inserted={counts['positions_inserted']}",
            file=output,
        )
        return 0
    except Exception as exc:
        print(f"Result operation failed: {exc}", file=error_output)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
