"""Contract tests for the local control panel and scheduled scraper runners."""

from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import tempfile
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace


PROJECT_DIR = Path(__file__).resolve().parents[2]
PANEL_PATH = PROJECT_DIR / "scripts" / "control-panel" / "app.py"
RUNNER_HORARIOS = PROJECT_DIR / "scripts" / "run_scraper_horarios.sh"
RUNNER_RESULTADOS = PROJECT_DIR / "scripts" / "run_scraper_resultados.sh"
RUNNER_WRAPPER = PROJECT_DIR / "scripts" / "run_scraper_wrapper.sh"
RESULTADOS_SERVICE = PROJECT_DIR / "scripts" / "scraper-resultados.service"
RESULTADOS_TIMER = PROJECT_DIR / "scripts" / "scraper-resultados.timer"
ALINEACIONES_TIMER = PROJECT_DIR / "scripts" / "scraper-alineaciones.timer"
SYSTEMD_INSTALLER = PROJECT_DIR / "scripts" / "install_scraper_systemd.sh"
CRONTAB_PATH = PROJECT_DIR / "scripts" / "crontab"
PANEL_LAUNCHER = PROJECT_DIR / "abrir-panel-liga.sh"
WINDOWS_PANEL_LAUNCHER = PROJECT_DIR / "abrir-panel-liga.bat"
PANEL_README = PROJECT_DIR / "scripts" / "control-panel" / "README.md"
COMMANDS_GUIDE = PROJECT_DIR / "COMANDOS.md"
BACKEND_OPERATIONS_GUIDE = PROJECT_DIR / "backend" / "README_OPERACIONES.md"


def load_control_panel():
    spec = importlib.util.spec_from_file_location("liga_control_panel_test", PANEL_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load control panel from {PANEL_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


panel = load_control_panel()


class ScheduleValidationTests(unittest.TestCase):
    def valid_params(self, **overrides):
        params = {
            "script": "ambos",
            "torneo_id": "3",
            "fecha": "9",
            "category": "primera",
            "mode": "date",
            "run_date": "2026-10-02",
            "start_time": "19:00",
            "end_time": "19:20",
            "interval_minutes": "10",
            "confirm_text": "ESCRIBIR",
        }
        params.update(overrides)
        return params

    def test_date_schedule_is_normalized_and_expanded_inclusively(self):
        schedule = panel.validate_schedule_params(
            self.valid_params(), today=date(2026, 9, 30)
        )

        self.assertEqual(schedule["torneo_id"], 3)
        self.assertEqual(schedule["fecha"], 9)
        self.assertEqual(schedule["interval_minutes"], 10)
        self.assertEqual(
            panel.schedule_calendar_entries(schedule),
            [
                "2026-10-02 19:00:00",
                "2026-10-02 19:10:00",
                "2026-10-02 19:20:00",
            ],
        )

    def test_weekly_schedule_uses_systemd_weekday(self):
        schedule = panel.validate_schedule_params(
            self.valid_params(mode="weekly", weekday="wednesday"),
            today=date(2026, 9, 30),
        )

        self.assertEqual(
            panel.schedule_calendar_entries(schedule)[0],
            "Wed *-*-* 19:00:00",
        )

    def test_alignments_require_round_and_confirmation(self):
        for overrides in (
            {"fecha": ""},
            {"confirm_text": "SI"},
        ):
            with self.subTest(overrides=overrides):
                with self.assertRaises(panel.RequestValidationError):
                    panel.validate_schedule_params(
                        self.valid_params(**overrides), today=date(2026, 9, 30)
                    )

    def test_rejects_past_dates_bad_windows_and_unsupported_intervals(self):
        invalid = (
            {"run_date": "2026-09-29"},
            {"start_time": "21:00", "end_time": "20:00"},
            {"interval_minutes": "7"},
        )
        for overrides in invalid:
            with self.subTest(overrides=overrides):
                with self.assertRaises(panel.RequestValidationError):
                    panel.validate_schedule_params(
                        self.valid_params(**overrides), today=date(2026, 9, 30)
                    )

    def test_both_unit_runs_results_then_alignments_without_a_shell(self):
        schedule = panel.validate_schedule_params(
            self.valid_params(), today=date(2026, 9, 30)
        )
        schedule["id"] = "abcdef123456"
        service, timer = panel.build_schedule_units(
            schedule,
            project_dir=Path("/srv/ligadelincoln"),
            python=Path("/srv/ligadelincoln/backend/venv/bin/python"),
        )

        self.assertEqual(service.count("ExecStart="), 2)
        self.assertIn("scraper_resultados.py", service)
        self.assertIn("scraper_alineaciones.py", service)
        self.assertEqual(service.count("--execute"), 2)
        self.assertNotIn("/bin/sh", service)
        self.assertIn("WorkingDirectory=/srv/ligadelincoln", service)
        self.assertNotIn('WorkingDirectory="', service)
        self.assertEqual(timer.count("OnCalendar="), 3)

    def test_working_directory_must_be_an_unquoted_absolute_linux_path(self):
        self.assertEqual(
            panel._systemd_working_directory("/home/gallardo/Documentos/ligadelincoln"),
            "/home/gallardo/Documentos/ligadelincoln",
        )
        with self.assertRaises(panel.ScheduleOperationError):
            panel._systemd_working_directory('"/home/gallardo/Documentos/ligadelincoln"')


class SchedulePersistenceTests(unittest.TestCase):
    def valid_params(self):
        return {
            "script": "resultados",
            "torneo_id": "3",
            "category": "",
            "mode": "date",
            "run_date": "2026-10-02",
            "start_time": "20:00",
            "end_time": "20:10",
            "interval_minutes": "5",
            "confirm_text": "ESCRIBIR",
        }

    def test_create_list_and_delete_manage_exact_user_units(self):
        calls = []

        def runner(command, **kwargs):
            calls.append((command, kwargs))
            return SimpleNamespace(returncode=0, stdout="", stderr="")

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            state_dir = root / "state"
            systemd_dir = root / "systemd"
            schedule = panel.create_schedule(
                self.valid_params(),
                state_dir=state_dir,
                systemd_dir=systemd_dir,
                project_dir=Path("/srv/ligadelincoln"),
                python=Path("/venv/bin/python"),
                runner=runner,
                today=date(2026, 9, 30),
            )

            unit = f"liga-panel-{schedule['id']}"
            self.assertTrue((systemd_dir / f"{unit}.service").is_file())
            self.assertTrue((systemd_dir / f"{unit}.timer").is_file())
            self.assertEqual(panel.list_schedules(state_dir=state_dir), [schedule])
            self.assertIn(
                ["systemctl", "--user", "enable", "--now", f"{unit}.timer"],
                [call[0] for call in calls],
            )

            panel.delete_schedule(
                schedule["id"],
                state_dir=state_dir,
                systemd_dir=systemd_dir,
                runner=runner,
            )

            self.assertEqual(panel.list_schedules(state_dir=state_dir), [])
            self.assertFalse((systemd_dir / f"{unit}.service").exists())
            self.assertFalse((systemd_dir / f"{unit}.timer").exists())

    def test_api_dispatch_keeps_validation_server_side(self):
        created = []
        response, status = panel.dispatch_schedule_create(
            {"params": self.valid_params()},
            lambda params: created.append(params) or {"id": "abcdef123456"},
        )
        self.assertEqual(status, 201)
        self.assertEqual(response["id"], "abcdef123456")
        self.assertEqual(len(created), 1)

        response, status = panel.dispatch_schedule_create(
            {"params": {**self.valid_params(), "confirm_text": ""}},
            lambda params: panel.create_schedule(params),
        )
        self.assertEqual(status, 400)
        self.assertIn("ESCRIBIR", response["error"])


class HttpRequestBoundaryTests(unittest.TestCase):
    def test_content_length_parser_accepts_only_bounded_decimal_lengths(self):
        self.assertEqual(panel.parse_content_length("0"), 0)
        self.assertEqual(
            panel.parse_content_length(str(panel.MAX_REQUEST_BODY_BYTES)),
            panel.MAX_REQUEST_BODY_BYTES,
        )

        invalid_values = (
            None,
            "",
            "-1",
            "+1",
            "1.5",
            "not-a-number",
            str(panel.MAX_REQUEST_BODY_BYTES + 1),
            "9" * 5000,
        )
        for value in invalid_values:
            with self.subTest(value=value):
                with self.assertRaises(panel.RequestValidationError):
                    panel.parse_content_length(value)

    def test_invalid_content_lengths_never_read_or_dispatch(self):
        reads = []
        dispatches = []

        def body_reader(length):
            reads.append(length)
            return b"{}"

        def dispatcher(payload):
            dispatches.append(payload)
            return {"id": "unexpected"}, 201

        invalid_values = (
            "malformed",
            "-1",
            str(panel.MAX_REQUEST_BODY_BYTES + 1),
        )
        for value in invalid_values:
            with self.subTest(value=value):
                response, status = panel.handle_run_http_request(
                    value,
                    body_reader,
                    dispatcher,
                )
                self.assertEqual(status, 400)
                self.assertIn("Content-Length", response["error"])

        self.assertEqual(reads, [])
        self.assertEqual(dispatches, [])

    def test_malformed_json_returns_400_without_dispatch(self):
        dispatches = []
        response, status = panel.handle_run_http_request(
            "1",
            lambda length: b"{",
            lambda payload: dispatches.append(payload),
        )

        self.assertEqual(status, 400)
        self.assertEqual(response, {"error": "JSON inválido"})
        self.assertEqual(dispatches, [])


class PythonResolutionTests(unittest.TestCase):
    def test_override_resolves_relative_to_project(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            project = Path(temporary_directory)
            override = project / "custom" / "python"
            override.parent.mkdir()
            override.touch()

            resolved = panel.resolve_project_python(
                project,
                {"LIGA_PYTHON": "custom/python"},
            )

            self.assertEqual(resolved, override)

    def test_invalid_override_fails_instead_of_falling_back(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            project = Path(temporary_directory)
            fallback = project / "backend" / "venv" / "bin" / "python"
            fallback.parent.mkdir(parents=True)
            fallback.touch()

            with self.assertRaisesRegex(panel.PythonResolutionError, "LIGA_PYTHON"):
                panel.resolve_project_python(project, {"LIGA_PYTHON": "missing/python"})

    def test_windows_candidate_is_preferred_and_posix_candidate_is_supported(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            project = Path(temporary_directory)
            windows_python = project / "backend" / "venv" / "Scripts" / "python.exe"
            posix_python = project / "backend" / "venv" / "bin" / "python"
            windows_python.parent.mkdir(parents=True)
            posix_python.parent.mkdir(parents=True)
            windows_python.touch()
            posix_python.touch()

            self.assertEqual(panel.resolve_project_python(project, {}), windows_python)
            windows_python.unlink()
            self.assertEqual(panel.resolve_project_python(project, {}), posix_python)

    def test_missing_project_interpreter_fails_visibly(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            with self.assertRaisesRegex(
                panel.PythonResolutionError,
                "entorno virtual del backend",
            ):
                panel.resolve_project_python(Path(temporary_directory), {})


class ScraperCommandTests(unittest.TestCase):
    PYTHON = Path("test-venv") / "python"

    def expected(self, scraper, *arguments):
        return [
            str(self.PYTHON),
            str(panel.BACKEND_SCRIPTS / f"scraper_{scraper}.py"),
            *arguments,
        ]

    def test_all_six_preview_and_execute_vectors(self):
        cases = (
            (
                "horarios preview",
                "horarios",
                {"torneo_id": "2"},
                False,
                self.expected("horarios", "--torneo-id", "2"),
            ),
            (
                "horarios execute",
                "horarios",
                {"torneo_id": "2"},
                True,
                self.expected("horarios", "--torneo-id", "2", "--execute"),
            ),
            (
                "resultados preview",
                "resultados",
                {"torneo_id": "3", "category": "primera"},
                False,
                self.expected(
                    "resultados",
                    "--torneo-id",
                    "3",
                    "--category",
                    "primera",
                ),
            ),
            (
                "resultados execute",
                "resultados",
                {"torneo_id": "3", "category": "novena"},
                True,
                self.expected(
                    "resultados",
                    "--torneo-id",
                    "3",
                    "--category",
                    "novena",
                    "--execute",
                ),
            ),
            (
                "alineaciones preview",
                "alineaciones",
                {"torneo_id": "4", "fecha": "7"},
                False,
                self.expected(
                    "alineaciones",
                    "--torneo-id",
                    "4",
                    "--fecha",
                    "7",
                ),
            ),
            (
                "alineaciones execute",
                "alineaciones",
                {"torneo_id": "4", "fecha": "7"},
                True,
                self.expected(
                    "alineaciones",
                    "--torneo-id",
                    "4",
                    "--fecha",
                    "7",
                    "--execute",
                ),
            ),
        )

        for label, scraper, params, execute, expected in cases:
            with self.subTest(label=label):
                command = panel.build_scraper_command(
                    scraper,
                    params,
                    execute=execute,
                    python=self.PYTHON,
                )
                self.assertEqual(command, expected)
                self.assertNotIn("--dry-run", command)

    def test_result_category_is_optional(self):
        command = panel.build_scraper_command(
            "resultados",
            {"torneo_id": 2, "category": ""},
            python=self.PYTHON,
        )
        self.assertEqual(
            command,
            self.expected("resultados", "--torneo-id", "2"),
        )

    def test_tournament_id_is_required_and_positive_for_every_scraper_action(self):
        invalid_values = (None, "", "0", "-1", "abc", "1.5", True)
        for action_id in panel.SCRAPER_ACTIONS:
            scraper, execute = panel.SCRAPER_ACTIONS[action_id]
            base_params = {"fecha": "1"} if scraper == "alineaciones" else {}
            if execute:
                base_params["confirm_text"] = "ESCRIBIR"
            for value in invalid_values:
                params = {**base_params, "torneo_id": value}
                with self.subTest(action_id=action_id, value=value):
                    with self.assertRaisesRegex(
                        panel.RequestValidationError,
                        "torneo_id",
                    ):
                        panel.validate_action_request(action_id, params)

    def test_lineup_round_is_required_and_positive(self):
        for value in (None, "", "0", "-3", "abc"):
            with self.subTest(value=value):
                with self.assertRaisesRegex(panel.RequestValidationError, "fecha"):
                    panel.validate_action_request(
                        "scraper_alineaciones_preview",
                        {"torneo_id": "2", "fecha": value},
                    )

    def test_invalid_result_category_is_rejected(self):
        with self.assertRaisesRegex(panel.RequestValidationError, "category inválida"):
            panel.validate_action_request(
                "scraper_resultados_preview",
                {"torneo_id": "2", "category": "reserva"},
            )

    def test_execute_actions_require_escribir_confirmation(self):
        for action_id, (_, execute) in panel.SCRAPER_ACTIONS.items():
            if not execute:
                continue
            with self.subTest(action_id=action_id):
                with self.assertRaisesRegex(panel.RequestValidationError, "ESCRIBIR"):
                    panel.validate_action_request(action_id, {"torneo_id": "2", "fecha": "1"})
                normalized = panel.validate_action_request(
                    action_id,
                    {"torneo_id": "2", "fecha": "1", "confirm_text": " escribir "},
                )
                self.assertNotIn("confirm_text", normalized)

    def test_action_metadata_distinguishes_safe_preview_from_database_write(self):
        for action_id, (_, execute) in panel.SCRAPER_ACTIONS.items():
            action = panel.ACTIONS[action_id]
            with self.subTest(action_id=action_id):
                self.assertEqual(action["risk"], "writes-db" if execute else "safe")
                self.assertEqual(action.get("confirm"), "ESCRIBIR" if execute else None)

    def test_scraper_descriptions_have_no_deploy_assumption(self):
        descriptions = " ".join(
            panel.ACTIONS[action_id]["description"]
            for action_id in panel.SCRAPER_ACTIONS
        ).lower()
        self.assertNotIn("deploy", descriptions)
        self.assertNotIn("desplieg", descriptions)


class RunDispatchTests(unittest.TestCase):
    def test_invalid_scraper_input_returns_400_without_creating_job(self):
        calls = []

        def fake_job_factory(action_id, params):
            calls.append((action_id, params))
            return {"id": "unexpected"}

        response, status = panel.dispatch_run(
            {
                "action_id": "scraper_resultados_preview",
                "params": {"torneo_id": "2", "category": "invalid"},
            },
            job_factory=fake_job_factory,
        )

        self.assertEqual(status, 400)
        self.assertIn("category", response["error"])
        self.assertEqual(calls, [])

    def test_missing_required_input_returns_400_without_creating_job(self):
        calls = []
        response, status = panel.dispatch_run(
            {
                "action_id": "scraper_alineaciones_preview",
                "params": {"torneo_id": "2"},
            },
            job_factory=lambda *args: calls.append(args),
        )

        self.assertEqual(status, 400)
        self.assertIn("fecha", response["error"])
        self.assertEqual(calls, [])

    def test_valid_execute_request_reaches_job_factory_with_normalized_values(self):
        calls = []

        def fake_job_factory(action_id, params):
            calls.append((action_id, params))
            return {"id": "job-1"}

        response, status = panel.dispatch_run(
            {
                "action_id": "scraper_resultados_execute",
                "params": {
                    "torneo_id": "2",
                    "category": "decima",
                    "confirm_text": "ESCRIBIR",
                },
            },
            job_factory=fake_job_factory,
        )

        self.assertEqual(status, 201)
        self.assertEqual(response, {"id": "job-1"})
        self.assertEqual(
            calls,
            [
                (
                    "scraper_resultados_execute",
                    {"torneo_id": 2, "category": "decima"},
                )
            ],
        )


class ShellRunnerContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.horarios = RUNNER_HORARIOS.read_text(encoding="utf-8")
        cls.resultados = RUNNER_RESULTADOS.read_text(encoding="utf-8")

    def test_both_runners_use_strict_project_venv_contract(self):
        for path, contents in (
            (RUNNER_HORARIOS, self.horarios),
            (RUNNER_RESULTADOS, self.resultados),
        ):
            with self.subTest(path=path.name):
                self.assertIn("set -euo pipefail", contents)
                self.assertIn("backend/venv/Scripts/python.exe", contents)
                self.assertIn("backend/venv/bin/python", contents)
                self.assertIn('source "$PROJECT_DIR/backend/.env"', contents)
                self.assertIn("ACTIVE_TORNEO_ID", contents)
                self.assertIn('[[ ! "$ACTIVE_TORNEO_ID" =~ ^[0-9]+$', contents)
                self.assertIn('"$ACTIVE_TORNEO_ID" =~ ^0+$', contents)
                self.assertIn("exit 2", contents)
                self.assertIn('--torneo-id "$ACTIVE_TORNEO_ID"', contents)
                self.assertIn("--execute", contents)
                self.assertNotIn("pip install", contents.lower())
                self.assertNotIn("--break-system-packages", contents)
                self.assertNotIn("deploy", contents.lower())

    def test_results_runner_preserves_schedule_gates_and_configurable_log(self):
        self.assertIn('DAY="$(date +%w)"', self.resultados)
        self.assertIn('HOUR="$(date +%H)"', self.resultados)
        self.assertIn('"$DAY" != "6" && "$DAY" != "0"', self.resultados)
        self.assertIn('"$HOUR" -lt 13', self.resultados)
        self.assertNotIn('"$HOUR" -ge 22', self.resultados)
        self.assertIn('LIGA_FORCE', self.resultados)
        self.assertIn('SCRAPER_LOG_DIR:-/home/gallardo/logs', self.resultados)
        self.assertIn('mkdir -p -- "$LOG_DIR"', self.resultados)
        self.assertIn('scraper_resultados.log', self.resultados)
        validation = 'if [[ ! "$ACTIVE_TORNEO_ID" =~ ^[0-9]+$'
        self.assertLess(self.resultados.index(validation), self.resultados.index('HOUR="$(date +%H)"'))
        self.assertLess(self.resultados.index(validation), self.resultados.index('DAY="$(date +%w)"'))


class ResultsRunnerExecutionTests(unittest.TestCase):
    CATEGORIES = ("primera", "septima", "octava", "novena", "decima")
    BASH = shutil.which("bash") or "bash"

    @staticmethod
    def shell_path(path):
        return Path(path).as_posix()

    def run_isolated_runner(self, failing_category=None):
        with tempfile.TemporaryDirectory(dir=PROJECT_DIR) as temporary_directory:
            project = Path(temporary_directory) / "project"
            scripts = project / "scripts"
            scripts.mkdir(parents=True)
            runner = scripts / RUNNER_RESULTADOS.name
            runner.write_text(
                RUNNER_RESULTADOS.read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            runner.chmod(0o755)

            call_log = project / "calls.log"
            scraper_log_dir = project / "logs"
            fake_python = project / "fake-python"
            fake_python.write_text(
                """#!/bin/bash
printf 'CALL' >> "$RUNNER_CALL_LOG"
for argument in "$@"; do
    printf '\\t%s' "$argument" >> "$RUNNER_CALL_LOG"
done
printf '\\n' >> "$RUNNER_CALL_LOG"
category=''
while [[ $# -gt 0 ]]; do
    if [[ "$1" == "--category" ]]; then
        category="$2"
        break
    fi
    shift
done
if [[ -n "${FAIL_CATEGORY:-}" && "$category" == "$FAIL_CATEGORY" ]]; then
    exit 17
fi
""",
                encoding="utf-8",
            )
            fake_python.chmod(0o755)

            environment = {
                "PATH": os.environ.get("PATH", ""),
                "ACTIVE_TORNEO_ID": "23",
                "LIGA_FORCE": "1",
                "LIGA_PYTHON": self.shell_path(fake_python),
                "RUNNER_CALL_LOG": self.shell_path(call_log),
                "SCRAPER_LOG_DIR": self.shell_path(scraper_log_dir),
            }
            if os.environ.get("SYSTEMROOT"):
                environment["SYSTEMROOT"] = os.environ["SYSTEMROOT"]
            if failing_category is not None:
                environment["FAIL_CATEGORY"] = failing_category

            completed = subprocess.run(
                [self.BASH, self.shell_path(runner)],
                cwd=PROJECT_DIR,
                env=environment,
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            self.assertTrue(
                call_log.is_file(),
                f"runner did not invoke the stub: stdout={completed.stdout!r}, stderr={completed.stderr!r}",
            )
            calls = [
                line.split("\t")[1:]
                for line in call_log.read_text(encoding="utf-8").splitlines()
            ]
            log = (scraper_log_dir / "scraper_resultados.log").read_text(
                encoding="utf-8"
            )
            return completed, calls, log

    def assert_category_calls(self, calls):
        self.assertEqual(len(calls), len(self.CATEGORIES))
        for call, category in zip(calls, self.CATEGORIES):
            with self.subTest(category=category):
                self.assertTrue(call[0].endswith("/backend/scripts/scraper_resultados.py"))
                self.assertEqual(
                    call[1:],
                    [
                        "--torneo-id",
                        "23",
                        "--category",
                        category,
                        "--execute",
                    ],
                )

    def test_category_failure_does_not_stop_later_categories_and_returns_nonzero(self):
        completed, calls, log = self.run_isolated_runner("septima")

        self.assertEqual(completed.returncode, 17)
        self.assert_category_calls(calls)
        self.assertIn("Categoría primera completada", log)
        self.assertIn("ERROR: categoría septima falló con código 17", log)
        for category in ("octava", "novena", "decima"):
            self.assertIn(f"Categoría {category} completada", log)

    def test_runner_returns_zero_only_when_every_category_succeeds(self):
        completed, calls, log = self.run_isolated_runner()

        self.assertEqual(completed.returncode, 0)
        self.assert_category_calls(calls)
        for category in self.CATEGORIES:
            self.assertIn(f"Categoría {category} completada", log)
        self.assertNotIn("ERROR: categoría", log)


class SystemdContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.service = RESULTADOS_SERVICE.read_text(encoding="utf-8")
        cls.timer = RESULTADOS_TIMER.read_text(encoding="utf-8")
        cls.alineaciones_timer = ALINEACIONES_TIMER.read_text(encoding="utf-8")
        cls.installer = SYSTEMD_INSTALLER.read_text(encoding="utf-8")
        cls.crontab = CRONTAB_PATH.read_text(encoding="utf-8")
        cls.wrapper = RUNNER_WRAPPER.read_text(encoding="utf-8")

    def test_service_calls_modern_runner_directly(self):
        self.assertIn("Type=oneshot", self.service)
        self.assertIn("User=gallardo", self.service)
        self.assertIn("Group=gallardo", self.service)
        self.assertIn("WorkingDirectory=/home/gallardo/Documentos/ligadelincoln", self.service)
        self.assertIn(
            "ExecStart=/bin/bash /home/gallardo/Documentos/ligadelincoln/scripts/run_scraper_resultados.sh",
            self.service,
        )
        self.assertNotIn("run_scraper_wrapper.sh", self.service)
        self.assertNotIn("PYTHONPATH", self.service)
        self.assertNotIn("site-packages", self.service)
        self.assertNotIn("%h", self.service)

    def test_compatibility_wrapper_has_no_pythonpath_or_hard_coded_home(self):
        self.assertNotIn("PYTHONPATH", self.wrapper)
        self.assertNotIn("site-packages", self.wrapper)
        self.assertNotIn("/home/gallardo", self.wrapper)
        self.assertIn('exec /bin/bash "$SCRIPT_DIR/run_scraper_resultados.sh"', self.wrapper)

    def test_systemd_is_the_only_results_schedule(self):
        self.assertNotIn("run_scraper_resultados.sh", self.crontab)
        self.assertIn("scraper-resultados.timer", self.crontab)
        self.assertIn("generar_placas_resultados.sh", self.crontab)
        self.assertIn("OnCalendar=", self.timer)
        self.assertIn("WantedBy=timers.target", self.timer)

    def test_weekend_timers_run_every_five_minutes_through_2355(self):
        for timer in (self.timer, self.alineaciones_timer):
            self.assertIn("OnCalendar=Sat *-*-* 13..23:0/5:00", timer)
            self.assertIn("OnCalendar=Sun *-*-* 13..23:0/5:00", timer)
            self.assertNotIn("13..21:0/5:00", timer)

    def test_installer_uses_checked_in_system_units_without_user_mode(self):
        self.assertIn('"$SCRIPT_DIR/scraper-resultados.service"', self.installer)
        self.assertIn('"$SCRIPT_DIR/scraper-resultados.timer"', self.installer)
        self.assertIn('"$SCRIPT_DIR/scraper-alineaciones.service"', self.installer)
        self.assertIn('"$SCRIPT_DIR/scraper-alineaciones.timer"', self.installer)
        self.assertIn('"$SCRIPT_DIR/scraper-worker.service"', self.installer)
        self.assertIn("/etc/systemd/system/scraper-resultados.service", self.installer)
        self.assertIn("/etc/systemd/system/scraper-resultados.timer", self.installer)
        self.assertIn("/etc/systemd/system/scraper-alineaciones.service", self.installer)
        self.assertIn("/etc/systemd/system/scraper-alineaciones.timer", self.installer)
        self.assertIn("/etc/systemd/system/scraper-worker.service", self.installer)
        self.assertIn("systemctl daemon-reload", self.installer)
        self.assertIn("systemctl enable --now scraper-resultados.timer", self.installer)
        self.assertIn("systemctl enable --now scraper-alineaciones.timer", self.installer)
        self.assertIn("systemctl enable --now scraper-worker.service", self.installer)
        self.assertNotIn("--user", self.installer)


class PanelLauncherContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.launcher = PANEL_LAUNCHER.read_text(encoding="utf-8")

    def test_launcher_uses_only_override_or_project_venv(self):
        self.assertIn("LIGA_PYTHON", self.launcher)
        self.assertIn("backend/venv/bin/python", self.launcher)
        self.assertIn("backend/venv/Scripts/python.exe", self.launcher)
        self.assertIn("no se encontró Python", self.launcher)
        self.assertNotIn("command -v python3", self.launcher)
        self.assertNotIn("command -v python)", self.launcher)
        self.assertNotIn('PYTHON="python', self.launcher)


class WindowsPanelLauncherContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.launcher = WINDOWS_PANEL_LAUNCHER.read_text(encoding="utf-8")

    def test_launcher_uses_existing_override_then_project_venv_candidates(self):
        override = 'if exist "%LIGA_PYTHON%"'
        windows_venv = "backend\\venv\\Scripts\\python.exe"
        posix_venv = "backend\\venv\\bin\\python"

        self.assertIn("LIGA_PYTHON", self.launcher)
        self.assertIn(override, self.launcher)
        self.assertIn(windows_venv, self.launcher)
        self.assertIn(posix_venv, self.launcher)
        self.assertLess(self.launcher.index(override), self.launcher.index(windows_venv))
        self.assertLess(self.launcher.index(windows_venv), self.launcher.index(posix_venv))
        self.assertIn(f'"%~dp0{posix_venv}" --version', self.launcher)

    def test_launcher_fails_visibly_and_propagates_panel_exit_status(self):
        self.assertIn("ERROR: no se encontro Python", self.launcher)
        self.assertIn("exit /b 1", self.launcher)
        self.assertIn('"%PYTHON%" "%~dp0scripts\\control-panel\\app.py"', self.launcher)
        self.assertIn('set "EXIT_CODE=%ERRORLEVEL%"', self.launcher)
        self.assertIn("exit /b %EXIT_CODE%", self.launcher)

    def test_launcher_neither_uses_system_python_nor_kills_port_owners(self):
        lowered = self.launcher.lower()
        self.assertNotIn("powershell", lowered)
        self.assertNotIn("get-nettcpconnection", lowered)
        self.assertNotIn("stop-process", lowered)
        self.assertNotIn("taskkill", lowered)
        self.assertNotIn("where python", lowered)
        self.assertNotIn("python scripts\\control-panel\\app.py", lowered)


class OperatorGuidanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.panel_readme = PANEL_README.read_text(encoding="utf-8")
        cls.commands = COMMANDS_GUIDE.read_text(encoding="utf-8")
        cls.backend_operations = BACKEND_OPERATIONS_GUIDE.read_text(encoding="utf-8")
        cls.operator_docs = f"{cls.commands}\n{cls.backend_operations}"

    def test_panel_readme_documents_all_six_safe_actions(self):
        for action in (
            "Previsualizar horarios",
            "Ejecutar horarios",
            "Previsualizar resultados",
            "Ejecutar resultados",
            "Previsualizar alineaciones",
            "Ejecutar alineaciones",
        ):
            with self.subTest(action=action):
                self.assertIn(action, self.panel_readme)
        self.assertIn("ID de torneo positivo", self.panel_readme)
        self.assertIn("ESCRIBIR", self.panel_readme)
        self.assertIn("LIGA_PYTHON", self.panel_readme)
        self.assertIn("no construye ni despliega", self.panel_readme)

    def test_commands_guide_points_to_one_canonical_backend_manual(self):
        self.assertTrue(BACKEND_OPERATIONS_GUIDE.is_file())
        self.assertIn(
            "[`backend/README_OPERACIONES.md`](backend/README_OPERACIONES.md)",
            self.commands,
        )
        self.assertIn("guía canónica", self.commands)
        self.assertIn("manual de ingesta", self.commands)
        self.assertIn("deploy", self.commands.lower())
        self.assertIn("manual", self.commands.lower())
        self.assertNotIn("## Deploy a Vercel", self.commands)

    def test_operator_docs_use_preview_execute_and_visible_placeholders(self):
        self.assertIn("## Camino rápido", self.backend_operations)
        self.assertIn("Previsualizar", self.backend_operations)
        self.assertIn("--execute", self.backend_operations)
        self.assertIn("<TORNEO_ID>", self.backend_operations)
        self.assertIn("<FECHA>", self.backend_operations)
        self.assertIn("reemplazá todos los marcadores", self.backend_operations.lower())
        self.assertIn("secuenciales y no transaccionales", self.backend_operations)
        self.assertIn("ESCRIBIR", self.backend_operations)
        self.assertIn("SQL Editor", self.backend_operations)

    def test_operator_docs_cover_all_retained_cli_entrypoints(self):
        cli_names = (
            "activar_torneo.py",
            "auditar_torneo_oficial.py",
            "comparar_partidos_oficiales.py",
            "corregir_resultados_desde_oficial.py",
            "importar_fixture_torneo.py",
            "importar_torneo_historico_oficial.py",
            "inicializar_posiciones_torneo.py",
            "scraper_alineaciones.py",
            "scraper_horarios.py",
            "scraper_resultados.py",
            "upsert_palmares.py",
        )
        for cli_name in cli_names:
            with self.subTest(cli_name=cli_name):
                self.assertIn(cli_name, self.backend_operations)

    def test_operator_docs_reject_stale_scope_scheduler_and_deploy_guidance(self):
        lowered = self.operator_docs.lower()
        self.assertNotIn("--dry-run", self.operator_docs)
        self.assertNotIn("--no-deploy", self.operator_docs)
        self.assertNotIn("systemctl --user", self.operator_docs)
        self.assertNotIn("deploy ya queda incluido", lowered)
        self.assertNotIn("deploy del frontend si guardó", lowered)
        self.assertNotIn("cada 15 min", lowered)
        self.assertNotIn("14-21", lowered)
        self.assertNotRegex(self.operator_docs, r"--torneo-id\s+[\"']?2(?:\s|$)")
        self.assertNotRegex(self.operator_docs, r"--fecha\s+[\"']?7(?:\s|$)")
        self.assertIn("único scheduler de resultados", lowered)
        self.assertIn(
            "`scripts/crontab` conserva únicamente medios y no debe programar resultados",
            self.commands,
        )
        self.assertIn("no construye ni despliega el frontend", lowered)


if __name__ == "__main__":
    unittest.main()
