"""Network-free tests for activation, standings initialization, and palmares."""

from __future__ import annotations

import io
import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import activar_torneo as activation  # noqa: E402
import fuente_fixture_actual as profiles  # noqa: E402
import inicializar_posiciones_torneo as initializer  # noqa: E402
import upsert_palmares as palmares  # noqa: E402
from operation_common import OperationContext  # noqa: E402


SETUP_PROFILE = profiles.CurrentFixtureSourceProfile(
    key="primavera-verano-2026",
    display_name="Target",
    slug="target",
    season=2026,
    parser_format=profiles.CURRENT_TABLE_FORMAT,
    parser_version=profiles.CURRENT_TABLE_VERSION,
    category_sources={"primera": "https://example.invalid/primera"},
    category_expectations={
        "primera": profiles.CategoryCompletenessExpectation(frozenset({1}), 2)
    },
)


class FakeQuery:
    def __init__(self, client: "FakeClient", table: str) -> None:
        self.client = client
        self.table = table
        self.operation = "select"
        self.values = None
        self.filters: list[tuple[str, object]] = []
        self.range_value: tuple[int, int] | None = None
        self.order_value: tuple[str, bool] | None = None
        self.count_mode = None

    def select(self, columns: str, **kwargs: object) -> "FakeQuery":
        self.operation = "select"
        self.count_mode = kwargs.get("count")
        self.client.columns.append((self.table, columns))
        return self

    def insert(self, values: object) -> "FakeQuery":
        self.operation = "insert"
        self.values = values
        return self

    def update(self, values: object) -> "FakeQuery":
        self.operation = "update"
        self.values = values
        return self

    def eq(self, field: str, value: object) -> "FakeQuery":
        self.filters.append((field, value))
        return self

    def in_(self, field: str, values: object) -> "FakeQuery":
        self.filters.append((field, tuple(values)))
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
            if self.count_mode != "exact" or self.range_value is None:
                raise AssertionError("all setup reads must use exact pagination")
            rows = list(self.client.inventory.get(self.table, []))
            if not self.client.ignore_filters:
                for field, value in self.filters:
                    if isinstance(value, tuple):
                        rows = [row for row in rows if row.get(field) in value]
                    else:
                        rows = [row for row in rows if row.get(field) == value]
            start, end = self.range_value
            cap = self.client.server_caps.get(self.table)
            if cap is not None:
                end = min(end, start + cap - 1)
            self.client.reads.append(
                (self.table, tuple(self.filters), self.range_value, self.order_value)
            )
            return SimpleNamespace(data=rows[start : end + 1], count=len(rows))

        self.client.write_attempts += 1
        if self.client.write_error_at == self.client.write_attempts:
            raise RuntimeError("database write failed")
        self.client.mutations.append(
            (self.table, self.operation, self.values, tuple(self.filters))
        )
        return SimpleNamespace(data=[{"id": 999}])


class FakeClient:
    def __init__(
        self,
        *,
        server_caps=None,
        write_error_at=None,
        read_error=None,
        ignore_filters: bool = False,
        **tables,
    ) -> None:
        self.inventory = {key: list(value) for key, value in tables.items()}
        self.server_caps = dict(server_caps or {})
        self.write_error_at = write_error_at
        self.read_error = read_error
        self.ignore_filters = ignore_filters
        self.reads: list[tuple[object, ...]] = []
        self.columns: list[tuple[str, str]] = []
        self.mutations: list[tuple[object, ...]] = []
        self.write_attempts = 0

    def table(self, name: str) -> FakeQuery:
        return FakeQuery(self, name)


def fixture(
    row_id: int,
    *,
    category: int = 1,
    local: object = 1,
    visitor: object = 2,
    state: str = "programado",
    local_goals=None,
    visitor_goals=None,
) -> dict[str, object]:
    return {
        "id": row_id,
        "torneo_id": 7,
        "categoria_id": category,
        "local_id": local,
        "visitante_id": visitor,
        "fecha_id": 1,
        "estado": state,
        "goles_local": local_goals,
        "goles_visitante": visitor_goals,
    }


def position(
    row_id: int,
    club: int,
    *,
    category: int = 1,
    **changes: object,
) -> dict[str, object]:
    row: dict[str, object] = {
        "id": row_id,
        "torneo_id": 7,
        "categoria_id": category,
        "club_id": club,
        "pts": 0,
        "pj": 0,
        "pg": 0,
        "pe": 0,
        "pp": 0,
        "gf": 0,
        "gc": 0,
        "dif": 0,
        "ultimos_5": [],
    }
    row.update(changes)
    return row


def setup_client(*, target_active: bool = False, include_old_active: bool = True, **kwargs) -> FakeClient:
    tournaments = [
        {"id": 7, "nombre": "Target", "slug": "target", "temporada": 2026, "activo": target_active}
    ]
    if include_old_active:
        tournaments.append(
            {"id": 6, "nombre": "Old", "slug": "old", "temporada": 2025, "activo": True}
        )
    defaults = {
        "torneos": tournaments,
        "partidos": [fixture(1), fixture(2, local=3, visitor=None, state="libre")],
        "posiciones": [position(10, 1), position(11, 2), position(12, 3)],
    }
    defaults.update(kwargs)
    return FakeClient(**defaults)


def inspect_activation(client: FakeClient) -> activation.ActivationPlan:
    return activation.inspect_activation(client, 7, SETUP_PROFILE)


def run_activation_main(argv, **kwargs):
    with mock.patch.object(activation, "get_source_profile", return_value=SETUP_PROFILE):
        return activation.main(argv, **kwargs)


def run_initializer_main(argv, **kwargs):
    with mock.patch.object(initializer, "get_source_profile", return_value=SETUP_PROFILE):
        return initializer.main(argv, **kwargs)


def palmares_client(*, existing=(), **kwargs) -> FakeClient:
    defaults = {
        "torneos": [{"id": 7, "nombre": "Target"}],
        "categorias": [{"id": 1, "nombre": "Primera"}],
        "clubes": [{"id": 3, "nombre": "Club Three"}],
        "palmares": list(existing),
    }
    defaults.update(kwargs)
    return FakeClient(**defaults)


def champion(**changes: object) -> dict[str, object]:
    row: dict[str, object] = {
        "id": 20,
        "nombre": "Champion 2026",
        "temporada": "2026",
        "club_id": 3,
        "torneo_id": 7,
        "categoria_id": 1,
    }
    row.update(changes)
    return row


class ActivationTests(unittest.TestCase):
    def test_readiness_accepts_zero_or_coherent_progressed_standings(self) -> None:
        client = setup_client(
            posiciones=[
                position(10, 1, pts=3, pj=1, pg=1, gf=2, gc=1, dif=1, ultimos_5=["G"]),
                position(11, 2, pj=1, pp=1, gf=1, gc=2, dif=-1, ultimos_5=["P"]),
                position(12, 3),
            ]
        )
        plan = inspect_activation(client)
        self.assertTrue(plan.valid, plan.issues)
        self.assertEqual(plan.deactivate_ids, (6,))

    def test_already_sole_active_is_noop(self) -> None:
        client = setup_client(target_active=True, include_old_active=False)
        plan = inspect_activation(client)
        self.assertTrue(plan.noop)
        self.assertEqual(activation.execute_activation(client, plan), {"activated": 0, "deactivated": 0})
        self.assertEqual(client.mutations, [])

    def test_execution_is_target_first_then_narrow_deactivation(self) -> None:
        client = setup_client()
        plan = inspect_activation(client)
        counts = activation.execute_activation(client, plan)
        self.assertEqual(counts, {"activated": 1, "deactivated": 1})
        self.assertEqual(
            client.mutations,
            [
                ("torneos", "update", {"activo": True}, (("id", 7),)),
                ("torneos", "update", {"activo": False}, (("id", 6),)),
            ],
        )

    def test_missing_or_partial_fixture_blocks(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "fixture is empty"):
            inspect_activation(setup_client(partidos=[]))
        with self.assertRaisesRegex(RuntimeError, "Incomplete fixture row count"):
            inspect_activation(setup_client(partidos=[fixture(1)]))
        plan = inspect_activation(
            setup_client(posiciones=[position(10, 1), position(11, 2)])
        )
        self.assertFalse(plan.valid)
        self.assertIn("Missing position identities", "\n".join(plan.issues))

    def test_duplicate_malformed_and_out_of_scope_inventories_block(self) -> None:
        cases = (
            setup_client(posiciones=[position(10, 1), position(11, 1), position(12, 2), position(13, 3)]),
            setup_client(posiciones=[position(10, 1, pts=True), position(11, 2), position(12, 3)]),
            setup_client(posiciones=[position(10, 1), position(11, 2), position(12, 99)]),
        )
        for client in cases:
            with self.subTest(client=client):
                plan = inspect_activation(client)
                self.assertFalse(plan.valid)
        with self.assertRaisesRegex(RuntimeError, "repeated row id"):
            inspect_activation(setup_client(partidos=[fixture(1), fixture(1)]))

    def test_server_caps_paginate_and_write_failure_is_nonzero(self) -> None:
        client = setup_client(server_caps={"partidos": 1, "posiciones": 1, "torneos": 1})
        plan = inspect_activation(client)
        self.assertTrue(plan.valid, plan.issues)
        starts = [read[2][0] for read in client.reads if read[0] == "posiciones"]
        self.assertEqual(starts, [0, 1, 2])
        self.assertTrue(
            {"torneos", "partidos", "posiciones"}.issubset(
                {read[0] for read in client.reads}
            )
        )
        self.assertTrue(all(read[3] == ("id", False) for read in client.reads))

        failing = setup_client(write_error_at=2)
        error = io.StringIO()
        code = run_activation_main(
            ["--profile", "primavera-verano-2026", "--torneo-id", "7", "--execute"],
            client_factory=lambda: failing,
            stderr=error,
        )
        self.assertEqual(code, 2)
        self.assertIn("database write failed", error.getvalue())
        self.assertEqual(failing.mutations[0][3], (("id", 7),))

    def test_dry_run_and_required_id_never_mutate(self) -> None:
        client = setup_client()
        output = io.StringIO()
        code = run_activation_main(
            ["--profile", "primavera-verano-2026", "--torneo-id", "7"],
            client_factory=lambda: client,
            stdout=output,
        )
        self.assertEqual(code, 0)
        self.assertIn("temporarily remain active", output.getvalue())
        self.assertEqual(client.write_attempts, 0)
        with self.assertRaises(SystemExit):
            activation.build_parser().parse_args([])
        with mock.patch.dict(os.environ, {"ACTIVE_TORNEO_ID": "7"}, clear=True):
            with self.assertRaises(SystemExit):
                activation.build_parser().parse_args(
                    ["--profile", "primavera-verano-2026"]
                )


class InitializationTests(unittest.TestCase):
    def test_partial_fixture_blocks_before_position_initialization(self) -> None:
        client = setup_client(partidos=[fixture(1)], posiciones=[])
        code = run_initializer_main(
            ["--profile", "primavera-verano-2026", "--torneo-id", "7"],
            client_factory=lambda: client,
            stderr=io.StringIO(),
        )
        self.assertEqual(code, 2)
        self.assertEqual(client.write_attempts, 0)

    def test_derives_fixture_participants_including_byes(self) -> None:
        readiness = initializer.read_fixture_readiness(setup_client(), 7)
        self.assertEqual(readiness.participants, {1: frozenset({1, 2, 3})})

    def test_exact_zero_coverage_is_noop(self) -> None:
        client = setup_client()
        readiness = initializer.read_fixture_readiness(client, 7)
        plan = initializer.build_initialization_plan(readiness, client.inventory["posiciones"], 7)
        self.assertTrue(plan.noop)
        self.assertEqual(initializer.execute_initialization(client, plan), 0)

    def test_safely_completes_only_missing_expected_rows(self) -> None:
        client = setup_client(posiciones=[position(10, 1)])
        readiness = initializer.read_fixture_readiness(client, 7)
        plan = initializer.build_initialization_plan(readiness, client.inventory["posiciones"], 7)
        self.assertTrue(plan.valid, plan.issues)
        self.assertEqual([(row["categoria_id"], row["club_id"]) for row in plan.inserts], [(1, 2), (1, 3)])
        initializer.execute_initialization(client, plan)
        inserted = client.mutations[0][2]
        self.assertTrue(all(row["torneo_id"] == 7 for row in inserted))
        self.assertEqual({row["club_id"] for row in inserted}, {2, 3})

    def test_every_unsafe_existing_or_fixture_state_blocks_all_writes(self) -> None:
        cases = (
            ([position(10, 1), position(11, 2), position(12, 99)], [fixture(1), fixture(2, local=3, visitor=None, state="libre")]),
            ([position(10, 1), position(11, 1), position(12, 2), position(13, 3)], [fixture(1), fixture(2, local=3, visitor=None, state="libre")]),
            ([position(10, 1, pts=1), position(11, 2), position(12, 3)], [fixture(1), fixture(2, local=3, visitor=None, state="libre")]),
            ([position(10, 1, ultimos_5=["G"]), position(11, 2), position(12, 3)], [fixture(1), fixture(2, local=3, visitor=None, state="libre")]),
            ([position(10, 1, pj="0"), position(11, 2), position(12, 3)], [fixture(1), fixture(2, local=3, visitor=None, state="libre")]),
            ([position(10, 1), position(11, 2), position(12, 3)], [fixture(1, state="jugado", local_goals=1, visitor_goals=0), fixture(2, local=3, visitor=None, state="libre")]),
        )
        for positions, fixtures in cases:
            with self.subTest(positions=positions, fixtures=fixtures):
                client = setup_client(posiciones=positions, partidos=fixtures)
                readiness = initializer.read_fixture_readiness(client, 7)
                plan = initializer.build_initialization_plan(readiness, positions, 7)
                self.assertFalse(plan.valid)
                with self.assertRaises(ValueError):
                    initializer.execute_initialization(client, plan)
                self.assertEqual(client.write_attempts, 0)

    def test_dry_run_repeated_categories_and_execute_insert(self) -> None:
        dry = setup_client(posiciones=[position(10, 1)])
        output = io.StringIO()
        code = run_initializer_main(
            [
                "--profile", "primavera-verano-2026",
                "--torneo-id", "7",
                "--category", "primera",
                "--category", "primera",
            ],
            client_factory=lambda: dry,
            stdout=output,
        )
        self.assertEqual(code, 0)
        self.assertEqual(dry.write_attempts, 0)

        execute = setup_client(posiciones=[position(10, 1)])
        code = run_initializer_main(
            ["--profile", "primavera-verano-2026", "--torneo-id", "7", "--execute"],
            client_factory=lambda: execute,
            stdout=io.StringIO(),
        )
        self.assertEqual(code, 0)
        self.assertEqual(execute.mutations[0][0:2], ("posiciones", "insert"))
        with self.assertRaises(SystemExit):
            initializer.build_parser().parse_args([])
        with mock.patch.dict(os.environ, {"ACTIVE_TORNEO_ID": "7"}, clear=True):
            with self.assertRaises(SystemExit):
                initializer.build_parser().parse_args(
                    ["--profile", "primavera-verano-2026"]
                )
        with self.assertRaises(SystemExit):
            initializer.build_parser().parse_args(
                ["--profile", "primavera-verano-2026", "--torneo-id", "7", "--force"]
            )


class PalmaresTests(unittest.TestCase):
    ARGS = {
        "category_id": 1,
        "club_id": 3,
        "name": "Champion 2026",
        "season": "2026",
    }

    def plan(self, client: FakeClient, *, replace: bool = False) -> palmares.PalmaresPlan:
        return palmares.build_plan(
            client,
            OperationContext(7),
            replace_existing=replace,
            **self.ARGS,
        )

    def test_insert_and_exact_same_record_noop(self) -> None:
        client = palmares_client()
        plan = self.plan(client)
        self.assertEqual(plan.action, "insert")
        self.assertEqual(
            {read[0] for read in client.reads},
            {"torneos", "categorias", "clubes", "palmares"},
        )
        self.assertTrue(all(read[3] == ("id", False) for read in client.reads))
        palmares.execute_plan(client, plan)
        self.assertEqual(client.mutations[0][0:2], ("palmares", "insert"))

        same = palmares_client(existing=[champion()])
        noop = self.plan(same)
        self.assertTrue(noop.noop)
        self.assertEqual(palmares.execute_plan(same, noop), [])
        self.assertEqual(same.write_attempts, 0)

    def test_conflict_blocks_unless_explicit_replacement_is_narrow(self) -> None:
        client = palmares_client(existing=[champion(club_id=2)])
        blocked = self.plan(client)
        self.assertFalse(blocked.valid)
        with self.assertRaises(ValueError):
            palmares.execute_plan(client, blocked)

        replace_client = palmares_client(existing=[champion(club_id=2)])
        replacement = self.plan(replace_client, replace=True)
        self.assertEqual(replacement.action, "update")
        palmares.execute_plan(replace_client, replacement)
        mutation = replace_client.mutations[0]
        self.assertEqual(mutation[0:2], ("palmares", "update"))
        self.assertEqual(
            mutation[3],
            (("id", 20), ("torneo_id", 7), ("categoria_id", 1)),
        )

    def test_duplicate_existing_and_malformed_references_block(self) -> None:
        with self.assertRaisesRegex(Exception, "Duplicate palmares"):
            self.plan(palmares_client(existing=[champion(), champion(id=21)]))
        with self.assertRaisesRegex(Exception, "malformed nombre"):
            self.plan(palmares_client(clubes=[{"id": 3, "nombre": ""}]))

    def test_missing_and_out_of_scope_references_block_independently(self) -> None:
        with self.assertRaisesRegex(Exception, "Missing club reference"):
            self.plan(palmares_client(clubes=[]))

        out_of_scope = palmares_client(
            clubes=[{"id": 99, "nombre": "Wrong"}],
            ignore_filters=True,
        )
        with self.assertRaisesRegex(Exception, "out-of-scope"):
            palmares.require_reference(out_of_scope, "clubes", 3, "club")

    def test_all_values_are_required_and_dry_run_never_writes(self) -> None:
        parser = palmares.build_parser()
        with self.assertRaises(SystemExit):
            parser.parse_args(["--torneo-id", "7"])
        with mock.patch.dict(os.environ, {"ACTIVE_TORNEO_ID": "7"}, clear=True):
            with self.assertRaises(SystemExit):
                parser.parse_args(
                    [
                        "--categoria-id", "1",
                        "--club-id", "3",
                        "--nombre", "Champion 2026",
                        "--temporada", "2026",
                    ]
                )
        client = palmares_client()
        output = io.StringIO()
        code = palmares.main(
            [
                "--torneo-id", "7",
                "--categoria-id", "1",
                "--club-id", "3",
                "--nombre", "Champion 2026",
                "--temporada", "2026",
            ],
            client_factory=lambda: client,
            stdout=output,
        )
        self.assertEqual(code, 0)
        self.assertIn("Dry run only", output.getvalue())
        self.assertEqual(client.write_attempts, 0)


if __name__ == "__main__":
    unittest.main()
