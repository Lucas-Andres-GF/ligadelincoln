#!/usr/bin/env python3
"""Panel local de operaciones para Liga de Lincoln.

Corre en localhost y ejecuta scripts del proyecto con logs visibles.
No tiene dependencias externas: usa solo la librería estándar de Python.
"""

import json
import os
import re
import shutil
import subprocess
import threading
import time
import uuid
import webbrowser
from datetime import date, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

HOST = "127.0.0.1"
PORT = int(os.environ.get("CONTROL_PANEL_PORT", "8765"))
MAX_REQUEST_BODY_BYTES = 1024 * 1024

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent.parent
BACKEND_SCRIPTS = PROJECT_DIR / "backend" / "scripts"
VENV_PYTHON_CANDIDATES = (
    Path("backend/venv/Scripts/python.exe"),
    Path("backend/venv/bin/python"),
)
RESULT_CATEGORIES = ("primera", "septima", "octava", "novena", "decima")
SCHEDULE_SCRIPTS = ("resultados", "alineaciones", "ambos")
SCHEDULE_MODES = ("date", "weekly")
SCHEDULE_INTERVALS = (5, 10, 15, 20, 30, 60)
SYSTEMD_WEEKDAYS = {
    "monday": "Mon",
    "tuesday": "Tue",
    "wednesday": "Wed",
    "thursday": "Thu",
    "friday": "Fri",
    "saturday": "Sat",
    "sunday": "Sun",
}
SCHEDULE_ID_PATTERN = re.compile(r"^[a-f0-9]{12}$")
SCHEDULE_UNIT_PREFIX = "liga-panel-"
SCHEDULE_STATE_DIR = Path(
    os.environ.get(
        "LIGA_SCHEDULE_STATE_DIR",
        Path.home() / ".local" / "share" / "ligadelincoln" / "schedules",
    )
)
SYSTEMD_USER_DIR = Path(
    os.environ.get(
        "LIGA_SYSTEMD_USER_DIR",
        Path.home() / ".config" / "systemd" / "user",
    )
)
SCRAPER_ACTIONS = {
    "scraper_horarios_preview": ("horarios", False),
    "scraper_horarios_execute": ("horarios", True),
    "scraper_resultados_preview": ("resultados", False),
    "scraper_resultados_execute": ("resultados", True),
    "scraper_alineaciones_preview": ("alineaciones", False),
    "scraper_alineaciones_execute": ("alineaciones", True),
}

JOBS = {}
JOBS_LOCK = threading.Lock()
SCHEDULES_LOCK = threading.Lock()


class PythonResolutionError(RuntimeError):
    """Raised when the project's backend Python interpreter is unavailable."""


class RequestValidationError(ValueError):
    """Raised when an action request is unsafe or incomplete."""


class ScheduleOperationError(RuntimeError):
    """Raised when a persistent custom schedule cannot be managed safely."""


def parse_content_length(value, maximum=MAX_REQUEST_BODY_BYTES):
    """Parse a bounded HTTP Content-Length without reading request data."""
    if not isinstance(value, str) or not value.isascii() or not value.isdecimal():
        raise RequestValidationError("Content-Length inválido")

    try:
        length = int(value)
    except ValueError as exc:
        raise RequestValidationError("Content-Length inválido") from exc
    if length > maximum:
        raise RequestValidationError(
            f"Content-Length excede el máximo permitido de {maximum} bytes"
        )
    return length


def parse_json_request(content_length, body_reader):
    """Read and decode one size-bounded JSON request body."""
    length = parse_content_length(content_length)
    try:
        raw_body = body_reader(length)
        return json.loads(raw_body.decode("utf-8") or "{}")
    except (AttributeError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RequestValidationError("JSON inválido") from exc


def resolve_project_python(project_dir=PROJECT_DIR, environ=None):
    """Resolve the backend venv interpreter without running or importing it."""
    project_dir = Path(project_dir)
    environ = os.environ if environ is None else environ
    override = str(environ.get("LIGA_PYTHON", "")).strip()

    if override:
        candidate = Path(override).expanduser()
        if not candidate.is_absolute():
            candidate = project_dir / candidate
        if candidate.is_file():
            return candidate
        raise PythonResolutionError(f"LIGA_PYTHON no existe o no es un archivo: {candidate}")

    candidates = [project_dir / relative_path for relative_path in VENV_PYTHON_CANDIDATES]
    for candidate in candidates:
        if candidate.is_file():
            return candidate

    checked = ", ".join(str(candidate) for candidate in candidates)
    raise PythonResolutionError(
        "No se encontró el intérprete Python del entorno virtual del backend. "
        f"Revisados: {checked}. También podés definir LIGA_PYTHON."
    )


def py(path, *args, python=None):
    interpreter = Path(python) if python is not None else resolve_project_python()
    command = [str(interpreter), str(path)]
    index = 0
    args = list(args)
    while index < len(args):
        arg = args[index]
        next_arg = args[index + 1] if index + 1 < len(args) else None

        if isinstance(arg, str) and arg.startswith("--") and index + 1 < len(args) and next_arg in (None, ""):
            index += 2
            continue

        if arg not in (None, ""):
            command.append(str(arg))
        index += 1

    return command


def _positive_integer(params, name, label):
    value = params.get(name)
    if isinstance(value, bool) or value in (None, ""):
        raise RequestValidationError(f"{label} es obligatorio y debe ser un entero positivo")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise RequestValidationError(f"{label} debe ser un entero positivo") from exc
    if parsed <= 0 or str(value).strip() != str(parsed):
        raise RequestValidationError(f"{label} debe ser un entero positivo")
    return parsed


def validate_scraper_params(scraper, params):
    """Validate and normalize tournament-scoped scraper parameters."""
    if not isinstance(params, dict):
        raise RequestValidationError("params debe ser un objeto JSON")

    normalized = dict(params)
    normalized["torneo_id"] = _positive_integer(params, "torneo_id", "torneo_id")

    if scraper == "alineaciones":
        normalized["fecha"] = _positive_integer(params, "fecha", "fecha")
    elif scraper == "resultados":
        category = params.get("category")
        if category in (None, ""):
            normalized.pop("category", None)
        elif not isinstance(category, str) or category not in RESULT_CATEGORIES:
            allowed = ", ".join(RESULT_CATEGORIES)
            raise RequestValidationError(f"category inválida; opciones: {allowed}")
        else:
            normalized["category"] = category
    elif scraper != "horarios":
        raise RequestValidationError(f"scraper inválido: {scraper}")

    return normalized


def build_scraper_command(scraper, params, *, execute=False, python=None):
    """Build one validated dry-run-first scraper command vector."""
    normalized = validate_scraper_params(scraper, params)
    script = BACKEND_SCRIPTS / f"scraper_{scraper}.py"
    args = ["--torneo-id", normalized["torneo_id"]]

    if scraper == "resultados" and normalized.get("category"):
        args.extend(["--category", normalized["category"]])
    if scraper == "alineaciones":
        args.extend(["--fecha", normalized["fecha"]])
    if execute:
        args.append("--execute")

    return py(script, *args, python=python)


def _schedule_choice(params, name, label, choices):
    value = params.get(name)
    if not isinstance(value, str) or value not in choices:
        raise RequestValidationError(
            f"{label} inválido; opciones: {', '.join(str(choice) for choice in choices)}"
        )
    return value


def _parse_clock(params, name, label):
    value = params.get(name)
    if not isinstance(value, str) or not re.fullmatch(r"\d{2}:\d{2}", value):
        raise RequestValidationError(f"{label} debe tener formato HH:MM")
    try:
        return datetime.strptime(value, "%H:%M").time()
    except ValueError as exc:
        raise RequestValidationError(f"{label} debe tener formato HH:MM") from exc


def validate_schedule_params(params, *, today=None):
    """Validate and normalize one persistent scraper schedule."""
    if not isinstance(params, dict):
        raise RequestValidationError("params debe ser un objeto JSON")

    script = _schedule_choice(params, "script", "script", SCHEDULE_SCRIPTS)
    mode = _schedule_choice(params, "mode", "modo", SCHEDULE_MODES)
    torneo_id = _positive_integer(params, "torneo_id", "torneo_id")
    normalized = {
        "script": script,
        "mode": mode,
        "torneo_id": torneo_id,
        "fecha": None,
        "category": None,
    }

    if script in ("alineaciones", "ambos"):
        normalized["fecha"] = _positive_integer(params, "fecha", "fecha")
    if script in ("resultados", "ambos"):
        category = params.get("category")
        if category not in (None, ""):
            if not isinstance(category, str) or category not in RESULT_CATEGORIES:
                raise RequestValidationError(
                    f"category inválida; opciones: {', '.join(RESULT_CATEGORIES)}"
                )
            normalized["category"] = category

    start = _parse_clock(params, "start_time", "hora de inicio")
    end = _parse_clock(params, "end_time", "hora de fin")
    if start > end:
        raise RequestValidationError("la hora de inicio no puede ser posterior a la hora de fin")
    normalized["start_time"] = start.strftime("%H:%M")
    normalized["end_time"] = end.strftime("%H:%M")

    interval = params.get("interval_minutes")
    try:
        interval = int(interval)
    except (TypeError, ValueError) as exc:
        raise RequestValidationError("frecuencia inválida") from exc
    if isinstance(params.get("interval_minutes"), bool) or interval not in SCHEDULE_INTERVALS:
        raise RequestValidationError(
            f"frecuencia inválida; opciones: {', '.join(map(str, SCHEDULE_INTERVALS))} minutos"
        )
    normalized["interval_minutes"] = interval

    if mode == "date":
        raw_date = params.get("run_date")
        try:
            run_date = date.fromisoformat(raw_date)
        except (TypeError, ValueError) as exc:
            raise RequestValidationError("fecha de ejecución inválida") from exc
        reference_date = today or date.today()
        if run_date < reference_date:
            raise RequestValidationError("la fecha de ejecución no puede estar en el pasado")
        normalized["run_date"] = run_date.isoformat()
        normalized["weekday"] = None
    else:
        weekday = _schedule_choice(
            params, "weekday", "día semanal", tuple(SYSTEMD_WEEKDAYS)
        )
        normalized["run_date"] = None
        normalized["weekday"] = weekday

    confirmation = str(params.get("confirm_text", "")).strip().upper()
    if confirmation != "ESCRIBIR":
        raise RequestValidationError("confirmación inválida; escribí ESCRIBIR")
    return normalized


def schedule_occurrence_times(start_time, end_time, interval_minutes):
    """Return every inclusive execution time in the requested daily window."""
    cursor = datetime.combine(date.min, datetime.strptime(start_time, "%H:%M").time())
    limit = datetime.combine(date.min, datetime.strptime(end_time, "%H:%M").time())
    occurrences = []
    while cursor <= limit:
        occurrences.append(cursor.strftime("%H:%M"))
        cursor += timedelta(minutes=interval_minutes)
    return occurrences


def schedule_calendar_entries(schedule):
    prefix = (
        schedule["run_date"]
        if schedule["mode"] == "date"
        else f"{SYSTEMD_WEEKDAYS[schedule['weekday']]} *-*-*"
    )
    return [
        f"{prefix} {clock}:00"
        for clock in schedule_occurrence_times(
            schedule["start_time"],
            schedule["end_time"],
            schedule["interval_minutes"],
        )
    ]


def _systemd_quote(value):
    value = str(value)
    if "\n" in value or "\r" in value or "\0" in value:
        raise ScheduleOperationError("valor inválido para una unidad systemd")
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def build_schedule_commands(schedule, *, project_dir=PROJECT_DIR, python=None):
    """Build direct, shell-free scraper commands for a scheduled service."""
    project_dir = Path(project_dir)
    interpreter = Path(python) if python is not None else resolve_project_python(project_dir)
    backend_scripts = project_dir / "backend" / "scripts"
    commands = []
    if schedule["script"] in ("resultados", "ambos"):
        args = [
            str(interpreter),
            str(backend_scripts / "scraper_resultados.py"),
            "--torneo-id",
            str(schedule["torneo_id"]),
        ]
        if schedule.get("category"):
            args.extend(["--category", schedule["category"]])
        args.append("--execute")
        commands.append(args)
    if schedule["script"] in ("alineaciones", "ambos"):
        commands.append(
            [
                str(interpreter),
                str(backend_scripts / "scraper_alineaciones.py"),
                "--torneo-id",
                str(schedule["torneo_id"]),
                "--fecha",
                str(schedule["fecha"]),
                "--execute",
            ]
        )
    return commands


def build_schedule_units(schedule, *, project_dir=PROJECT_DIR, python=None):
    unit_name = f"{SCHEDULE_UNIT_PREFIX}{schedule['id']}"
    commands = build_schedule_commands(schedule, project_dir=project_dir, python=python)
    exec_lines = "\n".join(
        "ExecStart=" + " ".join(_systemd_quote(arg) for arg in command)
        for command in commands
    )
    calendar_lines = "\n".join(
        f"OnCalendar={entry}" for entry in schedule_calendar_entries(schedule)
    )
    service = f"""[Unit]
Description=Liga de Lincoln - {schedule['script']} ({schedule['id']})

[Service]
Type=oneshot
WorkingDirectory={_systemd_quote(Path(project_dir))}
Environment=PYTHONIOENCODING=utf-8
{exec_lines}
"""
    timer = f"""[Unit]
Description=Programación Liga de Lincoln ({schedule['id']})

[Timer]
{calendar_lines}
Persistent=true
AccuracySec=30s
Unit={unit_name}.service

[Install]
WantedBy=timers.target
"""
    return service, timer


def _run_systemctl(arguments, *, runner=subprocess.run, allow_failure=False):
    if shutil.which("systemctl") is None and runner is subprocess.run:
        raise ScheduleOperationError(
            "systemd no está disponible. Abrí este panel desde Linux Mint para programar tareas."
        )
    try:
        result = runner(
            ["systemctl", "--user", *arguments],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ScheduleOperationError(f"no se pudo ejecutar systemctl --user: {exc}") from exc
    if result.returncode != 0 and not allow_failure:
        detail = (result.stderr or result.stdout or "error desconocido").strip()
        raise ScheduleOperationError(f"systemctl --user falló: {detail}")
    return result


def scheduler_available():
    return os.name == "posix" and shutil.which("systemctl") is not None


def _schedule_manifest_path(schedule_id, state_dir=SCHEDULE_STATE_DIR):
    if not SCHEDULE_ID_PATTERN.fullmatch(schedule_id):
        raise RequestValidationError("identificador de programación inválido")
    return Path(state_dir) / f"{schedule_id}.json"


def list_schedules(*, state_dir=SCHEDULE_STATE_DIR):
    state_dir = Path(state_dir)
    if not state_dir.exists():
        return []
    schedules = []
    for path in state_dir.glob("*.json"):
        if not SCHEDULE_ID_PATTERN.fullmatch(path.stem):
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict) and payload.get("id") == path.stem:
            schedules.append(payload)
    return sorted(schedules, key=lambda item: item.get("created_at", ""), reverse=True)


def create_schedule(
    params,
    *,
    state_dir=SCHEDULE_STATE_DIR,
    systemd_dir=SYSTEMD_USER_DIR,
    project_dir=PROJECT_DIR,
    python=None,
    runner=subprocess.run,
    today=None,
):
    schedule = validate_schedule_params(params, today=today)
    schedule.update(
        {
            "id": uuid.uuid4().hex[:12],
            "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        }
    )
    schedule["calendar_entries"] = schedule_calendar_entries(schedule)
    unit_name = f"{SCHEDULE_UNIT_PREFIX}{schedule['id']}"
    schedule["unit_name"] = unit_name
    service_text, timer_text = build_schedule_units(
        schedule, project_dir=project_dir, python=python
    )

    state_dir = Path(state_dir)
    systemd_dir = Path(systemd_dir)
    manifest_path = _schedule_manifest_path(schedule["id"], state_dir)
    service_path = systemd_dir / f"{unit_name}.service"
    timer_path = systemd_dir / f"{unit_name}.timer"
    written_paths = []
    with SCHEDULES_LOCK:
        try:
            state_dir.mkdir(parents=True, exist_ok=True)
            systemd_dir.mkdir(parents=True, exist_ok=True)
            service_path.write_text(service_text, encoding="utf-8", newline="\n")
            written_paths.append(service_path)
            timer_path.write_text(timer_text, encoding="utf-8", newline="\n")
            written_paths.append(timer_path)
            manifest_path.write_text(
                json.dumps(schedule, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
                newline="\n",
            )
            written_paths.append(manifest_path)
            _run_systemctl(["daemon-reload"], runner=runner)
            _run_systemctl(["enable", "--now", f"{unit_name}.timer"], runner=runner)
        except Exception:
            try:
                _run_systemctl(
                    ["disable", "--now", f"{unit_name}.timer"],
                    runner=runner,
                    allow_failure=True,
                )
            except ScheduleOperationError:
                pass
            for path in written_paths:
                path.unlink(missing_ok=True)
            try:
                _run_systemctl(["daemon-reload"], runner=runner, allow_failure=True)
            except ScheduleOperationError:
                pass
            raise
    return schedule


def delete_schedule(
    schedule_id,
    *,
    state_dir=SCHEDULE_STATE_DIR,
    systemd_dir=SYSTEMD_USER_DIR,
    runner=subprocess.run,
):
    manifest_path = _schedule_manifest_path(schedule_id, state_dir)
    if not manifest_path.is_file():
        raise RequestValidationError("la programación no existe")
    unit_name = f"{SCHEDULE_UNIT_PREFIX}{schedule_id}"
    with SCHEDULES_LOCK:
        _run_systemctl(
            ["disable", "--now", f"{unit_name}.timer"],
            runner=runner,
            allow_failure=True,
        )
        (Path(systemd_dir) / f"{unit_name}.timer").unlink(missing_ok=True)
        (Path(systemd_dir) / f"{unit_name}.service").unlink(missing_ok=True)
        manifest_path.unlink(missing_ok=True)
        _run_systemctl(["daemon-reload"], runner=runner)
    return {"deleted": schedule_id}


def placas_resultados_command(params):
    command = py(
        PROJECT_DIR / "scripts" / "generador-placas" / "generar_placas_resultados.py",
        "--fecha",
        params.get("fecha"),
    )

    categoria = params.get("categoria")
    if categoria:
        command.extend(["--categoria", str(categoria)])

    if params.get("force"):
        command.append("--force")

    return command


def publicar_tablas_command(params):
    fecha = params.get("fecha")
    command = py(
        PROJECT_DIR / "scripts" / "social" / "subir_tablas.py",
        "--fecha",
        fecha,
        "--publish",
        "--yes",
    )

    only = params.get("only")
    if only:
        command.extend(["--only", str(only)])

    return command


def publicar_resultados_command(params):
    fecha = params.get("fecha")
    categoria = params.get("categoria")
    command = py(
        PROJECT_DIR / "scripts" / "social" / "subir_resultados.py",
        "--fecha",
        fecha,
        "--categoria",
        categoria,
        "--publish",
        "--yes",
    )

    only = params.get("only")
    if only:
        command.extend(["--only", str(only)])

    return command


def publicar_fixture_command(params):
    fecha = params.get("fecha")
    command = py(
        PROJECT_DIR / "scripts" / "social" / "subir_fixture.py",
        "--fecha",
        fecha,
        "--publish",
        "--yes",
    )

    only = params.get("only")
    if only:
        command.extend(["--only", str(only)])

    return command


def action_definitions():
    return {
        "scraper_horarios_preview": {
            "title": "Previsualizar horarios",
            "description": "Muestra los cambios de fecha, hora y cancha sin escribir en la base de datos.",
            "risk": "safe",
            "scraper": "horarios",
            "execute": False,
            "fields": [{"name": "torneo_id", "label": "ID de torneo", "type": "number", "required": True}],
            "cwd": BACKEND_SCRIPTS,
            "command": lambda p: build_scraper_command("horarios", p),
        },
        "scraper_horarios_execute": {
            "title": "Ejecutar horarios",
            "description": "Actualiza fecha, hora y cancha para el torneo indicado.",
            "risk": "writes-db",
            "scraper": "horarios",
            "execute": True,
            "confirm": "ESCRIBIR",
            "fields": [{"name": "torneo_id", "label": "ID de torneo", "type": "number", "required": True}],
            "cwd": BACKEND_SCRIPTS,
            "command": lambda p: build_scraper_command("horarios", p, execute=True),
        },
        "scraper_resultados_preview": {
            "title": "Previsualizar resultados",
            "description": "Muestra los cambios de resultados y posiciones sin escribir en la base de datos.",
            "risk": "safe",
            "scraper": "resultados",
            "execute": False,
            "fields": [
                {"name": "torneo_id", "label": "ID de torneo", "type": "number", "required": True},
                {"name": "category", "label": "Categoría opcional", "type": "select", "options": ["", *RESULT_CATEGORIES]},
            ],
            "cwd": BACKEND_SCRIPTS,
            "command": lambda p: build_scraper_command("resultados", p),
        },
        "scraper_resultados_execute": {
            "title": "Ejecutar resultados",
            "description": "Actualiza resultados y posiciones para el torneo indicado.",
            "risk": "writes-db",
            "scraper": "resultados",
            "execute": True,
            "confirm": "ESCRIBIR",
            "fields": [
                {"name": "torneo_id", "label": "ID de torneo", "type": "number", "required": True},
                {"name": "category", "label": "Categoría opcional", "type": "select", "options": ["", *RESULT_CATEGORIES]},
            ],
            "cwd": BACKEND_SCRIPTS,
            "command": lambda p: build_scraper_command("resultados", p, execute=True),
        },
        "scraper_alineaciones_preview": {
            "title": "Previsualizar alineaciones",
            "description": "Muestra el reemplazo de alineaciones de Primera sin escribir en la base de datos.",
            "risk": "safe",
            "scraper": "alineaciones",
            "execute": False,
            "fields": [
                {"name": "torneo_id", "label": "ID de torneo", "type": "number", "required": True},
                {"name": "fecha", "label": "Fecha", "type": "number", "required": True},
            ],
            "cwd": BACKEND_SCRIPTS,
            "command": lambda p: build_scraper_command("alineaciones", p),
        },
        "scraper_alineaciones_execute": {
            "title": "Ejecutar alineaciones",
            "description": "Reemplaza las alineaciones de Primera para el torneo y la fecha indicados.",
            "risk": "writes-db",
            "scraper": "alineaciones",
            "execute": True,
            "confirm": "ESCRIBIR",
            "fields": [
                {"name": "torneo_id", "label": "ID de torneo", "type": "number", "required": True},
                {"name": "fecha", "label": "Fecha", "type": "number", "required": True},
            ],
            "cwd": BACKEND_SCRIPTS,
            "command": lambda p: build_scraper_command("alineaciones", p, execute=True),
        },
        "capturar_tablas": {
            "title": "Generar tablas",
            "description": "Genera portada y placas de tablas de posiciones.",
            "risk": "generates-files",
            "fields": [{"name": "fecha", "label": "Fecha", "type": "number", "required": True}],
            "cwd": PROJECT_DIR,
            "command": lambda p: py(PROJECT_DIR / "scripts" / "capturar_tablas.py", "--fecha", p.get("fecha")),
        },
        "capturar_fixture": {
            "title": "Generar fixture",
            "description": "Genera portada y placas del fixture.",
            "risk": "generates-files",
            "fields": [
                {"name": "fecha", "label": "Fecha", "type": "number", "required": True},
                {"name": "categoria", "label": "Categoría opcional", "type": "select", "options": ["", "primera", "septima", "octava", "novena", "decima"]},
            ],
            "cwd": PROJECT_DIR,
            "command": lambda p: py(PROJECT_DIR / "scripts" / "capturar_fixture.py", "--fecha", p.get("fecha"), "--categoria", p.get("categoria")),
        },
        "placas_resultados": {
            "title": "Generar placas resultados",
            "description": "Genera placas sociales de resultados por fecha/categoría.",
            "risk": "generates-files",
            "fields": [
                {"name": "fecha", "label": "Fecha", "type": "number", "required": True},
                {"name": "categoria", "label": "Categoría opcional", "type": "select", "options": ["", "primera", "septima", "octava", "novena", "decima"]},
                {"name": "force", "label": "Regenerar aunque exista", "type": "checkbox"},
            ],
            "cwd": PROJECT_DIR,
            "command": placas_resultados_command,
        },
        "subir_tablas_dry_run": {
            "title": "Subir tablas dry-run",
            "description": "Valida carrusel de tablas sin generar, subir ni publicar.",
            "risk": "safe",
            "fields": [{"name": "fecha", "label": "Fecha", "type": "number", "required": True}],
            "cwd": PROJECT_DIR,
            "command": lambda p: py(PROJECT_DIR / "scripts" / "social" / "subir_tablas.py", "--fecha", p.get("fecha"), "--dry-run"),
        },
        "subir_tablas_upload": {
            "title": "Subir tablas a Storage",
            "description": "Regenera tablas y sube imágenes públicas a Supabase Storage. No publica en redes.",
            "risk": "external-upload",
            "fields": [{"name": "fecha", "label": "Fecha", "type": "number", "required": True}],
            "cwd": PROJECT_DIR,
            "command": lambda p: py(PROJECT_DIR / "scripts" / "social" / "subir_tablas.py", "--fecha", p.get("fecha")),
        },
        "publicar_tablas": {
            "title": "Publicar tablas",
            "description": "Genera caption con IA y publica tablas en Instagram/Facebook.",
            "risk": "external-upload",
            "confirm": "S",
            "confirm_accept": ["S", "Y", "SI", "SÍ", "YES"],
            "fields": [
                {"name": "fecha", "label": "Fecha", "type": "number", "required": True},
                {"name": "only", "label": "Plataforma", "type": "select", "options": ["both", "instagram", "facebook"]},
            ],
            "cwd": PROJECT_DIR,
            "command": publicar_tablas_command,
        },
        "publicar_resultados": {
            "title": "Publicar resultados",
            "description": "Genera caption con IA y publica resultados de una división. Orden recomendado: décima, novena, octava, séptima, primera.",
            "risk": "external-upload",
            "confirm": "S",
            "confirm_accept": ["S", "Y", "SI", "SÍ", "YES"],
            "fields": [
                {"name": "fecha", "label": "Fecha", "type": "number", "required": True},
                {"name": "categoria", "label": "Categoría", "type": "select", "options": ["decima", "novena", "octava", "septima", "primera"]},
                {"name": "only", "label": "Plataforma", "type": "select", "options": ["both", "instagram", "facebook"]},
            ],
            "cwd": PROJECT_DIR,
            "command": publicar_resultados_command,
        },
        "publicar_fixture": {
            "title": "Publicar fixture",
            "description": "Genera caption con IA y publica el fixture en Instagram/Facebook.",
            "risk": "external-upload",
            "confirm": "S",
            "confirm_accept": ["S", "Y", "SI", "SÍ", "YES"],
            "fields": [
                {"name": "fecha", "label": "Fecha", "type": "number", "required": True},
                {"name": "only", "label": "Plataforma", "type": "select", "options": ["both", "instagram", "facebook"]},
            ],
            "cwd": PROJECT_DIR,
            "command": publicar_fixture_command,
        },
    }


ACTIONS = action_definitions()


def serialize_actions():
    return [
        {
            "id": action_id,
            "title": config["title"],
            "description": config["description"],
            "risk": config["risk"],
            "confirm": config.get("confirm"),
            "confirm_accept": config.get("confirm_accept", []),
            "fields": config.get("fields", []),
        }
        for action_id, config in ACTIONS.items()
    ]


def validate_action_request(action_id, params):
    """Validate action-specific API input before any command or job is created."""
    config = ACTIONS[action_id]
    if not isinstance(params, dict):
        raise RequestValidationError("params debe ser un objeto JSON")

    scraper = config.get("scraper")
    if not scraper:
        return dict(params)

    normalized = validate_scraper_params(scraper, params)
    if config.get("execute"):
        confirmation = str(params.get("confirm_text", "")).strip().upper()
        if confirmation != "ESCRIBIR":
            raise RequestValidationError("confirmación inválida; escribí ESCRIBIR")
    normalized.pop("confirm_text", None)
    return normalized


def create_job(action_id, params):
    job_id = uuid.uuid4().hex[:10]
    config = ACTIONS[action_id]
    command = config["command"](params)
    job = {
        "id": job_id,
        "action_id": action_id,
        "title": config["title"],
        "status": "queued",
        "command": command,
        "cwd": str(config["cwd"]),
        "logs": [],
        "created_at": time.time(),
        "returncode": None,
    }
    with JOBS_LOCK:
        JOBS[job_id] = job
    threading.Thread(target=run_job, args=(job_id,), daemon=True).start()
    return job


def dispatch_run(payload, job_factory=None):
    """Validate an API run payload and create a job only when it is safe."""
    if not isinstance(payload, dict):
        return {"error": "el cuerpo debe ser un objeto JSON"}, 400

    action_id = payload.get("action_id")
    if action_id not in ACTIONS:
        return {"error": "acción inválida"}, 400

    try:
        params = validate_action_request(action_id, payload.get("params") or {})
        job = (job_factory or create_job)(action_id, params)
    except RequestValidationError as exc:
        return {"error": str(exc)}, 400
    except PythonResolutionError as exc:
        return {"error": str(exc)}, 500

    return job, 201


def handle_run_http_request(content_length, body_reader, dispatcher=None):
    """Validate HTTP framing and JSON before dispatching any action."""
    try:
        payload = parse_json_request(content_length, body_reader)
    except RequestValidationError as exc:
        return {"error": str(exc)}, 400
    return (dispatcher or dispatch_run)(payload)


def dispatch_schedule_create(payload, creator=None):
    if not isinstance(payload, dict):
        return {"error": "el cuerpo debe ser un objeto JSON"}, 400
    try:
        params = payload.get("params") or {}
        normalized = validate_schedule_params(params)
        schedule = creator(normalized) if creator else create_schedule(params)
    except RequestValidationError as exc:
        return {"error": str(exc)}, 400
    except (PythonResolutionError, ScheduleOperationError, OSError) as exc:
        return {"error": str(exc)}, 500
    return schedule, 201


def dispatch_schedule_delete(schedule_id, deleter=None):
    try:
        result = (deleter or delete_schedule)(schedule_id)
    except RequestValidationError as exc:
        return {"error": str(exc)}, 400
    except (ScheduleOperationError, OSError) as exc:
        return {"error": str(exc)}, 500
    return result, 200


def append_log(job, line):
    job["logs"].append(line.rstrip("\n"))
    if len(job["logs"]) > 1000:
        job["logs"] = job["logs"][-1000:]


def run_job(job_id):
    with JOBS_LOCK:
        job = JOBS[job_id]
        job["status"] = "running"

    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"

    append_log(job, f"$ {' '.join(job['command'])}")
    append_log(job, f"cwd: {job['cwd']}")

    try:
        process = subprocess.Popen(
            job["command"],
            cwd=job["cwd"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
        )
        for line in process.stdout or []:
            append_log(job, line)
        job["returncode"] = process.wait()
        job["status"] = "completed" if job["returncode"] == 0 else "failed"
    except Exception as exc:  # noqa: BLE001 - surface local tool errors in UI
        append_log(job, f"ERROR: {exc}")
        job["status"] = "failed"
        job["returncode"] = -1


HTML = r"""
<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Panel Liga de Lincoln</title>
  <style>
    :root { color-scheme: dark; --bg:#021108; --card:#0a2815; --card-deep:#061c0e; --line:#1f6336; --green:#2ee76f; --yellow:#ffd51e; --muted:#9db6a6; --danger:#ff6363; }
    * { box-sizing: border-box; }
    body { margin:0; min-height:100vh; font-family:"Aptos", "Segoe UI", sans-serif; background:radial-gradient(circle at 12% -8%, #19653a 0, transparent 34%), linear-gradient(145deg, #04170c, var(--bg) 56%); color:#f8fafc; }
    header { padding:26px clamp(18px, 3vw, 42px); border-bottom:1px solid rgba(255,213,30,.28); display:flex; justify-content:space-between; gap:16px; align-items:center; background:rgba(2,17,8,.72); backdrop-filter:blur(16px); }
    h1, h2, h3 { font-family:"Bahnschrift Condensed", "Arial Narrow", sans-serif; }
    h1 { margin:0; text-transform:uppercase; letter-spacing:.09em; font-size:clamp(22px, 3vw, 30px); }
    .eyebrow { color:var(--green); font-size:10px; font-weight:900; letter-spacing:.2em; text-transform:uppercase; margin-bottom:5px; }
    .local-badge, .system-badge { border:1px solid rgba(46,231,111,.38); color:var(--green); border-radius:999px; padding:7px 11px; font-size:11px; font-weight:900; letter-spacing:.07em; white-space:nowrap; }
    main { display:grid; grid-template-columns:minmax(420px, 580px) minmax(420px, 1fr); gap:20px; padding:24px clamp(16px, 2.6vw, 40px) 40px; align-items:start; }
    .control-stack { display:grid; gap:20px; min-width:0; }
    .panel, .job { background:linear-gradient(150deg, rgba(12,48,25,.96), rgba(6,28,14,.98)); border:1px solid rgba(46,231,111,.22); border-radius:18px; box-shadow:0 18px 52px rgba(0,0,0,.25); }
    .panel-head { display:flex; justify-content:space-between; gap:16px; align-items:flex-start; padding:18px 18px 14px; border-bottom:1px solid rgba(46,231,111,.16); }
    .panel-head h2 { margin:0; font-size:20px; letter-spacing:.04em; text-transform:uppercase; }
    .panel-head p { margin:4px 0 0; color:var(--muted); font-size:12px; line-height:1.4; }
    .schedule-form { padding:16px 18px 18px; }
    .form-grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:10px 12px; }
    .field.full { grid-column:1/-1; }
    .schedule-actions { display:flex; gap:10px; align-items:center; margin-top:12px; }
    .schedule-note { font-size:11px; color:var(--muted); line-height:1.35; }
    .schedule-list { border-top:1px solid rgba(46,231,111,.16); padding:14px 18px 18px; display:grid; gap:9px; }
    .schedule-card { display:grid; grid-template-columns:1fr auto; gap:12px; align-items:center; border:1px solid rgba(255,255,255,.09); border-radius:13px; padding:12px; background:rgba(2,17,8,.55); }
    .schedule-card strong { display:block; font-size:14px; margin-bottom:3px; }
    .schedule-meta { color:var(--muted); font-size:11px; line-height:1.4; }
    .schedule-empty { color:var(--muted); font-size:12px; text-align:center; padding:10px; }
    .actions { padding:16px; display:grid; gap:12px; max-height:70vh; overflow:auto; }
    .action { border:1px solid rgba(255,255,255,.09); border-radius:14px; padding:14px; background:rgba(2,17,8,.52); }
    .action h3 { margin:0 0 4px; font-size:17px; letter-spacing:.025em; }
    .action p { margin:0 0 12px; color:var(--muted); font-size:13px; line-height:1.35; }
    .risk { display:inline-block; font-size:10px; font-weight:900; text-transform:uppercase; letter-spacing:.08em; padding:4px 8px; border-radius:999px; margin-bottom:8px; background:#164e28; color:#bbf7d0; }
    .risk.writes-db, .risk.external-upload { background:#4a2b04; color:#fde68a; }
    .risk.safe { background:#06351f; color:#86efac; }
    label { display:block; font-size:12px; color:#cbd5d1; margin:8px 0 4px; }
    input, select { width:100%; min-height:39px; padding:9px 10px; border-radius:10px; border:1px solid var(--line); background:#021108; color:#fff; outline:none; }
    input:focus, select:focus { border-color:var(--green); box-shadow:0 0 0 3px rgba(46,231,111,.11); }
    input[type="checkbox"] { width:auto; }
    button { cursor:pointer; border:0; padding:10px 13px; border-radius:11px; font-weight:900; background:var(--yellow); color:#052e16; margin-top:10px; }
    button:hover { filter:brightness(1.05); }
    button:disabled { cursor:not-allowed; opacity:.45; }
    .delete-button { background:rgba(255,99,99,.1); color:#ff9b9b; border:1px solid rgba(255,99,99,.28); margin:0; padding:8px 10px; }
    .jobs-panel { position:sticky; top:18px; }
    .jobs { padding:16px; display:grid; gap:14px; max-height:calc(100vh - 155px); overflow:auto; }
    .job { padding:14px; }
    .job-head { display:flex; justify-content:space-between; gap:12px; align-items:center; margin-bottom:8px; }
    .status { font-size:11px; text-transform:uppercase; font-weight:900; letter-spacing:.08em; color:var(--yellow); }
    .status.completed { color:var(--green); } .status.failed { color:var(--danger); }
    pre { margin:0; padding:12px; background:#020d07; border-radius:12px; overflow:auto; max-height:360px; white-space:pre-wrap; font-size:12px; line-height:1.45; }
    .empty { color:var(--muted); padding:30px; text-align:center; }
    .hidden { display:none !important; }
    @media (max-width: 980px) { main { grid-template-columns:1fr; } .jobs-panel { position:static; } .jobs { max-height:none; } }
    @media (max-width: 560px) { header { align-items:flex-start; } main { padding-inline:12px; } .form-grid { grid-template-columns:1fr; } .field.full { grid-column:auto; } .schedule-actions { align-items:stretch; flex-direction:column; } .schedule-actions button { width:100%; } }
  </style>
</head>
<body>
  <header>
    <div>
      <div class="eyebrow">Centro de operaciones</div>
      <h1>Panel Liga de Lincoln</h1>
      <div style="color:var(--muted);font-size:13px">Scripts, programación y registros en un solo lugar</div>
    </div>
    <div class="local-badge">LOCAL · 127.0.0.1</div>
  </header>
  <main>
    <div class="control-stack">
      <section class="panel">
        <div class="panel-head">
          <div><div class="eyebrow">Automatización</div><h2>Programador</h2><p>Creá una ventana especial para un partido postergado u otra jornada.</p></div>
          <span class="system-badge">SYSTEMD · MINT</span>
        </div>
        <form id="schedule-form" class="schedule-form">
          <div class="form-grid">
            <div class="field"><label for="schedule-script">Proceso</label><select id="schedule-script" name="script"><option value="resultados">Resultados</option><option value="alineaciones">Alineaciones</option><option value="ambos">Resultados + alineaciones</option></select></div>
            <div class="field"><label for="schedule-torneo">ID de torneo</label><input id="schedule-torneo" name="torneo_id" type="number" min="1" required></div>
            <div class="field" id="schedule-category-field"><label for="schedule-category">Categoría de resultados</label><select id="schedule-category" name="category"><option value="">Todas</option><option value="primera">Primera</option><option value="septima">Séptima</option><option value="octava">Octava</option><option value="novena">Novena</option><option value="decima">Décima</option></select></div>
            <div class="field hidden" id="schedule-fecha-field"><label for="schedule-fecha">N.º de fecha para alineaciones</label><input id="schedule-fecha" name="fecha" type="number" min="1"></div>
            <div class="field"><label for="schedule-mode">Repetición</label><select id="schedule-mode" name="mode"><option value="date">Una fecha puntual</option><option value="weekly">Todas las semanas</option></select></div>
            <div class="field" id="schedule-date-field"><label for="schedule-date">Día</label><input id="schedule-date" name="run_date" type="date" required></div>
            <div class="field hidden" id="schedule-weekday-field"><label for="schedule-weekday">Día semanal</label><select id="schedule-weekday" name="weekday"><option value="monday">Lunes</option><option value="tuesday">Martes</option><option value="wednesday">Miércoles</option><option value="thursday">Jueves</option><option value="friday">Viernes</option><option value="saturday">Sábado</option><option value="sunday">Domingo</option></select></div>
            <div class="field"><label for="schedule-start">Desde</label><input id="schedule-start" name="start_time" type="time" value="19:00" required></div>
            <div class="field"><label for="schedule-end">Hasta</label><input id="schedule-end" name="end_time" type="time" value="23:00" required></div>
            <div class="field"><label for="schedule-interval">Frecuencia</label><select id="schedule-interval" name="interval_minutes"><option value="5">Cada 5 minutos</option><option value="10">Cada 10 minutos</option><option value="15">Cada 15 minutos</option><option value="20">Cada 20 minutos</option><option value="30">Cada 30 minutos</option><option value="60">Cada 60 minutos</option></select></div>
            <div class="field"><label for="schedule-confirm">Confirmación: escribí ESCRIBIR</label><input id="schedule-confirm" name="confirm_text" autocomplete="off" placeholder="ESCRIBIR" required></div>
          </div>
          <div class="schedule-actions"><button id="schedule-submit" type="submit">Guardar programación</button><span class="schedule-note" id="schedule-availability">Se guarda en Mint y continúa aunque cierres el panel.</span></div>
        </form>
        <div id="schedule-list" class="schedule-list"><div class="schedule-empty">Cargando programaciones…</div></div>
      </section>
      <section class="panel">
        <div class="panel-head"><div><div class="eyebrow">Ejecución manual</div><h2>Acciones</h2></div></div>
        <div class="actions" id="actions"></div>
      </section>
    </div>
    <section class="panel jobs-panel">
      <div class="panel-head"><div><div class="eyebrow">Actividad</div><h2>Registro de ejecuciones</h2><p>Salida en vivo de las tareas iniciadas manualmente.</p></div></div>
      <div class="jobs" id="jobs"><div class="empty">Todavía no hay ejecuciones.</div></div>
    </section>
  </main>
<script>
let actions = [];
let pollingTimer = null;
async function api(path, options) { const r = await fetch(path, options); const payload = await r.json().catch(() => ({error:'Respuesta inválida'})); if (!r.ok) throw new Error(payload.error || 'Error inesperado'); return payload; }
function escapeHtml(value) { return String(value).replace(/[&<>]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[c])); }
function isActiveJob(job) { return ['queued', 'running'].includes(job.status); }
function rememberLogScrolls() {
  const state = {};
  document.querySelectorAll('.job[data-id]').forEach(jobEl => {
    const pre = jobEl.querySelector('pre');
    if (!pre) return;
    const distanceFromBottom = pre.scrollHeight - pre.scrollTop - pre.clientHeight;
    state[jobEl.dataset.id] = { scrollTop: pre.scrollTop, stickToBottom: distanceFromBottom < 8 };
  });
  return state;
}
function restoreLogScrolls(state) {
  document.querySelectorAll('.job[data-id]').forEach(jobEl => {
    const pre = jobEl.querySelector('pre');
    const previous = state[jobEl.dataset.id];
    if (!pre || !previous) return;
    pre.scrollTop = previous.stickToBottom ? pre.scrollHeight : previous.scrollTop;
  });
}
function startPolling() {
  if (!pollingTimer) pollingTimer = setInterval(loadJobs, 1500);
}
function stopPolling() {
  if (!pollingTimer) return;
  clearInterval(pollingTimer);
  pollingTimer = null;
}
function fieldHtml(action, field) {
  if (field.type === 'select') return `<label>${field.label}</label><select name="${field.name}">${field.options.map(o => `<option value="${o}">${o || 'Todas'}</option>`).join('')}</select>`;
  if (field.type === 'checkbox') return `<label><input type="checkbox" name="${field.name}"> ${field.label}</label>`;
  return `<label>${field.label}</label><input name="${field.name}" type="${field.type || 'text'}" value="${field.default || ''}" ${field.required ? 'required' : ''}>`;
}
function renderActions() {
  document.getElementById('actions').innerHTML = actions.map(a => `
    <form class="action" data-id="${a.id}" data-confirm="${a.confirm || ''}" data-confirm-accept="${(a.confirm_accept || []).join('|')}">
      <span class="risk ${a.risk}">${a.risk}</span>
      <h3>${a.title}</h3><p>${a.description}</p>
      ${(a.fields || []).map(f => fieldHtml(a, f)).join('')}
      ${a.confirm ? `<label>Confirmación: escribí ${(a.confirm_accept && a.confirm_accept.length) ? a.confirm_accept.join(' o ') : a.confirm}</label><input name="confirm_text" placeholder="${a.confirm}">` : ''}
      <button>Ejecutar</button>
    </form>`).join('');
  document.querySelectorAll('form.action').forEach(form => form.addEventListener('submit', runAction));
}
async function runAction(ev) {
  ev.preventDefault();
  const form = ev.currentTarget;
  const confirmWord = form.dataset.confirm;
  const acceptedConfirmations = (form.dataset.confirmAccept || confirmWord).split('|').filter(Boolean).map(v => v.toUpperCase());
  const fd = new FormData(form);
  if (confirmWord && !acceptedConfirmations.includes(String(fd.get('confirm_text') || '').trim().toUpperCase())) { alert(`Para esta acción escribí ${acceptedConfirmations.join(' o ')}`); return; }
  const params = {};
  for (const [k, v] of fd.entries()) params[k] = v === 'on' ? true : v;
  const action_id = form.dataset.id;
  await api('/api/run', { method:'POST', headers:{'content-type':'application/json'}, body: JSON.stringify({action_id, params}) });
  startPolling();
  await loadJobs();
}
async function loadJobs() {
  const jobs = await api('/api/jobs');
  const el = document.getElementById('jobs');
  const scrollState = rememberLogScrolls();
  if (!jobs.length) { el.innerHTML = '<div class="empty">Todavía no hay ejecuciones.</div>'; stopPolling(); return; }
  el.innerHTML = jobs.map(j => `<article class="job" data-id="${escapeHtml(j.id)}"><div class="job-head"><strong>${escapeHtml(j.title)}</strong><span class="status ${escapeHtml(j.status)}">${escapeHtml(j.status)}</span></div><pre>${escapeHtml((j.logs || []).join('\n'))}</pre></article>`).join('');
  restoreLogScrolls(scrollState);
  if (jobs.some(isActiveJob)) startPolling(); else stopPolling();
}
function updateScheduleFields() {
  const script = document.getElementById('schedule-script').value;
  const mode = document.getElementById('schedule-mode').value;
  const needsAlignments = ['alineaciones', 'ambos'].includes(script);
  const needsResults = ['resultados', 'ambos'].includes(script);
  document.getElementById('schedule-fecha-field').classList.toggle('hidden', !needsAlignments);
  document.getElementById('schedule-fecha').required = needsAlignments;
  document.getElementById('schedule-category-field').classList.toggle('hidden', !needsResults);
  document.getElementById('schedule-date-field').classList.toggle('hidden', mode !== 'date');
  document.getElementById('schedule-date').required = mode === 'date';
  document.getElementById('schedule-weekday-field').classList.toggle('hidden', mode !== 'weekly');
}
function scheduleDescription(schedule) {
  const processNames = {resultados:'Resultados', alineaciones:'Alineaciones', ambos:'Resultados + alineaciones'};
  const weekdays = {monday:'lunes', tuesday:'martes', wednesday:'miércoles', thursday:'jueves', friday:'viernes', saturday:'sábado', sunday:'domingo'};
  const day = schedule.mode === 'date' ? schedule.run_date.split('-').reverse().join('/') : `Cada ${weekdays[schedule.weekday]}`;
  return `${day} · ${schedule.start_time}–${schedule.end_time} · cada ${schedule.interval_minutes} min · torneo ${schedule.torneo_id}${schedule.fecha ? ` · fecha ${schedule.fecha}` : ''}`;
}
function renderSchedules(payload) {
  const list = document.getElementById('schedule-list');
  const button = document.getElementById('schedule-submit');
  const note = document.getElementById('schedule-availability');
  button.disabled = !payload.available;
  note.textContent = payload.available ? 'Se guarda en Mint y continúa aunque cierres el panel.' : 'Programación disponible únicamente al abrir el panel desde Linux Mint con systemd.';
  if (!payload.schedules.length) { list.innerHTML = '<div class="schedule-empty">No hay programaciones especiales activas.</div>'; return; }
  const processNames = {resultados:'Resultados', alineaciones:'Alineaciones', ambos:'Resultados + alineaciones'};
  list.innerHTML = payload.schedules.map(schedule => `<article class="schedule-card"><div><strong>${escapeHtml(processNames[schedule.script] || schedule.script)}</strong><div class="schedule-meta">${escapeHtml(scheduleDescription(schedule))}</div></div><button type="button" class="delete-button" data-schedule-id="${escapeHtml(schedule.id)}">Eliminar</button></article>`).join('');
  list.querySelectorAll('[data-schedule-id]').forEach(button => button.addEventListener('click', deleteSchedule));
}
async function loadSchedules() { renderSchedules(await api('/api/schedules')); }
async function saveSchedule(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const params = Object.fromEntries(new FormData(form).entries());
  try {
    await api('/api/schedules', {method:'POST', headers:{'content-type':'application/json'}, body:JSON.stringify({params})});
    form.querySelector('[name="confirm_text"]').value = '';
    await loadSchedules();
  } catch (error) { alert(error.message); }
}
async function deleteSchedule(event) {
  const id = event.currentTarget.dataset.scheduleId;
  if (!confirm('¿Eliminar esta programación? El timer se desactivará en Mint.')) return;
  try { await api(`/api/schedules/${id}`, {method:'DELETE'}); await loadSchedules(); }
  catch (error) { alert(error.message); }
}
async function init() {
  const dateInput = document.getElementById('schedule-date');
  const today = new Date();
  const localDate = new Date(today.getTime() - today.getTimezoneOffset() * 60000).toISOString().slice(0,10);
  dateInput.min = localDate; dateInput.value = localDate;
  document.getElementById('schedule-script').addEventListener('change', updateScheduleFields);
  document.getElementById('schedule-mode').addEventListener('change', updateScheduleFields);
  document.getElementById('schedule-form').addEventListener('submit', saveSchedule);
  updateScheduleFields();
  actions = await api('/api/actions'); renderActions();
  await Promise.all([loadJobs(), loadSchedules()]);
}
init();
</script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    def _json(self, payload, status=200):
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/":
            data = HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        elif path == "/api/actions":
            self._json(serialize_actions())
        elif path == "/api/jobs":
            with JOBS_LOCK:
                jobs = sorted(JOBS.values(), key=lambda j: j["created_at"], reverse=True)
            self._json(jobs)
        elif path == "/api/schedules":
            self._json(
                {
                    "available": scheduler_available(),
                    "timezone": "hora local de Mint",
                    "schedules": list_schedules(),
                }
            )
        else:
            self._json({"error": "not found"}, 404)

    def do_POST(self):
        path = urlparse(self.path).path
        if path not in ("/api/run", "/api/schedules"):
            self._json({"error": "not found"}, 404)
            return

        try:
            payload = parse_json_request(
                self.headers.get("Content-Length"), self.rfile.read
            )
        except RequestValidationError as exc:
            self._json({"error": str(exc)}, 400)
            return
        if path == "/api/run":
            response, status = dispatch_run(payload)
        else:
            response, status = dispatch_schedule_create(payload)
        self._json(response, status)

    def do_DELETE(self):
        path = urlparse(self.path).path
        prefix = "/api/schedules/"
        if not path.startswith(prefix):
            self._json({"error": "not found"}, 404)
            return
        schedule_id = path[len(prefix):]
        response, status = dispatch_schedule_delete(schedule_id)
        self._json(response, status)

    def log_message(self, fmt, *args):
        return


def main():
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    url = f"http://{HOST}:{PORT}"
    print(f"Panel local: {url}")
    print("Ctrl+C para cerrar")
    if os.environ.get("CONTROL_PANEL_OPEN", "1") == "1":
        webbrowser.open(url)
    server.serve_forever()


if __name__ == "__main__":
    main()
