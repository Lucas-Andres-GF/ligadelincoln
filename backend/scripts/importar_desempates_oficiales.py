# -*- coding: utf-8 -*-
"""Preview or import an official two-leg championship decider.

The command is dry-run-first and writes only to ``partidos_definicion`` when
``--execute`` is explicit. The supported source shape is anchored to the
official ``ENCUENTROS FINALES POR DESEMPATE`` section and tolerates nested
wrapper tables from exported HTML.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, Sequence, TextIO
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request, urlopen

from operation_common import (
    OperationContext,
    add_operation_arguments,
    load_backend_environment,
    operation_context_from_args,
    read_exact_paginated,
    validate_positive_tournament_id,
)


SERIES_NAME = "Desempate por el campeonato"
SECTION_MARKER = "ENCUENTROS FINALES POR DESEMPATE"
USER_AGENT = "liga-lincoln-decider-importer/1.0"
MIN_TIMEOUT_SECONDS = 0.1
MAX_TIMEOUT_SECONDS = 120.0
INVENTORY_PAGE_SIZE = 100
INVENTORY_MAX_TOTAL = 100
SOURCE_IDENTITY_ALIASES = {
    "C A PINTENSE": "CA PINTENSE",
}
PAYLOAD_FIELDS = (
    "torneo_id",
    "categoria_id",
    "local_id",
    "visitante_id",
    "campeon_id",
    "serie",
    "instancia",
    "orden",
    "goles_local",
    "goles_visitante",
    "dia",
    "cancha",
    "fuente_url",
)


class DeciderSourceError(ValueError):
    """Raised when an official decider section is incomplete or inconsistent."""


@dataclass(frozen=True)
class OfficialLeg:
    instance: str
    date: str
    local_name: str
    visitor_name: str
    local_id: int
    visitor_id: int
    local_goals: int
    visitor_goals: int
    ground: str


@dataclass(frozen=True)
class DeciderSeries:
    source_url: str
    legs: tuple[OfficialLeg, OfficialLeg]
    champion_name: str
    champion_id: int
    aggregate: tuple[int, int]


@dataclass(frozen=True)
class ImportPlan:
    payloads: tuple[dict[str, Any], ...]
    action: str
    issues: tuple[str, ...]

    @property
    def valid(self) -> bool:
        return self.action in {"insert", "noop", "replace"} and not self.issues


class _TableRowParser(HTMLParser):
    """Extract rows while recovering useful nested-table rows independently."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[list[str]] = []
        self._row: Optional[list[str]] = None
        self._cell: Optional[list[str]] = None

    def handle_starttag(
        self, tag: str, attrs: Sequence[tuple[str, Optional[str]]]
    ) -> None:
        del attrs
        tag = tag.lower()
        if tag == "tr":
            if self._row is not None:
                self._finish_row()
            self._row = []
        elif tag in {"td", "th"} and self._row is not None:
            if self._cell is not None:
                self._finish_cell()
            self._cell = []
        elif tag == "br" and self._cell is not None:
            self._cell.append(" ")

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"td", "th"} and self._cell is not None:
            self._finish_cell()
        elif tag == "tr" and self._row is not None:
            self._finish_row()

    def close(self) -> None:
        super().close()
        if self._cell is not None:
            self._finish_cell()
        if self._row is not None:
            self._finish_row()

    def _finish_cell(self) -> None:
        if self._row is not None and self._cell is not None:
            self._row.append(normalize_space("".join(self._cell)))
        self._cell = None

    def _finish_row(self) -> None:
        if self._cell is not None:
            self._finish_cell()
        if self._row is not None and any(self._row):
            self.rows.append(self._row)
        self._row = None


def normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace("\xa0", " ")).strip()


def identity_text(value: str) -> str:
    """Return stable case/accent-insensitive identity text."""
    repaired = normalize_space(value).replace("Ã‘", "Ñ").replace("Ã±", "ñ")
    decomposed = unicodedata.normalize("NFKD", repaired)
    ascii_like = "".join(char for char in decomposed if not unicodedata.combining(char))
    return normalize_space(re.sub(r"[^A-Za-z0-9]+", " ", ascii_like).upper())


def canonical_source(source: str) -> str:
    """Canonicalize an HTTP(S) source or a readable local recovery path."""
    path = Path(source)
    if path.is_file():
        return path.resolve().as_uri()
    parsed = urlsplit(source)
    if parsed.scheme.lower() == "file" and parsed.path:
        return urlunsplit(("file", parsed.netloc, parsed.path, "", ""))
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"Source is not a readable file or HTTP(S) URL: {source}")
    return urlunsplit(
        (parsed.scheme.lower(), parsed.netloc.lower(), parsed.path or "/", parsed.query, "")
    )


def decode_official_html(raw: bytes) -> str:
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw.decode("utf-8-sig")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("cp1252")


def load_decider_source(source: str, timeout: float = 30.0) -> str:
    """Load a local or HTTP(S) official source through a bounded timeout."""
    if not MIN_TIMEOUT_SECONDS <= timeout <= MAX_TIMEOUT_SECONDS:
        raise ValueError(
            f"timeout must be between {MIN_TIMEOUT_SECONDS} and {MAX_TIMEOUT_SECONDS} seconds"
        )
    path = Path(source)
    if path.is_file():
        return decode_official_html(path.read_bytes())
    canonical = canonical_source(source)
    request = Request(canonical, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=timeout) as response:  # noqa: S310 - operator source URL
        return decode_official_html(response.read())


def _extract_rows(html: str) -> list[list[str]]:
    parser = _TableRowParser()
    try:
        parser.feed(html)
        parser.close()
    except Exception as exc:
        raise DeciderSourceError(f"Malformed official HTML: {exc}") from exc
    if not parser.rows:
        raise DeciderSourceError("Official source contains no table rows")
    return parser.rows


def _row_identity(row: Sequence[str]) -> str:
    return identity_text(" | ".join(cell for cell in row if normalize_space(cell)))


def _parse_date(block: Sequence[Sequence[str]], instance: str) -> str:
    matches: list[str] = []
    for row in block:
        for cell in row:
            match = re.search(r"\b(\d{1,2})/(\d{1,2})/(\d{2}|\d{4})\b", cell)
            if match is None:
                continue
            day, month, year = match.groups()
            full_year = int(year) + 2000 if len(year) == 2 else int(year)
            try:
                parsed = datetime(full_year, int(month), int(day)).date().isoformat()
            except ValueError as exc:
                raise DeciderSourceError(
                    f"Malformed {instance} date: {match.group(0)}"
                ) from exc
            matches.append(parsed)
    if len(set(matches)) != 1:
        raise DeciderSourceError(
            f"{instance} must contain exactly one unambiguous official date"
        )
    return matches[0]


def _parse_ground(block: Sequence[Sequence[str]], instance: str) -> str:
    grounds: list[str] = []
    for row in block:
        row_identities = {identity_text(cell) for cell in row}
        is_match_header = {"LOCAL", "VISITANTE"} <= row_identities
        for index, cell in enumerate(row):
            match = re.match(r"\s*CANCHA\s*:\s*(.+)\s*$", cell, re.IGNORECASE)
            if match is not None:
                grounds.append(normalize_space(match.group(1)))
                continue
            if (
                not is_match_header
                and identity_text(cell) == "CANCHA"
                and index + 1 < len(row)
            ):
                value = normalize_space(row[index + 1])
                if value:
                    grounds.append(value)

    tabular_headers = [
        (index, row.index("CANCHA"))
        for index, row in enumerate(
            [[identity_text(cell) for cell in source_row] for source_row in block]
        )
        if "LOCAL" in row and "VISITANTE" in row and row.count("CANCHA") == 1
    ]
    if tabular_headers:
        if len(tabular_headers) != 1:
            raise DeciderSourceError(
                f"{instance} must contain exactly one unambiguous CANCHA column"
            )
        header_index, ground_index = tabular_headers[0]
        for row in block[header_index + 1 :]:
            if len(row) <= ground_index or len(row) < 4:
                continue
            if not re.fullmatch(r"\d+", normalize_space(row[1])):
                continue
            if not re.fullmatch(r"\d+", normalize_space(row[2])):
                continue
            value = normalize_space(row[ground_index])
            if value:
                grounds.append(value)

    unique = list(dict.fromkeys(grounds))
    if len(unique) != 1:
        raise DeciderSourceError(
            f"{instance} must contain exactly one unambiguous official ground"
        )
    return unique[0]


def _club_identities(club_map: Mapping[str, int]) -> dict[str, int]:
    identities: dict[str, int] = {}
    for source_name, raw_id in club_map.items():
        key = identity_text(source_name)
        if not key:
            continue
        try:
            club_id = validate_positive_tournament_id(
                raw_id, source=f"club ID for {source_name}"
            )
        except ValueError as exc:
            raise DeciderSourceError(str(exc)) from exc
        previous = identities.get(key)
        if previous is not None and previous != club_id:
            raise DeciderSourceError(
                f"Conflicting authoritative club identity for {source_name!r}"
            )
        identities[key] = club_id
    return identities


def _resolve_club(raw_name: str, identities: Mapping[str, int]) -> int:
    source_identity = identity_text(raw_name)
    club_id = identities.get(source_identity)
    if club_id is None:
        alias = SOURCE_IDENTITY_ALIASES.get(source_identity)
        club_id = identities.get(alias) if alias is not None else None
    if club_id is None:
        raise DeciderSourceError(
            f"Official club is missing from authoritative configuration: {raw_name!r}"
        )
    return club_id


def _match_row(block: Sequence[Sequence[str]], instance: str) -> tuple[str, int, int, str]:
    header_index = next(
        (
            index
            for index, row in enumerate(block)
            if "LOCAL" in {identity_text(cell) for cell in row}
            and "VISITANTE" in {identity_text(cell) for cell in row}
        ),
        None,
    )
    if header_index is None:
        raise DeciderSourceError(f"{instance} is missing the LOCAL/VISITANTE header")

    candidates: list[tuple[str, int, int, str]] = []
    for row in block[header_index + 1 :]:
        if len(row) < 4 or not normalize_space(row[0]) or not normalize_space(row[3]):
            continue
        left = normalize_space(row[1])
        right = normalize_space(row[2])
        if not re.fullmatch(r"-?\d+", left) or not re.fullmatch(r"-?\d+", right):
            raise DeciderSourceError(f"Malformed {instance} score row: {list(row)!r}")
        local_goals, visitor_goals = int(left), int(right)
        if local_goals < 0 or visitor_goals < 0:
            raise DeciderSourceError(f"{instance} scores must be non-negative")
        candidates.append(
            (
                normalize_space(row[0]),
                local_goals,
                visitor_goals,
                normalize_space(row[3]),
            )
        )
    if len(candidates) != 1:
        raise DeciderSourceError(
            f"{instance} must contain exactly one complete official match row"
        )
    return candidates[0]


def _parse_leg(
    block: Sequence[Sequence[str]],
    instance: str,
    identities: Mapping[str, int],
) -> OfficialLeg:
    local, local_goals, visitor_goals, visitor = _match_row(block, instance)
    local_id = _resolve_club(local, identities)
    visitor_id = _resolve_club(visitor, identities)
    if local_id == visitor_id:
        raise DeciderSourceError(f"{instance} cannot contain the same club on both sides")
    return OfficialLeg(
        instance=instance,
        date=_parse_date(block, instance),
        local_name=local,
        visitor_name=visitor,
        local_id=local_id,
        visitor_id=visitor_id,
        local_goals=local_goals,
        visitor_goals=visitor_goals,
        ground=_parse_ground(block, instance),
    )


def _champion_name(row: Sequence[str]) -> str:
    text = normalize_space(" ".join(cell for cell in row if normalize_space(cell)))
    match = re.search(
        r"CAMPE[ÓO]N(?:\s+DEL\s+TORNEO\s+CLAUSURA\s+\d{4})?\s*:\s*(.+)$",
        text,
        re.IGNORECASE,
    )
    if match is None or not normalize_space(match.group(1)):
        raise DeciderSourceError("Official champion text is malformed")
    return normalize_space(match.group(1))


def parse_decider_html(
    html: str,
    source: str,
    club_map: Mapping[str, int],
) -> DeciderSeries:
    """Parse and fully validate one official home-and-away decider section."""
    rows = _extract_rows(html)
    section_indices = [
        index for index, row in enumerate(rows) if SECTION_MARKER in _row_identity(row)
    ]
    if len(section_indices) != 1:
        raise DeciderSourceError(
            "Official source must contain exactly one "
            f"{SECTION_MARKER!r} section"
        )
    section_start = section_indices[0] + 1
    champion_index = next(
        (
            index
            for index in range(section_start, len(rows))
            if _row_identity(rows[index]).startswith("CAMPEON")
        ),
        None,
    )
    if champion_index is None:
        raise DeciderSourceError(
            "Decider section must contain exactly one official champion row"
        )
    section = rows[section_start : champion_index + 1]

    markers: list[tuple[int, str]] = []
    for index, row in enumerate(section[:-1]):
        cells = {identity_text(cell) for cell in row}
        if cells & {"IDA", "PARTIDO DE IDA"}:
            markers.append((index, "ida"))
        if cells & {"VUELTA", "PARTIDO DE VUELTA"}:
            markers.append((index, "vuelta"))
    if [instance for _, instance in markers] != ["ida", "vuelta"]:
        raise DeciderSourceError(
            "Decider section must contain exactly one IDA followed by exactly one VUELTA"
        )

    identities = _club_identities(club_map)
    ida_start = markers[0][0]
    vuelta_start = markers[1][0]
    ida = _parse_leg(section[ida_start:vuelta_start], "ida", identities)
    vuelta = _parse_leg(section[vuelta_start:-1], "vuelta", identities)
    if (ida.local_id, ida.visitor_id) != (vuelta.visitor_id, vuelta.local_id):
        raise DeciderSourceError(
            "IDA and VUELTA must contain the same two clubs with reversed home teams"
        )
    if ida.date >= vuelta.date:
        raise DeciderSourceError("IDA date must be earlier than VUELTA date")

    first_team_total = ida.local_goals + vuelta.visitor_goals
    second_team_total = ida.visitor_goals + vuelta.local_goals
    if first_team_total == second_team_total:
        raise DeciderSourceError(
            "Aggregate score is drawn; no deterministic championship winner exists"
        )
    aggregate_winner = ida.local_id if first_team_total > second_team_total else ida.visitor_id
    official_champion_name = _champion_name(section[-1])
    official_champion_id = _resolve_club(official_champion_name, identities)
    if official_champion_id != aggregate_winner:
        raise DeciderSourceError(
            "Official champion does not equal the validated aggregate winner"
        )

    winner_total, runner_up_total = sorted(
        (first_team_total, second_team_total), reverse=True
    )
    return DeciderSeries(
        source_url=canonical_source(source),
        legs=(ida, vuelta),
        champion_name=official_champion_name,
        champion_id=official_champion_id,
        aggregate=(winner_total, runner_up_total),
    )


def build_payloads(
    series: DeciderSeries,
    tournament_id: int,
    category_id: int,
) -> tuple[dict[str, Any], ...]:
    """Build the complete two-row database payload for a validated series."""
    tournament_id = validate_positive_tournament_id(
        tournament_id, source="--torneo-id"
    )
    category_id = validate_positive_tournament_id(
        category_id, source="--categoria-id"
    )
    return tuple(
        {
            "torneo_id": tournament_id,
            "categoria_id": category_id,
            "local_id": leg.local_id,
            "visitante_id": leg.visitor_id,
            "campeon_id": series.champion_id,
            "serie": SERIES_NAME,
            "instancia": leg.instance,
            "orden": order,
            "goles_local": leg.local_goals,
            "goles_visitante": leg.visitor_goals,
            "dia": leg.date,
            "cancha": leg.ground,
            "fuente_url": series.source_url,
        }
        for order, leg in enumerate(series.legs, start=1)
    )


def _positive_inventory_id(row: Any) -> int:
    if not isinstance(row, Mapping):
        raise RuntimeError("Decider inventory contains a malformed row")
    value = row.get("id")
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise RuntimeError("Decider inventory row id must be a positive integer")
    return value


def inspect_existing_inventory(
    client: Any,
    tournament_id: int,
    category_id: int,
) -> tuple[Mapping[str, Any], ...]:
    """Read only the exact tournament/category/series inventory."""
    tournament_id = validate_positive_tournament_id(
        tournament_id, source="--torneo-id"
    )
    category_id = validate_positive_tournament_id(
        category_id, source="--categoria-id"
    )

    def fetch_page(start: int, end: int) -> Any:
        return (
            client.table("partidos_definicion")
            .select("id," + ",".join(PAYLOAD_FIELDS), count="exact")
            .eq("torneo_id", tournament_id)
            .eq("categoria_id", category_id)
            .eq("serie", SERIES_NAME)
            .order("id")
            .range(start, end)
            .execute()
        )

    rows = read_exact_paginated(
        fetch_page,
        label="Decider inventory",
        maximum_total=INVENTORY_MAX_TOTAL,
        page_size=INVENTORY_PAGE_SIZE,
        identity=_positive_inventory_id,
        identity_name="row id",
    )
    for row in rows:
        if (
            row.get("torneo_id") != tournament_id
            or row.get("categoria_id") != category_id
            or row.get("serie") != SERIES_NAME
        ):
            raise RuntimeError("Decider inventory returned a row outside the exact scope")
    return tuple(rows)


def _comparable(row: Mapping[str, Any]) -> dict[str, Any]:
    return {field: row.get(field) for field in PAYLOAD_FIELDS}


def build_import_plan(
    expected_payloads: Sequence[Mapping[str, Any]],
    existing_inventory: Sequence[Mapping[str, Any]],
    *,
    replace_existing: bool,
) -> ImportPlan:
    """Classify exact inventory as insert, noop, replace, or blocked."""
    payloads = tuple(dict(row) for row in expected_payloads)
    if len(payloads) != 2 or [row.get("orden") for row in payloads] != [1, 2]:
        return ImportPlan(payloads, "blocked", ("Expected payload is not one complete two-leg series",))

    existing = tuple(existing_inventory)
    if not existing:
        return ImportPlan(payloads, "insert", ())

    by_order: dict[Any, Mapping[str, Any]] = {}
    duplicate_order = False
    for row in existing:
        order = row.get("orden")
        if order in by_order:
            duplicate_order = True
        by_order[order] = row
    exact = (
        len(existing) == 2
        and not duplicate_order
        and set(by_order) == {1, 2}
        and all(_comparable(by_order[index]) == payloads[index - 1] for index in (1, 2))
    )
    if exact:
        return ImportPlan(payloads, "noop", ())
    if replace_existing:
        return ImportPlan(payloads, "replace", ())
    return ImportPlan(
        payloads,
        "blocked",
        (
            "Existing decider inventory is partial, conflicting, or contains extra rows; "
            "use --replace-existing to authorize one scoped two-row upsert",
        ),
    )


def execute_import_plan(client: Any, plan: ImportPlan) -> int:
    """Apply one complete series in a single unique-key upsert call."""
    if not plan.valid:
        raise ValueError("Refusing to execute a blocked decider import plan")
    if plan.action == "noop":
        return 0
    if plan.action not in {"insert", "replace"}:
        raise ValueError(f"Unsupported decider import action: {plan.action}")
    rows = [dict(row) for row in plan.payloads]
    if len(rows) != 2:
        raise ValueError("Refusing to execute anything other than one complete two-row series")
    (
        client.table("partidos_definicion")
        .upsert(
            rows,
            on_conflict="torneo_id,categoria_id,serie,orden",
        )
        .execute()
    )
    return 2


def _category_argument(value: str) -> int:
    try:
        return validate_positive_tournament_id(value, source="--categoria-id")
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
        description="Preview or import an official two-leg championship decider.",
    )
    add_operation_arguments(parser, tournament_required=True)
    parser.add_argument(
        "--categoria-id",
        required=True,
        type=_category_argument,
        help="Required positive category ID.",
    )
    parser.add_argument(
        "--source",
        required=True,
        help="Official HTTP(S) URL or readable local recovery file.",
    )
    parser.add_argument(
        "--timeout",
        type=_timeout_argument,
        default=30.0,
        help="HTTP timeout in seconds, between 0.1 and 120 (default: 30).",
    )
    parser.add_argument(
        "--replace-existing",
        action="store_true",
        help="Authorize one scoped two-row upsert for partial/conflicting/extra inventory.",
    )
    parser.add_argument("--json", action="store_true", help="Emit the report as JSON.")
    return parser


def _database_client() -> Any:
    from config import supabase

    return supabase


def _authoritative_clubs() -> Mapping[str, int]:
    from config import MAPEO_CLUBES

    return MAPEO_CLUBES


def _report(
    context: OperationContext,
    category_id: int,
    series: DeciderSeries,
    plan: ImportPlan,
    writes: int,
) -> dict[str, Any]:
    return {
        "mode": context.mode,
        "tournament_id": context.tournament_id,
        "category_id": category_id,
        "series": SERIES_NAME,
        "source_url": series.source_url,
        "legs": [
            {
                "order": order,
                "instance": leg.instance,
                "date": leg.date,
                "local": {"name": leg.local_name, "id": leg.local_id},
                "visitor": {"name": leg.visitor_name, "id": leg.visitor_id},
                "score": {"local": leg.local_goals, "visitor": leg.visitor_goals},
                "ground": leg.ground,
            }
            for order, leg in enumerate(series.legs, start=1)
        ],
        "aggregate": {
            "champion": series.aggregate[0],
            "runner_up": series.aggregate[1],
        },
        "champion": {"name": series.champion_name, "id": series.champion_id},
        "action": plan.action,
        "issues": list(plan.issues),
        "writes": writes,
    }


def render_report(report: Mapping[str, Any]) -> str:
    lines = [
        "Official championship decider: "
        f"mode={report['mode']} tournament_id={report['tournament_id']} "
        f"category_id={report['category_id']}",
        f"Series: {report['series']}",
        f"Source: {report['source_url']}",
    ]
    for leg in report["legs"]:
        lines.append(
            f"  {leg['order']} {str(leg['instance']).upper()}: "
            f"{leg['date']} {leg['local']['name']} {leg['score']['local']}-"
            f"{leg['score']['visitor']} {leg['visitor']['name']} "
            f"ground={leg['ground']}"
        )
    aggregate = report["aggregate"]
    champion = report["champion"]
    lines.extend(
        [
            f"Aggregate: {aggregate['champion']}-{aggregate['runner_up']}",
            f"Champion: {champion['name']} (id={champion['id']})",
            f"Action: {report['action']}",
            f"Issues: {len(report['issues'])}",
        ]
    )
    lines.extend(f"  ERROR: {issue}" for issue in report["issues"])
    lines.append(f"writes={report['writes']}")
    if report["mode"] == "dry-run":
        lines.append("Dry run only; zero database mutations were attempted.")
    return "\n".join(lines)


def main(
    argv: Optional[Sequence[str]] = None,
    *,
    client_factory: Optional[Callable[[], Any]] = None,
    source_loader: Optional[Callable[[str, float], str]] = None,
    identity_loader: Optional[Callable[[], Mapping[str, int]]] = None,
    stdout: Optional[TextIO] = None,
    stderr: Optional[TextIO] = None,
) -> int:
    """Run the dry-run-first decider import and return a process exit code."""
    args = build_parser().parse_args(argv)
    output = stdout or sys.stdout
    error_output = stderr or sys.stderr
    try:
        load_backend_environment()
        context = operation_context_from_args(args)
        canonical = canonical_source(args.source)
        loader = source_loader or load_decider_source
        html = loader(args.source, args.timeout)
        clubs = (identity_loader or _authoritative_clubs)()
        series = parse_decider_html(html, canonical, clubs)
        payloads = build_payloads(series, context.tournament_id, args.categoria_id)
        client = (client_factory or _database_client)()
        existing = inspect_existing_inventory(
            client, context.tournament_id, args.categoria_id
        )
        plan = build_import_plan(
            payloads,
            existing,
            replace_existing=args.replace_existing,
        )
        writes = 0
        if context.execute and plan.valid:
            writes = execute_import_plan(client, plan)
        report = _report(context, args.categoria_id, series, plan, writes)
        if args.json:
            print(json.dumps(report, ensure_ascii=False, indent=2), file=output)
        else:
            print(render_report(report), file=output)
        return 0 if plan.valid else 1
    except Exception as exc:  # noqa: BLE001 - operational CLI must fail closed.
        message = f"Official decider import failed: {exc}"
        if args.json:
            print(
                json.dumps(
                    {
                        "mode": "execute" if args.execute else "dry-run",
                        "action": "blocked",
                        "issues": [str(exc)],
                        "writes": 0,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                file=output,
            )
        else:
            print(message, file=error_output)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
