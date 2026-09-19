# -*- coding: utf-8 -*-
"""Shared historical official-source parsing and identity primitives.

Importing this module is side-effect free. Network access is available only through
``fetch_rows`` and Supabase/configuration is loaded only through the explicit
``load_supabase_dependencies`` boundary used by database-backed commands.
"""

from __future__ import annotations

import argparse
import re
import unicodedata
from datetime import datetime
from html.parser import HTMLParser
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


HISTORICAL_DIRECTORY = "https://ligaamateurdedeportes.com.ar/torneos%20anteriores/"
COMPETENCIA_FILES = {
    "apertura-2026": {
        "primera": "z2026apertura1ra.html",
        "septima": "z2026apertura7ma.html",
        "octava": "z2026apertura8va.html",
        "novena": "z2026apertura9na.html",
        "decima": "z2026apertura10ma.html",
    },
    "clausura-2026": {
        "primera": "z2026clausura1ra.html",
        "septima": "z2026clausura7ma.html",
        "octava": "z2026clausura8va.html",
        "novena": "z2026clausura9na.html",
        "decima": "z2026clausura10ma.html",
    },
}
SOURCE_CATEGORIES = tuple(next(iter(COMPETENCIA_FILES.values())))
STAT_FIELDS = ("pts", "pj", "pg", "pe", "pp", "gf", "gc")
USER_AGENT = "liga-lincoln-historical-source/1.0"
MatchKey = Tuple[int, int, int]


class HistoricalSourceError(RuntimeError):
    """The historical official source is incomplete, malformed, or ambiguous."""


class TableRowParser(HTMLParser):
    """Extract table cells while tolerating nested tags in exported HTML."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: List[List[str]] = []
        self._row: Optional[List[str]] = None
        self._cell: Optional[List[str]] = None

    def handle_starttag(self, tag: str, attrs: Sequence[Tuple[str, Optional[str]]]) -> None:
        tag = tag.lower()
        if tag == "tr":
            if self._row is not None:
                self._finish_row()
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            if self._cell is not None:
                self._finish_cell()
            self._cell = []

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in ("td", "th") and self._cell is not None:
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
        if self._row is not None:
            self.rows.append(self._row)
        self._row = None


def normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace("\xa0", " ")).strip()


def folded_text(value: str) -> str:
    """Return case/accent-insensitive text, repairing common historical mojibake."""
    value = normalize_space(value).upper()
    value = value.replace("Ã‘", "Ñ").replace("Ã\u2018", "Ñ").replace("Ã\x91", "Ñ")
    value = value.replace("�", "N")
    value = unicodedata.normalize("NFD", value)
    return "".join(char for char in value if unicodedata.category(char) != "Mn")


def normalize_team_name(value: str) -> str:
    value = folded_text(value).replace("#", "")
    return re.sub(r"[^A-Z0-9]+", "", value)


def normalized_club_map(club_map: Mapping[str, int]) -> Dict[str, int]:
    mapped: Dict[str, int] = {}
    for name, raw_club_id in club_map.items():
        club_id = int(raw_club_id)
        key = normalize_team_name(name)
        if not key:
            continue
        previous = mapped.get(key)
        if previous is not None and previous != club_id:
            raise HistoricalSourceError(f"MAPEO_CLUBES tiene nombres ambiguos para {name!r}")
        mapped[key] = club_id
    return mapped


def club_labels(club_map: Mapping[str, int]) -> Dict[int, str]:
    labels: Dict[int, str] = {}
    for name, club_id in club_map.items():
        labels.setdefault(int(club_id), name)
    return labels


def load_authoritative_identities() -> Tuple[Mapping[str, int], Mapping[str, int]]:
    """Load identity constants without requesting the lazy Supabase client."""
    from config import CATEGORIAS, MAPEO_CLUBES  # type: ignore

    return MAPEO_CLUBES, CATEGORIAS


def load_supabase_dependencies() -> Tuple[Any, Mapping[str, int], Mapping[str, int]]:
    """Load the lazy DB proxy and authoritative identities at a DB command boundary."""
    from config import CATEGORIAS, MAPEO_CLUBES, supabase  # type: ignore

    return supabase, MAPEO_CLUBES, CATEGORIAS


def source_url(competencia: str, category: str) -> str:
    try:
        filename = COMPETENCIA_FILES[competencia][category]
    except KeyError as exc:
        raise HistoricalSourceError(
            f"Fuente histórica no soportada: competencia={competencia!r}, categoría={category!r}"
        ) from exc
    return HISTORICAL_DIRECTORY + filename


def decode_official_html(raw: bytes) -> str:
    """Prefer the decoding that preserves historical section markers and text."""
    candidates: List[Tuple[int, int, str]] = []
    for encoding in ("utf-8", "cp1252"):
        text = raw.decode(encoding, errors="replace")
        marker_score = sum(
            marker in folded_text(text)
            for marker in ("FIXTURE COMPLETO", "ULTIMOS ENCUENTROS", "EQUIPOS")
        )
        candidates.append((marker_score, -text.count("�"), text))
    return max(candidates, key=lambda item: (item[0], item[1]))[2]


def extract_rows(html: str, source: str = "HTML oficial") -> List[List[str]]:
    parser = TableRowParser()
    try:
        parser.feed(html)
        parser.close()
    except Exception as exc:
        raise HistoricalSourceError(f"HTML inválido en {source}: {exc}") from exc
    if not parser.rows:
        raise HistoricalSourceError(f"No se encontraron filas de tablas en {source}")
    return parser.rows


def fetch_rows(url: str, timeout: int = 30) -> List[List[str]]:
    """Explicit remote boundary. Calling this function performs the only HTTP I/O."""
    request = Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read()
    except HTTPError as exc:
        raise HistoricalSourceError(f"HTTP {exc.code} al descargar {url}") from exc
    except URLError as exc:
        raise HistoricalSourceError(f"No se pudo descargar {url}: {exc.reason}") from exc
    except OSError as exc:
        raise HistoricalSourceError(f"No se pudo descargar {url}: {exc}") from exc
    return extract_rows(decode_official_html(raw), url)


def is_integer(value: str) -> bool:
    return bool(re.fullmatch(r"-?\d+", value.strip()))


def integer_or_value(value: Any) -> Any:
    if value is None or isinstance(value, bool):
        return value
    try:
        return int(value)
    except (TypeError, ValueError):
        return value


def parse_date(value: str) -> Optional[str]:
    match = re.search(r"(\d{1,2})/(\d{1,2})/(\d{2,4})", value)
    if not match:
        return None
    day, month, year = match.groups()
    year = f"20{year}" if len(year) == 2 else year
    try:
        return datetime(int(year), int(month), int(day)).date().isoformat()
    except ValueError:
        return None


def normalized_date(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = normalize_space(str(value))
    return parse_date(text) or (text[:10] if re.fullmatch(r"\d{4}-\d{2}-\d{2}.*", text) else text)


def find_fixture_start(rows: Sequence[Sequence[str]]) -> int:
    for index, row in enumerate(rows):
        if "FIXTURE COMPLETO" in folded_text(" | ".join(row)):
            return index + 1
    raise HistoricalSourceError("No se encontró 'FIXTURE COMPLETO, TABLAS Y RESULTADOS'")


def fecha_number(row: Sequence[str]) -> Optional[int]:
    for index, cell in enumerate(row):
        match = re.search(r"FECHA\s*:?\s*(\d+)", folded_text(cell))
        if match:
            return int(match.group(1))
        if folded_text(cell).rstrip(":") == "FECHA":
            for next_cell in row[index + 1 : index + 3]:
                if is_integer(next_cell):
                    return int(next_cell)
    return None


def find_block_date(block: Sequence[Sequence[str]]) -> Optional[str]:
    for row in block[:8]:
        for cell in row:
            parsed = parse_date(cell)
            if parsed:
                return parsed
    return None


def is_bye(value: str) -> bool:
    return normalize_team_name(value.rstrip(": ")) == "LIBRE"


def row_has_match_header(row: Sequence[str]) -> bool:
    cells = {folded_text(cell) for cell in row}
    return "LOCAL" in cells and "VISITANTE" in cells


def _is_standings_header(row: Sequence[str]) -> bool:
    required = {"EQUIPOS", "PTS", "J", "G", "E", "P", "GF", "GC"}
    return required.issubset({folded_text(cell) for cell in row})


def map_team(
    raw_name: str,
    clubs: Mapping[str, int],
    category: str,
    fecha_id: int,
    url: str,
) -> int:
    club_id = clubs.get(normalize_team_name(raw_name))
    if club_id is None:
        location = f" fecha {fecha_id}" if fecha_id else ""
        raise HistoricalSourceError(
            f"Equipo oficial sin MAPEO_CLUBES en {category}{location}: {raw_name!r} ({url})"
        )
    return club_id


def _standings_candidate(row: Sequence[str]) -> Optional[Tuple[str, Sequence[str]]]:
    for index, raw_name in enumerate(row):
        values = row[index + 1 : index + 1 + len(STAT_FIELDS)]
        if raw_name and len(values) == len(STAT_FIELDS) and all(is_integer(value) for value in values):
            return normalize_space(raw_name).lstrip("# "), values
    return None


def parse_standings_after_header(
    rows: Sequence[Sequence[str]],
    header_index: int,
    end_index: int,
    category: str,
    clubs: Mapping[str, int],
    url: str,
) -> List[Dict[str, Any]]:
    standings: List[Dict[str, Any]] = []
    seen: Set[int] = set()
    for row in rows[header_index + 1 : end_index]:
        if fecha_number(row) is not None or row_has_match_header(row) or _is_standings_header(row):
            break
        candidate = _standings_candidate(row)
        if candidate is None:
            normalized_cells = {normalize_team_name(cell) for cell in row if normalize_space(cell)}
            known_team_present = any(cell in clubs for cell in normalized_cells)
            numeric_cells = sum(is_integer(cell) for cell in row)
            if known_team_present or numeric_cells >= 2:
                raise HistoricalSourceError(
                    f"Fila de posiciones oficial malformada en {category}: {list(row)!r} ({url})"
                )
            continue
        name, values = candidate
        if not name or is_bye(name) or normalize_team_name(name) in {"EQUIPOS", "LOCAL", "VISITANTE"}:
            continue
        club_id = map_team(name, clubs, category, 0, url)
        if club_id in seen:
            raise HistoricalSourceError(
                f"Equipo repetido en posiciones oficiales de {category}: {name!r} ({url})"
            )
        seen.add(club_id)
        standings.append(
            {
                "team": name,
                "club_id": club_id,
                **{field: int(value) for field, value in zip(STAT_FIELDS, values)},
            }
        )
    return standings


def parse_final_standings(
    rows: Sequence[Sequence[str]],
    fixture_start: int,
    category: str,
    clubs: Mapping[str, int],
    url: str,
) -> List[Dict[str, Any]]:
    """Parse an optional final table before the fixture section."""
    header_index = next(
        (index for index, row in enumerate(rows[:fixture_start]) if _is_standings_header(row)),
        None,
    )
    if header_index is None:
        return []
    standings = parse_standings_after_header(rows, header_index, fixture_start, category, clubs, url)
    if not standings:
        raise HistoricalSourceError(f"La tabla final oficial no contiene filas válidas en {url}")
    return standings


def parse_latest_fixture_standings(
    rows: Sequence[Sequence[str]],
    date_indices: Sequence[int],
    category: str,
    clubs: Mapping[str, int],
    url: str,
) -> List[Dict[str, Any]]:
    for position in range(len(date_indices) - 1, -1, -1):
        block_start = date_indices[position]
        block_end = date_indices[position + 1] if position + 1 < len(date_indices) else len(rows)
        header_index = next(
            (index for index in range(block_start, block_end) if _is_standings_header(rows[index])),
            None,
        )
        if header_index is None:
            continue
        standings = parse_standings_after_header(rows, header_index, block_end, category, clubs, url)
        if not standings:
            raise HistoricalSourceError(f"La tabla de posiciones oficial está vacía en {url}")
        return standings
    return []


def _score_pair(row: Sequence[str], category: str, fecha_id: int, url: str) -> Tuple[Optional[int], Optional[int]]:
    left = normalize_space(row[1])
    right = normalize_space(row[2])
    if is_integer(left) and is_integer(right):
        return int(left), int(right)
    empty_markers = {"", "-"}
    if folded_text(left) in empty_markers and folded_text(right) in empty_markers:
        return None, None
    raise HistoricalSourceError(
        f"Resultado oficial malformado en {category} fecha {fecha_id}: {list(row)!r} ({url})"
    )


def _validate_bye_score_cells(
    row: Sequence[str], category: str, fecha_id: int, url: str
) -> None:
    """Require both LIBRE score cells to be explicit non-score placeholders."""
    try:
        local_goals, visitor_goals = _score_pair(row, category, fecha_id, url)
    except HistoricalSourceError as exc:
        raise HistoricalSourceError(
            f"Fila LIBRE con resultado malformado en {category} fecha {fecha_id}: "
            f"{list(row)!r} ({url})"
        ) from exc
    if local_goals is not None or visitor_goals is not None:
        raise HistoricalSourceError(
            f"Fila LIBRE no puede tener resultado en {category} fecha {fecha_id}: "
            f"{list(row)!r} ({url})"
        )


def match_key(row: Mapping[str, Any]) -> Optional[MatchKey]:
    fecha_id = integer_or_value(row.get("fecha_id"))
    local_id = integer_or_value(row.get("local_id"))
    visitor_id = integer_or_value(row.get("visitante_id"))
    if not all(isinstance(value, int) for value in (fecha_id, local_id, visitor_id)):
        return None
    return fecha_id, local_id, visitor_id


def duplicate_keys(keys: Iterable[Optional[MatchKey]]) -> Set[MatchKey]:
    seen: Set[MatchKey] = set()
    duplicates: Set[MatchKey] = set()
    for key in keys:
        if key is not None:
            if key in seen:
                duplicates.add(key)
            seen.add(key)
    return duplicates


def validate_official_match_keys(matches: Sequence[Mapping[str, Any]], url: str) -> None:
    by_key: Dict[MatchKey, Mapping[str, Any]] = {}
    for row in matches:
        key = match_key(row)
        if key is None:
            raise HistoricalSourceError(f"Partido oficial sin clave válida: {dict(row)!r} ({url})")
        previous = by_key.get(key)
        if previous is not None:
            fields = ("goles_local", "goles_visitante", "estado", "dia")
            conflicting = any(previous.get(field) != row.get(field) for field in fields)
            reason = "resultados oficiales conflictivos" if conflicting else "clave oficial duplicada"
            raise HistoricalSourceError(f"{reason} para {key} ({url})")
        by_key[key] = row


def parse_official_fixture(
    rows: Sequence[Sequence[str]],
    url: str,
    category: str,
    club_map: Mapping[str, int],
) -> Dict[str, Any]:
    clubs = normalized_club_map(club_map)
    fixture_start = find_fixture_start(rows)
    date_indices = [
        index for index in range(fixture_start, len(rows)) if fecha_number(rows[index]) is not None
    ]
    if not date_indices:
        raise HistoricalSourceError(f"No se encontraron fechas del fixture en {url}")

    matches: List[Dict[str, Any]] = []
    byes: List[Dict[str, Any]] = []
    participants: Dict[int, str] = {}
    date_numbers: List[int] = []

    for position, block_start in enumerate(date_indices):
        block_end = date_indices[position + 1] if position + 1 < len(date_indices) else len(rows)
        block = rows[block_start:block_end]
        fecha_id = fecha_number(rows[block_start])
        if fecha_id is None:
            raise HistoricalSourceError(f"Fecha oficial malformada en {url}")
        date_numbers.append(fecha_id)
        day = find_block_date(block)
        header_index = next((index for index, row in enumerate(block) if row_has_match_header(row)), None)
        if header_index is None:
            raise HistoricalSourceError(
                f"No se encontró la cabecera Local/Visitante en {category} fecha {fecha_id}"
            )

        parsed_rows = 0
        for row in block[header_index + 1 :]:
            if _is_standings_header(row) or fecha_number(row) is not None:
                break
            if not any(normalize_space(cell) for cell in row):
                continue
            if len(row) < 4:
                normalized_cells = {normalize_team_name(cell) for cell in row}
                if any(cell in clubs or cell == "LIBRE" for cell in normalized_cells):
                    raise HistoricalSourceError(
                        f"Fila de partido oficial malformada en {category} fecha {fecha_id}: {list(row)!r} ({url})"
                    )
                continue
            raw_local = normalize_space(row[0]).rstrip(": ")
            raw_visitor = normalize_space(row[3]).rstrip(": ")
            if not raw_local and not raw_visitor:
                continue
            if not raw_local or not raw_visitor:
                raise HistoricalSourceError(
                    f"Fila de partido oficial incompleta en {category} fecha {fecha_id}: {list(row)!r} ({url})"
                )

            local_bye = is_bye(raw_local)
            visitor_bye = is_bye(raw_visitor)
            if local_bye or visitor_bye:
                if local_bye and visitor_bye:
                    raise HistoricalSourceError(
                        f"Fila LIBRE sin equipo en {category} fecha {fecha_id}: {list(row)!r} ({url})"
                    )
                _validate_bye_score_cells(row, category, fecha_id, url)
                team_name = raw_visitor if local_bye else raw_local
                team_id = map_team(team_name, clubs, category, fecha_id, url)
                participants[team_id] = team_name
                byes.append(
                    {"fecha_id": fecha_id, "dia": day, "club_id": team_id, "team": team_name}
                )
                parsed_rows += 1
                continue

            local_id = map_team(raw_local, clubs, category, fecha_id, url)
            visitor_id = map_team(raw_visitor, clubs, category, fecha_id, url)
            if local_id == visitor_id:
                raise HistoricalSourceError(
                    f"Partido oficial con el mismo club en ambos lados en {category} fecha {fecha_id} ({url})"
                )
            local_goals, visitor_goals = _score_pair(row, category, fecha_id, url)
            participants[local_id] = raw_local
            participants[visitor_id] = raw_visitor
            matches.append(
                {
                    "fecha_id": fecha_id,
                    "dia": day,
                    "local_id": local_id,
                    "visitante_id": visitor_id,
                    "local": raw_local,
                    "visitante": raw_visitor,
                    "goles_local": local_goals,
                    "goles_visitante": visitor_goals,
                    "estado": "jugado" if local_goals is not None else "programado",
                }
            )
            parsed_rows += 1
        if parsed_rows == 0:
            raise HistoricalSourceError(
                f"La fecha {fecha_id} no contiene partidos ni LIBRE válidos en {url}"
            )

    validate_official_match_keys(matches, url)
    bye_keys = [(int(row["fecha_id"]), int(row["club_id"])) for row in byes]
    if len(bye_keys) != len(set(bye_keys)):
        raise HistoricalSourceError(f"Filas LIBRE duplicadas en {url}")

    standings = parse_final_standings(rows, fixture_start, category, clubs, url)
    standings_source = "pre_fixture_final_table"
    if not standings:
        standings = parse_latest_fixture_standings(rows, date_indices, category, clubs, url)
        standings_source = "latest_fixture_table" if standings else "not_found"
    participant_rows = [
        {"club_id": club_id, "team": participants[club_id]} for club_id in sorted(participants)
    ]
    participant_ids = set(participants)
    standing_ids = {int(row["club_id"]) for row in standings}
    standings_only_ids = standing_ids - participant_ids
    if standings_only_ids:
        standings_only = [
            {"club_id": int(row["club_id"]), "team": row["team"]}
            for row in standings
            if int(row["club_id"]) in standings_only_ids
        ]
        raise HistoricalSourceError(
            f"Equipos de posiciones ausentes del fixture completo en {category}: "
            f"{standings_only!r} ({url})"
        )
    return {
        "matches": matches,
        "byes": byes,
        "participants": participant_rows,
        "date_numbers": sorted(set(date_numbers)),
        "final_standings": standings,
        "final_standings_source": standings_source,
        "final_table_omissions": [row for row in participant_rows if row["club_id"] not in standing_ids],
        "fixture_start": fixture_start,
    }


def parse_official_standings(
    rows: Sequence[Sequence[str]],
    url: str,
    category: str,
    club_map: Mapping[str, int],
) -> List[Dict[str, Any]]:
    """Parse the required current/final table used by the standings audit."""
    clubs = normalized_club_map(club_map)
    fixture_marker = next(
        (index for index, row in enumerate(rows) if "FIXTURE COMPLETO" in folded_text(" | ".join(row))),
        None,
    )
    latest_marker = next(
        (index for index, row in enumerate(rows) if "ULTIMOS ENCUENTROS" in folded_text(" | ".join(row))),
        None,
    )
    if latest_marker is not None:
        end = fixture_marker if fixture_marker is not None and fixture_marker > latest_marker else len(rows)
        header_index = next(
            (index for index in range(latest_marker + 1, end) if _is_standings_header(rows[index])),
            None,
        )
        if header_index is None:
            raise HistoricalSourceError(f"No se encontró el encabezado de posiciones en {url}")
        standings = parse_standings_after_header(rows, header_index, end, category, clubs, url)
    else:
        if fixture_marker is None:
            raise HistoricalSourceError(
                f"No se encontró 'ÚLTIMOS ENCUENTROS' ni 'FIXTURE COMPLETO' en {url}"
            )
        headers = [index for index in range(fixture_marker + 1, len(rows)) if _is_standings_header(rows[index])]
        if not headers:
            raise HistoricalSourceError(f"No se encontró el encabezado de posiciones en {url}")
        header_index = headers[-1]
        standings = parse_standings_after_header(rows, header_index, len(rows), category, clubs, url)
    if not standings:
        raise HistoricalSourceError(f"No se pudieron extraer filas de posiciones en {url}")
    return standings


def positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("debe ser un entero positivo") from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError("debe ser un entero positivo")
    return parsed
