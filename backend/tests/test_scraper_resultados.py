"""Network-free tests for safe result ingestion and projected standings."""

from __future__ import annotations

import io
import os
import subprocess
import sys
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = BACKEND_DIR.parent
SCRIPTS_DIR = BACKEND_DIR / "scripts"
FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "resultados_sample.html"
sys.path.insert(0, str(SCRIPTS_DIR))

import scraper_resultados as results  # noqa: E402


FIXTURES = [
    {
        "id": 101,
        "torneo_id": 2,
        "categoria_id": 1,
        "local_id": 1,
        "visitante_id": 8,
        "fecha_id": 3,
        "dia": "2026-04-12",
        "estado": "programado",
        "goles_local": None,
        "goles_visitante": None,
    },
    {
        "id": 102,
        "torneo_id": 2,
        "categoria_id": 1,
        "local_id": 2,
        "visitante_id": 4,
        "fecha_id": 3,
        "dia": "2026-04-12",
        "estado": "jugado",
        "goles_local": 0,
        "goles_visitante": 0,
    },
    {
        "id": 103,
        "torneo_id": 2,
        "categoria_id": 1,
        "local_id": 4,
        "visitante_id": 1,
        "fecha_id": 2,
        "dia": "2026-04-05",
        "estado": "jugado",
        "goles_local": 3,
        "goles_visitante": 1,
    },
    {
        "id": 104,
        "torneo_id": 2,
        "categoria_id": 1,
        "local_id": 6,
        "visitante_id": 1,
        "fecha_id": 4,
        "dia": "2026-04-19",
        "estado": "programado",
        "goles_local": None,
        "goles_visitante": None,
    },
]


def official_rows() -> list[results.OfficialResult]:
    return results.parse_results_html(FIXTURE_PATH.read_text(encoding="utf-8"), "primera")


def fixture_records(values=FIXTURES) -> list[results.FixtureRecord]:
    return [results.FixtureRecord.from_mapping(item) for item in values]


class FakeQuery:
    def __init__(self, client: "FakeClient", table: str) -> None:
        self.client = client
        self.table = table
        self.operation = "select"
        self.values = None
        self.filters: list[tuple[str, object]] = []
        self.in_filters: list[tuple[str, tuple[object, ...]]] = []

    def select(self, columns: str) -> "FakeQuery":
        self.client.selected_columns[self.table] = columns
        return self

    def update(self, values: dict[str, object]) -> "FakeQuery":
        self.operation = "update"
        self.values = values
        return self

    def insert(self, values: dict[str, object]) -> "FakeQuery":
        self.operation = "insert"
        self.values = values
        return self

    def eq(self, column: str, value: object) -> "FakeQuery":
        self.filters.append((column, value))
        return self

    def in_(self, column: str, values: list[object]) -> "FakeQuery":
        self.in_filters.append((column, tuple(values)))
        return self

    def limit(self, value: int) -> "FakeQuery":
        self.client.limits[self.table] = value
        return self

    def execute(self) -> SimpleNamespace:
        if self.operation != "select":
            self.client.mutation_attempts += 1
            if self.client.write_error is not None:
                raise self.client.write_error
            self.client.executed_mutations.append(
                (self.table, self.operation, self.values, tuple(self.filters))
            )
            return SimpleNamespace(data=[{"id": 1}])

        self.client.reads.append(
            (self.table, tuple(self.filters), tuple(self.in_filters))
        )
        data = self.client.fixtures if self.table == "partidos" else self.client.positions
        return SimpleNamespace(data=list(data))


class FakeClient:
    def __init__(
        self,
        fixtures=FIXTURES,
        positions=(),
        write_error: Exception | None = None,
    ) -> None:
        self.fixtures = fixtures
        self.positions = positions
        self.write_error = write_error
        self.mutation_attempts = 0
        self.executed_mutations: list[tuple[object, ...]] = []
        self.reads: list[tuple[object, ...]] = []
        self.selected_columns: dict[str, str] = {}
        self.limits: dict[str, int] = {}

    def table(self, name: str) -> FakeQuery:
        if name not in {"partidos", "posiciones"}:
            raise AssertionError(f"Unexpected table: {name}")
        return FakeQuery(self, name)


class ResultParsingTests(unittest.TestCase):
    def test_parses_latest_round_date_scores_and_authoritative_aliases(self) -> None:
        rows = official_rows()

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0].round_id, 3)
        self.assertEqual(rows[0].date, "2026-04-12")
        self.assertEqual((rows[0].local_id, rows[0].visitor_id), (1, 8))
        self.assertEqual((rows[0].local_goals, rows[0].visitor_goals), (2, 1))
        self.assertEqual((rows[1].local_id, rows[1].visitor_id), (2, 4))
        self.assertNotIn("VILLA FRANCIA", [row.local for row in rows])

    def test_parses_nested_official_results_table_without_flattening_rows(self) -> None:
        html = """
        <table class="outer-wrapper">
          <tr><td>
            <table class="results">
              <tr><td colspan="4">ÚLTIMOS ENCUENTROS</td></tr>
              <tr><td colspan="4">FECHA 3 - 12/04/2026</td></tr>
              <tr><th>LOCAL</th><th>GL</th><th>GV</th><th>VISITANTE</th></tr>
              <tr><td>Argentino</td><td>2</td><td>1</td><td>El Linqueño</td></tr>
              <tr><td>Atl. Pasteur</td><td></td><td></td><td>CA. Pintense</td></tr>
              <tr><td>LIBRE</td><td></td><td></td><td>Villa Francia</td></tr>
              <tr>
                <td></td><td></td><td></td><td></td><td></td>
                <td>Argentino</td><td>6</td><td>4</td>
              </tr>
              <tr><td colspan="8">PRÓXIMA: SEGUNDA FECHA</td></tr>
              <tr><td>Villa Francia</td><td></td><td></td><td>Argentino</td></tr>
              <tr><th>LOCAL</th><th>GL</th><th>GV</th><th>VISITANTE</th></tr>
              <tr><td>Argentino</td><td>2</td><td>1</td><td>El Linqueño</td></tr>
            </table>
          </td></tr>
        </table>
        <table>
          <tr><td colspan="4">ÚLTIMOS ENCUENTROS</td></tr>
          <tr><td colspan="4">FECHA 2 - 05/04/2026</td></tr>
          <tr><th>LOCAL</th><th>GL</th><th>GV</th><th>VISITANTE</th></tr>
          <tr><td>Villa Francia</td><td>9</td><td>9</td><td>Argentino</td></tr>
        </table>
        """

        rows = results.parse_results_html(html, "primera")

        self.assertEqual(len(rows), 2)
        self.assertEqual(
            (rows[0].category_key, rows[0].category_id, rows[0].round_id, rows[0].date),
            ("primera", 1, 3, "2026-04-12"),
        )
        self.assertEqual(
            (rows[0].local, rows[0].local_goals, rows[0].visitor_goals, rows[0].visitor),
            ("ARGENTINO", 2, 1, "EL LINQUEÑO"),
        )
        self.assertEqual(
            (rows[1].local, rows[1].local_goals, rows[1].visitor_goals, rows[1].visitor),
            ("ATL. PASTEUR", None, None, "CA. PINTENSE"),
        )
        self.assertNotIn("LIBRE", {row.local for row in rows})
        self.assertNotIn("VILLA FRANCIA", {row.local for row in rows})

    def test_score_validation_rejects_signed_decimal_and_mixed_values(self) -> None:
        self.assertEqual(results.parse_score(" 12 "), 12)
        for value in ("", "-1", "1.0", "2 goals", "+3"):
            with self.subTest(value=value):
                self.assertIsNone(results.parse_score(value))

    def test_malformed_score_is_retained_for_blocking_validation(self) -> None:
        html = FIXTURE_PATH.read_text(encoding="utf-8").replace(
            "<td>2</td><td>1</td>", "<td>2x</td><td>1</td>", 1
        )

        row = results.parse_results_html(html, "primera")[0]
        plan = results.build_result_plan([row], fixture_records(), 2)

        self.assertIsNone(row.local_goals)
        self.assertFalse(plan.valid)
        self.assertTrue(any("Malformed score" in issue for issue in plan.issues))

    def test_incomplete_or_missing_team_result_rows_fail_explicitly(self) -> None:
        original = FIXTURE_PATH.read_text(encoding="utf-8")
        complete_row = (
            "<tr><td>Argentino</td><td>2</td><td>1</td>"
            "<td>El Linqueño</td></tr>"
        )
        incomplete_rows = (
            "<tr><td>Argentino</td><td>2</td><td>1</td></tr>",
            "<tr><td>Argentino</td><td>2</td><td>1</td><td></td></tr>",
        )

        for incomplete_row in incomplete_rows:
            with self.subTest(incomplete_row=incomplete_row):
                html = original.replace(complete_row, incomplete_row, 1)
                with self.assertRaisesRegex(results.ResultParseError, "Incomplete|missing"):
                    results.parse_results_html(html, "primera")

    def test_missing_supported_table_is_an_explicit_failure(self) -> None:
        with self.assertRaisesRegex(results.ResultParseError, "ULTIMOS ENCUENTROS"):
            results.parse_results_html("<table><tr><td>other</td></tr></table>", "primera")


class ResultPlanningTests(unittest.TestCase):
    def test_unique_matching_plans_only_changed_results(self) -> None:
        plan = results.build_result_plan(official_rows(), fixture_records(), 2)

        self.assertTrue(plan.valid)
        self.assertEqual(plan.matched_target_ids, (101, 102))
        self.assertEqual([entry.target_id for entry in plan.entries], [101])
        self.assertEqual(plan.entries[0].values["estado"], "jugado")

    def test_missing_and_ambiguous_targets_block_the_plan(self) -> None:
        rows = official_rows()
        missing = results.build_result_plan(rows, fixture_records(FIXTURES[1:]), 2)
        duplicate = {**FIXTURES[0], "id": 999}
        ambiguous = results.build_result_plan(
            rows, fixture_records([*FIXTURES, duplicate]), 2
        )

        self.assertFalse(missing.valid)
        self.assertTrue(any("Missing fixture target" in issue for issue in missing.issues))
        self.assertFalse(ambiguous.valid)
        self.assertTrue(any("Ambiguous fixture target" in issue for issue in ambiguous.issues))

    def test_duplicate_and_conflicting_official_rows_are_blocking(self) -> None:
        row = official_rows()[0]
        duplicate = results.build_result_plan([row, row], fixture_records(), 2)
        conflicting = results.build_result_plan(
            [row, replace(row, local_goals=7)], fixture_records(), 2
        )

        self.assertFalse(duplicate.valid)
        self.assertTrue(any("matched more than once" in issue for issue in duplicate.issues))
        self.assertFalse(conflicting.valid)
        self.assertTrue(any("Conflicting official rows" in issue for issue in conflicting.issues))

    def test_unknown_club_and_category_are_blocking(self) -> None:
        row = replace(
            official_rows()[0],
            category_raw="Reserva",
            category_key=None,
            category_id=None,
            local="UNKNOWN CLUB",
            local_id=None,
        )

        plan = results.build_result_plan([row], fixture_records(), 2)

        self.assertFalse(plan.valid)
        self.assertTrue(any("Unknown category" in issue for issue in plan.issues))
        self.assertTrue(any("Unknown local club" in issue for issue in plan.issues))

    def test_overlay_changes_only_planned_fixture_snapshot(self) -> None:
        fixtures = fixture_records()
        plan = results.build_result_plan(official_rows(), fixtures, 2)

        projected = results.overlay_planned_results(fixtures, plan)

        self.assertEqual(fixtures[0].state, "programado")
        self.assertEqual(projected[0].state, "jugado")
        self.assertEqual((projected[0].local_goals, projected[0].visitor_goals), (2, 1))
        self.assertEqual(projected[1], fixtures[1])


class StandingsTests(unittest.TestCase):
    def test_participants_come_from_fixture_even_when_absent_from_official_rows(self) -> None:
        fixtures = fixture_records()
        plan = results.build_result_plan(official_rows(), fixtures, 2)
        projected = results.overlay_planned_results(fixtures, plan)

        participants = results.derive_participants(projected, [1])
        projection = results.calculate_projected_standings(projected, 2, [1])

        self.assertIn(6, participants[1])
        omitted = next(row for row in projection.rows if row.club_id == 6)
        self.assertEqual((omitted.pj, omitted.pts, omitted.dif), (0, 0, 0))

    def test_calculates_wins_draws_losses_difference_form_and_tie_order(self) -> None:
        raw = [
            {**FIXTURES[0], "id": 1, "local_id": 1, "visitante_id": 2, "fecha_id": 1, "estado": "jugado", "goles_local": 2, "goles_visitante": 0},
            {**FIXTURES[0], "id": 2, "local_id": 3, "visitante_id": 4, "fecha_id": 1, "estado": "jugado", "goles_local": 1, "goles_visitante": 1},
            {**FIXTURES[0], "id": 3, "local_id": 1, "visitante_id": 3, "fecha_id": 2, "estado": "jugado", "goles_local": 0, "goles_visitante": 3},
            {**FIXTURES[0], "id": 4, "local_id": 2, "visitante_id": 4, "fecha_id": 2, "estado": "jugado", "goles_local": 2, "goles_visitante": 2},
            {**FIXTURES[0], "id": 5, "local_id": 1, "visitante_id": 4, "fecha_id": 3, "estado": "jugado", "goles_local": 1, "goles_visitante": 1},
            {**FIXTURES[0], "id": 6, "local_id": 5, "visitante_id": 6, "fecha_id": 4, "estado": "programado", "goles_local": None, "goles_visitante": None},
        ]

        projection = results.calculate_projected_standings(fixture_records(raw), 2, [1])
        by_club = {row.club_id: row for row in projection.rows}

        self.assertFalse(projection.issues)
        self.assertEqual([row.club_id for row in projection.rows[:4]], [3, 1, 4, 2])
        self.assertEqual(
            (by_club[1].pj, by_club[1].pg, by_club[1].pe, by_club[1].pp),
            (3, 1, 1, 1),
        )
        self.assertEqual((by_club[1].gf, by_club[1].gc, by_club[1].dif), (3, 4, -1))
        self.assertEqual(by_club[1].pts, 4)
        self.assertEqual(by_club[1].ultimos_5, ("G", "P", "E"))
        self.assertEqual([row.club_id for row in projection.rows[-2:]], [5, 6])

    def test_played_fixture_with_missing_participant_blocks_position_planning(self) -> None:
        invalid_fixture = {
            **FIXTURES[0],
            "id": 200,
            "local_id": None,
            "visitante_id": 8,
            "estado": "jugado",
            "goles_local": 1,
            "goles_visitante": 0,
        }
        fixtures = fixture_records([*FIXTURES, invalid_fixture])

        projection = results.calculate_projected_standings(fixtures, 2, [1])
        operation = results.build_operation_plan(
            official_rows(), fixtures, [], 2, ["primera"], [1]
        )

        self.assertTrue(any("missing participant identity" in issue for issue in projection.issues))
        self.assertFalse(operation.valid)
        self.assertEqual(operation.position_actions, ())
        client = FakeClient()
        with self.assertRaisesRegex(ValueError, "invalid result operation plan"):
            results.execute_operation_plan(client, operation)
        self.assertEqual(client.mutation_attempts, 0)

    def test_position_plan_updates_inserts_and_blocks_stale_rows_without_delete(self) -> None:
        projection = results.calculate_projected_standings(fixture_records(), 2, [1])
        first = projection.rows[0]
        existing = [
            {
                "id": 90,
                "torneo_id": 2,
                "categoria_id": 1,
                "club_id": first.club_id,
                **{**first.values(), "pts": 999},
            },
            {
                "id": 91,
                "torneo_id": 2,
                "categoria_id": 1,
                "club_id": 999,
                "pts": 0,
                "pj": 0,
                "pg": 0,
                "pe": 0,
                "pp": 0,
                "gf": 0,
                "gc": 0,
                "dif": 0,
                "ultimos_5": [],
            },
        ]

        plan = results.build_position_plan(projection.rows, existing, 2, [1])

        self.assertTrue(any(action.operation == "update" for action in plan.actions))
        self.assertTrue(any(action.operation == "insert" for action in plan.actions))
        self.assertTrue(any("Stale position row" in issue for issue in plan.issues))
        self.assertNotIn("delete", {action.operation for action in plan.actions})

    def test_duplicate_existing_position_rows_are_rejected(self) -> None:
        projection = results.calculate_projected_standings(fixture_records(), 2, [1])
        standing = projection.rows[0]
        existing = {
            "id": 90,
            "torneo_id": 2,
            "categoria_id": standing.category_id,
            "club_id": standing.club_id,
            **standing.values(),
        }

        plan = results.build_position_plan(
            projection.rows, [existing, {**existing, "id": 91}], 2, [1]
        )

        self.assertTrue(any("Duplicate existing position target" in issue for issue in plan.issues))

    def test_existing_positions_without_positive_row_ids_block_planning(self) -> None:
        projection = results.calculate_projected_standings(fixture_records(), 2, [1])
        standing = projection.rows[0]
        base = {
            "torneo_id": 2,
            "categoria_id": standing.category_id,
            "club_id": standing.club_id,
            **standing.values(),
        }
        invalid_ids = ("missing", None, "not-an-id", 0, -4)

        for invalid_id in invalid_ids:
            with self.subTest(invalid_id=invalid_id):
                existing = dict(base)
                if invalid_id != "missing":
                    existing["id"] = invalid_id
                plan = results.build_position_plan(
                    projection.rows, [existing], 2, [1]
                )
                self.assertTrue(
                    any("position id" in issue for issue in plan.issues),
                    plan.issues,
                )

    def test_position_actions_enforce_update_ids_and_preserve_inserts(self) -> None:
        projection = results.calculate_projected_standings(fixture_records(), 2, [1])
        insert_plan = results.build_position_plan(projection.rows, [], 2, [1])

        self.assertFalse(insert_plan.issues)
        self.assertTrue(insert_plan.actions)
        self.assertTrue(all(action.operation == "insert" for action in insert_plan.actions))
        self.assertTrue(all(action.existing_id is None for action in insert_plan.actions))
        with self.assertRaisesRegex(ValueError, "positive existing row ID"):
            results.PositionAction(
                operation="update",
                tournament_id=2,
                category_id=1,
                club_id=1,
                values={},
            )
        with self.assertRaisesRegex(ValueError, "cannot have an existing row ID"):
            results.PositionAction(
                operation="insert",
                tournament_id=2,
                category_id=1,
                club_id=1,
                values={},
                existing_id=10,
            )


class InventorySafetyTests(unittest.TestCase):
    def test_inventory_reads_are_tournament_category_scoped_and_bounded(self) -> None:
        client = FakeClient()

        fixtures = results.read_fixture_inventory(client, 2, [1])
        positions = results.read_position_inventory(client, 2, [1])

        self.assertEqual(len(fixtures), len(FIXTURES))
        self.assertEqual(positions, [])
        for _, filters, in_filters in client.reads:
            self.assertIn(("torneo_id", 2), filters)
            self.assertIn(("categoria_id", (1,)), in_filters)
        self.assertEqual(client.limits["partidos"], results.FIXTURE_INVENTORY_LIMIT)
        self.assertEqual(client.limits["posiciones"], results.POSITION_INVENTORY_LIMIT)

    def test_position_inventory_rejects_rows_returned_outside_requested_scope(self) -> None:
        for out_of_scope in (
            {"id": 1, "torneo_id": 3, "categoria_id": 1},
            {"id": 2, "torneo_id": 2, "categoria_id": 2},
        ):
            with self.subTest(out_of_scope=out_of_scope):
                client = FakeClient(positions=[out_of_scope])
                with self.assertRaisesRegex(RuntimeError, "outside the requested scope"):
                    results.read_position_inventory(client, 2, [1])
                self.assertIn(
                    ("posiciones", (("torneo_id", 2),), (("categoria_id", (1,)),)),
                    client.reads,
                )
                self.assertEqual(client.mutation_attempts, 0)

    def test_position_inventory_rejects_missing_null_malformed_or_nonpositive_ids(self) -> None:
        invalid_ids = ("missing", None, "not-an-id", 0, -9)
        for invalid_id in invalid_ids:
            with self.subTest(invalid_id=invalid_id):
                row = {"torneo_id": 2, "categoria_id": 1}
                if invalid_id != "missing":
                    row["id"] = invalid_id
                client = FakeClient(positions=[row])

                with self.assertRaisesRegex(RuntimeError, "position id"):
                    results.read_position_inventory(client, 2, [1])

                self.assertEqual(client.mutation_attempts, 0)

    def test_possible_fixture_or_position_inventory_truncation_is_rejected(self) -> None:
        fixture_client = FakeClient(
            fixtures=[FIXTURES[0]] * results.FIXTURE_INVENTORY_LIMIT
        )
        position_client = FakeClient(
            positions=[{}] * results.POSITION_INVENTORY_LIMIT
        )

        with self.assertRaisesRegex(RuntimeError, "possibly partial plan"):
            results.read_fixture_inventory(fixture_client, 2, [1])
        with self.assertRaisesRegex(RuntimeError, "possibly partial plan"):
            results.read_position_inventory(position_client, 2, [1])
        self.assertEqual(fixture_client.mutation_attempts, 0)
        self.assertEqual(position_client.mutation_attempts, 0)


class ResultCliSafetyTests(unittest.TestCase):
    def test_dry_run_builds_complete_plan_without_mutations(self) -> None:
        client = FakeClient()
        output = io.StringIO()

        exit_code = results.main(
            [
                "--torneo-id",
                "2",
                "--category",
                "primera",
                "--source",
                f"primera={FIXTURE_PATH}",
            ],
            client_factory=lambda: client,
            stdout=output,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(client.mutation_attempts, 0)
        self.assertEqual([read[0] for read in client.reads], ["partidos", "posiciones"])
        self.assertIn("Dry run only", output.getvalue())
        self.assertIn("Planned position actions", output.getvalue())

    def test_incomplete_result_snapshot_blocks_execute_before_database_access(self) -> None:
        malformed_html = FIXTURE_PATH.read_text(encoding="utf-8").replace(
            "<tr><td>Argentino</td><td>2</td><td>1</td><td>El Linqueño</td></tr>",
            "<tr><td>Argentino</td><td>2</td><td>1</td></tr>",
            1,
        )
        client_factory = mock.Mock()
        error_output = io.StringIO()

        exit_code = results.main(
            [
                "--torneo-id",
                "2",
                "--category",
                "primera",
                "--source",
                "primera=local-fixture",
                "--execute",
            ],
            fetcher=lambda source, timeout: malformed_html,
            client_factory=client_factory,
            stderr=error_output,
        )

        self.assertEqual(exit_code, 2)
        self.assertIn("Incomplete result row", error_output.getvalue())
        client_factory.assert_not_called()

    def test_execute_filters_results_by_fixture_and_tournament(self) -> None:
        fixtures = fixture_records()
        plan = results.build_operation_plan(
            official_rows(), fixtures, [], 2, ["primera"], [1]
        )
        client = FakeClient()

        counts = results.execute_operation_plan(client, plan)

        result_updates = [
            mutation
            for mutation in client.executed_mutations
            if mutation[0] == "partidos" and mutation[1] == "update"
        ]
        self.assertEqual(counts["results_updated"], 1)
        self.assertEqual(len(result_updates), 1)
        self.assertIn(("id", 101), result_updates[0][3])
        self.assertIn(("torneo_id", 2), result_updates[0][3])

    def test_position_updates_use_all_narrow_identifying_filters(self) -> None:
        fixtures = fixture_records()
        projection = results.calculate_projected_standings(
            results.overlay_planned_results(
                fixtures, results.build_result_plan(official_rows(), fixtures, 2)
            ),
            2,
            [1],
        )
        standing = projection.rows[0]
        existing = {
            "id": 501,
            "torneo_id": 2,
            "categoria_id": standing.category_id,
            "club_id": standing.club_id,
            **{**standing.values(), "pts": standing.pts + 99},
        }
        plan = results.build_operation_plan(
            official_rows(), fixtures, [existing], 2, ["primera"], [1]
        )
        client = FakeClient()

        results.execute_operation_plan(client, plan)

        position_updates = [
            mutation
            for mutation in client.executed_mutations
            if mutation[0] == "posiciones" and mutation[1] == "update"
        ]
        self.assertEqual(len(position_updates), 1)
        filters = position_updates[0][3]
        self.assertIn(("id", 501), filters)
        self.assertIn(("torneo_id", 2), filters)
        self.assertIn(("categoria_id", standing.category_id), filters)
        self.assertIn(("club_id", standing.club_id), filters)

    def test_execute_failure_is_visible_and_returns_nonzero(self) -> None:
        client = FakeClient(write_error=RuntimeError("database write failed"))
        error_output = io.StringIO()

        exit_code = results.main(
            [
                "--torneo-id",
                "2",
                "--category",
                "primera",
                "--source",
                f"primera={FIXTURE_PATH}",
                "--execute",
            ],
            client_factory=lambda: client,
            stderr=error_output,
        )

        self.assertEqual(exit_code, 2)
        self.assertGreaterEqual(client.mutation_attempts, 1)
        self.assertIn("database write failed", error_output.getvalue())

    def test_invalid_source_overrides_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "CATEGORY=URL_OR_PATH"):
            results._parse_source_overrides(["not-an-assignment"])
        with self.assertRaisesRegex(ValueError, "Duplicate --source"):
            results._parse_source_overrides(
                ["primera=first.html", "primera=second.html"]
            )
        with self.assertRaisesRegex(ValueError, "unselected category"):
            results._selected_sources(["primera"], ["septima=seventh.html"])

    def test_missing_tournament_scope_fails_before_fetch_or_database_access(self) -> None:
        fetcher = mock.Mock()
        client_factory = mock.Mock()
        error_output = io.StringIO()
        with mock.patch.dict(os.environ, {}, clear=True), mock.patch.object(
            results, "load_backend_environment", return_value=False
        ):
            exit_code = results.main(
                ["--category", "primera"],
                fetcher=fetcher,
                client_factory=client_factory,
                stderr=error_output,
            )

        self.assertEqual(exit_code, 2)
        self.assertIn("Tournament ID is required", error_output.getvalue())
        fetcher.assert_not_called()
        client_factory.assert_not_called()

    def test_import_and_help_have_no_credentials_or_external_side_effects(self) -> None:
        environment = os.environ.copy()
        for name in ("SUPABASE_URL", "SUPABASE_KEY", "ACTIVE_TORNEO_ID"):
            environment.pop(name, None)
        import_command = (
            "import sys; sys.path.insert(0, 'backend/scripts'); "
            "import scraper_resultados; print('import-ok')"
        )

        imported = subprocess.run(
            [sys.executable, "-c", import_command],
            cwd=REPO_DIR,
            env=environment,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        helped = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "scraper_resultados.py"), "--help"],
            cwd=REPO_DIR,
            env=environment,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )

        self.assertEqual(imported.returncode, 0, imported.stderr)
        self.assertEqual(imported.stdout.strip(), "import-ok")
        self.assertEqual(helped.returncode, 0, helped.stderr)
        self.assertIn("--torneo-id", helped.stdout)
        self.assertIn("--execute", helped.stdout)
        self.assertIn("--category", helped.stdout)
        self.assertIn("--source", helped.stdout)


if __name__ == "__main__":
    unittest.main()
