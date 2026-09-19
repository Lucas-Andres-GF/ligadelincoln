"""Network-free tests for safe schedule ingestion."""

from __future__ import annotations

import io
import os
import subprocess
import sys
import unittest
from dataclasses import replace
from unittest import mock
from pathlib import Path
from types import SimpleNamespace


BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = BACKEND_DIR.parent
SCRIPTS_DIR = BACKEND_DIR / "scripts"
FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "horarios_sample.html"
sys.path.insert(0, str(SCRIPTS_DIR))

import scraper_horarios as schedule  # noqa: E402


INVENTORY = [
    {
        "id": 101,
        "torneo_id": 2,
        "categoria_id": 1,
        "local_id": 1,
        "visitante_id": 8,
        "fecha_id": 1,
    },
    {
        "id": 102,
        "torneo_id": 2,
        "categoria_id": 2,
        "local_id": 2,
        "visitante_id": 4,
        "fecha_id": 1,
    },
    {
        "id": 103,
        "torneo_id": 2,
        "categoria_id": 3,
        "local_id": 7,
        "visitante_id": 11,
        "fecha_id": 1,
    },
    {
        "id": 104,
        "torneo_id": 2,
        "categoria_id": 5,
        "local_id": 5,
        "visitante_id": 9,
        "fecha_id": 3,
    },
]


def parsed_rows() -> list[schedule.ScheduleRow]:
    html = FIXTURE_PATH.read_text(encoding="utf-8")
    return schedule.calculate_schedule_times(schedule.parse_schedule_html(html))


def fixture_records(values=INVENTORY) -> list[schedule.FixtureRecord]:
    return [schedule.FixtureRecord.from_mapping(item) for item in values]


class FakeQuery:
    def __init__(self, client: "FakeClient") -> None:
        self.client = client
        self.filters: list[tuple[str, object]] = []
        self.operation = "select"
        self.values = None

    def select(self, columns: str) -> "FakeQuery":
        self.client.select_columns = columns
        return self

    def update(self, values: dict[str, object]) -> "FakeQuery":
        self.operation = "update"
        self.values = values
        self.client.update_calls += 1
        return self

    def eq(self, column: str, value: object) -> "FakeQuery":
        self.filters.append((column, value))
        return self

    def limit(self, value: int) -> "FakeQuery":
        self.client.limit = value
        return self

    def execute(self) -> SimpleNamespace:
        if self.operation == "update":
            if self.client.update_error is not None:
                raise self.client.update_error
            self.client.executed_updates.append((self.values, tuple(self.filters)))
            return SimpleNamespace(data=[{"id": 1}])
        self.client.inventory_filters.append(tuple(self.filters))
        return SimpleNamespace(data=list(self.client.inventory))


class FakeClient:
    def __init__(self, inventory=INVENTORY, update_error: Exception | None = None) -> None:
        self.inventory = inventory
        self.update_error = update_error
        self.update_calls = 0
        self.executed_updates: list[tuple[object, object]] = []
        self.inventory_filters: list[tuple[tuple[str, object], ...]] = []
        self.select_columns = ""
        self.limit = None

    def table(self, name: str) -> FakeQuery:
        if name != "partidos":
            raise AssertionError(f"Unexpected table: {name}")
        return FakeQuery(self)


class ScheduleParsingTests(unittest.TestCase):
    def test_parses_explicit_and_postponed_dates_without_the_ignored_block(self) -> None:
        rows = schedule.parse_schedule_html(FIXTURE_PATH.read_text(encoding="utf-8"))

        self.assertEqual(len(rows), 4)
        self.assertEqual(rows[0].date, "2026-04-12")
        self.assertEqual(rows[0].scheduled_time, "13:00")
        self.assertFalse(rows[0].inherited_time)
        self.assertEqual(rows[3].date, "2026-04-20")
        self.assertEqual(rows[3].round_id, 3)
        self.assertEqual(rows[3].category_id, 5)
        self.assertNotIn("SAN MARTIN", [row.local for row in rows])

    def test_calculates_inherited_time_from_previous_category_duration(self) -> None:
        rows = parsed_rows()

        self.assertEqual(rows[0].calculated_time, "13:00")
        self.assertTrue(rows[1].inherited_time)
        self.assertEqual(rows[1].scheduled_time, "13:00")
        self.assertEqual(rows[1].calculated_time, "14:45")
        self.assertEqual(rows[1].venue, "Estadio Central")
        self.assertEqual(rows[2].calculated_time, "17:00")

    def test_missing_schedule_table_is_an_explicit_parse_failure(self) -> None:
        with self.assertRaisesRegex(schedule.ScheduleParseError, "CRONOGRAMA"):
            schedule.parse_schedule_html("<table><tr><td>not a schedule</td></tr></table>")


class SchedulePlanningTests(unittest.TestCase):
    def test_unique_matches_produce_a_complete_tournament_scoped_plan(self) -> None:
        plan = schedule.build_update_plan(parsed_rows(), fixture_records(), 2)

        self.assertTrue(plan.valid)
        self.assertEqual([entry.target_id for entry in plan.entries], [101, 102, 103, 104])
        self.assertEqual(plan.entries[1].values["hora"], "14:45")
        self.assertEqual(plan.entries[3].values["dia"], "2026-04-20")

    def test_ambiguous_and_missing_targets_are_blocking(self) -> None:
        rows = parsed_rows()
        duplicate = {**INVENTORY[0], "id": 999, "fecha_id": 8}
        ambiguous = schedule.build_update_plan(
            rows,
            fixture_records([*INVENTORY, duplicate]),
            2,
        )
        missing = schedule.build_update_plan(rows, fixture_records(INVENTORY[1:]), 2)

        self.assertFalse(ambiguous.valid)
        self.assertTrue(any("Ambiguous fixture target" in issue for issue in ambiguous.issues))
        self.assertFalse(missing.valid)
        self.assertTrue(any("Missing fixture target" in issue for issue in missing.issues))

        client = FakeClient()
        with self.assertRaisesRegex(ValueError, "invalid or empty"):
            schedule.execute_update_plan(client, ambiguous)
        self.assertEqual(client.update_calls, 0)

    def test_two_schedule_rows_cannot_claim_the_same_fixture_target(self) -> None:
        html = """
            <table>
              <tr><th>CRONOGRAMA</th></tr>
              <tr><th>Domingo 12 de abril de 2026</th></tr>
              <tr><td>Primera</td><td>Argentino</td><td>vs</td><td>El Linqueño</td><td>13:00</td><td>Central</td></tr>
              <tr><th>Domingo 19 de abril de 2026</th></tr>
              <tr><td>Primera</td><td>Argentino</td><td>vs</td><td>El Linqueño</td><td>14:00</td><td>Central</td></tr>
            </table>
        """
        rows = schedule.calculate_schedule_times(schedule.parse_schedule_html(html))

        plan = schedule.build_update_plan(rows, fixture_records(INVENTORY[:1]), 2)

        self.assertEqual(len(rows), 2)
        self.assertFalse(plan.valid)
        self.assertEqual([entry.target_id for entry in plan.entries], [101])
        self.assertTrue(any("matched more than once" in issue for issue in plan.issues))
        client = FakeClient()
        with self.assertRaisesRegex(ValueError, "invalid or empty"):
            schedule.execute_update_plan(client, plan)
        self.assertEqual(client.update_calls, 0)

    def test_unknown_clubs_and_categories_are_reported(self) -> None:
        row = replace(
            parsed_rows()[0],
            category_raw="Reserva",
            category_key=None,
            category_id=None,
            local="UNKNOWN CLUB",
            local_id=None,
        )

        plan = schedule.build_update_plan([row], fixture_records(), 2)

        self.assertFalse(plan.valid)
        self.assertTrue(any("Unknown category" in issue for issue in plan.issues))
        self.assertTrue(any("Unknown local club" in issue for issue in plan.issues))

    def test_execute_uses_only_target_id_and_tournament_scope(self) -> None:
        plan = schedule.build_update_plan(parsed_rows(), fixture_records(), 2)
        client = FakeClient()

        applied = schedule.execute_update_plan(client, plan)

        self.assertEqual(applied, 4)
        for _, filters in client.executed_updates:
            self.assertIn(("torneo_id", 2), filters)
            self.assertEqual(sum(column == "id" for column, _ in filters), 1)

    def test_inventory_at_or_above_safety_limit_is_rejected(self) -> None:
        for inventory_size in (schedule.INVENTORY_LIMIT, schedule.INVENTORY_LIMIT + 1):
            with self.subTest(inventory_size=inventory_size):
                client = FakeClient(inventory=[INVENTORY[0]] * inventory_size)

                with self.assertRaisesRegex(RuntimeError, "safety limit"):
                    schedule.read_fixture_inventory(client, 2)

                self.assertEqual(client.update_calls, 0)
                self.assertEqual(client.limit, schedule.INVENTORY_LIMIT)


class ScheduleCliSafetyTests(unittest.TestCase):
    def test_dry_run_reads_inventory_without_mutating(self) -> None:
        client = FakeClient()
        output = io.StringIO()

        exit_code = schedule.main(
            ["--torneo-id", "2", "--source", str(FIXTURE_PATH)],
            client_factory=lambda: client,
            stdout=output,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(client.update_calls, 0)
        self.assertEqual(client.inventory_filters, [(('torneo_id', 2),)])
        self.assertEqual(client.limit, schedule.INVENTORY_LIMIT)
        self.assertIn("Dry run only", output.getvalue())

    def test_execute_failure_propagates_and_main_returns_nonzero(self) -> None:
        plan = schedule.build_update_plan(parsed_rows(), fixture_records(), 2)
        direct_client = FakeClient(update_error=RuntimeError("database write failed"))

        with self.assertRaisesRegex(RuntimeError, "database write failed"):
            schedule.execute_update_plan(direct_client, plan)
        self.assertEqual(direct_client.update_calls, 1)
        self.assertEqual(direct_client.executed_updates, [])

        cli_client = FakeClient(update_error=RuntimeError("database write failed"))
        error_output = io.StringIO()
        exit_code = schedule.main(
            ["--torneo-id", "2", "--source", str(FIXTURE_PATH), "--execute"],
            client_factory=lambda: cli_client,
            stderr=error_output,
        )

        self.assertEqual(exit_code, 2)
        self.assertIn("database write failed", error_output.getvalue())
        self.assertEqual(cli_client.executed_updates, [])

    def test_import_and_help_need_no_credentials_or_network(self) -> None:
        environment = os.environ.copy()
        for name in ("SUPABASE_URL", "SUPABASE_KEY", "ACTIVE_TORNEO_ID"):
            environment.pop(name, None)
        import_command = (
            "import sys; sys.path.insert(0, 'backend/scripts'); "
            "import scraper_horarios; print('import-ok')"
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
            [sys.executable, str(SCRIPTS_DIR / "scraper_horarios.py"), "--help"],
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

    def test_missing_tournament_scope_fails_without_fallback(self) -> None:
        client_factory = mock.Mock(return_value=FakeClient())
        error_output = io.StringIO()
        with mock.patch.dict(os.environ, {}, clear=True), mock.patch.object(
            schedule,
            "load_backend_environment",
            return_value=False,
        ):
            exit_code = schedule.main(
                ["--source", str(FIXTURE_PATH)],
                client_factory=client_factory,
                stderr=error_output,
            )

        self.assertEqual(exit_code, 2)
        self.assertIn("Tournament ID is required", error_output.getvalue())
        client_factory.assert_not_called()


if __name__ == "__main__":
    unittest.main()
