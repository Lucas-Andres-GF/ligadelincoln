"""Network-free tests for safe Primera lineup replacement."""

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
FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "alineaciones_sample.html"
sys.path.insert(0, str(SCRIPTS_DIR))

import scraper_alineaciones as lineups  # noqa: E402


INVENTORY = [
    {
        "id": 801,
        "torneo_id": 2,
        "categoria_id": 1,
        "local_id": 1,
        "visitante_id": 8,
        "fecha_id": 8,
        "estado": "jugado",
    },
    {
        "id": 802,
        "torneo_id": 2,
        "categoria_id": 1,
        "local_id": 2,
        "visitante_id": 4,
        "fecha_id": 8,
        "estado": "jugado",
    },
]


def parsed_matches() -> list[lineups.OfficialMatch]:
    return lineups.parse_lineups_html(FIXTURE_PATH.read_text(encoding="utf-8"))


def fixture_records(values=INVENTORY) -> list[lineups.FixtureRecord]:
    return [lineups.FixtureRecord.from_mapping(item) for item in values]


def valid_plan() -> lineups.ReplacementPlan:
    return lineups.build_replacement_plan(parsed_matches(), fixture_records(), 2, 8, 1)


def single_match_html(
    final_score: tuple[int, int] = (0, 0),
    events: tuple[tuple[str, str], ...] = (),
) -> str:
    event_rows = "".join(
        "<tr><td></td><td></td><td></td><td></td><td></td><td></td><td></td>"
        f"<td>{scorer}</td><td>{score}</td></tr>"
        for scorer, score in events
    )
    return f"""
        <h1>PRIMERA - FECHA: OCTAVA</h1>
        <table>
          <tr><td>ARGENTINO</td><td>{final_score[0]}</td><td>{final_score[1]}</td>
              <td>EL LINQUEÑO</td></tr>
          <tr><td>1</td><td>CARLOS LÓPEZ</td><td></td>
              <td>1</td><td>JOSÉ GÓMEZ</td><td></td></tr>
          <tr><td>9</td><td>JUAN PÉREZ</td><td></td>
              <td>4</td><td>PABLO MUÑOZ</td><td></td></tr>
          {event_rows}
        </table>
    """


class FakeQuery:
    def __init__(self, client: "FakeClient", table: str) -> None:
        self.client = client
        self.table = table
        self.operation = "select"
        self.values = None
        self.filters: list[tuple[str, object]] = []

    def select(self, columns: str) -> "FakeQuery":
        self.client.selected_columns = columns
        return self

    def delete(self) -> "FakeQuery":
        self.operation = "delete"
        return self

    def insert(self, values: object) -> "FakeQuery":
        self.operation = "insert"
        self.values = values
        return self

    def update(self, values: object) -> "FakeQuery":
        self.operation = "update"
        self.values = values
        return self

    def eq(self, column: str, value: object) -> "FakeQuery":
        self.filters.append((column, value))
        return self

    def limit(self, value: int) -> "FakeQuery":
        self.client.limit = value
        return self

    def execute(self) -> SimpleNamespace:
        if self.operation == "select":
            self.client.reads.append((self.table, tuple(self.filters)))
            return SimpleNamespace(data=list(self.client.inventory))
        self.client.mutation_attempts += 1
        if self.client.write_error is not None:
            raise self.client.write_error
        self.client.mutations.append(
            (self.table, self.operation, self.values, tuple(self.filters))
        )
        return SimpleNamespace(data=[{"id": 1}])


class FakeClient:
    def __init__(self, inventory=INVENTORY, write_error: Exception | None = None) -> None:
        self.inventory = inventory
        self.write_error = write_error
        self.reads: list[tuple[object, ...]] = []
        self.mutations: list[tuple[object, ...]] = []
        self.mutation_attempts = 0
        self.selected_columns = ""
        self.limit = None

    def table(self, name: str) -> FakeQuery:
        if name not in {"partidos", "alineaciones"}:
            raise AssertionError(f"Unexpected table: {name}")
        return FakeQuery(self, name)


class LineupParsingTests(unittest.TestCase):
    def test_parses_round_teams_players_goals_cards_staff_and_encoding(self) -> None:
        matches = parsed_matches()

        self.assertEqual(len(matches), 2)
        first = matches[0]
        self.assertEqual((first.round_id, first.local_id, first.visitor_id), (8, 1, 8))
        self.assertEqual(first.visitor, "EL LINQUEÑO")
        self.assertEqual((first.final_local_goals, first.final_visitor_goals), (2, 1))
        self.assertEqual([player.number for player in first.local_players], [1, 9, 12])
        self.assertEqual(first.visitor_players[1].name, "PABLO MUÑOZ")
        self.assertEqual(first.local_players[1].goals, 2)
        self.assertEqual(first.visitor_players[0].goals, 1)
        self.assertTrue(first.local_players[1].red_card)
        self.assertTrue(first.visitor_players[1].red_card)
        self.assertEqual(
            (first.local_coach, first.visitor_coach, first.referee),
            ("ANA GARCÍA", "LUIS NÚÑEZ", "ROBERTO DÍAZ"),
        )
        self.assertEqual((matches[1].local_id, matches[1].visitor_id), (2, 4))

    def test_missing_table_incomplete_blocks_and_malformed_players_fail_closed(self) -> None:
        with self.assertRaisesRegex(lineups.LineupNotPublished, "No alineaciones"):
            lineups.parse_lineups_html("<h1>FECHA 8</h1><table><tr><td>none</td></tr></table>")

        incomplete = """
            <h1>FECHA 8</h1><table>
            <tr><td>ARGENTINO</td><td>0</td><td>0</td><td>EL LINQUEÑO</td></tr>
            <tr><td>1</td><td>PLAYER ONE</td><td></td><td></td><td></td></tr>
            </table>
        """
        with self.assertRaisesRegex(lineups.LineupParseError, "Incomplete match block"):
            lineups.parse_lineups_html(incomplete)

        malformed = FIXTURE_PATH.read_text(encoding="utf-8").replace(
            "<td>9</td><td>JUAN PÉREZ</td>",
            "<td>9</td><td></td>",
            1,
        )
        with self.assertRaisesRegex(lineups.LineupParseError, "Malformed local player"):
            lineups.parse_lineups_html(malformed)

    def test_scorer_without_valid_cumulative_score_fails_closed(self) -> None:
        for score in ("", "not-a-score"):
            with self.subTest(score=score), self.assertRaisesRegex(
                lineups.LineupParseError,
                "scorer but no valid cumulative score",
            ):
                lineups.parse_lineups_html(
                    single_match_html((1, 0), (("JUAN PÉREZ", score),))
                )

    def test_score_transition_without_scorer_fails_closed(self) -> None:
        with self.assertRaisesRegex(lineups.LineupParseError, "no scorer"):
            lineups.parse_lineups_html(single_match_html((1, 0), (("", "1-0"),)))

    def test_regressive_and_invalid_score_progressions_fail_closed(self) -> None:
        cases = (
            ("regressive", (0, 0), (("JUAN PÉREZ", "1-0"), ("JOSÉ GÓMEZ", "0-0"))),
            ("multi-goal jump", (2, 0), (("JUAN PÉREZ", "2-0"),)),
        )
        for label, final_score, events in cases:
            with self.subTest(label=label), self.assertRaisesRegex(
                lineups.LineupParseError,
                "Malformed scoring sequence",
            ):
                lineups.parse_lineups_html(single_match_html(final_score, events))

    def test_final_header_score_must_equal_attributed_events(self) -> None:
        with self.assertRaisesRegex(lineups.LineupParseError, "Final score/event mismatch"):
            lineups.parse_lineups_html(
                single_match_html((2, 0), (("JUAN PÉREZ", "1-0"),))
            )

    def test_scoreless_match_without_goal_events_is_valid(self) -> None:
        match = lineups.parse_lineups_html(single_match_html())[0]

        self.assertEqual((match.final_local_goals, match.final_visitor_goals), (0, 0))
        self.assertEqual(sum(player.goals for player in match.local_players), 0)
        self.assertEqual(sum(player.goals for player in match.visitor_players), 0)

    def test_valid_goal_events_are_attributed_to_unique_players(self) -> None:
        match = lineups.parse_lineups_html(
            single_match_html(
                (2, 1),
                (
                    ("JUAN PÉREZ", "1-0"),
                    ("JOSÉ GÓMEZ", "1-1"),
                    ("JUAN PÉREZ", "2-1"),
                ),
            )
        )[0]

        self.assertEqual((match.final_local_goals, match.final_visitor_goals), (2, 1))
        self.assertEqual(
            {player.number: player.goals for player in match.local_players},
            {1: 0, 9: 2},
        )
        self.assertEqual(
            {player.number: player.goals for player in match.visitor_players},
            {1: 1, 4: 0},
        )

    def test_goal_scorer_matching_no_lineup_player_fails_closed(self) -> None:
        with self.assertRaisesRegex(lineups.LineupParseError, "did not match one player"):
            lineups.parse_lineups_html(
                single_match_html((1, 0), (("UNKNOWN SCORER", "1-0"),))
            )

    def test_goal_scorer_matching_multiple_lineup_players_fails_closed(self) -> None:
        html = single_match_html((1, 0), (("JUAN PÉREZ", "1-0"),))
        html = html.replace("CARLOS LÓPEZ", "JUAN PÉREZ UNO").replace(
            "<td>9</td><td>JUAN PÉREZ</td>",
            "<td>9</td><td>JUAN PÉREZ DOS</td>",
        )

        with self.assertRaisesRegex(lineups.LineupParseError, "did not match one player"):
            lineups.parse_lineups_html(html)

    def test_nested_wrapper_tables_and_unplayed_blocks_are_handled(self) -> None:
        html = f"""
        <h1>PRIMERA - FECHA: OCTAVA</h1>
        <table width="90%">
          <tr>
            <td>
              <table>
                <tr><td>ARGENTINO</td><td>2</td><td>1</td><td>EL LINQUEÑO</td></tr>
                <tr><td>1</td><td>CARLOS LÓPEZ</td><td></td><td>1</td><td>JOSÉ GÓMEZ</td><td></td></tr>
                <tr><td>9</td><td>JUAN PÉREZ</td><td></td><td>4</td><td>PABLO MUÑOZ</td><td></td></tr>
                <tr><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td>JUAN PÉREZ</td><td>1-0</td></tr>
                <tr><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td>JOSÉ GÓMEZ</td><td>1-1</td></tr>
                <tr><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td>JUAN PÉREZ</td><td>2-1</td></tr>
                <tr><td>ATL. PASTEUR</td><td></td><td></td><td>CA. PINTENSE</td></tr>
                <tr><td>1</td><td>TOMÁS SILVA</td><td></td><td>1</td><td>MARTÍN LUNA</td><td></td></tr>
              </table>
            </td>
          </tr>
        </table>
        """
        matches = lineups.parse_lineups_html(html)
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].local, "ARGENTINO")
        self.assertEqual(len(matches[0].local_players), 2)
        self.assertEqual(len(matches[0].visitor_players), 2)


class LineupPlanningTests(unittest.TestCase):
    def test_unique_matches_build_complete_replacements_without_result_fields(self) -> None:
        plan = valid_plan()

        self.assertTrue(plan.valid)
        self.assertEqual([entry.fixture_id for entry in plan.entries], [801, 802])
        self.assertEqual(sum(len(entry.lineup_rows) for entry in plan.entries), 10)
        self.assertEqual(plan.entries[0].metadata["arbitro"], "ROBERTO DÍAZ")
        forbidden = {"goles_local", "goles_visitante", "estado"}
        self.assertTrue(
            all(forbidden.isdisjoint(row) for entry in plan.entries for row in entry.lineup_rows)
        )
        self.assertTrue(forbidden.isdisjoint(plan.entries[0].metadata))

    def test_unknown_missing_and_ambiguous_fixture_targets_are_blocking(self) -> None:
        matches = parsed_matches()
        unknown = replace(matches[0], local="UNKNOWN", local_id=None)
        unknown_plan = lineups.build_replacement_plan([unknown], fixture_records(), 2, 8, 1)
        missing_plan = lineups.build_replacement_plan(matches, fixture_records(INVENTORY[1:]), 2, 8, 1)
        duplicate = {**INVENTORY[0], "id": 899}
        ambiguous_plan = lineups.build_replacement_plan(
            [matches[0]], fixture_records([INVENTORY[0], duplicate]), 2, 8, 1
        )

        self.assertTrue(any("Unknown local club" in issue for issue in unknown_plan.issues))
        self.assertTrue(any("Missing fixture target" in issue for issue in missing_plan.issues))
        self.assertTrue(any("Ambiguous fixture target" in issue for issue in ambiguous_plan.issues))
        for plan in (unknown_plan, missing_plan, ambiguous_plan):
            client = FakeClient()
            with self.assertRaisesRegex(ValueError, "invalid or empty"):
                lineups.execute_replacement_plan(client, plan)
            self.assertEqual(client.mutation_attempts, 0)

    def test_duplicate_targets_lineup_identities_and_wrong_teams_are_blocking(self) -> None:
        match = parsed_matches()[0]
        duplicate_target = lineups.build_replacement_plan(
            [match, match], fixture_records(), 2, 8, 1
        )
        duplicate_player = replace(
            match,
            local_players=(*match.local_players, match.local_players[0]),
        )
        duplicate_lineup = lineups.build_replacement_plan(
            [duplicate_player], fixture_records(), 2, 8, 1
        )
        wrong_player = replace(match.local_players[0], team_id=999)
        wrong_team = lineups.build_replacement_plan(
            [replace(match, local_players=(wrong_player, *match.local_players[1:]))],
            fixture_records(),
            2,
            8,
            1,
        )

        self.assertTrue(any("matched more than once" in issue for issue in duplicate_target.issues))
        self.assertTrue(any("Duplicate lineup identity" in issue for issue in duplicate_lineup.issues))
        self.assertTrue(any("Team mismatch" in issue for issue in wrong_team.issues))

    def test_round_mismatch_blocks_the_entire_plan(self) -> None:
        match = replace(parsed_matches()[0], round_id=7)
        plan = lineups.build_replacement_plan([match], fixture_records(), 2, 8, 1)

        self.assertFalse(plan.valid)
        self.assertTrue(any("Wrong round" in issue for issue in plan.issues))

    def test_omitted_played_fixture_blocks_the_complete_plan(self) -> None:
        omitted_played = {
            "id": 899,
            "torneo_id": 2,
            "categoria_id": 1,
            "local_id": 3,
            "visitante_id": 5,
            "fecha_id": 8,
            "estado": "jugado",
        }

        plan = lineups.build_replacement_plan(
            parsed_matches(),
            fixture_records([*INVENTORY, omitted_played]),
            2,
            8,
            1,
        )

        self.assertFalse(plan.valid)
        self.assertTrue(
            any("Played fixture omitted" in issue and "fixture=899" in issue for issue in plan.issues)
        )

    def test_omitted_nonplayed_fixtures_do_not_block_for_absence(self) -> None:
        for state in ("programado", "postergado", "libre"):
            with self.subTest(state=state):
                omitted_nonplayed = {
                    "id": 899,
                    "torneo_id": 2,
                    "categoria_id": 1,
                    "local_id": 3,
                    "visitante_id": 5,
                    "fecha_id": 8,
                    "estado": state,
                }
                plan = lineups.build_replacement_plan(
                    parsed_matches(),
                    fixture_records([*INVENTORY, omitted_nonplayed]),
                    2,
                    8,
                    1,
                )

                self.assertTrue(plan.valid, plan.issues)


class InventorySafetyTests(unittest.TestCase):
    def test_inventory_is_tournament_primera_round_scoped_and_bounded(self) -> None:
        client = FakeClient()

        fixtures = lineups.read_fixture_inventory(client, 2, 8, 1)

        self.assertEqual(len(fixtures), 2)
        self.assertEqual(
            client.reads,
            [("partidos", (("torneo_id", 2), ("categoria_id", 1), ("fecha_id", 8)))],
        )
        self.assertEqual(client.limit, lineups.FIXTURE_INVENTORY_LIMIT)
        self.assertEqual(
            client.selected_columns,
            "id,torneo_id,categoria_id,local_id,visitante_id,fecha_id,estado",
        )
        self.assertEqual([fixture.state for fixture in fixtures], ["jugado", "jugado"])

    def test_missing_blank_and_malformed_inventory_state_is_rejected(self) -> None:
        invalid_rows = (
            {key: value for key, value in INVENTORY[0].items() if key != "estado"},
            {**INVENTORY[0], "estado": "   "},
            {**INVENTORY[0], "estado": 1},
        )
        for row in invalid_rows:
            with self.subTest(state=row.get("estado")), self.assertRaisesRegex(
                ValueError,
                "fixture estado",
            ):
                lineups.FixtureRecord.from_mapping(row)

    def test_possible_inventory_truncation_is_rejected(self) -> None:
        client = FakeClient(inventory=[INVENTORY[0]] * lineups.FIXTURE_INVENTORY_LIMIT)

        with self.assertRaisesRegex(RuntimeError, "safety limit"):
            lineups.read_fixture_inventory(client, 2, 8, 1)
        self.assertEqual(client.mutation_attempts, 0)


class ExecutionSafetyTests(unittest.TestCase):
    def test_dry_run_reads_and_reports_without_mutating(self) -> None:
        client = FakeClient()
        output = io.StringIO()

        exit_code = lineups.main(
            ["--torneo-id", "2", "--fecha", "8", "--source", str(FIXTURE_PATH)],
            client_factory=lambda: client,
            stdout=output,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(client.mutation_attempts, 0)
        self.assertIn("Dry run only", output.getvalue())
        self.assertIn("non-transactional", output.getvalue())

    def test_no_published_lineups_is_a_no_op_without_database_access(self) -> None:
        client_factory = mock.Mock()
        output = io.StringIO()

        exit_code = lineups.main(
            ["--torneo-id", "2", "--fecha", "8"],
            client_factory=client_factory,
            source_loader=lambda source, timeout: "<h1>FECHA 8</h1>",
            stdout=output,
        )

        self.assertEqual(exit_code, 0)
        self.assertIn("No alineaciones publicadas", output.getvalue())
        client_factory.assert_not_called()

    def test_fecha_defaults_to_page_round_when_omitted(self) -> None:
        client = FakeClient()
        output = io.StringIO()

        exit_code = lineups.main(
            ["--torneo-id", "2", "--source", str(FIXTURE_PATH)],
            client_factory=lambda: client,
            stdout=output,
        )

        self.assertEqual(exit_code, 0)
        self.assertIn("Selected round: 8", output.getvalue())

    def test_execute_uses_narrow_deletes_updates_and_validated_inserts(self) -> None:
        client = FakeClient()

        counts = lineups.execute_replacement_plan(client, valid_plan())

        self.assertEqual(counts, {"fixtures_replaced": 2, "lineups_inserted": 10, "metadata_updated": 2})
        deletes = [item for item in client.mutations if item[1] == "delete"]
        inserts = [item for item in client.mutations if item[1] == "insert"]
        updates = [item for item in client.mutations if item[1] == "update"]
        self.assertEqual([item[3] for item in deletes], [(('partido_id', 801),), (('partido_id', 802),)])
        self.assertEqual(len(inserts), 2)
        self.assertEqual(
            {(row["partido_id"], row["equipo_id"]) for item in inserts for row in item[2]},
            {(801, 1), (801, 8), (802, 2), (802, 4)},
        )
        for table, _, values, filters in updates:
            self.assertEqual(table, "partidos")
            self.assertIn(("torneo_id", 2), filters)
            self.assertEqual(sum(column == "id" for column, _ in filters), 1)
            self.assertTrue({"goles_local", "goles_visitante", "estado"}.isdisjoint(values))

    def test_execute_failure_is_visible_and_returns_nonzero(self) -> None:
        direct = FakeClient(write_error=RuntimeError("database write failed"))
        with self.assertRaisesRegex(RuntimeError, "database write failed"):
            lineups.execute_replacement_plan(direct, valid_plan())
        self.assertEqual(direct.mutation_attempts, 1)

        cli_client = FakeClient(write_error=RuntimeError("database write failed"))
        error_output = io.StringIO()
        exit_code = lineups.main(
            [
                "--torneo-id",
                "2",
                "--fecha",
                "8",
                "--source",
                str(FIXTURE_PATH),
                "--execute",
            ],
            client_factory=lambda: cli_client,
            stderr=error_output,
        )
        self.assertEqual(exit_code, 2)
        self.assertIn("database write failed", error_output.getvalue())

    def test_missing_tournament_scope_fails_before_fetch_or_database_access(self) -> None:
        source_loader = mock.Mock()
        client_factory = mock.Mock()
        error_output = io.StringIO()
        with mock.patch.dict(os.environ, {}, clear=True), mock.patch.object(
            lineups, "load_backend_environment", return_value=False
        ):
            exit_code = lineups.main(
                ["--fecha", "8"],
                client_factory=client_factory,
                source_loader=source_loader,
                stderr=error_output,
            )

        self.assertEqual(exit_code, 2)
        self.assertIn("Tournament ID is required", error_output.getvalue())
        source_loader.assert_not_called()
        client_factory.assert_not_called()

    def test_import_and_help_have_no_credentials_or_external_side_effects(self) -> None:
        environment = os.environ.copy()
        for name in ("SUPABASE_URL", "SUPABASE_KEY", "ACTIVE_TORNEO_ID"):
            environment.pop(name, None)
        imported = subprocess.run(
            [
                sys.executable,
                "-c",
                "import sys; sys.path.insert(0, 'backend/scripts'); "
                "import scraper_alineaciones; print('import-ok')",
            ],
            cwd=REPO_DIR,
            env=environment,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        helped = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "scraper_alineaciones.py"), "--help"],
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
        self.assertIn("--fecha", helped.stdout)
        self.assertIn("--execute", helped.stdout)
        self.assertNotIn("--dry-run", helped.stdout)
        self.assertNotIn("--no-deploy", helped.stdout)


if __name__ == "__main__":
    unittest.main()
