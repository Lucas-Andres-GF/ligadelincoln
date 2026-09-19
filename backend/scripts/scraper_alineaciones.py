# -*- coding: utf-8 -*-
"""Safe, tournament-scoped Primera lineup replacement operation."""

from __future__ import annotations

import argparse
import re
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Optional, Sequence, TextIO
from urllib.parse import urlparse
from urllib.request import urlopen

from bs4 import BeautifulSoup
from bs4.element import Tag

from operation_common import (
    OperationContext,
    add_operation_arguments,
    load_backend_environment,
    operation_context_from_args,
    validate_positive_tournament_id,
)


DEFAULT_SOURCE_URL = "https://www.ligaamateurdedeportes.com.ar/alineaciones.html"
CATEGORY_KEY = "primera"
FIXTURE_INVENTORY_LIMIT = 500
MIN_TIMEOUT_SECONDS = 0.1
MAX_TIMEOUT_SECONDS = 120.0

ROUND_NAMES = {
    "PRIMERA": 1,
    "SEGUNDA": 2,
    "TERCERA": 3,
    "CUARTA": 4,
    "QUINTA": 5,
    "SEXTA": 6,
    "SEPTIMA": 7,
    "OCTAVA": 8,
    "NOVENA": 9,
    "DECIMA": 10,
    "UNDECIMA": 11,
    "DUODECIMA": 12,
    "DECIMOTERCERA": 13,
    "DECIMOCUARTA": 14,
    "DECIMOQUINTA": 15,
    "DECIMOSEXTA": 16,
    "DECIMOSEPTIMA": 17,
    "DECIMOCTAVA": 18,
    "DECIMONOVENA": 19,
    "VIGESIMA": 20,
}
ROUND_TOKEN = "|".join((*ROUND_NAMES, r"\d+"))
ROUND_PATTERNS = (
    re.compile(rf"\bFECHA\s*:?[\s-]*({ROUND_TOKEN})\b", re.IGNORECASE),
    re.compile(rf"\b({ROUND_TOKEN})\s+FECHA\b", re.IGNORECASE),
)
SCORE_PATTERN = re.compile(r"^\s*(\d+)\s*-\s*(\d+)\s*$")


class LineupParseError(ValueError):
    """Raised when the supported official Primera lineup structure is incomplete."""


@dataclass(frozen=True)
class OfficialPlayer:
    team_id: Optional[int]
    number: int
    name: str
    goals: int = 0
    red_card: bool = False


@dataclass(frozen=True)
class OfficialMatch:
    source_row: int
    round_id: int
    local: str
    local_id: Optional[int]
    visitor: str
    visitor_id: Optional[int]
    final_local_goals: int
    final_visitor_goals: int
    local_players: tuple[OfficialPlayer, ...]
    visitor_players: tuple[OfficialPlayer, ...]
    local_coach: Optional[str]
    visitor_coach: Optional[str]
    referee: Optional[str]


@dataclass(frozen=True)
class FixtureRecord:
    id: int
    tournament_id: int
    category_id: int
    local_id: int
    visitor_id: int
    round_id: int
    state: str

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "FixtureRecord":
        return cls(
            id=_positive_int(value.get("id"), "fixture id"),
            tournament_id=_positive_int(value.get("torneo_id"), "fixture torneo_id"),
            category_id=_positive_int(value.get("categoria_id"), "fixture categoria_id"),
            local_id=_positive_int(value.get("local_id"), "fixture local_id"),
            visitor_id=_positive_int(value.get("visitante_id"), "fixture visitante_id"),
            round_id=_positive_int(value.get("fecha_id"), "fixture fecha_id"),
            state=_fixture_state(value.get("estado")),
        )


@dataclass(frozen=True)
class ReplacementEntry:
    fixture_id: int
    match: OfficialMatch
    lineup_rows: tuple[Mapping[str, Any], ...]
    metadata: Mapping[str, str]


@dataclass(frozen=True)
class ReplacementPlan:
    tournament_id: int
    category_id: int
    round_id: int
    entries: tuple[ReplacementEntry, ...]
    issues: tuple[str, ...]

    @property
    def valid(self) -> bool:
        return bool(self.entries) and not self.issues


def _positive_int(value: Any, label: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{label} must be a positive integer")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be a positive integer") from exc
    if parsed <= 0:
        raise ValueError(f"{label} must be a positive integer")
    return parsed


def _fixture_state(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("fixture estado must be a non-empty string")
    return identity_text(value).lower()


def repair_encoding(value: str) -> str:
    """Repair common UTF-8-as-Latin-1/Windows-1252 mojibake and whitespace."""
    text = value or ""
    if "Ã" in text or "Â" in text:
        for encoding in ("cp1252", "latin1"):
            try:
                text = text.encode(encoding).decode("utf-8")
                break
            except (UnicodeEncodeError, UnicodeDecodeError):
                continue
    return " ".join(text.replace("\xa0", " ").split())


def normalize_text(value: str) -> str:
    return repair_encoding(value).strip().upper()


def identity_text(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", repair_encoding(value))
    without_accents = "".join(char for char in decomposed if not unicodedata.combining(char))
    return " ".join(re.sub(r"[^A-Za-z0-9]+", " ", without_accents).upper().split())


def _identity_configuration() -> tuple[dict[str, int], int]:
    # Numeric identities remain owned by config; the import is deferred so importing
    # this module and displaying --help do not load environment or DB state.
    from config import CATEGORIAS, MAPEO_CLUBES

    category_id = CATEGORIAS.get(CATEGORY_KEY)
    if category_id is None:
        raise RuntimeError("The configured Primera category identity is missing")

    clubs: dict[str, int] = {}
    for source_name, club_id in MAPEO_CLUBES.items():
        key = identity_text(source_name)
        parsed_id = _positive_int(club_id, f"club identity for {source_name}")
        previous = clubs.get(key)
        if previous is not None and previous != parsed_id:
            raise RuntimeError(f"Conflicting authoritative club identity for {source_name!r}")
        clubs[key] = parsed_id
    return clubs, _positive_int(category_id, "Primera category ID")


def resolve_club_id(name: str) -> Optional[int]:
    clubs, _ = _identity_configuration()
    return clubs.get(identity_text(name))


def _parse_round(text: str) -> int:
    normalized = identity_text(text)
    for pattern in ROUND_PATTERNS:
        match = pattern.search(normalized)
        if match is None:
            continue
        token = identity_text(match.group(1))
        if token.isdigit():
            return _positive_int(token, "official round")
        if token in ROUND_NAMES:
            return ROUND_NAMES[token]
    raise LineupParseError("Official lineup round marker was not found")


def _cell_text(cell: Tag) -> str:
    return normalize_text(cell.get_text(" ", strip=True))


def _style_classes(soup: BeautifulSoup) -> dict[str, str]:
    styles: dict[str, str] = {}
    for style_tag in soup.find_all("style"):
        for match in re.finditer(
            r"\.([A-Za-z0-9_-]+)\s*\{([^}]*)\}", style_tag.get_text() or "", re.DOTALL
        ):
            styles[match.group(1)] = f"{styles.get(match.group(1), '')};{match.group(2)}"
    return styles


def _background_values(css: str) -> list[str]:
    return [
        match.group(2).replace("!important", "").strip().lower()
        for match in re.finditer(
            r"(?<![-\w])(background(?:-color)?)\s*:\s*([^;]+)", css or "", re.IGNORECASE
        )
    ]


def _is_red(value: str) -> bool:
    compact = value.lower().replace(" ", "")
    if re.search(r"(^|[^a-z])red([^a-z]|$)", compact) or "#ff0000" in compact or "#f00" in compact:
        return True
    rgb = re.search(r"rgba?\((\d+),(\d+),(\d+)(?:,[^)]+)?\)", compact)
    if rgb is None:
        return False
    red, green, blue = (int(rgb.group(index)) for index in range(1, 4))
    return red >= 240 and green <= 20 and blue <= 20


def cell_has_red_background(cell: Tag, class_styles: Mapping[str, str]) -> bool:
    inline = _background_values(str(cell.get("style", "")))
    if inline:
        return any(_is_red(value) for value in inline)
    bgcolor = str(cell.get("bgcolor", "")).strip()
    if bgcolor:
        return _is_red(bgcolor)
    return any(
        _is_red(value)
        for class_name in cell.get("class", [])
        for value in _background_values(class_styles.get(str(class_name), ""))
    )


def _match_header(cells: Sequence[Tag]) -> Optional[tuple[str, int, int, str]]:
    if len(cells) < 4:
        return None
    local = _cell_text(cells[0])
    visitor = _cell_text(cells[3])
    local_score = _cell_text(cells[1])
    visitor_score = _cell_text(cells[2])
    if not local or not visitor or not local_score.isdigit() or not visitor_score.isdigit():
        return None
    return local, int(local_score), int(visitor_score), visitor


def _player_matches(scorer_name: str, player_name: str) -> bool:
    scorer = identity_text(scorer_name)
    player = identity_text(player_name)
    if not scorer or not player:
        return False
    if scorer == player:
        return True
    scorer_words = [word for word in scorer.split() if len(word) >= 3]
    player_words = [word for word in player.split() if len(word) >= 3]
    matches = sum(
        1
        for scorer_word in scorer_words
        if any(scorer_word in player_word or player_word in scorer_word for player_word in player_words)
    )
    return len(scorer_words) >= 2 and matches >= 2


def _goal_counts(
    rows: Sequence[tuple[int, Sequence[Tag]]],
    local_players: Sequence[OfficialPlayer],
    visitor_players: Sequence[OfficialPlayer],
    final_score: tuple[int, int],
) -> tuple[dict[int, int], dict[int, int]]:
    local_goals: dict[int, int] = {}
    visitor_goals: dict[int, int] = {}
    previous = (0, 0)
    for source_row, cells in rows:
        if len(cells) <= 7:
            continue
        scorer = _cell_text(cells[7])
        score_text = repair_encoding(cells[8].get_text(" ", strip=True)) if len(cells) > 8 else ""
        score_match = SCORE_PATTERN.fullmatch(score_text)
        if scorer and score_match is None:
            raise LineupParseError(
                f"Goal event at source row {source_row} has a scorer but no valid cumulative score"
            )
        if score_match is None:
            continue

        current = (int(score_match.group(1)), int(score_match.group(2)))
        if current == previous:
            if scorer:
                raise LineupParseError(
                    f"Goal event at source row {source_row} has a scorer without score progression"
                )
            continue
        if not scorer:
            raise LineupParseError(
                f"Goal event at source row {source_row} changes the score but has no scorer"
            )

        local_delta = current[0] - previous[0]
        visitor_delta = current[1] - previous[1]
        if (local_delta, visitor_delta) not in {(1, 0), (0, 1)}:
            raise LineupParseError(f"Malformed scoring sequence at source row {source_row}")
        scoring_players, target = (
            (local_players, local_goals)
            if local_delta == 1
            else (visitor_players, visitor_goals)
        )
        matches = [player for player in scoring_players if _player_matches(scorer, player.name)]
        if len(matches) != 1:
            raise LineupParseError(
                f"Goal scorer {scorer!r} at source row {source_row} did not match one player"
            )
        target[matches[0].number] = target.get(matches[0].number, 0) + 1
        previous = current

    attributed_score = (sum(local_goals.values()), sum(visitor_goals.values()))
    if previous != final_score or attributed_score != final_score:
        raise LineupParseError(
            "Final score/event mismatch: "
            f"header={final_score[0]}-{final_score[1]} "
            f"events={attributed_score[0]}-{attributed_score[1]}"
        )
    return local_goals, visitor_goals


def _parse_match_block(
    rows: Sequence[tuple[int, Sequence[Tag]]],
    round_id: int,
    class_styles: Mapping[str, str],
) -> OfficialMatch:
    source_row, header_cells = rows[0]
    header = _match_header(header_cells)
    if header is None:
        raise LineupParseError(f"Malformed match header at source row {source_row}")
    local, final_local_goals, final_visitor_goals, visitor = header
    local_id = resolve_club_id(local)
    visitor_id = resolve_club_id(visitor)
    local_players: list[OfficialPlayer] = []
    visitor_players: list[OfficialPlayer] = []
    coaches: list[str] = []
    referee: Optional[str] = None

    for row_number, cells in rows:
        texts = [_cell_text(cell) for cell in cells]
        for index, text in enumerate(texts):
            normalized_label = identity_text(text)
            if normalized_label.replace(" ", "") == "DT" and index + 1 < len(texts):
                coach = texts[index + 1]
                if coach and coach != "0":
                    coaches.append(coach)
            if "ARBITRO" in normalized_label and index + 1 < len(texts):
                candidate = texts[index + 1]
                if candidate and candidate != "0":
                    referee = candidate

        if len(cells) < 5:
            continue
        local_number = texts[0]
        visitor_number = texts[3]
        if local_number.isdigit():
            name = texts[1]
            if not name or name == "0":
                raise LineupParseError(f"Malformed local player at source row {row_number}")
            local_players.append(
                OfficialPlayer(
                    team_id=local_id,
                    number=int(local_number),
                    name=name,
                    red_card=len(cells) > 2 and cell_has_red_background(cells[2], class_styles),
                )
            )
        if visitor_number.isdigit():
            name = texts[4]
            if not name or name == "0":
                raise LineupParseError(f"Malformed visiting player at source row {row_number}")
            visitor_players.append(
                OfficialPlayer(
                    team_id=visitor_id,
                    number=int(visitor_number),
                    name=name,
                    red_card=len(cells) > 5 and cell_has_red_background(cells[5], class_styles),
                )
            )

    if not local_players or not visitor_players:
        raise LineupParseError(
            f"Incomplete match block at source row {source_row}: both teams require players"
        )

    local_goals, visitor_goals = _goal_counts(
        rows,
        local_players,
        visitor_players,
        (final_local_goals, final_visitor_goals),
    )
    local_players = [
        OfficialPlayer(
            team_id=player.team_id,
            number=player.number,
            name=player.name,
            goals=local_goals.get(player.number, 0),
            red_card=player.red_card,
        )
        for player in local_players
    ]
    visitor_players = [
        OfficialPlayer(
            team_id=player.team_id,
            number=player.number,
            name=player.name,
            goals=visitor_goals.get(player.number, 0),
            red_card=player.red_card,
        )
        for player in visitor_players
    ]
    return OfficialMatch(
        source_row=source_row,
        round_id=round_id,
        local=local,
        local_id=local_id,
        visitor=visitor,
        visitor_id=visitor_id,
        final_local_goals=final_local_goals,
        final_visitor_goals=final_visitor_goals,
        local_players=tuple(local_players),
        visitor_players=tuple(visitor_players),
        local_coach=coaches[0] if coaches else None,
        visitor_coach=coaches[1] if len(coaches) > 1 else None,
        referee=referee,
    )


def parse_lineups_html(html: str) -> list[OfficialMatch]:
    """Parse the one supported official Primera lineup table."""
    soup = BeautifulSoup(html, "html.parser")
    round_id = _parse_round(soup.get_text(" ", strip=True))
    candidate_tables: list[tuple[Tag, list[tuple[int, Sequence[Tag]]], list[int]]] = []
    for table in soup.find_all("table"):
        rows: list[tuple[int, Sequence[Tag]]] = []
        starts: list[int] = []
        for source_row, row in enumerate(table.find_all("tr"), start=1):
            cells = row.find_all("td", recursive=False)
            rows.append((source_row, cells))
            if _match_header(cells) is not None:
                starts.append(len(rows) - 1)
        if starts:
            candidate_tables.append((table, rows, starts))
    if len(candidate_tables) != 1:
        raise LineupParseError(
            f"Expected one official lineup table, found {len(candidate_tables)}"
        )

    _, rows, starts = candidate_tables[0]
    class_styles = _style_classes(soup)
    matches: list[OfficialMatch] = []
    for position, start in enumerate(starts):
        end = starts[position + 1] if position + 1 < len(starts) else len(rows)
        matches.append(_parse_match_block(rows[start:end], round_id, class_styles))
    return matches


def load_local_html(path: Path) -> str:
    """Load a local recovery source without network access."""
    payload = path.read_bytes()
    try:
        return payload.decode("utf-8")
    except UnicodeDecodeError:
        return payload.decode("cp1252")


def fetch_remote_html(source: str, timeout: float) -> str:
    """Fetch an operator-selected HTTP(S) source with a bounded timeout."""
    with urlopen(source, timeout=timeout) as response:  # noqa: S310 - operator-selected URL
        payload = response.read()
        encoding = response.headers.get_content_charset() or "iso-8859-1"
    return payload.decode(encoding)


def load_lineup_source(source: str = DEFAULT_SOURCE_URL, timeout: float = 30.0) -> str:
    """Load lineup HTML from a local path or the official HTTP(S) source."""
    if not MIN_TIMEOUT_SECONDS <= timeout <= MAX_TIMEOUT_SECONDS:
        raise ValueError(
            f"timeout must be between {MIN_TIMEOUT_SECONDS} and {MAX_TIMEOUT_SECONDS} seconds"
        )
    local_path = Path(source)
    if local_path.is_file():
        return load_local_html(local_path)
    parsed = urlparse(source)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError(f"Lineup source is not a readable file or HTTP(S) URL: {source}")
    return fetch_remote_html(source, timeout)


def read_fixture_inventory(
    client: Any,
    tournament_id: int,
    round_id: int,
    category_id: int,
) -> list[FixtureRecord]:
    """Read one bounded fixture snapshot for the selected tournament/Primera/round."""
    tournament_id = validate_positive_tournament_id(tournament_id)
    round_id = validate_positive_tournament_id(round_id, source="round ID")
    category_id = validate_positive_tournament_id(category_id, source="category ID")
    response = (
        client.table("partidos")
        .select("id,torneo_id,categoria_id,local_id,visitante_id,fecha_id,estado")
        .eq("torneo_id", tournament_id)
        .eq("categoria_id", category_id)
        .eq("fecha_id", round_id)
        .limit(FIXTURE_INVENTORY_LIMIT)
        .execute()
    )
    data = list(response.data or [])
    if len(data) >= FIXTURE_INVENTORY_LIMIT:
        raise RuntimeError(
            f"Fixture inventory reached the safety limit of {FIXTURE_INVENTORY_LIMIT}; "
            "refusing a possibly partial replacement"
        )
    fixtures = [FixtureRecord.from_mapping(item) for item in data]
    seen: set[int] = set()
    for fixture in fixtures:
        if (
            fixture.tournament_id != tournament_id
            or fixture.category_id != category_id
            or fixture.round_id != round_id
        ):
            raise RuntimeError("Fixture inventory returned a row outside the requested scope")
        if fixture.id in seen:
            raise RuntimeError(f"Fixture inventory contains duplicate id {fixture.id}")
        seen.add(fixture.id)
    return fixtures


def _match_label(match: OfficialMatch) -> str:
    return f"row {match.source_row}: round={match.round_id} {match.local} vs {match.visitor}"


def _validate_player(player: OfficialPlayer, expected_team_id: Optional[int], label: str) -> list[str]:
    issues: list[str] = []
    if player.team_id != expected_team_id or expected_team_id is None:
        issues.append(f"Team mismatch for {label}")
    if isinstance(player.number, bool) or not isinstance(player.number, int) or player.number <= 0:
        issues.append(f"Malformed player number for {label}")
    if not player.name.strip() or player.name == "0" or len(player.name) > 100:
        issues.append(f"Malformed player name for {label}")
    if isinstance(player.goals, bool) or not isinstance(player.goals, int) or player.goals < 0:
        issues.append(f"Malformed goal marker for {label}")
    if not isinstance(player.red_card, bool):
        issues.append(f"Malformed red-card marker for {label}")
    return issues


def build_replacement_plan(
    matches: Iterable[OfficialMatch],
    fixtures: Iterable[FixtureRecord],
    tournament_id: int,
    round_id: int,
    category_id: int,
) -> ReplacementPlan:
    """Match and validate the complete replacement before any remote mutation."""
    tournament_id = validate_positive_tournament_id(tournament_id)
    round_id = validate_positive_tournament_id(round_id, source="round ID")
    category_id = validate_positive_tournament_id(category_id, source="category ID")
    official_matches = list(matches)
    scoped_fixtures = [
        fixture
        for fixture in fixtures
        if fixture.tournament_id == tournament_id
        and fixture.category_id == category_id
        and fixture.round_id == round_id
    ]
    entries: list[ReplacementEntry] = []
    issues: list[str] = []
    claimed_targets: set[int] = set()
    lineup_identities: set[tuple[int, int, int]] = set()

    if not official_matches:
        issues.append("No official lineup matches were parsed")

    for match in official_matches:
        label = _match_label(match)
        match_issues: list[str] = []
        if match.round_id != round_id:
            match_issues.append(f"Wrong round at {label}; selected round is {round_id}")
        if match.local_id is None:
            match_issues.append(f"Unknown local club at {label}")
        if match.visitor_id is None:
            match_issues.append(f"Unknown visiting club at {label}")
        if match.local_id is not None and match.local_id == match.visitor_id:
            match_issues.append(f"Same local and visiting club at {label}")
        if not match.local_players or not match.visitor_players:
            match_issues.append(f"Incomplete match block at {label}")
        for side, players, expected_team in (
            ("local", match.local_players, match.local_id),
            ("visitor", match.visitor_players, match.visitor_id),
        ):
            for player in players:
                match_issues.extend(
                    _validate_player(player, expected_team, f"{label} {side} #{player.number}")
                )
        if match_issues:
            issues.extend(match_issues)
            continue

        targets = [
            fixture
            for fixture in scoped_fixtures
            if fixture.local_id == match.local_id and fixture.visitor_id == match.visitor_id
        ]
        if not targets:
            issues.append(f"Missing fixture target for {label}")
            continue
        if len(targets) > 1:
            issues.append(f"Ambiguous fixture target ({len(targets)} matches) for {label}")
            continue
        target = targets[0]
        if target.id in claimed_targets:
            issues.append(f"Fixture target {target.id} was matched more than once ({label})")
            continue
        claimed_targets.add(target.id)

        rows: list[Mapping[str, Any]] = []
        duplicate_found = False
        for player in (*match.local_players, *match.visitor_players):
            identity = (target.id, int(player.team_id), player.number)
            if identity in lineup_identities:
                issues.append(
                    "Duplicate lineup identity "
                    f"(partido_id={identity[0]}, equipo_id={identity[1]}, numero={identity[2]})"
                )
                duplicate_found = True
                continue
            lineup_identities.add(identity)
            rows.append(
                {
                    "categoria_id": category_id,
                    "partido_id": target.id,
                    "equipo_id": player.team_id,
                    "numero": player.number,
                    "nombre": player.name,
                    "es_titular": player.number <= 11,
                    "tiempo": "PT",
                    "goleo": player.goals,
                    "roja": player.red_card,
                    "fecha_id": round_id,
                }
            )
        if duplicate_found:
            continue

        metadata = {
            key: value
            for key, value in (
                ("dt_local", match.local_coach),
                ("dt_visitante", match.visitor_coach),
                ("arbitro", match.referee),
            )
            if value
        }
        if any(len(value) > 100 for value in metadata.values()):
            issues.append(f"Malformed match metadata at {label}")
            continue
        entries.append(
            ReplacementEntry(
                fixture_id=target.id,
                match=match,
                lineup_rows=tuple(rows),
                metadata=metadata,
            )
        )

    for fixture in scoped_fixtures:
        if fixture.state == "jugado" and fixture.id not in claimed_targets:
            issues.append(
                "Played fixture omitted from official lineup source: "
                f"fixture={fixture.id} local_id={fixture.local_id} visitor_id={fixture.visitor_id}"
            )

    return ReplacementPlan(
        tournament_id=tournament_id,
        category_id=category_id,
        round_id=round_id,
        entries=tuple(entries),
        issues=tuple(issues),
    )


def render_report(context: OperationContext, plan: ReplacementPlan) -> str:
    """Render the full replacement preview and its non-transactional risk."""
    lines = [
        f"Lineup operation: mode={context.mode} tournament_id={context.tournament_id}",
        f"Supported category: Primera (category_id={plan.category_id})",
        f"Selected round: {plan.round_id}",
        f"Planned fixture replacements: {len(plan.entries)}",
        f"Planned lineup inserts: {sum(len(entry.lineup_rows) for entry in plan.entries)}",
    ]
    for entry in plan.entries:
        lines.append(
            f"  REPLACE fixture={entry.fixture_id}: {entry.match.local} vs {entry.match.visitor} "
            f"rows={len(entry.lineup_rows)} metadata={','.join(entry.metadata) or '-'}"
        )
    if plan.issues:
        lines.append(f"Blocking issues: {len(plan.issues)}")
        lines.extend(f"  ERROR: {issue}" for issue in plan.issues)
    else:
        lines.append("Blocking issues: 0")
    lines.append(
        "Execution risk: Supabase delete/insert/update calls are sequential and non-transactional; "
        "a write failure can leave a partial replacement."
    )
    return "\n".join(lines)


def execute_replacement_plan(client: Any, plan: ReplacementPlan) -> dict[str, int]:
    """Apply only a completely validated plan using narrow defensive filters."""
    if not plan.valid:
        raise ValueError("Refusing to execute an invalid or empty lineup replacement plan")

    counts = {"fixtures_replaced": 0, "lineups_inserted": 0, "metadata_updated": 0}
    for entry in plan.entries:
        client.table("alineaciones").delete().eq("partido_id", entry.fixture_id).execute()
        client.table("alineaciones").insert([dict(row) for row in entry.lineup_rows]).execute()
        counts["lineups_inserted"] += len(entry.lineup_rows)
        if entry.metadata:
            (
                client.table("partidos")
                .update(dict(entry.metadata))
                .eq("id", entry.fixture_id)
                .eq("torneo_id", plan.tournament_id)
                .execute()
            )
            counts["metadata_updated"] += 1
        counts["fixtures_replaced"] += 1
    return counts


def _round_argument(value: str) -> int:
    try:
        return validate_positive_tournament_id(value, source="--fecha")
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


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
        description="Preview or apply a tournament-scoped Primera lineup replacement.",
    )
    add_operation_arguments(parser)
    parser.add_argument(
        "--fecha",
        type=_round_argument,
        required=True,
        help="Positive round ID to replace; required explicitly.",
    )
    parser.add_argument(
        "--source",
        default=DEFAULT_SOURCE_URL,
        help="Official lineup URL or a local HTML recovery file.",
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
    """Run lineup replacement and return a process-compatible exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)
    output = stdout or sys.stdout
    error_output = stderr or sys.stderr
    try:
        load_backend_environment()
        context = operation_context_from_args(args)
        html = (source_loader or load_lineup_source)(args.source, args.timeout)
        matches = parse_lineups_html(html)
        _, category_id = _identity_configuration()
        client = (client_factory or _database_client)()
        fixtures = read_fixture_inventory(
            client,
            context.tournament_id,
            args.fecha,
            category_id,
        )
        plan = build_replacement_plan(
            matches,
            fixtures,
            context.tournament_id,
            args.fecha,
            category_id,
        )
        print(render_report(context, plan), file=output)
        if not plan.valid:
            return 1
        if not context.execute:
            print("Dry run only; no database mutations were attempted.", file=output)
            return 0

        counts = execute_replacement_plan(client, plan)
        print(
            "Applied replacement: "
            f"fixtures={counts['fixtures_replaced']} "
            f"lineups={counts['lineups_inserted']} "
            f"metadata_updates={counts['metadata_updated']}",
            file=output,
        )
        return 0
    except Exception as exc:
        print(f"Lineup operation failed: {exc}", file=error_output)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
