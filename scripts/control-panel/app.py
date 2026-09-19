#!/usr/bin/env python3
"""Panel local de operaciones para Liga de Lincoln.

Corre en localhost y ejecuta scripts del proyecto con logs visibles.
No tiene dependencias externas: usa solo la librería estándar de Python.
"""

import json
import os
import subprocess
import threading
import time
import uuid
import webbrowser
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


class PythonResolutionError(RuntimeError):
    """Raised when the project's backend Python interpreter is unavailable."""


class RequestValidationError(ValueError):
    """Raised when an action request is unsafe or incomplete."""


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
    :root { color-scheme: dark; --bg:#03170c; --card:#0d2a16; --line:#245b32; --green:#22c55e; --yellow:#facc15; --muted:#9db6a6; --danger:#ef4444; }
    * { box-sizing: border-box; }
    body { margin:0; font-family: Inter, system-ui, Segoe UI, sans-serif; background: radial-gradient(circle at top, #14532d 0, var(--bg) 42%); color:#f8fafc; }
    header { padding:28px 32px; border-bottom:1px solid rgba(250,204,21,.25); display:flex; justify-content:space-between; gap:16px; align-items:center; }
    h1 { margin:0; text-transform:uppercase; letter-spacing:.08em; font-size:24px; }
    main { display:grid; grid-template-columns: minmax(360px, 520px) 1fr; gap:20px; padding:24px; }
    .panel, .job { background:rgba(13,42,22,.92); border:1px solid rgba(34,197,94,.24); border-radius:18px; box-shadow: 0 18px 50px rgba(0,0,0,.22); }
    .actions { padding:16px; display:grid; gap:12px; max-height: calc(100vh - 130px); overflow:auto; }
    .action { border:1px solid rgba(255,255,255,.09); border-radius:14px; padding:14px; background:rgba(3,23,12,.45); }
    .action h3 { margin:0 0 4px; font-size:16px; }
    .action p { margin:0 0 12px; color:var(--muted); font-size:13px; line-height:1.35; }
    .risk { display:inline-block; font-size:10px; font-weight:900; text-transform:uppercase; letter-spacing:.08em; padding:4px 8px; border-radius:999px; margin-bottom:8px; background:#164e28; color:#bbf7d0; }
    .risk.writes-db, .risk.external-upload { background:#4a2b04; color:#fde68a; }
    .risk.safe { background:#06351f; color:#86efac; }
    label { display:block; font-size:12px; color:#cbd5d1; margin:8px 0 4px; }
    input, select { width:100%; padding:9px 10px; border-radius:10px; border:1px solid var(--line); background:#03170c; color:#fff; }
    input[type="checkbox"] { width:auto; }
    button { cursor:pointer; border:0; padding:10px 13px; border-radius:12px; font-weight:900; background:var(--yellow); color:#052e16; margin-top:10px; }
    button:hover { filter:brightness(1.05); }
    .jobs { padding:16px; display:grid; gap:14px; max-height: calc(100vh - 130px); overflow:auto; }
    .job { padding:14px; }
    .job-head { display:flex; justify-content:space-between; gap:12px; align-items:center; margin-bottom:8px; }
    .status { font-size:11px; text-transform:uppercase; font-weight:900; letter-spacing:.08em; color:var(--yellow); }
    .status.completed { color:var(--green); } .status.failed { color:var(--danger); }
    pre { margin:0; padding:12px; background:#020d07; border-radius:12px; overflow:auto; max-height:360px; white-space:pre-wrap; font-size:12px; line-height:1.45; }
    .empty { color:var(--muted); padding:30px; text-align:center; }
    @media (max-width: 900px) { main { grid-template-columns: 1fr; } }
  </style>
</head>
<body>
  <header>
    <div>
      <h1>Panel Liga de Lincoln</h1>
      <div style="color:var(--muted);font-size:13px">Local · Scripts · Producción con cuidado</div>
    </div>
    <div style="color:var(--yellow);font-weight:900">127.0.0.1</div>
  </header>
  <main>
    <section class="panel"><div class="actions" id="actions"></div></section>
    <section class="panel"><div class="jobs" id="jobs"><div class="empty">Todavía no hay ejecuciones.</div></div></section>
  </main>
<script>
let actions = [];
let pollingTimer = null;
async function api(path, options) { const r = await fetch(path, options); if (!r.ok) throw new Error(await r.text()); return r.json(); }
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
async function init() { actions = await api('/api/actions'); renderActions(); await loadJobs(); }
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
        else:
            self._json({"error": "not found"}, 404)

    def do_POST(self):
        path = urlparse(self.path).path
        if path != "/api/run":
            self._json({"error": "not found"}, 404)
            return

        response, status = handle_run_http_request(
            self.headers.get("Content-Length"),
            self.rfile.read,
        )
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
