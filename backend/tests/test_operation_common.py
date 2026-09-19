"""Tests for the shared backend operational contract."""

from __future__ import annotations

import argparse
import importlib.util
import os
import sys
import types
import unittest
from pathlib import Path
from unittest import mock


BACKEND_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = BACKEND_DIR / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import config  # noqa: E402
import operation_common  # noqa: E402


class TournamentIdValidationTests(unittest.TestCase):
    def test_positive_tournament_ids_are_normalized(self) -> None:
        self.assertEqual(operation_common.validate_positive_tournament_id(7), 7)
        self.assertEqual(operation_common.validate_positive_tournament_id(" 9 "), 9)

    def test_non_positive_and_non_integer_ids_are_rejected(self) -> None:
        for value in (0, -1, 1.5, "0", "-2", "abc", "1.5", True, None):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "positive integer"):
                    operation_common.validate_positive_tournament_id(value)

    def test_explicit_tournament_id_precedes_environment(self) -> None:
        resolved = operation_common.resolve_tournament_id(
            "8",
            environ={operation_common.ACTIVE_TOURNAMENT_ENV: "3"},
        )
        self.assertEqual(resolved, 8)


class EnvironmentResolutionTests(unittest.TestCase):
    def test_active_tournament_id_is_optional_when_unset(self) -> None:
        self.assertIsNone(operation_common.resolve_active_tournament_id({}))
        self.assertIsNone(
            operation_common.resolve_active_tournament_id(
                {operation_common.ACTIVE_TOURNAMENT_ENV: "  "}
            )
        )

    def test_active_tournament_id_is_validated_without_fallback(self) -> None:
        for value in ("0", "-1", "not-an-id"):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "ACTIVE_TORNEO_ID"):
                    operation_common.resolve_active_tournament_id(
                        {operation_common.ACTIVE_TOURNAMENT_ENV: value}
                    )

    def test_missing_explicit_and_environment_id_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "Pass --torneo-id"):
            operation_common.resolve_tournament_id(environ={})

    def test_environment_loader_uses_backend_file_without_overrides(self) -> None:
        custom_path = BACKEND_DIR / "test.env"
        with mock.patch.object(operation_common, "load_dotenv", return_value=True) as loader:
            loaded = operation_common.load_backend_environment(custom_path)

        self.assertTrue(loaded)
        loader.assert_called_once_with(dotenv_path=custom_path, override=False)


class LazySupabaseCompatibilityTests(unittest.TestCase):
    def test_config_import_without_credentials_does_not_create_client(self) -> None:
        module_name = "config_without_credentials_test"
        module_spec = importlib.util.spec_from_file_location(
            module_name,
            SCRIPTS_DIR / "config.py",
        )
        self.assertIsNotNone(module_spec)
        self.assertIsNotNone(module_spec.loader)
        module = importlib.util.module_from_spec(module_spec)
        create_client = mock.Mock(name="create_client")
        fake_supabase_module = types.SimpleNamespace(create_client=create_client)

        try:
            with mock.patch.dict(os.environ, {}, clear=True), mock.patch.object(
                operation_common,
                "load_backend_environment",
                return_value=False,
            ), mock.patch.dict(sys.modules, {"supabase": fake_supabase_module}):
                sys.modules[module_name] = module
                module_spec.loader.exec_module(module)
        finally:
            sys.modules.pop(module_name, None)

        self.assertIsNone(module.ACTIVE_TORNEO_ID)
        self.assertIsNone(module.SUPABASE_URL)
        self.assertIsNone(module.SUPABASE_KEY)
        create_client.assert_not_called()

    def test_missing_credentials_fail_only_when_client_is_requested(self) -> None:
        with mock.patch.object(config, "SUPABASE_URL", None), mock.patch.object(
            config,
            "SUPABASE_KEY",
            None,
        ):
            with self.assertRaisesRegex(RuntimeError, "credentials are required"):
                config._create_supabase_client()

    def test_supabase_proxy_preserves_table_calls_and_caches_client(self) -> None:
        client = mock.Mock()
        client.table.side_effect = lambda name: f"table:{name}"
        factory = mock.Mock(return_value=client)
        proxy = config.LazySupabaseClient(factory)

        factory.assert_not_called()
        self.assertEqual(proxy.table("partidos"), "table:partidos")
        self.assertEqual(proxy.table("clubes"), "table:clubes")
        factory.assert_called_once_with()
        self.assertEqual(
            client.table.call_args_list,
            [mock.call("partidos"), mock.call("clubes")],
        )

    def test_existing_identity_constants_remain_available(self) -> None:
        self.assertEqual(config.MAPEO_CLUBES["ARGENTINO"], 1)
        self.assertEqual(config.CATEGORIAS["primera"], 1)
        self.assertIn(1, config.EQUIPOS_POR_CATEGORIA[1])
        self.assertTrue(callable(config.supabase.table))


class OperationCliContractTests(unittest.TestCase):
    def test_cli_defaults_to_dry_run_and_resolves_environment_scope(self) -> None:
        parser = argparse.ArgumentParser()
        operation_common.add_operation_arguments(parser)

        args = parser.parse_args([])
        context = operation_common.operation_context_from_args(
            args,
            environ={operation_common.ACTIVE_TOURNAMENT_ENV: "4"},
        )

        self.assertEqual(context.mode, "dry-run")
        self.assertEqual(
            context.summary("schedule-import", {"planned": 3}),
            {
                "operation": "schedule-import",
                "mode": "dry-run",
                "tournament_id": 4,
                "metadata": {"planned": 3},
            },
        )

    def test_execute_mode_requires_an_explicit_flag(self) -> None:
        parser = argparse.ArgumentParser()
        operation_common.add_operation_arguments(parser)

        args = parser.parse_args(["--torneo-id", "6", "--execute"])
        context = operation_common.operation_context_from_args(args, environ={})

        self.assertEqual(context.tournament_id, 6)
        self.assertEqual(context.mode, "execute")


if __name__ == "__main__":
    unittest.main()
