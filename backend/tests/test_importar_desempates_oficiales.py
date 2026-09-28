"""Network-free tests for official two-leg championship decider imports."""

from __future__ import annotations

import io
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


BACKEND_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = BACKEND_DIR / "scripts"
FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "decider_clausura_sample.html"
sys.path.insert(0, str(SCRIPTS_DIR))

import importar_desempates_oficiales as importer  # noqa: E402


SAMPLE_HTML = FIXTURE_PATH.read_text(encoding="utf-8")
CLUBS = {
    "CA. PINTENSE": 4,
    "DEP. ARENAZA": 6,
}
LEGACY_CLUBS = {
    "ARGENTINO": 1,
    "EL LINQUEÑO": 8,
}
LEGACY_HTML = """
<table>
  <tr><td>ENCUENTROS FINALES POR DESEMPATE</td></tr>
  <tr><td>IDA</td><td>08/07/2026</td><td>CANCHA: Argentino</td></tr>
  <tr><th>LOCAL</th><th>GL</th><th>GV</th><th>VISITANTE</th></tr>
  <tr><td>Argentino</td><td>1</td><td>0</td><td>El Linqueño</td></tr>
  <tr><td>VUELTA</td><td>15/07/2026</td><td>CANCHA: El Linqueño</td></tr>
  <tr><th>LOCAL</th><th>GL</th><th>GV</th><th>VISITANTE</th></tr>
  <tr><td>El Linqueño</td><td>1</td><td>2</td><td>Argentino</td></tr>
  <tr><td>CAMPEÓN: ARGENTINO</td></tr>
</table>
"""
SOURCE_URL = "https://liga.example/torneos/clausura-primera.html#finales"


class FakeQuery:
    def __init__(self, client: "FakeClient", table: str) -> None:
        self.client = client
        self.table = table
        self.operation = "select"
        self.values = None
        self.filters: list[tuple[str, object]] = []
        self.count_mode = None
        self.order_value = None
        self.range_value = None
        self.upsert_options: dict[str, object] = {}

    def select(self, columns: str, **kwargs: object) -> "FakeQuery":
        self.operation = "select"
        self.client.selected_columns = columns
        self.count_mode = kwargs.get("count")
        return self

    def eq(self, column: str, value: object) -> "FakeQuery":
        self.filters.append((column, value))
        return self

    def order(self, column: str, desc: bool = False) -> "FakeQuery":
        self.order_value = (column, desc)
        return self

    def range(self, start: int, end: int) -> "FakeQuery":
        self.range_value = (start, end)
        return self

    def upsert(self, values: object, **kwargs: object) -> "FakeQuery":
        self.operation = "upsert"
        self.values = values
        self.upsert_options = dict(kwargs)
        return self

    def execute(self) -> SimpleNamespace:
        if self.operation == "select":
            self.client.reads.append(
                (self.table, tuple(self.filters), self.order_value, self.range_value)
            )
            if self.count_mode != "exact":
                raise AssertionError("inventory reads must request exact count")
            rows = list(self.client.inventory)
            start, end = self.range_value or (0, len(rows))
            return SimpleNamespace(data=rows[start : end + 1], count=len(rows))
        self.client.mutations.append(
            (
                self.table,
                self.operation,
                self.values,
                dict(self.upsert_options),
                tuple(self.filters),
            )
        )
        return SimpleNamespace(data=list(self.values))


class FakeClient:
    def __init__(self, inventory=()) -> None:
        self.inventory = list(inventory)
        self.reads: list[tuple[object, ...]] = []
        self.mutations: list[tuple[object, ...]] = []
        self.selected_columns = ""

    def table(self, name: str) -> FakeQuery:
        if name != "partidos_definicion":
            raise AssertionError(f"unexpected table access: {name}")
        return FakeQuery(self, name)


def parsed_series(
    html: str = SAMPLE_HTML,
    clubs: dict[str, int] = CLUBS,
) -> importer.DeciderSeries:
    return importer.parse_decider_html(html, SOURCE_URL, clubs)


def payloads() -> tuple[dict[str, object], ...]:
    return importer.build_payloads(parsed_series(), tournament_id=7, category_id=1)


def stored_rows(rows=None) -> list[dict[str, object]]:
    source_rows = payloads() if rows is None else rows
    return [{"id": index + 20, **dict(row)} for index, row in enumerate(source_rows)]


class OfficialDeciderParserTests(unittest.TestCase):
    def test_live_official_sample_parses_only_dedicated_section_and_builds_payloads(self) -> None:
        series = parsed_series()

        self.assertEqual(series.champion_id, 6)
        self.assertEqual(series.champion_name, "DEP ARENAZA")
        self.assertEqual(series.aggregate, (3, 0))
        self.assertEqual([leg.instance for leg in series.legs], ["ida", "vuelta"])
        self.assertEqual([leg.date for leg in series.legs], ["2026-09-06", "2026-09-12"])
        self.assertEqual(
            [
                (
                    leg.local_name,
                    leg.local_id,
                    leg.local_goals,
                    leg.visitor_goals,
                    leg.visitor_name,
                    leg.visitor_id,
                )
                for leg in series.legs
            ],
            [
                ("C A PINTENSE", 4, 0, 1, "DEP ARENAZA", 6),
                ("DEP ARENAZA", 6, 2, 0, "C A PINTENSE", 4),
            ],
        )

        rows = importer.build_payloads(series, tournament_id=7, category_id=1)
        self.assertEqual(len(rows), 2)
        self.assertEqual([row["orden"] for row in rows], [1, 2])
        self.assertEqual([row["instancia"] for row in rows], ["ida", "vuelta"])
        self.assertTrue(all(row["serie"] == importer.SERIES_NAME for row in rows))
        self.assertTrue(all(row["campeon_id"] == 6 for row in rows))
        self.assertTrue(all(row["torneo_id"] == 7 for row in rows))
        self.assertTrue(all(row["categoria_id"] == 1 for row in rows))
        self.assertTrue(
            all(
                row["fuente_url"]
                == "https://liga.example/torneos/clausura-primera.html"
                for row in rows
            )
        )
        self.assertEqual([row["cancha"] for row in rows], ["C A PINTENSE", "DEP ARENAZA"])

    def test_prior_marker_ground_and_champion_patterns_remain_accepted(self) -> None:
        series = parsed_series(LEGACY_HTML, LEGACY_CLUBS)

        self.assertEqual(series.champion_name, "ARGENTINO")
        self.assertEqual(series.aggregate, (3, 1))
        self.assertEqual([leg.ground for leg in series.legs], ["Argentino", "El Linqueño"])

    def test_pintense_source_identity_alias_is_exact_not_fuzzy(self) -> None:
        unsupported = SAMPLE_HTML.replace("C A PINTENSE", "C A PINTENSE CLUB")

        with self.assertRaisesRegex(
            importer.DeciderSourceError,
            "missing from authoritative configuration",
        ):
            parsed_series(unsupported)

    def test_nested_wrapper_tables_do_not_change_series_detection(self) -> None:
        nested = SAMPLE_HTML.replace(
            "<tr><td>ENCUENTROS FINALES POR DESEMPATE</td></tr>",
            "<tr><td><div><table><tr><td>ENCUENTROS FINALES POR DESEMPATE</td></tr></table></div></td></tr>",
        )
        series = parsed_series(nested)
        self.assertEqual(len(series.legs), 2)
        self.assertEqual(series.champion_id, 6)

    def test_missing_duplicate_and_malformed_sections_fail_closed(self) -> None:
        cases = {
            "missing": SAMPLE_HTML.replace(
                "ENCUENTROS FINALES POR DESEMPATE", "ENCUENTROS"
            ),
            "duplicate": SAMPLE_HTML.replace(
                "<tr><td>TABLA FINAL</td></tr>",
                "<tr><td>ENCUENTROS FINALES POR DESEMPATE</td></tr><tr><td>TABLA FINAL</td></tr>",
            ),
            "one leg": SAMPLE_HTML.replace("PARTIDO DE VUELTA", "SEGUNDO PARTIDO", 1),
            "duplicate leg marker": SAMPLE_HTML.replace(
                "<tr><td>PARTIDO DE VUELTA</td></tr>",
                "<tr><td>PARTIDO DE IDA</td></tr><tr><td>PARTIDO DE VUELTA</td></tr>",
                1,
            ),
            "duplicate match row": SAMPLE_HTML.replace(
                "<tr><td>PARTIDO DE VUELTA</td></tr>",
                "<tr><td>C A PINTENSE</td><td>0</td><td>1</td><td>DEP ARENAZA</td><td>06/09/2026</td><td>CA. Pintense</td></tr><tr><td>PARTIDO DE VUELTA</td></tr>",
                1,
            ),
            "bad score": SAMPLE_HTML.replace(
                "<td>C A PINTENSE</td><td>0</td><td>1</td><td>DEP ARENAZA</td>",
                "<td>C A PINTENSE</td><td>-1</td><td>1</td><td>DEP ARENAZA</td>",
                1,
            ),
        }
        for label, html in cases.items():
            with self.subTest(label=label):
                with self.assertRaises(importer.DeciderSourceError):
                    parsed_series(html)

    def test_non_reversed_teams_dates_aggregate_draw_and_champion_mismatch_fail(self) -> None:
        cases = {
            "not reversed": SAMPLE_HTML.replace(
                "<td>DEP ARENAZA</td><td>2</td><td>0</td><td>C A PINTENSE</td>",
                "<td>C A PINTENSE</td><td>2</td><td>0</td><td>DEP ARENAZA</td>",
            ),
            "chronology": SAMPLE_HTML.replace("12/09/26", "01/09/26"),
            "aggregate draw": SAMPLE_HTML.replace(
                "<td>DEP ARENAZA</td><td>2</td><td>0</td><td>C A PINTENSE</td>",
                "<td>DEP ARENAZA</td><td>0</td><td>1</td><td>C A PINTENSE</td>",
            ),
            "champion mismatch": SAMPLE_HTML.replace(
                "CAMPEÓN DEL TORNEO CLAUSURA 2026: DEP ARENAZA",
                "CAMPEÓN DEL TORNEO CLAUSURA 2026: C A PINTENSE",
            ),
        }
        for label, html in cases.items():
            with self.subTest(label=label):
                with self.assertRaises(importer.DeciderSourceError):
                    parsed_series(html)


class InventoryAndPlanningTests(unittest.TestCase):
    def test_inventory_is_read_from_exact_tournament_category_series_scope(self) -> None:
        client = FakeClient(stored_rows())

        inventory = importer.inspect_existing_inventory(client, 7, 1)

        self.assertEqual(len(inventory), 2)
        self.assertEqual(len(client.reads), 1)
        self.assertEqual(
            client.reads[0][1],
            (
                ("torneo_id", 7),
                ("categoria_id", 1),
                ("serie", importer.SERIES_NAME),
            ),
        )
        self.assertEqual(client.reads[0][2], ("id", False))
        self.assertIn("fuente_url", client.selected_columns)

    def test_empty_inventory_inserts_and_exact_two_rows_are_noop(self) -> None:
        expected = payloads()
        insert = importer.build_import_plan(expected, (), replace_existing=False)
        noop = importer.build_import_plan(expected, stored_rows(), replace_existing=False)

        self.assertTrue(insert.valid)
        self.assertEqual(insert.action, "insert")
        self.assertEqual(insert.issues, ())
        self.assertTrue(noop.valid)
        self.assertEqual(noop.action, "noop")
        self.assertEqual(noop.issues, ())

    def test_partial_conflicting_and_extra_inventory_block_unless_replace_is_explicit(self) -> None:
        expected = payloads()
        partial = stored_rows()[:1]
        conflicting = stored_rows()
        conflicting[1]["goles_local"] = 4
        extra = stored_rows() + [{**stored_rows()[0], "id": 99, "orden": 3}]

        for label, inventory in (("partial", partial), ("conflicting", conflicting), ("extra", extra)):
            with self.subTest(label=label):
                blocked = importer.build_import_plan(expected, inventory, replace_existing=False)
                replacement = importer.build_import_plan(expected, inventory, replace_existing=True)
                self.assertFalse(blocked.valid)
                self.assertEqual(blocked.action, "blocked")
                self.assertTrue(blocked.issues)
                self.assertTrue(replacement.valid, replacement.issues)
                self.assertEqual(replacement.action, "replace")


class CliAndExecutionTests(unittest.TestCase):
    def test_cli_requires_positive_scope_source_and_bounded_timeout(self) -> None:
        parser = importer.build_parser()
        invalid = (
            [],
            ["--torneo-id", "0", "--categoria-id", "1", "--source", "x"],
            ["--torneo-id", "7", "--categoria-id", "-1", "--source", "x"],
            ["--torneo-id", "7", "--categoria-id", "1"],
            ["--torneo-id", "7", "--categoria-id", "1", "--source", "x", "--timeout", "0"],
            ["--torneo-id", "7", "--categoria-id", "1", "--source", "x", "--timeout", "121"],
        )
        for argv in invalid:
            with self.subTest(argv=argv), self.assertRaises(SystemExit):
                parser.parse_args(argv)

        args = parser.parse_args(
            ["--torneo-id", "7", "--categoria-id", "1", "--source", str(FIXTURE_PATH), "--json"]
        )
        self.assertFalse(args.execute)
        self.assertFalse(args.replace_existing)
        self.assertTrue(args.json)

    def test_dry_run_reports_both_legs_aggregate_champion_action_issues_and_zero_writes(self) -> None:
        client = FakeClient()
        output = io.StringIO()
        exit_code = importer.main(
            [
                "--torneo-id", "7",
                "--categoria-id", "1",
                "--source", str(FIXTURE_PATH),
                "--json",
            ],
            client_factory=lambda: client,
            source_loader=lambda source, timeout: SAMPLE_HTML,
            identity_loader=lambda: CLUBS,
            stdout=output,
        )

        self.assertEqual(exit_code, 0, output.getvalue())
        report = json.loads(output.getvalue())
        self.assertEqual(report["mode"], "dry-run")
        self.assertEqual(len(report["legs"]), 2)
        self.assertEqual(report["aggregate"], {"champion": 3, "runner_up": 0})
        self.assertEqual(report["champion"]["id"], 6)
        self.assertEqual(report["action"], "insert")
        self.assertEqual(report["issues"], [])
        self.assertEqual(report["writes"], 0)
        self.assertEqual(client.mutations, [])

    def test_execute_uses_one_atomic_two_row_upsert_and_no_other_table(self) -> None:
        client = FakeClient()
        output = io.StringIO()
        exit_code = importer.main(
            [
                "--torneo-id", "7",
                "--categoria-id", "1",
                "--source", str(FIXTURE_PATH),
                "--execute",
            ],
            client_factory=lambda: client,
            source_loader=lambda source, timeout: SAMPLE_HTML,
            identity_loader=lambda: CLUBS,
            stdout=output,
        )

        self.assertEqual(exit_code, 0, output.getvalue())
        self.assertEqual(len(client.mutations), 1)
        table, operation, rows, options, filters = client.mutations[0]
        self.assertEqual(table, "partidos_definicion")
        self.assertEqual(operation, "upsert")
        self.assertEqual(len(rows), 2)
        self.assertEqual(
            options.get("on_conflict"),
            "torneo_id,categoria_id,serie,orden",
        )
        self.assertEqual(filters, ())
        self.assertIn("writes=2", output.getvalue())

    def test_conflict_never_writes_without_replace_and_replace_upserts_once(self) -> None:
        conflict = stored_rows()
        conflict[0]["cancha"] = "Wrong Ground"
        blocked_client = FakeClient(conflict)
        blocked_output = io.StringIO()
        blocked_code = importer.main(
            ["--torneo-id", "7", "--categoria-id", "1", "--source", str(FIXTURE_PATH), "--execute"],
            client_factory=lambda: blocked_client,
            source_loader=lambda source, timeout: SAMPLE_HTML,
            identity_loader=lambda: CLUBS,
            stdout=blocked_output,
        )
        self.assertEqual(blocked_code, 1)
        self.assertEqual(blocked_client.mutations, [])

        replace_client = FakeClient(conflict)
        replace_code = importer.main(
            [
                "--torneo-id", "7", "--categoria-id", "1", "--source", str(FIXTURE_PATH),
                "--replace-existing", "--execute",
            ],
            client_factory=lambda: replace_client,
            source_loader=lambda source, timeout: SAMPLE_HTML,
            identity_loader=lambda: CLUBS,
            stdout=io.StringIO(),
        )
        self.assertEqual(replace_code, 0)
        self.assertEqual(len(replace_client.mutations), 1)


if __name__ == "__main__":
    unittest.main()
