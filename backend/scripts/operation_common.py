"""Shared safety conventions for tournament-scoped operations."""

from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Hashable, Mapping, MutableMapping, Optional, Union

from dotenv import load_dotenv


ACTIVE_TOURNAMENT_ENV = "ACTIVE_TORNEO_ID"
DEFAULT_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
Environment = Mapping[str, str]
TournamentIdInput = Union[int, str]


def load_backend_environment(env_path: Optional[Union[str, Path]] = None) -> bool:
    """Load backend environment values without overriding process settings."""
    path = Path(env_path) if env_path is not None else DEFAULT_ENV_PATH
    return bool(load_dotenv(dotenv_path=path, override=False))


def validate_positive_tournament_id(
    value: TournamentIdInput,
    *,
    source: str = "tournament ID",
) -> int:
    """Return a positive integer tournament ID or raise a useful error."""
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise ValueError(f"{source} must be a positive integer")

    try:
        parsed = int(value)
    except ValueError as exc:
        raise ValueError(f"{source} must be a positive integer") from exc

    if parsed <= 0:
        raise ValueError(f"{source} must be a positive integer")
    return parsed


def resolve_active_tournament_id(
    environ: Optional[Environment] = None,
) -> Optional[int]:
    """Resolve an optional active tournament ID from validated environment data."""
    environment = os.environ if environ is None else environ
    raw_value = environment.get(ACTIVE_TOURNAMENT_ENV)
    if raw_value is None or not raw_value.strip():
        return None
    return validate_positive_tournament_id(
        raw_value,
        source=ACTIVE_TOURNAMENT_ENV,
    )


def resolve_tournament_id(
    explicit_tournament_id: Optional[TournamentIdInput] = None,
    *,
    environ: Optional[Environment] = None,
) -> int:
    """Resolve an explicit ID first, then the validated active environment ID."""
    if explicit_tournament_id is not None:
        return validate_positive_tournament_id(
            explicit_tournament_id,
            source="--torneo-id",
        )

    active_tournament_id = resolve_active_tournament_id(environ)
    if active_tournament_id is None:
        raise ValueError(
            "Tournament ID is required. Pass --torneo-id or set ACTIVE_TORNEO_ID."
        )
    return active_tournament_id


def tournament_id_argument(value: str) -> int:
    """Adapt strict tournament ID validation for argparse."""
    try:
        return validate_positive_tournament_id(value, source="--torneo-id")
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def add_operation_arguments(
    parser: argparse.ArgumentParser,
    *,
    tournament_required: bool = False,
) -> None:
    """Add the shared tournament scope and dry-run-first execution flags."""
    parser.add_argument(
        "--torneo-id",
        type=tournament_id_argument,
        required=tournament_required,
        default=None,
        help=(
            "Required positive tournament ID."
            if tournament_required
            else "Positive tournament ID; defaults to validated ACTIVE_TORNEO_ID."
        ),
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Apply changes. Without this flag the operation is a dry run.",
    )


@dataclass(frozen=True)
class OperationContext:
    """Resolved scope and execution mode shared by operational scripts."""

    tournament_id: int
    execute: bool = False

    @property
    def mode(self) -> str:
        return "execute" if self.execute else "dry-run"

    def summary(
        self,
        operation: str,
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> MutableMapping[str, Any]:
        return {
            "operation": operation,
            "mode": self.mode,
            "tournament_id": self.tournament_id,
            "metadata": dict(metadata or {}),
        }


def read_exact_paginated(
    fetch_page: Callable[[int, int], Any],
    *,
    label: str,
    maximum_total: int,
    page_size: int = 200,
    identity: Callable[[Any], Hashable] = lambda row: row["id"],
    identity_name: str = "row identity",
) -> list[Any]:
    """Read a bounded inventory while proving exact, stable completeness.

    ``fetch_page`` receives inclusive start/end offsets. It owns query creation,
    invariant filters, and deterministic ordering; callers must apply the same
    stable order (normally ascending primary-key order) before every range.
    """
    if page_size <= 0 or maximum_total <= 0:
        raise ValueError("Exact pagination bounds must be positive")

    rows: list[Any] = []
    seen: set[Hashable] = set()
    expected_count: Optional[int] = None
    effective_page_size: Optional[int] = None

    while expected_count is None or len(rows) < expected_count:
        start = len(rows)
        response = fetch_page(start, start + page_size - 1)
        page_count = getattr(response, "count", None)
        if isinstance(page_count, bool) or not isinstance(page_count, int) or page_count < 0:
            raise RuntimeError(f"{label} exact count is missing or malformed")
        if page_count > maximum_total:
            raise RuntimeError(
                f"{label} exact count {page_count} exceeds safety maximum {maximum_total}"
            )
        if expected_count is None:
            expected_count = page_count
        elif page_count != expected_count:
            raise RuntimeError(
                f"{label} exact count changed during pagination: "
                f"expected {expected_count}, received {page_count}"
            )

        raw_page = getattr(response, "data", None)
        if raw_page is None:
            page: list[Any] = []
        elif isinstance(raw_page, (str, bytes, Mapping)):
            raise RuntimeError(f"{label} returned malformed page data")
        else:
            try:
                page = list(raw_page)
            except TypeError as exc:
                raise RuntimeError(f"{label} returned malformed page data") from exc

        if len(rows) + len(page) > expected_count:
            raise RuntimeError(f"{label} page rows exceed exact count {expected_count}")
        if expected_count == 0:
            if page:
                raise RuntimeError(f"{label} returned rows for an exact count of zero")
            break
        if not page:
            raise RuntimeError(
                f"{label} pagination ended before exact count {expected_count} was satisfied"
            )

        remaining_after_page = expected_count - len(rows) - len(page)
        if effective_page_size is None and remaining_after_page > 0:
            effective_page_size = len(page)
        elif remaining_after_page > 0 and len(page) != effective_page_size:
            raise RuntimeError(
                f"{label} returned an inconsistent short page before exact count was satisfied"
            )
        elif effective_page_size is not None and len(page) > effective_page_size:
            raise RuntimeError(f"{label} returned an inconsistent page size")

        for item in page:
            try:
                item_identity = identity(item)
                hash(item_identity)
            except Exception as exc:
                raise RuntimeError(f"{label} contains a malformed row identity") from exc
            if item_identity in seen:
                raise RuntimeError(
                    f"{label} pagination repeated {identity_name} {item_identity!r}"
                )
            seen.add(item_identity)
            rows.append(item)

    if expected_count is None or len(rows) != expected_count:
        raise RuntimeError(
            f"{label} accumulated {len(rows)} rows but exact count was {expected_count}"
        )
    return rows


def operation_context_from_args(
    args: argparse.Namespace,
    *,
    environ: Optional[Environment] = None,
) -> OperationContext:
    """Build a validated operation context from shared CLI arguments."""
    return OperationContext(
        tournament_id=resolve_tournament_id(args.torneo_id, environ=environ),
        execute=bool(args.execute),
    )
