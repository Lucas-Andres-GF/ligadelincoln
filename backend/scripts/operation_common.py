"""Shared safety conventions for tournament-scoped operations."""

from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, MutableMapping, Optional, Union

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


def add_operation_arguments(parser: argparse.ArgumentParser) -> None:
    """Add the shared tournament scope and dry-run-first execution flags."""
    parser.add_argument(
        "--torneo-id",
        type=tournament_id_argument,
        default=None,
        help="Positive tournament ID; defaults to validated ACTIVE_TORNEO_ID.",
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
