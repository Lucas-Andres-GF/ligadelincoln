"""Network-free tests for versioned current fixture imports."""

from __future__ import annotations

import io
import os
import sys
import unittest
from dataclasses import fields
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


BACKEND_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = BACKEND_DIR / "scripts"
FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "fixture_actual_sample.html"
sys.path.insert(0, str(SCRIPTS_DIR))

import fuente_fixture_actual as profiles  # noqa: E402
import importar_fixture_torneo as importer  # noqa: E402


SAMPLE_HTML = FIXTURE_PATH.read_text(encoding="utf-8")
COMPACT_PROFILE = profiles.CurrentFixtureSourceProfile(
    key="primavera-verano-2026",
    display_name="Primavera/Verano 2026",
    slug="primavera-verano-2026",
    season=2026,
    parser_format=profiles.CURRENT_TABLE_FORMAT,
    parser_version=profiles.CURRENT_TABLE_VERSION,
    category_sources={"primera": str(FIXTURE_PATH)},
    category_expectations={
        "primera": profiles.CategoryCompletenessExpectation(frozenset({1, 2}), 6)
    },
)


def run_compact_main(argv, **kwargs):
    with mock.patch.object(importer, "get_source_profile", return_value=COMPACT_PROFILE):
        return importer.main(argv, **kwargs)


class FakeQuery:
    def __init__(self, client: "FakeClient", table: str) -> None:
        self.client = client
        self.table = table
        self.operation = "select"
        self.values = None
        self.filters: list[tuple[str, object]] = []
        self.limit_value: int | None = None
        self.range_value: tuple[int, int] | None = None
        self.order_value: tuple[str, bool] | None = None
        self.count_mode: object = None

    def select(self, columns: str, **kwargs: object) -> "FakeQuery":
        self.operation = "select"
        self.count_mode = kwargs.get("count")
        self.client.selected_columns[self.table] = columns
        return self

    def insert(self, values: object) -> "FakeQuery":
        self.operation = "insert"
        self.values = values
        return self

    def update(self, values: object) -> "FakeQuery":
        self.operation = "update"
        self.values = values
        return self

    def delete(self) -> "FakeQuery":
        self.operation = "delete"
        return self

    def eq(self, column: str, value: object) -> "FakeQuery":
        self.filters.append((column, value))
        return self

    def in_(self, column: str, values: object) -> "FakeQuery":
        self.filters.append((column, tuple(values)))
        return self

    def limit(self, value: int) -> "FakeQuery":
        self.limit_value = value
        self.client.limits[self.table] = value
        return self

    def order(self, column: str, desc: bool = False) -> "FakeQuery":
        self.order_value = (column, desc)
        return self

    def range(self, start: int, end: int) -> "FakeQuery":
        self.range_value = (start, end)
        return self

    def execute(self) -> SimpleNamespace:
        if self.operation == "select":
            if self.client.read_error is not None:
                raise self.client.read_error
            self.client.reads.append(
                (self.table, tuple(self.filters), self.range_value, self.order_value)
            )
            rows = list(self.client.inventory.get(self.table, []))
            if self.range_value is None:
                return SimpleNamespace(data=rows)
            if self.count_mode != "exact":
                raise AssertionError("paginated inventory reads must request exact count")
            start, end = self.range_value
            cap = self.client.server_caps.get(self.table)
            if cap is not None:
                end = min(end, start + cap - 1)
            scripted = self.client.scripted_pages.get(self.table)
            page_index = self.client.page_calls.get(self.table, 0)
            self.client.page_calls[self.table] = page_index + 1
            if scripted is not None and page_index < len(scripted):
                page = list(scripted[page_index])
            elif scripted is not None:
                page = []
            else:
                page = rows[start : end + 1]
            count_value = self.client.counts.get(self.table, len(rows))
            if isinstance(count_value, list):
                count = count_value[min(page_index, len(count_value) - 1)]
            else:
                count = count_value
            return SimpleNamespace(data=page, count=count)
        self.client.mutation_attempts += 1
        if self.client.write_error is not None:
            raise self.client.write_error
        self.client.mutations.append(
            (self.table, self.operation, self.values, tuple(self.filters))
        )
        return SimpleNamespace(data=[{"id": 1}])


class FakeClient:
    def __init__(
        self,
        *,
        tournaments=(),
        fixtures=(),
        positions=(),
        lineups=(),
        read_error: Exception | None = None,
        write_error: Exception | None = None,
        server_caps=None,
        counts=None,
        scripted_pages=None,
    ) -> None:
        self.inventory = {
            "torneos": list(tournaments),
            "partidos": list(fixtures),
            "posiciones": list(positions),
            "alineaciones": list(lineups),
        }
        self.read_error = read_error
        self.write_error = write_error
        self.server_caps = dict(server_caps or {})
        self.counts = dict(counts or {})
        self.scripted_pages = dict(scripted_pages or {})
        self.page_calls: dict[str, int] = {}
        self.reads: list[tuple[object, ...]] = []
        self.mutations: list[tuple[object, ...]] = []
        self.mutation_attempts = 0
        self.selected_columns: dict[str, str] = {}
        self.limits: dict[str, int] = {}

    def table(self, name: str) -> FakeQuery:
        return FakeQuery(self, name)


def parsed_rows(html: str = SAMPLE_HTML) -> list[importer.OfficialFixtureRow]:
    return importer.parse_current_table_html(html, "primera")


def source_plan() -> importer.SourcePlan:
    rows = importer.parse_profile_source(COMPACT_PROFILE, "primera", SAMPLE_HTML)
    plan = importer.build_category_plan(rows, 7, "primera")
    return importer.validate_source_plan([plan], 7, COMPACT_PROFILE.key, ["primera"])


def empty_scope(
    *,
    tournament=None,
    fixtures=(),
    positions=(),
    lineups=(),
) -> importer.ExistingScope:
    return importer.ExistingScope(
        tournament=tournament,
        fixtures=tuple(fixtures),
        positions=tuple(positions),
        lineups=tuple(lineups),
    )


def existing_fixture(
    fixture_id: int = 90,
    *,
    category_id: int = 1,
    state: str = "programado",
    local_id: object = 1,
    visitor_id: object = 8,
    local_goals=None,
    visitor_goals=None,
) -> dict[str, object]:
    return {
        "id": fixture_id,
        "torneo_id": 7,
        "categoria_id": category_id,
        "local_id": local_id,
        "visitante_id": visitor_id,
        "fecha_id": 1,
        "estado": state,
        "goles_local": local_goals,
        "goles_visitante": visitor_goals,
    }


class SourceProfileTests(unittest.TestCase):
    def test_registry_exposes_explicit_versioned_profile_without_database_id(self) -> None:
        profile = profiles.get_source_profile("primavera-verano-2026")

        self.assertEqual(profile.display_name, "Primavera/Verano 2026")
        self.assertEqual(profile.slug, "primavera-verano-2026")
        self.assertEqual(profile.season, 2026)
        self.assertEqual(profile.format_id, "current-table-v1")
        self.assertEqual(
            tuple(profile.category_sources),
            ("primera", "septima", "octava", "novena", "decima"),
        )
        self.assertNotIn("torneo", {field.name for field in fields(profile)})

    def test_builtin_profile_records_exact_verified_completeness(self) -> None:
        profile = profiles.get_source_profile("primavera-verano-2026")
        counts = {
            key: expectation.fixture_count
            for key, expectation in profile.category_expectations.items()
        }
        self.assertEqual(
            counts,
            {"primera": 66, "septima": 56, "octava": 63, "novena": 56, "decima": 66},
        )
        self.assertEqual(sum(counts.values()), 307)
        self.assertTrue(
            all(
                expectation.round_ids == frozenset(range(1, 12))
                for expectation in profile.category_expectations.values()
            )
        )
        with self.assertRaises(TypeError):
            profile.category_expectations["primera"] = profiles.CategoryCompletenessExpectation(
                frozenset({1}), 1
            )

    def test_profile_construction_rejects_incomplete_or_malformed_expectations(self) -> None:
        base = dict(
            key="test",
            display_name="Test",
            slug="test",
            season=2026,
            parser_format=profiles.CURRENT_TABLE_FORMAT,
            parser_version=profiles.CURRENT_TABLE_VERSION,
            category_sources={"primera": "https://example.invalid/fixture"},
        )
        with self.assertRaisesRegex(ValueError, "exactly match"):
            profiles.CurrentFixtureSourceProfile(**base, category_expectations={})
        with self.assertRaisesRegex(ValueError, "round IDs"):
            profiles.CategoryCompletenessExpectation(frozenset(), 1)
        with self.assertRaisesRegex(ValueError, "fixture count"):
            profiles.CategoryCompletenessExpectation(frozenset({1}), 0)

    def test_unknown_profile_and_unsupported_format_fail_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unknown current fixture"):
            profiles.get_source_profile("unknown")

        unsupported = profiles.CurrentFixtureSourceProfile(
            key="future",
            display_name="Future",
            slug="future",
            season=2027,
            parser_format="current-table",
            parser_version=2,
            category_sources={"primera": "https://example.invalid/fixture"},
            category_expectations={
                "primera": profiles.CategoryCompletenessExpectation(frozenset({1, 2}), 6)
            },
        )
        with self.assertRaisesRegex(ValueError, "Unsupported current fixture parser"):
            importer.parse_profile_source(unsupported, "primera", SAMPLE_HTML)


class CurrentFixtureParserTests(unittest.TestCase):
    def test_production_profile_rejects_structurally_valid_partial_source(self) -> None:
        profile = profiles.get_source_profile("primavera-verano-2026")
        with self.assertRaisesRegex(importer.FixtureParseError, "Incomplete fixture rounds"):
            importer.parse_profile_source(profile, "primera", SAMPLE_HTML)

    def test_valid_rounds_dates_aliases_and_byes_are_preserved(self) -> None:
        rows = parsed_rows()
        plan = importer.build_category_plan(rows, 7, "primera")

        self.assertEqual(len(rows), 6)
        self.assertEqual({row.round_id for row in rows}, {1, 2})
        self.assertEqual(rows[0].date, "2026-04-06")
        self.assertEqual(rows[3].date, "2026-04-13")
        self.assertTrue(plan.valid, plan.issues)
        self.assertEqual(len(plan.fixtures), 6)
        self.assertEqual(
            [(item.local_id, item.visitor_id) for item in plan.fixtures if item.visitor_id is None],
            [(4, None), (1, None)],
        )
        self.assertEqual(plan.fixtures[0].visitor_id, 8)

    def test_utf8_cp1252_and_mojibake_names_resolve_to_authoritative_identity(self) -> None:
        self.assertIn("El Linqueño", importer.decode_current_html("El Linqueño".encode("utf-8")))
        self.assertIn("El Linqueño", importer.decode_current_html("El Linqueño".encode("cp1252")))
        self.assertEqual(importer.identity_text("EL LINQUEÃ‘O"), "EL LINQUENO")

        mojibake = SAMPLE_HTML.replace("El Linqueño", "El LinqueÃ‘o")
        plan = importer.build_category_plan(parsed_rows(mojibake), 7, "primera")
        self.assertTrue(plan.valid, plan.issues)
        self.assertIn(8, {item.local_id for item in plan.fixtures})

    def test_missing_section_empty_fixture_and_malformed_rows_fail(self) -> None:
        with self.assertRaisesRegex(importer.FixtureParseError, "FIXTURE COMPLETO"):
            parsed_rows(SAMPLE_HTML.replace("FIXTURE COMPLETO", "FIXTURE"))

        empty = SAMPLE_HTML.replace(
            '<tr><td>Argentino</td><td></td><td></td><td>El Linqueño</td></tr>',
            "",
        ).replace(
            '<tr><td>Atl. Pasteur</td><td></td><td></td><td>Atl. Roberts</td></tr>',
            "",
        ).replace(
            '<tr><td>CA. Pintense</td><td></td><td></td><td>LIBRE</td></tr>',
            "",
        ).replace(
            '<tr><td>El Linqueño</td><td></td><td></td><td>Atl Pasteur</td></tr>',
            "",
        ).replace(
            '<tr><td>Atl Roberts</td><td></td><td></td><td>C A Pintense</td></tr>',
            "",
        ).replace(
            '<tr><td>LIBRE</td><td></td><td></td><td>Argentino</td></tr>',
            "",
        )
        with self.assertRaisesRegex(importer.FixtureParseError, "No fixture rows"):
            parsed_rows(empty)

        malformed = SAMPLE_HTML.replace(
            '<tr><td>Argentino</td><td></td><td></td><td>El Linqueño</td></tr>',
            "<tr><td>Argentino</td><td></td><td></td></tr>",
        )
        with self.assertRaisesRegex(importer.FixtureParseError, "Malformed fixture row"):
            parsed_rows(malformed)

    def test_malformed_nonpositive_and_noncontiguous_rounds_fail(self) -> None:
        with self.assertRaisesRegex(importer.FixtureParseError, "nonpositive"):
            parsed_rows(SAMPLE_HTML.replace("FECHA: 1", "FECHA: 0"))
        with self.assertRaisesRegex(importer.FixtureParseError, "Malformed or nonpositive"):
            parsed_rows(SAMPLE_HTML.replace("FECHA: 1", "FECHA: PRIMERA"))
        with self.assertRaisesRegex(importer.FixtureParseError, "Noncontiguous"):
            parsed_rows(SAMPLE_HTML.replace("<td>2</td><td>13/04", "<td>3</td><td>13/04"))

    def test_unknown_club_duplicate_conflict_self_play_and_round_participation_block(self) -> None:
        base = parsed_rows()

        unknown = list(base)
        unknown[0] = importer.OfficialFixtureRow(4, "primera", 1, "2026-04-06", "Unknown", "El Linqueño")
        self.assertIn("Unknown club", "\n".join(importer.build_category_plan(unknown, 7, "primera").issues))

        duplicate = importer.build_category_plan([base[0], base[0]], 7, "primera")
        self.assertIn("Duplicate fixture key", "\n".join(duplicate.issues))

        reversed_row = importer.OfficialFixtureRow(
            99, "primera", 1, "2026-04-06", "El Linqueño", "Argentino"
        )
        conflict = importer.build_category_plan([base[0], reversed_row], 7, "primera")
        self.assertIn("Conflicting fixture rows", "\n".join(conflict.issues))

        self_play_row = importer.OfficialFixtureRow(
            99, "primera", 1, "2026-04-06", "Argentino", "ARGENTINO"
        )
        self_play = importer.build_category_plan([self_play_row], 7, "primera")
        self.assertIn("Self-play", "\n".join(self_play.issues))

        repeated_team = importer.OfficialFixtureRow(
            99, "primera", 1, "2026-04-06", "Argentino", "Atl. Roberts"
        )
        participation = importer.build_category_plan([base[0], repeated_team], 7, "primera")
        self.assertIn("Duplicate team participation", "\n".join(participation.issues))

    def test_unknown_category_fails_but_legacy_membership_does_not_constrain_profiles(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unknown configured category"):
            importer.build_category_plan(parsed_rows(), 7, "missing")

        row = importer.OfficialFixtureRow(
            1, "septima", 1, "2026-04-06", "Villa Francia", "San Martin"
        )
        plan = importer.build_category_plan([row], 7, "septima")
        self.assertTrue(plan.valid, plan.issues)
        self.assertEqual(
            {(fixture.local_id, fixture.visitor_id) for fixture in plan.fixtures},
            {(11, 10)},
        )

    def test_production_profile_row_count_is_not_limited_by_legacy_capacity(self) -> None:
        profile = profiles.get_source_profile("primavera-verano-2026")
        clubs = (
            "Argentino",
            "Atl. Pasteur",
            "Atl. Roberts",
            "CA. Pintense",
            "CASET",
            "Dep. Arenaza",
            "Dep. Gral Pinto",
            "El Linqueño",
            "Juventud Unida",
            "San Martin",
            "Villa Francia",
        )
        rows: list[importer.OfficialFixtureRow] = []
        source_row = 1
        for round_id in range(1, 12):
            round_clubs = clubs if round_id <= 8 else clubs[:10]
            for index in range(0, 10, 2):
                rows.append(
                    importer.OfficialFixtureRow(
                        source_row,
                        "octava",
                        round_id,
                        None,
                        round_clubs[index],
                        round_clubs[index + 1],
                    )
                )
                source_row += 1
            if round_id <= 8:
                rows.append(
                    importer.OfficialFixtureRow(
                        source_row,
                        "octava",
                        round_id,
                        None,
                        clubs[10],
                        "LIBRE",
                    )
                )
                source_row += 1

        importer.validate_category_completeness(
            profile, "octava", (row.round_id for row in rows), len(rows)
        )
        plan = importer.build_category_plan(rows, 7, "octava")
        self.assertTrue(plan.valid, plan.issues)
        self.assertEqual(len(plan.fixtures), 63)


class SelectionAndCliTests(unittest.TestCase):
    def test_all_profile_categories_are_the_deliberate_default(self) -> None:
        profile = profiles.get_source_profile("primavera-verano-2026")
        selected = importer.selected_sources(profile, [], [])
        self.assertEqual(tuple(selected), tuple(profile.category_sources))

    def test_source_overrides_are_validated_and_must_be_selected(self) -> None:
        profile = profiles.get_source_profile("primavera-verano-2026")
        selected = importer.selected_sources(
            profile,
            ["primera"],
            [f"primera={FIXTURE_PATH}"],
        )
        self.assertEqual(selected, {"primera": str(FIXTURE_PATH)})

        invalid_values = ("primera", "missing=x", "primera=ftp://example.test/a")
        for value in invalid_values:
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "CATEGORY=URL_OR_PATH|not a readable"):
                    importer.parse_source_overrides([value], profile)
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            importer.parse_source_overrides(
                [f"primera={FIXTURE_PATH}", f"primera={FIXTURE_PATH}"], profile
            )
        with self.assertRaisesRegex(ValueError, "unselected"):
            importer.selected_sources(
                profile,
                ["primera"],
                [f"septima={FIXTURE_PATH}"],
            )

    def test_profile_is_required_and_legacy_append_force_flag_is_absent(self) -> None:
        parser = importer.build_parser()
        with self.assertRaises(SystemExit):
            parser.parse_args(["--torneo-id", "7"])
        with self.assertRaises(SystemExit):
            parser.parse_args(["--profile", "primavera-verano-2026", "--force"])

        args = parser.parse_args(["--profile", "primavera-verano-2026", "--torneo-id", "7"])
        self.assertFalse(args.execute)
        self.assertFalse(args.replace_existing)

    def test_missing_tournament_id_is_rejected_even_with_active_environment(self) -> None:
        loader = mock.Mock(return_value=SAMPLE_HTML)
        client_factory = mock.Mock()
        with mock.patch.dict(os.environ, {"ACTIVE_TORNEO_ID": "7"}, clear=True):
            with self.assertRaises(SystemExit):
                run_compact_main(
                    ["--profile", "primavera-verano-2026"],
                    source_loader=loader,
                    client_factory=client_factory,
                )

        loader.assert_not_called()
        client_factory.assert_not_called()


class ExistingScopePolicyTests(unittest.TestCase):
    def test_new_tournament_is_inserted_inactive_from_profile_metadata(self) -> None:
        profile = profiles.get_source_profile("primavera-verano-2026")
        plan = importer.build_import_plan(
            source_plan(), empty_scope(), profile, replace_existing=False
        )

        self.assertTrue(plan.valid, plan.issues)
        self.assertEqual(plan.tournament_write.operation, "insert")
        self.assertEqual(
            plan.tournament_write.values,
            {
                "id": 7,
                "nombre": "Primavera/Verano 2026",
                "slug": "primavera-verano-2026",
                "temporada": 2026,
                "activo": False,
            },
        )

    def test_existing_tournament_update_preserves_active_state_and_accepts_metadata_overrides(self) -> None:
        profile = profiles.get_source_profile("primavera-verano-2026")
        existing = {"id": 7, "nombre": "Old", "slug": "old", "temporada": 2025, "activo": True}
        plan = importer.build_import_plan(
            source_plan(),
            empty_scope(tournament=existing),
            profile,
            replace_existing=False,
            tournament_name="Official 2026",
            slug="official-2026",
        )

        self.assertTrue(plan.valid, plan.issues)
        self.assertEqual(plan.tournament_write.operation, "update")
        self.assertEqual(
            plan.tournament_write.values,
            {"nombre": "Official 2026", "slug": "official-2026", "temporada": 2026},
        )
        self.assertNotIn("activo", plan.tournament_write.values)

    def test_existing_selected_fixtures_abort_by_default_without_append_path(self) -> None:
        profile = profiles.get_source_profile("primavera-verano-2026")
        plan = importer.build_import_plan(
            source_plan(),
            empty_scope(fixtures=[existing_fixture()]),
            profile,
            replace_existing=False,
        )
        self.assertFalse(plan.valid)
        self.assertIn("already contain partidos", "\n".join(plan.issues))
        self.assertEqual(plan.delete_category_ids, ())

    def test_safe_replacement_is_allowed_only_after_all_dependent_data_checks(self) -> None:
        profile = profiles.get_source_profile("primavera-verano-2026")
        safe = importer.build_import_plan(
            source_plan(),
            empty_scope(fixtures=[existing_fixture()]),
            profile,
            replace_existing=True,
        )
        self.assertTrue(safe.valid, safe.issues)
        self.assertEqual(safe.delete_category_ids, (1,))

        blocked_scopes = (
            empty_scope(fixtures=[existing_fixture(state="jugado")]),
            empty_scope(fixtures=[existing_fixture(local_goals=0, visitor_goals=0)]),
            empty_scope(
                fixtures=[existing_fixture()],
                positions=[{"id": 1, "torneo_id": 7, "categoria_id": 1}],
            ),
            empty_scope(
                fixtures=[existing_fixture()],
                lineups=[{"id": 1, "partido_id": 90}],
            ),
        )
        expected = ("played/result", "played/result", "positions", "lineups")
        for scope, message in zip(blocked_scopes, expected):
            with self.subTest(message=message):
                blocked = importer.build_import_plan(
                    source_plan(), scope, profile, replace_existing=True
                )
                self.assertFalse(blocked.valid)
                self.assertIn(message, "\n".join(blocked.issues))

    def test_scope_inspection_rejects_out_of_scope_data(self) -> None:
        client = FakeClient(fixtures=[existing_fixture()])
        scope = importer.inspect_existing_scope(client, 7, [1])
        self.assertEqual(len(scope.fixtures), 1)
        self.assertIn(("torneo_id", 7), client.reads[1][1])
        self.assertIn(("categoria_id", (1,)), client.reads[1][1])
        self.assertEqual(client.reads[1][2], (0, importer.INVENTORY_PAGE_SIZE - 1))
        paged_reads = [read for read in client.reads if read[2] is not None]
        self.assertEqual(
            {read[0] for read in paged_reads},
            {"partidos", "posiciones", "alineaciones"},
        )
        self.assertTrue(all(read[3] == ("id", False) for read in paged_reads))

        wrong_tournament = FakeClient(tournaments=[{"id": 8}])
        with self.assertRaisesRegex(RuntimeError, "outside the requested scope"):
            importer.inspect_existing_scope(wrong_tournament, 7, [1])

        outside = FakeClient(fixtures=[{**existing_fixture(), "categoria_id": 2}])
        with self.assertRaisesRegex(RuntimeError, "outside the selected scope"):
            importer.inspect_existing_scope(outside, 7, [1])


class InventoryPaginationTests(unittest.TestCase):
    def test_exact_count_pagination_accumulates_every_page(self) -> None:
        rows = [{"id": value} for value in range(1, 6)]
        client = FakeClient(fixtures=rows)

        inventory = importer._read_complete_inventory(
            client,
            table="partidos",
            columns="id",
            scope_query=lambda query: query.eq("torneo_id", 7),
            label="Fixture inventory",
            maximum_total=10,
            page_size=2,
        )

        self.assertEqual([row["id"] for row in inventory], [1, 2, 3, 4, 5])
        self.assertEqual(client.page_calls["partidos"], 3)
        self.assertEqual(
            [read[2] for read in client.reads],
            [(0, 1), (2, 3), (4, 5)],
        )
        self.assertTrue(all(read[1] == (("torneo_id", 7),) for read in client.reads))
        self.assertTrue(all(read[3] == ("id", False) for read in client.reads))

    def test_server_cap_smaller_than_requested_page_still_reads_complete_scope(self) -> None:
        fixtures = [existing_fixture(90 + index) for index in range(5)]
        client = FakeClient(fixtures=fixtures, server_caps={"partidos": 2})

        scope = importer.inspect_existing_scope(client, 7, [1])

        self.assertEqual(len(scope.fixtures), 5)
        self.assertEqual(client.page_calls["partidos"], 3)
        fixture_reads = [read for read in client.reads if read[0] == "partidos"]
        self.assertTrue(all(read[1] == fixture_reads[0][1] for read in fixture_reads))
        self.assertTrue(all(read[3] == ("id", False) for read in fixture_reads))
        self.assertEqual([read[2][0] for read in fixture_reads], [0, 2, 4])

    def test_missing_changed_and_underreported_exact_counts_fail_closed(self) -> None:
        missing = FakeClient(counts={"partidos": None})
        with self.assertRaisesRegex(RuntimeError, "exact count is missing or malformed"):
            importer.inspect_existing_scope(missing, 7, [1])

        changing = FakeClient(
            fixtures=[existing_fixture(90 + index) for index in range(3)],
            server_caps={"partidos": 2},
            counts={"partidos": [3, 4]},
        )
        with self.assertRaisesRegex(RuntimeError, "exact count changed"):
            importer.inspect_existing_scope(changing, 7, [1])

        underreported = FakeClient(
            fixtures=[existing_fixture(90), existing_fixture(91)],
            counts={"partidos": 1},
        )
        with self.assertRaisesRegex(RuntimeError, "rows exceed exact count"):
            importer.inspect_existing_scope(underreported, 7, [1])

    def test_incomplete_inconsistent_and_repeated_pages_fail_closed(self) -> None:
        fixtures = [existing_fixture(90 + index) for index in range(5)]
        incomplete = FakeClient(
            fixtures=fixtures,
            counts={"partidos": 3},
            scripted_pages={"partidos": [fixtures[:2], []]},
        )
        with self.assertRaisesRegex(RuntimeError, "ended before exact count"):
            importer.inspect_existing_scope(incomplete, 7, [1])

        inconsistent = FakeClient(
            fixtures=fixtures,
            counts={"partidos": 5},
            scripted_pages={"partidos": [fixtures[:2], fixtures[2:3], fixtures[3:]]},
        )
        with self.assertRaisesRegex(RuntimeError, "inconsistent short page"):
            importer.inspect_existing_scope(inconsistent, 7, [1])

        repeated = FakeClient(
            fixtures=fixtures[:3],
            counts={"partidos": 3},
            scripted_pages={"partidos": [fixtures[:2], [fixtures[1]]]},
        )
        with self.assertRaisesRegex(RuntimeError, "repeated row id"):
            importer.inspect_existing_scope(repeated, 7, [1])

    def test_maximum_total_is_independent_from_page_size(self) -> None:
        client = FakeClient(counts={"partidos": importer.FIXTURE_INVENTORY_MAX_TOTAL + 1})
        with self.assertRaisesRegex(RuntimeError, "exceeds safety maximum"):
            importer.inspect_existing_scope(client, 7, [1])
        self.assertEqual(client.page_calls["partidos"], 1)

    def test_fixture_position_and_lineup_identities_are_strictly_validated(self) -> None:
        malformed_fixtures = (
            {**existing_fixture(), "id": 0},
            {**existing_fixture(), "local_id": None},
            {**existing_fixture(), "visitante_id": True},
            {**existing_fixture(), "fecha_id": -1},
        )
        for row in malformed_fixtures:
            with self.subTest(fixture=row):
                with self.assertRaisesRegex(RuntimeError, "Fixture inventory|fixture inventory"):
                    importer.inspect_existing_scope(FakeClient(fixtures=[row]), 7, [1])
        with self.assertRaisesRegex(RuntimeError, "repeated row id"):
            importer.inspect_existing_scope(
                FakeClient(fixtures=[existing_fixture(), existing_fixture()]), 7, [1]
            )

        valid_fixture = existing_fixture()
        malformed_positions = (
            {"id": 0, "torneo_id": 7, "categoria_id": 1, "club_id": 1},
            {"id": 1, "torneo_id": 7, "categoria_id": 1, "club_id": None},
            {"id": 1, "torneo_id": 7, "categoria_id": True, "club_id": 1},
        )
        for row in malformed_positions:
            with self.subTest(position=row):
                with self.assertRaisesRegex(RuntimeError, "[Pp]osition inventory"):
                    importer.inspect_existing_scope(
                        FakeClient(fixtures=[valid_fixture], positions=[row]), 7, [1]
                    )
        duplicate_positions = [
            {"id": 1, "torneo_id": 7, "categoria_id": 1, "club_id": 1},
            {"id": 1, "torneo_id": 7, "categoria_id": 1, "club_id": 2},
        ]
        with self.assertRaisesRegex(RuntimeError, "repeated row id"):
            importer.inspect_existing_scope(
                FakeClient(fixtures=[valid_fixture], positions=duplicate_positions), 7, [1]
            )

        malformed_lineups = (
            {"id": 0, "partido_id": 90},
            {"id": 1, "partido_id": None},
            {"id": True, "partido_id": 90},
        )
        for row in malformed_lineups:
            with self.subTest(lineup=row):
                with self.assertRaisesRegex(RuntimeError, "[Ll]ineup inventory"):
                    importer.inspect_existing_scope(
                        FakeClient(fixtures=[valid_fixture], lineups=[row]), 7, [1]
                    )
        duplicate_lineups = [{"id": 1, "partido_id": 90}, {"id": 1, "partido_id": 90}]
        with self.assertRaisesRegex(RuntimeError, "repeated row id"):
            importer.inspect_existing_scope(
                FakeClient(fixtures=[valid_fixture], lineups=duplicate_lineups), 7, [1]
            )

    def test_bye_inventory_accepts_exactly_one_positive_team_side(self) -> None:
        valid_byes = (
            existing_fixture(state="libre", local_id=1, visitor_id=None),
            existing_fixture(state="libre", local_id=None, visitor_id=8),
        )
        for bye in valid_byes:
            with self.subTest(bye=bye):
                client = FakeClient(fixtures=[bye])
                scope = importer.inspect_existing_scope(client, 7, [1])
                self.assertEqual(scope.fixtures, (bye,))
                lineup_reads = [read for read in client.reads if read[0] == "alineaciones"]
                self.assertEqual(len(lineup_reads), 1)
                self.assertEqual(lineup_reads[0][1], (("partido_id", (90,)),))

    def test_bye_and_non_bye_team_side_invariants_fail_closed(self) -> None:
        invalid = (
            existing_fixture(state="libre", local_id=None, visitor_id=None),
            existing_fixture(state="libre", local_id=1, visitor_id=8),
            existing_fixture(state="libre", local_id=True, visitor_id=None),
            existing_fixture(state="libre", local_id="1", visitor_id=None),
            existing_fixture(state="libre", local_id=0, visitor_id=None),
            existing_fixture(state="libre", local_id=-1, visitor_id=None),
            existing_fixture(state="programado", local_id=None, visitor_id=8),
            existing_fixture(state="jugado", local_id=1, visitor_id=None),
            existing_fixture(state="postergado", local_id=False, visitor_id=8),
        )
        for row in invalid:
            with self.subTest(row=row):
                with self.assertRaisesRegex(RuntimeError, "fixture inventory|Fixture .*libre"):
                    importer.inspect_existing_scope(FakeClient(fixtures=[row]), 7, [1])

    def test_existing_bye_aborts_by_default_and_uses_normal_safe_replacement_rules(self) -> None:
        bye = existing_fixture(state="libre", local_id=4, visitor_id=None)
        client = FakeClient(fixtures=[bye])
        existing = importer.inspect_existing_scope(client, 7, [1])
        profile = profiles.get_source_profile("primavera-verano-2026")

        default_plan = importer.build_import_plan(
            source_plan(), existing, profile, replace_existing=False
        )
        self.assertFalse(default_plan.valid)
        self.assertIn("already contain partidos", "\n".join(default_plan.issues))

        replacement = importer.build_import_plan(
            source_plan(), existing, profile, replace_existing=True
        )
        self.assertTrue(replacement.valid, replacement.issues)
        self.assertEqual(replacement.delete_category_ids, (1,))

        dependent_client = FakeClient(
            fixtures=[bye],
            lineups=[{"id": 5, "partido_id": 90}],
        )
        dependent_scope = importer.inspect_existing_scope(dependent_client, 7, [1])
        blocked = importer.build_import_plan(
            source_plan(), dependent_scope, profile, replace_existing=True
        )
        self.assertFalse(blocked.valid)
        self.assertIn("lineups", "\n".join(blocked.issues))

    def test_dry_run_with_existing_bye_inspects_scope_without_mutation(self) -> None:
        client = FakeClient(
            fixtures=[existing_fixture(state="libre", local_id=4, visitor_id=None)]
        )
        output = io.StringIO()
        exit_code = run_compact_main(
            [
                "--profile",
                "primavera-verano-2026",
                "--torneo-id",
                "7",
                "--category",
                "primera",
                "--source",
                f"primera={FIXTURE_PATH}",
            ],
            source_loader=lambda source, timeout: SAMPLE_HTML,
            client_factory=lambda: client,
            stdout=output,
        )
        self.assertEqual(exit_code, 1)
        self.assertIn("already contain partidos", output.getvalue())
        self.assertEqual(client.mutation_attempts, 0)

    def test_unknown_fixture_state_fails_and_complete_safe_replacement_succeeds(self) -> None:
        unknown = FakeClient(fixtures=[existing_fixture(state="cancelado")])
        with self.assertRaisesRegex(RuntimeError, "unsupported estado"):
            importer.inspect_existing_scope(unknown, 7, [1])

        client = FakeClient(
            tournaments=[
                {"id": 7, "nombre": "Old", "slug": "old", "temporada": 2025, "activo": True}
            ],
            fixtures=[existing_fixture()],
        )
        existing = importer.inspect_existing_scope(client, 7, [1])
        plan = importer.build_import_plan(
            source_plan(),
            existing,
            profiles.get_source_profile("primavera-verano-2026"),
            replace_existing=True,
        )
        self.assertTrue(plan.valid, plan.issues)


class ExecutionTests(unittest.TestCase):
    def test_execute_new_import_uses_only_inactive_metadata_and_validated_rows(self) -> None:
        profile = profiles.get_source_profile("primavera-verano-2026")
        plan = importer.build_import_plan(source_plan(), empty_scope(), profile, replace_existing=False)
        client = FakeClient()

        counts = importer.execute_import_plan(client, plan)

        self.assertEqual(counts["tournaments_inserted"], 1)
        self.assertEqual(counts["fixtures_inserted"], 6)
        self.assertEqual([item[1] for item in client.mutations], ["insert", "insert"])
        tournament_payload = client.mutations[0][2]
        self.assertIs(tournament_payload["activo"], False)
        fixture_rows = client.mutations[1][2]
        self.assertTrue(all(row["torneo_id"] == 7 for row in fixture_rows))
        self.assertTrue(all(row["categoria_id"] == 1 for row in fixture_rows))

    def test_safe_replacement_deletes_and_inserts_only_selected_scope(self) -> None:
        profile = profiles.get_source_profile("primavera-verano-2026")
        existing = {"id": 7, "nombre": "Old", "slug": "old", "temporada": 2025, "activo": True}
        plan = importer.build_import_plan(
            source_plan(),
            empty_scope(tournament=existing, fixtures=[existing_fixture()]),
            profile,
            replace_existing=True,
        )
        client = FakeClient()

        counts = importer.execute_import_plan(client, plan)

        self.assertEqual(counts["categories_deleted"], 1)
        tournament_update = client.mutations[0]
        self.assertEqual(tournament_update[:2], ("torneos", "update"))
        self.assertNotIn("activo", tournament_update[2])
        self.assertEqual(tournament_update[3], (("id", 7),))
        fixture_delete = client.mutations[1]
        self.assertEqual(fixture_delete[:2], ("partidos", "delete"))
        self.assertEqual(
            fixture_delete[3],
            (("torneo_id", 7), ("categoria_id", 1)),
        )
        fixture_insert = client.mutations[2]
        self.assertEqual(fixture_insert[:2], ("partidos", "insert"))
        self.assertTrue(all(row["torneo_id"] == 7 for row in fixture_insert[2]))
        self.assertTrue(all(row["categoria_id"] == 1 for row in fixture_insert[2]))
        self.assertFalse(any(item[0] == "torneos" and item[1] == "update" and "activo" in item[2] for item in client.mutations))

    def test_invalid_plan_never_mutates_and_write_errors_propagate(self) -> None:
        profile = profiles.get_source_profile("primavera-verano-2026")
        invalid = importer.build_import_plan(
            source_plan(),
            empty_scope(fixtures=[existing_fixture()]),
            profile,
            replace_existing=False,
        )
        client = FakeClient()
        with self.assertRaisesRegex(ValueError, "invalid or empty"):
            importer.execute_import_plan(client, invalid)
        self.assertEqual(client.mutation_attempts, 0)

        failing = FakeClient(write_error=RuntimeError("database write failed"))
        valid = importer.build_import_plan(source_plan(), empty_scope(), profile, replace_existing=False)
        with self.assertRaisesRegex(RuntimeError, "database write failed"):
            importer.execute_import_plan(failing, valid)
        self.assertEqual(failing.mutation_attempts, 1)

    def test_dry_run_reads_scope_but_performs_zero_mutations(self) -> None:
        client = FakeClient()
        output = io.StringIO()
        exit_code = run_compact_main(
            [
                "--profile",
                "primavera-verano-2026",
                "--torneo-id",
                "7",
                "--category",
                "primera",
                "--source",
                f"primera={FIXTURE_PATH}",
            ],
            client_factory=lambda: client,
            source_loader=lambda source, timeout: SAMPLE_HTML,
            stdout=output,
        )

        self.assertEqual(exit_code, 0, output.getvalue())
        self.assertIn("Dry run only", output.getvalue())
        self.assertIn("non-transactional", output.getvalue())
        self.assertGreater(len(client.reads), 0)
        self.assertEqual(client.mutation_attempts, 0)

    def test_source_validation_and_database_errors_are_visible_and_nonzero(self) -> None:
        invalid_html = SAMPLE_HTML.replace("El Linqueño", "Unknown Club")
        client_factory = mock.Mock()
        output = io.StringIO()
        invalid_code = run_compact_main(
            [
                "--profile",
                "primavera-verano-2026",
                "--torneo-id",
                "7",
                "--category",
                "primera",
                "--source",
                f"primera={FIXTURE_PATH}",
            ],
            source_loader=lambda source, timeout: invalid_html,
            client_factory=client_factory,
            stdout=output,
        )
        self.assertEqual(invalid_code, 1)
        self.assertIn("Unknown club", output.getvalue())
        client_factory.assert_not_called()

        error_output = io.StringIO()
        db_error_code = run_compact_main(
            [
                "--profile",
                "primavera-verano-2026",
                "--torneo-id",
                "7",
                "--category",
                "primera",
                "--source",
                f"primera={FIXTURE_PATH}",
            ],
            source_loader=lambda source, timeout: SAMPLE_HTML,
            client_factory=lambda: FakeClient(read_error=RuntimeError("database read failed")),
            stderr=error_output,
        )
        self.assertEqual(db_error_code, 2)
        self.assertIn("database read failed", error_output.getvalue())

    def test_execute_failure_returns_nonzero_without_suppressing_error(self) -> None:
        error_output = io.StringIO()
        client = FakeClient(write_error=RuntimeError("database write failed"))
        exit_code = run_compact_main(
            [
                "--profile",
                "primavera-verano-2026",
                "--torneo-id",
                "7",
                "--category",
                "primera",
                "--source",
                f"primera={FIXTURE_PATH}",
                "--execute",
            ],
            source_loader=lambda source, timeout: SAMPLE_HTML,
            client_factory=lambda: client,
            stderr=error_output,
        )
        self.assertEqual(exit_code, 2)
        self.assertIn("database write failed", error_output.getvalue())
        self.assertEqual(client.mutation_attempts, 1)


if __name__ == "__main__":
    unittest.main()
