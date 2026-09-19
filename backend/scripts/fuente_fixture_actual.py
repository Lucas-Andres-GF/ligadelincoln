"""Versioned source profiles for current official fixture imports."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping


CURRENT_TABLE_FORMAT = "current-table"
CURRENT_TABLE_VERSION = 1


@dataclass(frozen=True)
class CurrentFixtureSourceProfile:
    """Immutable description of one supported current-fixture source."""

    key: str
    display_name: str
    slug: str
    season: int
    parser_format: str
    parser_version: int
    category_sources: Mapping[str, str]
    requires_contiguous_rounds: bool = True

    @property
    def format_id(self) -> str:
        return f"{self.parser_format}-v{self.parser_version}"


_PRIMAVERA_VERANO_2026 = CurrentFixtureSourceProfile(
    key="primavera-verano-2026",
    display_name="Primavera/Verano 2026",
    slug="primavera-verano-2026",
    season=2026,
    parser_format=CURRENT_TABLE_FORMAT,
    parser_version=CURRENT_TABLE_VERSION,
    category_sources=MappingProxyType(
        {
            "primera": "https://www.ligaamateurdedeportes.com.ar/primera.html",
            "septima": "https://www.ligaamateurdedeportes.com.ar/septima.html",
            "octava": "https://www.ligaamateurdedeportes.com.ar/octava.html",
            "novena": "https://www.ligaamateurdedeportes.com.ar/novena.html",
            "decima": "https://www.ligaamateurdedeportes.com.ar/decima.html",
        }
    ),
)

SOURCE_PROFILES: Mapping[str, CurrentFixtureSourceProfile] = MappingProxyType(
    {_PRIMAVERA_VERANO_2026.key: _PRIMAVERA_VERANO_2026}
)


def get_source_profile(key: str) -> CurrentFixtureSourceProfile:
    """Return a known profile, failing closed for unknown keys."""
    try:
        return SOURCE_PROFILES[key]
    except KeyError as exc:
        raise ValueError(f"Unknown current fixture source profile: {key}") from exc


def validate_supported_format(profile: CurrentFixtureSourceProfile) -> None:
    """Reject profiles whose parser contract is not implemented."""
    supported = (CURRENT_TABLE_FORMAT, CURRENT_TABLE_VERSION)
    actual = (profile.parser_format, profile.parser_version)
    if actual != supported:
        raise ValueError(f"Unsupported current fixture parser format: {profile.format_id}")
