# -*- coding: utf-8 -*-
"""Import a current official fixture through an explicit versioned profile."""

from __future__ import annotations

import argparse
import re
import sys
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Optional, Sequence, TextIO
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from fuente_fixture_actual import (
    SOURCE_PROFILES,
    CurrentFixtureSourceProfile,
    get_source_profile,
    validate_category_completeness,
    validate_supported_format,
)
from operation_common import (
    OperationContext,
    add_operation_arguments,
    load_backend_environment,
    operation_context_from_args,
    read_exact_paginated,
    validate_positive_tournament_id,
)


USER_AGENT = "Mozilla/5.0 fixture-importer/2.0"
INVENTORY_PAGE_SIZE = 200
FIXTURE_INVENTORY_MAX_TOTAL = 2000
POSITION_INVENTORY_MAX_TOTAL = 1000
LINEUP_INVENTORY_MAX_TOTAL = 5000
SUPPORTED_FIXTURE_STATES = frozenset({"programado", "jugado", "postergado", "libre"})
REPLACEABLE_FIXTURE_STATES = frozenset({"programado", "postergado", "libre"})
MIN_TIMEOUT_SECONDS = 0.1
MAX_TIMEOUT_SECONDS = 120.0
PROFILE_CATEGORY_CHOICES = tuple(
    dict.fromkeys(
        category
        for profile in SOURCE_PROFILES.values()
        for category in profile.category_sources
    )
)


class FixtureParseError(ValueError):
    """Raised when a supported current fixture source is incomplete or malformed."""


@dataclass(frozen=True)
class OfficialFixtureRow:
    source_row: int
    category_key: str
    round_id: int
    date: Optional[str]
    local: str
    visitor: str


@dataclass(frozen=True)
class PlannedFixture:
    source_row: int
    category_key: str
    category_id: int
    round_id: int
    local_id: int
    visitor_id: Optional[int]
    values: Mapping[str, Any]


@dataclass(frozen=True)
class CategoryPlan:
    category_key: str
    category_id: int
    fixtures: tuple[PlannedFixture, ...]
    issues: tuple[str, ...]

    @property
    def valid(self) -> bool:
        return bool(self.fixtures) and not self.issues


@dataclass(frozen=True)
class SourcePlan:
    tournament_id: int
    profile_key: str
    categories: tuple[CategoryPlan, ...]
    issues: tuple[str, ...]

    @property
    def valid(self) -> bool:
        return bool(self.categories) and all(item.valid for item in self.categories) and not self.issues

    @property
    def fixtures(self) -> tuple[PlannedFixture, ...]:
        return tuple(fixture for category in self.categories for fixture in category.fixtures)


@dataclass(frozen=True)
class ExistingScope:
    tournament: Optional[Mapping[str, Any]]
    fixtures: tuple[Mapping[str, Any], ...]
    positions: tuple[Mapping[str, Any], ...]
    lineups: tuple[Mapping[str, Any], ...]


@dataclass(frozen=True)
class TournamentWrite:
    operation: str
    values: Mapping[str, Any]


@dataclass(frozen=True)
class ImportPlan:
    tournament_id: int
    profile_key: str
    category_plans: tuple[CategoryPlan, ...]
    tournament_write: TournamentWrite
    replace_existing: bool
    delete_category_ids: tuple[int, ...]
    existing_fixture_count: int
    issues: tuple[str, ...]

    @property
    def valid(self) -> bool:
        return bool(self.category_plans) and all(item.valid for item in self.category_plans) and not self.issues

    @property
    def fixture_count(self) -> int:
        return sum(len(item.fixtures) for item in self.category_plans)


class _TableRowParser(HTMLParser):
    """Extract table rows from the Excel-exported official pages."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.rows: list[list[str]] = []
        self._row: Optional[list[str]] = None
        self._cell: Optional[list[str]] = None

    def handle_starttag(self, tag: str, attrs: Sequence[tuple[str, Optional[str]]]) -> None:
        del attrs
        tag = tag.lower()
        if tag == "tr":
            self._row = []
        elif tag in {"td", "th"} and self._row is not None:
            self._cell = []
        elif tag == "br" and self._cell is not None:
            self._cell.append(" ")

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)

    def handle_entityref(self, name: str) -> None:
        if self._cell is not None:
            self._cell.append(unescape(f"&{name};"))

    def handle_charref(self, name: str) -> None:
        if self._cell is not None:
            self._cell.append(unescape(f"&#{name};"))

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"td", "th"} and self._cell is not None:
            if self._row is not None:
                self._row.append(normalize_space("".join(self._cell)))
            self._cell = None
        elif tag == "tr" and self._row is not None:
            self.rows.append(self._row)
            self._row = None
            self._cell = None


def normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace("\xa0", " ")).strip()


def repair_encoding(value: str) -> str:
    """Repair common UTF-8 text decoded through a Windows code page."""
    text = value
    if "Ã" in text or "Â" in text:
        for encoding in ("cp1252", "latin1"):
            try:
                text = text.encode(encoding).decode("utf-8")
                break
            except (UnicodeEncodeError, UnicodeDecodeError):
                continue
    return normalize_space(text.replace("�", "Ñ"))


def identity_text(value: str) -> str:
    repaired = repair_encoding(value).replace(":", " ")
    decomposed = unicodedata.normalize("NFKD", repaired)
    without_accents = "".join(char for char in decomposed if not unicodedata.combining(char))
    return normalize_space(re.sub(r"[^A-Za-z0-9]+", " ", without_accents).upper())


def decode_current_html(raw: bytes) -> str:
    """Decode official pages and local recovery files without replacement loss."""
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw.decode("utf-8-sig")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("cp1252")


def load_fixture_source(source: str, timeout: float = 30.0) -> str:
    """Load one category source from a local file or an HTTP(S) URL."""
    if not MIN_TIMEOUT_SECONDS <= timeout <= MAX_TIMEOUT_SECONDS:
        raise ValueError(
            f"timeout must be between {MIN_TIMEOUT_SECONDS} and {MAX_TIMEOUT_SECONDS} seconds"
        )
    local_path = Path(source)
    if local_path.is_file():
        return decode_current_html(local_path.read_bytes())
    parsed = urlparse(source)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError(f"Fixture source is not a readable file or HTTP(S) URL: {source}")
    request = Request(source, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=timeout) as response:  # noqa: S310 - profile/operator URL
        return decode_current_html(response.read())


def _parse_date(value: str) -> Optional[str]:
    match = re.search(r"\b(\d{1,2})/(\d{1,2})/(\d{2}|\d{4})\b", value)
    if match is None:
        return None
    day, month, year = match.groups()
    full_year = int(year) + 2000 if len(year) == 2 else int(year)
    try:
        return datetime(full_year, int(month), int(day)).date().isoformat()
    except ValueError as exc:
        raise FixtureParseError(f"Malformed fixture date: {match.group(0)}") from exc


def _row_text(row: Sequence[str]) -> str:
    return " | ".join(cell for cell in row if cell)


def _round_marker(row: Sequence[str]) -> Optional[int]:
    for index, cell in enumerate(row):
        if "FECHA" not in identity_text(cell):
            continue
        same_cell = re.search(r"\bFECHA\s*:?\s*(-?\d+)\b", repair_encoding(cell), re.IGNORECASE)
        if same_cell is not None:
            round_id = int(same_cell.group(1))
        else:
            round_id = 0
            for next_cell in row[index + 1 : index + 3]:
                if re.fullmatch(r"-?\d+", next_cell.strip()):
                    round_id = int(next_cell)
                    break
        if round_id <= 0:
            raise FixtureParseError(f"Malformed or nonpositive round marker: {_row_text(row)!r}")
        return round_id
    return None


def _block_date(block: Sequence[Sequence[str]]) -> Optional[str]:
    for row in block[:8]:
        for cell in row:
            parsed = _parse_date(cell)
            if parsed is not None:
                return parsed
    return None


def _looks_like_header(row: Sequence[str]) -> bool:
    cells = {identity_text(cell) for cell in row}
    return "LOCAL" in cells and "VISITANTE" in cells


def _extract_rows(html: str) -> list[list[str]]:
    parser = _TableRowParser()
    parser.feed(html)
    return parser.rows


def parse_current_table_html(
    html: str,
    category_key: str,
    *,
    requires_contiguous_rounds: bool = True,
) -> list[OfficialFixtureRow]:
    """Parse the supported current-table-v1 fixture section for one category."""
    rows = _extract_rows(html)
    try:
        start = next(
            index + 1
            for index, row in enumerate(rows)
            if "FIXTURE COMPLETO" in identity_text(_row_text(row))
        )
    except StopIteration as exc:
        raise FixtureParseError("Current fixture section containing FIXTURE COMPLETO was not found") from exc

    markers: list[tuple[int, int]] = []
    for index in range(start, len(rows)):
        round_id = _round_marker(rows[index])
        if round_id is not None:
            markers.append((index, round_id))
    if not markers:
        raise FixtureParseError(f"No fixture rounds found for category {category_key}")

    round_ids = [round_id for _, round_id in markers]
    if len(set(round_ids)) != len(round_ids):
        raise FixtureParseError(f"Duplicate round markers for category {category_key}")
    if requires_contiguous_rounds:
        expected = list(range(1, max(round_ids) + 1))
        if sorted(round_ids) != expected:
            raise FixtureParseError(
                f"Noncontiguous rounds for category {category_key}: {sorted(round_ids)}"
            )

    parsed: list[OfficialFixtureRow] = []
    for marker_position, (block_start, round_id) in enumerate(markers):
        block_end = markers[marker_position + 1][0] if marker_position + 1 < len(markers) else len(rows)
        block = rows[block_start:block_end]
        date = _block_date(block)
        header_index = next((index for index, row in enumerate(block) if _looks_like_header(row)), None)
        if header_index is None:
            raise FixtureParseError(
                f"Fixture header missing in {category_key} round {round_id}"
            )

        for row_offset, row in enumerate(block[header_index + 1 :], start=header_index + 1):
            source_row = block_start + row_offset + 1
            if _looks_like_header(row):
                raise FixtureParseError(
                    f"Duplicate fixture header in {category_key} round {round_id}"
                )
            nonempty = [cell for cell in row if normalize_space(cell)]
            if not nonempty:
                continue
            if len(row) < 4:
                # Single-cell section labels and footers are common in the Excel
                # export. A multi-cell row beginning with a team-like value is an
                # incomplete match row and must not be silently discarded.
                if len(row) >= 2 and normalize_space(row[0]):
                    raise FixtureParseError(
                        f"Malformed fixture row {source_row} in {category_key}: {row!r}"
                    )
                continue
            local = repair_encoding(row[0])
            visitor = repair_encoding(row[3])
            if not local and not visitor:
                continue
            if not local or not visitor:
                raise FixtureParseError(
                    f"Malformed fixture row {source_row} in {category_key}: {row!r}"
                )
            parsed.append(
                OfficialFixtureRow(
                    source_row=source_row,
                    category_key=category_key,
                    round_id=round_id,
                    date=date,
                    local=local,
                    visitor=visitor,
                )
            )

    if not parsed:
        raise FixtureParseError(f"No fixture rows found for category {category_key}")
    return parsed


def parse_profile_source(
    profile: CurrentFixtureSourceProfile,
    category_key: str,
    html: str,
) -> list[OfficialFixtureRow]:
    """Parse and require the exact versioned shape for one profile category."""
    validate_supported_format(profile)
    rows = parse_current_table_html(
        html,
        category_key,
        requires_contiguous_rounds=profile.requires_contiguous_rounds,
    )
    try:
        validate_category_completeness(
            profile,
            category_key,
            (row.round_id for row in rows),
            len(rows),
        )
    except ValueError as exc:
        raise FixtureParseError(str(exc)) from exc
    return rows


def _identity_configuration() -> tuple[dict[str, int], dict[str, int]]:
    # Config remains the sole owner of numeric identities. Profile fixture data,
    # not legacy membership lists, defines current/future category participants.
    # Import is deferred so module import and --help remain credential-free.
    from config import CATEGORIAS, MAPEO_CLUBES

    clubs: dict[str, int] = {}
    for source_name, club_id in MAPEO_CLUBES.items():
        normalized = identity_text(source_name)
        parsed_id = validate_positive_tournament_id(club_id, source=f"club ID for {source_name}")
        previous = clubs.get(normalized)
        if previous is not None and previous != parsed_id:
            raise RuntimeError(f"Conflicting authoritative club identity for {source_name!r}")
        clubs[normalized] = parsed_id
    categories = {
        key: validate_positive_tournament_id(value, source=f"category ID for {key}")
        for key, value in CATEGORIAS.items()
    }
    return clubs, categories


def build_category_plan(
    rows: Iterable[OfficialFixtureRow],
    tournament_id: int,
    category_key: str,
) -> CategoryPlan:
    """Resolve identities and validate one complete category fixture."""
    tournament_id = validate_positive_tournament_id(tournament_id)
    clubs, categories = _identity_configuration()
    category_id = categories.get(category_key)
    if category_id is None:
        raise ValueError(f"Unknown configured category: {category_key}")

    source_rows = list(rows)
    fixtures: list[PlannedFixture] = []
    issues: list[str] = []
    exact_keys: dict[tuple[int, int, Optional[int]], OfficialFixtureRow] = {}
    matchup_keys: dict[tuple[int, frozenset[int]], OfficialFixtureRow] = {}
    round_participants: dict[int, set[int]] = {}

    if not source_rows:
        issues.append(f"No fixture rows parsed for category {category_key}")

    for row in source_rows:
        label = f"row {row.source_row}: {category_key} round={row.round_id} {row.local} vs {row.visitor}"
        if row.category_key != category_key:
            issues.append(f"Wrong category at {label}")
            continue
        if isinstance(row.round_id, bool) or not isinstance(row.round_id, int) or row.round_id <= 0:
            issues.append(f"Malformed or nonpositive round at {label}")
            continue

        local_name = identity_text(row.local)
        visitor_name = identity_text(row.visitor)
        local_bye = local_name == "LIBRE"
        visitor_bye = visitor_name == "LIBRE"
        if local_bye and visitor_bye:
            issues.append(f"Malformed double bye at {label}")
            continue
        if local_bye:
            local_id = clubs.get(visitor_name)
            visitor_id = None
        else:
            local_id = clubs.get(local_name)
            visitor_id = None if visitor_bye else clubs.get(visitor_name)

        if local_id is None:
            issues.append(f"Unknown club at {label}")
            continue
        if not visitor_bye and not local_bye and visitor_id is None:
            issues.append(f"Unknown club at {label}")
            continue
        if visitor_id is not None and local_id == visitor_id:
            issues.append(f"Self-play fixture at {label}")
            continue
        participants = {local_id} if visitor_id is None else {local_id, visitor_id}

        exact_key = (row.round_id, local_id, visitor_id)
        previous_exact = exact_keys.get(exact_key)
        if previous_exact is not None:
            if previous_exact.date == row.date:
                issues.append(f"Duplicate fixture key at {label}")
            else:
                issues.append(f"Conflicting fixture rows at {label}")
            continue
        matchup_key = (row.round_id, frozenset(participants))
        previous_matchup = matchup_keys.get(matchup_key)
        if previous_matchup is not None:
            issues.append(f"Conflicting fixture rows at {label}")
            continue

        already_seen = round_participants.setdefault(row.round_id, set())
        duplicated_participants = sorted(already_seen & participants)
        if duplicated_participants:
            issues.append(
                f"Duplicate team participation in {category_key} round {row.round_id}: "
                f"club IDs {duplicated_participants}"
            )
            continue
        already_seen.update(participants)
        exact_keys[exact_key] = row
        matchup_keys[matchup_key] = row
        fixtures.append(
            PlannedFixture(
                source_row=row.source_row,
                category_key=category_key,
                category_id=category_id,
                round_id=row.round_id,
                local_id=local_id,
                visitor_id=visitor_id,
                values={
                    "torneo_id": tournament_id,
                    "categoria_id": category_id,
                    "fecha_id": row.round_id,
                    "local_id": local_id,
                    "visitante_id": visitor_id,
                    "dia": row.date,
                    "goles_local": None,
                    "goles_visitante": None,
                    "estado": "programado",
                    "cancha": None,
                    "hora": None,
                    "arbitro": None,
                },
            )
        )

    return CategoryPlan(
        category_key=category_key,
        category_id=category_id,
        fixtures=tuple(fixtures),
        issues=tuple(issues),
    )


def validate_source_plan(
    category_plans: Sequence[CategoryPlan],
    tournament_id: int,
    profile_key: str,
    selected_categories: Sequence[str],
) -> SourcePlan:
    """Validate category coverage and cross-category fixture uniqueness."""
    tournament_id = validate_positive_tournament_id(tournament_id)
    issues: list[str] = []
    expected = tuple(selected_categories)
    actual = tuple(plan.category_key for plan in category_plans)
    if not expected:
        issues.append("At least one fixture category must be selected")
    if len(set(actual)) != len(actual):
        issues.append("Duplicate category plans were supplied")
    if set(actual) != set(expected):
        issues.append(f"Category plan coverage mismatch: expected={expected!r} actual={actual!r}")

    global_keys: set[tuple[int, int, int, Optional[int]]] = set()
    for plan in category_plans:
        for fixture in plan.fixtures:
            key = (
                fixture.category_id,
                fixture.round_id,
                fixture.local_id,
                fixture.visitor_id,
            )
            if key in global_keys:
                issues.append(f"Duplicate cross-category fixture key: {key!r}")
            global_keys.add(key)
    return SourcePlan(
        tournament_id=tournament_id,
        profile_key=profile_key,
        categories=tuple(category_plans),
        issues=tuple(issues),
    )


def _validate_category_ids(category_ids: Sequence[int]) -> tuple[int, ...]:
    selected = tuple(
        sorted(
            {
                validate_positive_tournament_id(item, source="category ID")
                for item in category_ids
            }
        )
    )
    if not selected:
        raise ValueError("At least one category ID is required")
    return selected


def _inventory_positive_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise RuntimeError(f"{label} must be a positive integer")
    return value


def _read_complete_inventory(
    client: Any,
    *,
    table: str,
    columns: str,
    scope_query: Callable[[Any], Any],
    label: str,
    maximum_total: int,
    page_size: int = INVENTORY_PAGE_SIZE,
) -> list[Mapping[str, Any]]:
    """Read a scoped Supabase inventory through the shared exact paginator."""

    def fetch_page(start: int, end: int) -> Any:
        query = client.table(table).select(columns, count="exact")
        query = scope_query(query)
        return query.order("id").range(start, end).execute()

    rows = read_exact_paginated(
        fetch_page,
        label=label,
        maximum_total=maximum_total,
        page_size=page_size,
        identity=lambda row: _inventory_positive_int(
            row.get("id") if isinstance(row, Mapping) else None,
            f"{label} row id",
        ),
        identity_name="row id",
    )
    if not all(isinstance(row, Mapping) for row in rows):
        raise RuntimeError(f"{label} contains a malformed row")
    return rows


def _fixture_state(value: Any, fixture_id: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RuntimeError(f"Fixture {fixture_id} estado is missing or malformed")
    state = identity_text(value).lower()
    if state not in SUPPORTED_FIXTURE_STATES:
        raise RuntimeError(f"Fixture {fixture_id} has unsupported estado {value!r}")
    return state


def _validate_fixture_sides(
    local_value: Any,
    visitor_value: Any,
    state: str,
    fixture_id: int,
) -> None:
    """Validate competitive teams or the exactly-one-club bye representation."""
    if state == "libre":
        local_is_null = local_value is None
        visitor_is_null = visitor_value is None
        if local_is_null == visitor_is_null:
            raise RuntimeError(
                f"Fixture {fixture_id} estado libre requires exactly one null team side"
            )
        if local_is_null:
            _inventory_positive_int(visitor_value, "fixture visitante_id")
        else:
            _inventory_positive_int(local_value, "fixture local_id")
        return

    _inventory_positive_int(local_value, "fixture local_id")
    _inventory_positive_int(visitor_value, "fixture visitante_id")


def inspect_existing_scope(
    client: Any,
    tournament_id: int,
    category_ids: Sequence[int],
) -> ExistingScope:
    """Read bounded tournament/category state needed for a safe import decision."""
    tournament_id = validate_positive_tournament_id(tournament_id)
    selected = _validate_category_ids(category_ids)

    tournament_response = (
        client.table("torneos")
        .select("id,nombre,slug,temporada,activo")
        .eq("id", tournament_id)
        .limit(2)
        .execute()
    )
    tournaments = list(tournament_response.data or [])
    if len(tournaments) > 1:
        raise RuntimeError(f"Tournament inventory returned duplicate id {tournament_id}")
    if tournaments:
        try:
            returned_tournament_id = validate_positive_tournament_id(
                tournaments[0].get("id"), source="tournament inventory id"
            )
        except ValueError as exc:
            raise RuntimeError(f"Malformed tournament inventory: {exc}") from exc
        if returned_tournament_id != tournament_id:
            raise RuntimeError("Tournament inventory returned a row outside the requested scope")

    fixtures = _read_complete_inventory(
        client,
        table="partidos",
        columns=(
            "id,torneo_id,categoria_id,local_id,visitante_id,fecha_id,estado,"
            "goles_local,goles_visitante"
        ),
        scope_query=lambda query: query.eq("torneo_id", tournament_id).in_(
            "categoria_id", list(selected)
        ),
        label="Fixture inventory",
        maximum_total=FIXTURE_INVENTORY_MAX_TOTAL,
    )
    fixture_ids: list[int] = []
    seen_fixture_ids: set[int] = set()
    for index, row in enumerate(fixtures, start=1):
        try:
            fixture_id = _inventory_positive_int(row.get("id"), "fixture id")
            row_tournament = _inventory_positive_int(
                row.get("torneo_id"), "fixture torneo_id"
            )
            row_category = _inventory_positive_int(
                row.get("categoria_id"), "fixture categoria_id"
            )
            state = _fixture_state(row.get("estado"), fixture_id)
            _validate_fixture_sides(
                row.get("local_id"),
                row.get("visitante_id"),
                state,
                fixture_id,
            )
            _inventory_positive_int(row.get("fecha_id"), "fixture fecha_id")
        except RuntimeError as exc:
            raise RuntimeError(f"Malformed fixture inventory row {index}: {exc}") from exc
        if row_tournament != tournament_id or row_category not in selected:
            raise RuntimeError("Fixture inventory returned a row outside the selected scope")
        if fixture_id in seen_fixture_ids:
            raise RuntimeError(f"Fixture inventory contains duplicate id {fixture_id}")
        seen_fixture_ids.add(fixture_id)
        fixture_ids.append(fixture_id)

    positions = _read_complete_inventory(
        client,
        table="posiciones",
        columns="id,torneo_id,categoria_id,club_id",
        scope_query=lambda query: query.eq("torneo_id", tournament_id).in_(
            "categoria_id", list(selected)
        ),
        label="Position inventory",
        maximum_total=POSITION_INVENTORY_MAX_TOTAL,
    )
    for index, row in enumerate(positions, start=1):
        try:
            _inventory_positive_int(row.get("id"), "position id")
            row_tournament = _inventory_positive_int(
                row.get("torneo_id"), "position torneo_id"
            )
            row_category = _inventory_positive_int(
                row.get("categoria_id"), "position categoria_id"
            )
            _inventory_positive_int(row.get("club_id"), "position club_id")
        except RuntimeError as exc:
            raise RuntimeError(f"Malformed position inventory row {index}: {exc}") from exc
        if row_tournament != tournament_id or row_category not in selected:
            raise RuntimeError("Position inventory returned a row outside the selected scope")

    lineups: list[Mapping[str, Any]] = []
    if fixture_ids:
        lineups = _read_complete_inventory(
            client,
            table="alineaciones",
            columns="id,partido_id",
            scope_query=lambda query: query.in_("partido_id", fixture_ids),
            label="Lineup inventory",
            maximum_total=LINEUP_INVENTORY_MAX_TOTAL,
        )
        for index, row in enumerate(lineups, start=1):
            try:
                _inventory_positive_int(row.get("id"), "lineup id")
                partido_id = _inventory_positive_int(
                    row.get("partido_id"), "lineup partido_id"
                )
            except RuntimeError as exc:
                raise RuntimeError(f"Malformed lineup inventory row {index}: {exc}") from exc
            if partido_id not in seen_fixture_ids:
                raise RuntimeError("Lineup inventory returned a row outside the selected fixture scope")

    return ExistingScope(
        tournament=tournaments[0] if tournaments else None,
        fixtures=tuple(fixtures),
        positions=tuple(positions),
        lineups=tuple(lineups),
    )


def _tournament_write(
    existing: Optional[Mapping[str, Any]],
    tournament_id: int,
    name: str,
    slug: str,
    season: int,
) -> TournamentWrite:
    values: dict[str, Any] = {
        "nombre": name,
        "slug": slug,
        "temporada": season,
    }
    if existing is None:
        return TournamentWrite(
            operation="insert",
            values={"id": tournament_id, **values, "activo": False},
        )
    return TournamentWrite(operation="update", values=values)


def build_import_plan(
    source_plan: SourcePlan,
    existing: ExistingScope,
    profile: CurrentFixtureSourceProfile,
    *,
    replace_existing: bool,
    tournament_name: Optional[str] = None,
    slug: Optional[str] = None,
) -> ImportPlan:
    """Combine a validated source with existing-state replacement policy."""
    name = normalize_space(tournament_name or profile.display_name)
    resolved_slug = normalize_space(slug or profile.slug)
    if not name:
        raise ValueError("Tournament name must not be empty")
    if re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", resolved_slug) is None:
        raise ValueError("Tournament slug must use lowercase letters, numbers, and hyphens")

    issues = list(source_plan.issues)
    for category in source_plan.categories:
        issues.extend(category.issues)
    if existing.fixtures and not replace_existing:
        issues.append(
            "Selected categories already contain partidos; use --replace-existing only for a safe replacement"
        )
    if replace_existing:
        for row in existing.fixtures:
            fixture_id = row.get("id")
            try:
                state = _fixture_state(row.get("estado"), int(fixture_id))
            except (RuntimeError, TypeError, ValueError) as exc:
                issues.append(str(exc))
                continue
            if (
                state not in REPLACEABLE_FIXTURE_STATES
                or row.get("goles_local") is not None
                or row.get("goles_visitante") is not None
            ):
                issues.append(
                    f"Existing fixture {fixture_id} contains played/result data and cannot be replaced"
                )
        if existing.positions:
            issues.append("Selected categories contain positions and cannot be replaced")
        if existing.lineups:
            issues.append("Selected fixtures contain lineups and cannot be replaced")

    category_ids = tuple(category.category_id for category in source_plan.categories)
    return ImportPlan(
        tournament_id=source_plan.tournament_id,
        profile_key=source_plan.profile_key,
        category_plans=source_plan.categories,
        tournament_write=_tournament_write(
            existing.tournament,
            source_plan.tournament_id,
            name,
            resolved_slug,
            profile.season,
        ),
        replace_existing=replace_existing,
        delete_category_ids=category_ids if replace_existing else (),
        existing_fixture_count=len(existing.fixtures),
        issues=tuple(issues),
    )


def render_source_report(context: OperationContext, source_plan: SourcePlan) -> str:
    lines = [
        f"Current fixture source: mode={context.mode} tournament_id={context.tournament_id}",
        f"Profile: {source_plan.profile_key}",
    ]
    for category in source_plan.categories:
        lines.append(
            f"  CATEGORY {category.category_key} id={category.category_id} "
            f"fixtures={len(category.fixtures)} issues={len(category.issues)}"
        )
        lines.extend(f"    ERROR: {issue}" for issue in category.issues)
    lines.extend(f"  ERROR: {issue}" for issue in source_plan.issues)
    return "\n".join(lines)


def render_report(context: OperationContext, plan: ImportPlan) -> str:
    """Render a deterministic import preview including sequential-write risk."""
    lines = [
        f"Current fixture import: mode={context.mode} tournament_id={context.tournament_id}",
        f"Profile: {plan.profile_key}",
        f"Categories: {', '.join(item.category_key for item in plan.category_plans)}",
        f"Validated fixture rows: {plan.fixture_count}",
        f"Existing selected fixtures: {plan.existing_fixture_count}",
        f"Replacement requested: {'yes' if plan.replace_existing else 'no'}",
        f"Tournament metadata action: {plan.tournament_write.operation}",
    ]
    for category in plan.category_plans:
        lines.append(
            f"  {'REPLACE' if category.category_id in plan.delete_category_ids else 'INSERT'} "
            f"category={category.category_key} id={category.category_id} rows={len(category.fixtures)}"
        )
    if plan.issues:
        lines.append(f"Blocking issues: {len(plan.issues)}")
        lines.extend(f"  ERROR: {issue}" for issue in plan.issues)
    else:
        lines.append("Blocking issues: 0")
    lines.append(
        "Execution risk: Supabase tournament/delete/insert calls are sequential and "
        "non-transactional; a write failure can leave a partial import."
    )
    return "\n".join(lines)


def execute_import_plan(client: Any, plan: ImportPlan) -> dict[str, int]:
    """Apply one fully validated plan with tournament/category-scoped fixture writes."""
    if not plan.valid:
        raise ValueError("Refusing to execute an invalid or empty current fixture import plan")

    counts = {"tournaments_inserted": 0, "tournaments_updated": 0, "categories_deleted": 0, "fixtures_inserted": 0}
    if plan.tournament_write.operation == "insert":
        client.table("torneos").insert(dict(plan.tournament_write.values)).execute()
        counts["tournaments_inserted"] = 1
    elif plan.tournament_write.operation == "update":
        (
            client.table("torneos")
            .update(dict(plan.tournament_write.values))
            .eq("id", plan.tournament_id)
            .execute()
        )
        counts["tournaments_updated"] = 1
    else:
        raise ValueError(f"Unsupported tournament write: {plan.tournament_write.operation}")

    delete_ids = set(plan.delete_category_ids)
    for category in plan.category_plans:
        if category.category_id in delete_ids:
            (
                client.table("partidos")
                .delete()
                .eq("torneo_id", plan.tournament_id)
                .eq("categoria_id", category.category_id)
                .execute()
            )
            counts["categories_deleted"] += 1
        rows = [dict(item.values) for item in category.fixtures]
        if not rows:
            raise ValueError(f"Refusing to insert an empty category plan: {category.category_key}")
        client.table("partidos").insert(rows).execute()
        counts["fixtures_inserted"] += len(rows)
    return counts


def parse_source_overrides(
    values: Sequence[str],
    profile: CurrentFixtureSourceProfile,
) -> dict[str, str]:
    overrides: dict[str, str] = {}
    for value in values:
        category, separator, source = value.partition("=")
        category = category.strip()
        source = source.strip()
        if not separator or category not in profile.category_sources or not source:
            raise ValueError(
                "--source must use CATEGORY=URL_OR_PATH for a category in the selected profile"
            )
        if category in overrides:
            raise ValueError(f"Duplicate --source override for category {category}")
        parsed = urlparse(source)
        if not Path(source).is_file() and parsed.scheme not in {"http", "https"}:
            raise ValueError(
                f"Source override for {category} is not a readable file or HTTP(S) URL: {source}"
            )
        overrides[category] = source
    return overrides


def selected_sources(
    profile: CurrentFixtureSourceProfile,
    categories: Sequence[str],
    source_overrides: Sequence[str],
) -> dict[str, str]:
    selected = list(dict.fromkeys(categories or profile.category_sources.keys()))
    unknown = sorted(set(selected) - set(profile.category_sources))
    if unknown:
        raise ValueError(
            f"Categories are not available in profile {profile.key}: {', '.join(unknown)}"
        )
    overrides = parse_source_overrides(source_overrides, profile)
    unselected = sorted(set(overrides) - set(selected))
    if unselected:
        raise ValueError(
            "Source override provided for unselected category: " + ", ".join(unselected)
        )
    return {
        category: overrides.get(category, profile.category_sources[category])
        for category in selected
    }


def _timeout_argument(value: str) -> float:
    try:
        timeout = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("--timeout must be a number") from exc
    if not MIN_TIMEOUT_SECONDS <= timeout <= MAX_TIMEOUT_SECONDS:
        raise argparse.ArgumentTypeError(
            f"--timeout must be between {MIN_TIMEOUT_SECONDS} and {MAX_TIMEOUT_SECONDS} seconds"
        )
    return timeout


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Preview or execute a profile-driven current fixture import.",
    )
    parser.add_argument(
        "--profile",
        required=True,
        choices=tuple(SOURCE_PROFILES),
        help="Required versioned current-fixture source profile.",
    )
    add_operation_arguments(parser, tournament_required=True)
    parser.add_argument(
        "--category",
        action="append",
        choices=PROFILE_CATEGORY_CHOICES,
        default=[],
        help="Category to import; repeat as needed (default: all categories in the profile).",
    )
    parser.add_argument(
        "--source",
        action="append",
        default=[],
        metavar="CATEGORY=URL_OR_PATH",
        help="Override one selected category source for local recovery or testing.",
    )
    parser.add_argument(
        "--torneo-nombre",
        default=None,
        help="Explicit tournament display-name override (default: profile metadata).",
    )
    parser.add_argument(
        "--slug",
        default=None,
        help="Explicit tournament slug override (default: profile metadata).",
    )
    parser.add_argument(
        "--replace-existing",
        action="store_true",
        help="Replace only selected safe tournament/category fixture scope; never append.",
    )
    parser.add_argument(
        "--timeout",
        type=_timeout_argument,
        default=30.0,
        help="HTTP timeout in seconds, between 0.1 and 120 (default: 30).",
    )
    return parser


def _database_client() -> Any:
    from config import supabase

    return supabase


def main(
    argv: Optional[Sequence[str]] = None,
    *,
    client_factory: Optional[Callable[[], Any]] = None,
    source_loader: Optional[Callable[[str, float], str]] = None,
    stdout: Optional[TextIO] = None,
    stderr: Optional[TextIO] = None,
) -> int:
    """Run current fixture import and return a process-compatible exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)
    output = stdout or sys.stdout
    error_output = stderr or sys.stderr
    try:
        load_backend_environment()
        context = operation_context_from_args(args)
        profile = get_source_profile(args.profile)
        validate_supported_format(profile)
        sources = selected_sources(profile, args.category, args.source)

        loader = source_loader or load_fixture_source
        category_plans: list[CategoryPlan] = []
        for category, source in sources.items():
            html = loader(source, args.timeout)
            rows = parse_profile_source(profile, category, html)
            category_plans.append(
                build_category_plan(rows, context.tournament_id, category)
            )
        source_plan = validate_source_plan(
            category_plans,
            context.tournament_id,
            profile.key,
            tuple(sources),
        )
        if not source_plan.valid:
            print(render_source_report(context, source_plan), file=output)
            return 1

        client = (client_factory or _database_client)()
        existing = inspect_existing_scope(
            client,
            context.tournament_id,
            [category.category_id for category in source_plan.categories],
        )
        plan = build_import_plan(
            source_plan,
            existing,
            profile,
            replace_existing=args.replace_existing,
            tournament_name=args.torneo_nombre,
            slug=args.slug,
        )
        print(render_report(context, plan), file=output)
        if not plan.valid:
            return 1
        if not context.execute:
            print("Dry run only; no database mutations were attempted.", file=output)
            return 0

        counts = execute_import_plan(client, plan)
        print(
            "Applied current fixture import: "
            f"tournaments_inserted={counts['tournaments_inserted']} "
            f"tournaments_updated={counts['tournaments_updated']} "
            f"categories_deleted={counts['categories_deleted']} "
            f"fixtures_inserted={counts['fixtures_inserted']}",
            file=output,
        )
        return 0
    except Exception as exc:
        print(f"Current fixture import failed: {exc}", file=error_output)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
