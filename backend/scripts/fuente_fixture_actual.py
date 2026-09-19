"""Versioned source profiles for current official fixture imports."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Iterable, Mapping


CURRENT_TABLE_FORMAT = "current-table"
CURRENT_TABLE_VERSION = 1


@dataclass(frozen=True)
class CategoryCompletenessExpectation:
    """Exact source/DB fixture shape required for one profile category."""

    round_ids: frozenset[int]
    fixture_count: int

    def __post_init__(self) -> None:
        rounds = frozenset(self.round_ids)
        if (
            not rounds
            or any(isinstance(value, bool) or not isinstance(value, int) or value <= 0 for value in rounds)
        ):
            raise ValueError("Profile category round IDs must be nonempty positive integers")
        if (
            isinstance(self.fixture_count, bool)
            or not isinstance(self.fixture_count, int)
            or self.fixture_count <= 0
        ):
            raise ValueError("Profile category fixture count must be a positive integer")
        object.__setattr__(self, "round_ids", rounds)


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
    category_expectations: Mapping[str, CategoryCompletenessExpectation]
    requires_contiguous_rounds: bool = True

    def __post_init__(self) -> None:
        sources = dict(self.category_sources)
        expectations = dict(self.category_expectations)
        if not sources:
            raise ValueError("Current fixture profile must define at least one category")
        if any(not isinstance(key, str) or not key.strip() for key in sources):
            raise ValueError("Profile category source keys must be nonempty strings")
        if any(not isinstance(value, str) or not value.strip() for value in sources.values()):
            raise ValueError("Profile category sources must be nonempty strings")
        if set(expectations) != set(sources):
            raise ValueError(
                "Profile completeness categories must exactly match category sources"
            )
        if any(
            not isinstance(value, CategoryCompletenessExpectation)
            for value in expectations.values()
        ):
            raise ValueError(
                "Profile completeness values must be CategoryCompletenessExpectation instances"
            )
        object.__setattr__(self, "category_sources", MappingProxyType(sources))
        object.__setattr__(self, "category_expectations", MappingProxyType(expectations))

    @property
    def format_id(self) -> str:
        return f"{self.parser_format}-v{self.parser_version}"


_ROUNDS_1_TO_11 = frozenset(range(1, 12))
_PRIMAVERA_VERANO_2026 = CurrentFixtureSourceProfile(
    key="primavera-verano-2026",
    display_name="Primavera/Verano 2026",
    slug="primavera-verano-2026",
    season=2026,
    parser_format=CURRENT_TABLE_FORMAT,
    parser_version=CURRENT_TABLE_VERSION,
    category_sources={
        "primera": "https://www.ligaamateurdedeportes.com.ar/primera.html",
        "septima": "https://www.ligaamateurdedeportes.com.ar/septima.html",
        "octava": "https://www.ligaamateurdedeportes.com.ar/octava.html",
        "novena": "https://www.ligaamateurdedeportes.com.ar/novena.html",
        "decima": "https://www.ligaamateurdedeportes.com.ar/decima.html",
    },
    category_expectations={
        "primera": CategoryCompletenessExpectation(_ROUNDS_1_TO_11, 66),
        "septima": CategoryCompletenessExpectation(_ROUNDS_1_TO_11, 56),
        "octava": CategoryCompletenessExpectation(_ROUNDS_1_TO_11, 63),
        "novena": CategoryCompletenessExpectation(_ROUNDS_1_TO_11, 56),
        "decima": CategoryCompletenessExpectation(_ROUNDS_1_TO_11, 66),
    },
)

SOURCE_PROFILES: Mapping[str, CurrentFixtureSourceProfile] = MappingProxyType(
    {_PRIMAVERA_VERANO_2026.key: _PRIMAVERA_VERANO_2026}
)


def validate_source_profile(profile: CurrentFixtureSourceProfile) -> None:
    """Revalidate registry/profile invariants at every trust boundary."""
    if not isinstance(profile, CurrentFixtureSourceProfile):
        raise ValueError("Malformed current fixture source profile")
    if set(profile.category_expectations) != set(profile.category_sources):
        raise ValueError("Profile completeness categories must exactly match category sources")
    for category, expectation in profile.category_expectations.items():
        if not isinstance(expectation, CategoryCompletenessExpectation):
            raise ValueError(f"Malformed completeness expectation for category {category}")
        # Frozen instances can still be forged through low-level mutation; verify values.
        CategoryCompletenessExpectation(expectation.round_ids, expectation.fixture_count)


def get_source_profile(key: str) -> CurrentFixtureSourceProfile:
    """Return a known, validated profile, failing closed for unknown keys."""
    try:
        profile = SOURCE_PROFILES[key]
    except KeyError as exc:
        raise ValueError(f"Unknown current fixture source profile: {key}") from exc
    validate_source_profile(profile)
    return profile


def validate_supported_format(profile: CurrentFixtureSourceProfile) -> None:
    """Reject profiles whose parser contract is not implemented."""
    validate_source_profile(profile)
    supported = (CURRENT_TABLE_FORMAT, CURRENT_TABLE_VERSION)
    actual = (profile.parser_format, profile.parser_version)
    if actual != supported:
        raise ValueError(f"Unsupported current fixture parser format: {profile.format_id}")


def validate_category_completeness(
    profile: CurrentFixtureSourceProfile,
    category_key: str,
    round_ids: Iterable[int],
    fixture_count: int,
) -> None:
    """Require the exact versioned fixture shape for one selected category."""
    validate_source_profile(profile)
    try:
        expectation = profile.category_expectations[category_key]
    except KeyError as exc:
        raise ValueError(
            f"Category {category_key!r} is not defined by profile {profile.key}"
        ) from exc
    actual_rounds = frozenset(round_ids)
    if actual_rounds != expectation.round_ids:
        raise ValueError(
            f"Incomplete fixture rounds for {category_key}: "
            f"expected={sorted(expectation.round_ids)} actual={sorted(actual_rounds)}"
        )
    if fixture_count != expectation.fixture_count:
        raise ValueError(
            f"Incomplete fixture row count for {category_key}: "
            f"expected={expectation.fixture_count} actual={fixture_count}"
        )
