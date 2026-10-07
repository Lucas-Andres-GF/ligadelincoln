"""Tests for the allow-listed remote scraper worker."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import scraper_worker as worker  # noqa: E402


class RecordingQuery:
    def __init__(self, client, table_name, operation, values):
        self.client = client
        self.table_name = table_name
        self.operation = operation
        self.values = values
        self.filters = []

    def eq(self, column, value):
        self.filters.append((column, value))
        return self

    def execute(self):
        self.client.calls.append(
            (self.table_name, self.operation, self.values, tuple(self.filters))
        )
        return SimpleNamespace(data=[])


class RecordingTable:
    def __init__(self, client, table_name):
        self.client = client
        self.table_name = table_name

    def update(self, values):
        return RecordingQuery(self.client, self.table_name, "update", values)

    def upsert(self, values, on_conflict=None):
        return RecordingQuery(
            self.client,
            self.table_name,
            f"upsert:{on_conflict}",
            values,
        )


class RecordingClient:
    def __init__(self):
        self.calls = []

    def table(self, table_name):
        return RecordingTable(self, table_name)


class ScraperJobValidationTests(unittest.TestCase):
    def test_builds_execute_results_without_using_a_shell(self) -> None:
        job = worker.ScraperJob.from_mapping(
            {
                "id": 7,
                "scraper": "resultados",
                "mode": "execute",
                "torneo_id": 3,
                "categoria": "primera",
                "fecha": None,
            }
        )

        commands = worker.build_job_commands(job, python="/venv/python")

        self.assertEqual(len(commands), 1)
        self.assertEqual(commands[0][0], "Resultados")
        self.assertEqual(commands[0][1][0:2], ["/venv/python", "-u"])
        self.assertIn("scraper_resultados.py", commands[0][1][2])
        self.assertEqual(
            commands[0][1][3:],
            ["--torneo-id", "3", "--category", "primera", "--execute"],
        )

    def test_combined_job_runs_results_before_lineups(self) -> None:
        job = worker.ScraperJob.from_mapping(
            {
                "id": 8,
                "scraper": "resultados_alineaciones",
                "mode": "preview",
                "torneo_id": 3,
                "categoria": None,
                "fecha": 4,
            }
        )

        commands = worker.build_job_commands(job, python="python")

        self.assertEqual([item[0] for item in commands], ["Resultados", "Alineaciones"])
        self.assertNotIn("--execute", commands[0][1])
        self.assertEqual(commands[1][1][-2:], ["--fecha", "4"])

    def test_rejects_arbitrary_scrapers_and_invalid_parameters(self) -> None:
        invalid_jobs = [
            {"id": 1, "scraper": "shell", "mode": "execute", "torneo_id": 3},
            {"id": 1, "scraper": "horarios", "mode": "execute", "torneo_id": 3, "fecha": 2},
            {"id": 1, "scraper": "alineaciones", "mode": "execute", "torneo_id": 3},
            {"id": 1, "scraper": "resultados", "mode": "root", "torneo_id": 3},
        ]

        for raw_job in invalid_jobs:
            with self.subTest(raw_job=raw_job), self.assertRaises(worker.JobValidationError):
                worker.ScraperJob.from_mapping(raw_job)

    def test_combined_job_stops_after_a_failed_first_process(self) -> None:
        client = RecordingClient()
        invoked = []

        def failing_runner(command, **kwargs):
            invoked.append(command)
            kwargs["on_output"]("falló resultados\n")
            return 7

        succeeded = worker.execute_claimed_job(
            client,
            {
                "id": 9,
                "scraper": "resultados_alineaciones",
                "mode": "execute",
                "torneo_id": 3,
                "categoria": None,
                "fecha": 4,
            },
            "mint-test",
            python="python",
            runner=failing_runner,
        )

        self.assertFalse(succeeded)
        self.assertEqual(len(invoked), 1)
        self.assertIn("scraper_resultados.py", invoked[0][2])
        final_updates = [
            values
            for table, operation, values, _ in client.calls
            if table == "scraper_jobs" and operation == "update" and "status" in values
        ]
        self.assertEqual(final_updates[-1]["status"], "failed")
        self.assertEqual(final_updates[-1]["exit_code"], 7)


class MigrationSecurityTests(unittest.TestCase):
    def test_queue_migration_keeps_execution_server_side(self) -> None:
        migration = (
            Path(__file__).resolve().parents[1]
            / "migrations"
            / "20261007_add_remote_scraper_jobs.sql"
        ).read_text(encoding="utf-8").lower()

        self.assertIn("enable row level security", migration)
        self.assertIn("public.is_liga_admin()", migration)
        self.assertIn("for insert to authenticated", migration)
        self.assertIn("grant execute on function public.claim_scraper_job(text) to service_role", migration)
        self.assertIn("revoke all on function public.claim_scraper_job(text) from public, anon, authenticated", migration)
        self.assertNotIn("grant update", migration)
        self.assertIn("scraper_jobs_single_active_idx", migration)


if __name__ == "__main__":
    unittest.main()
