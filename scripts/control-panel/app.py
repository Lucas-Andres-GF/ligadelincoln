#!/usr/bin/env python3
"""Panel local de operaciones para Liga de Lincoln.

Corre en localhost y ejecuta scripts del proyecto con logs visibles.
No tiene dependencias externas: usa solo la librería estándar de Python.
"""

import json
import os
import subprocess
import sys
import threading
import time
import uuid
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

HOST = "127.0.0.1"
PORT = int(os.environ.get("CONTROL_PANEL_PORT", "8765"))

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent.parent
BACKEND_SCRIPTS = PROJECT_DIR / "backend" / "scripts"
PYTHON = sys.executable

JOBS = {}
JOBS_LOCK = threading.Lock()


def py(path, *args):
    command = [PYTHON, str(path)]
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


def placas_resultados_command(params):
    command = [
        PYTHON,
        str(PROJECT_DIR / "scripts" / "generador-placas" / "generar_placas_resultados.py"),
        "--fecha",
        str(params.get("fecha")),
    ]

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
        "scraper_resultados": {
            "title": "Actualizar resultados",
            "description": "Scrapea resultados y actualiza partidos/posiciones.",
            "risk": "writes-db",
            "fields": [],
            "cwd": BACKEND_SCRIPTS,
            "command": lambda p: py(BACKEND_SCRIPTS / "scraper_resultados.py"),
        },
        "scraper_horarios": {
            "title": "Actualizar horarios",
            "description": "Scrapea fecha, hora y cancha de partidos.",
            "risk": "writes-db",
            "fields": [],
            "cwd": BACKEND_SCRIPTS,
            "command": lambda p: py(BACKEND_SCRIPTS / "scraper_horarios.py"),
        },
        "alineaciones_dry_run": {
            "title": "Alineaciones dry-run",
            "description": "Verifica qué alineaciones tocaría sin escribir en DB.",
            "risk": "safe",
            "fields": [{"name": "fecha", "label": "Fecha", "type": "number", "required": True}],
            "cwd": BACKEND_SCRIPTS,
            "command": lambda p: py(BACKEND_SCRIPTS / "scraper_alineaciones.py", "--fecha", p.get("fecha"), "--dry-run"),
        },
        "alineaciones_run": {
            "title": "Alineaciones real",
            "description": "Scrapea alineaciones de Primera, escribe en DB y despliega el frontend si guardó alineaciones.",
            "risk": "writes-db",
            "confirm": "ESCRIBIR",
            "fields": [{"name": "fecha", "label": "Fecha", "type": "number", "required": True}],
            "cwd": BACKEND_SCRIPTS,
            "command": lambda p: py(BACKEND_SCRIPTS / "scraper_alineaciones.py", "--fecha", p.get("fecha")),
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
  for (const [k, v] of fd.entries()) if (k !== 'confirm_text') params[k] = v === 'on' ? true : v;
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

        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
        action_id = payload.get("action_id")
        params = payload.get("params") or {}
        if action_id not in ACTIONS:
            self._json({"error": "acción inválida"}, 400)
            return
        job = create_job(action_id, params)
        self._json(job, 201)

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
