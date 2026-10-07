# -*- coding: utf-8 -*-
"""Consume validated remote scraper jobs from Supabase on the Mint host."""

from __future__ import annotations

import argparse
import os
import queue
import signal
import socket
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, Sequence

from config import supabase


SCRIPTS_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPTS_DIR.parents[1]
ALLOWED_SCRAPERS = {"horarios", "resultados", "alineaciones", "resultados_alineaciones"}
ALLOWED_MODES = {"preview", "execute"}
ALLOWED_CATEGORIES = {"primera", "septima", "octava", "novena", "decima"}
MAX_OUTPUT_CHARS = 60_000
DEFAULT_POLL_SECONDS = 5.0
DEFAULT_TIMEOUT_SECONDS = 900.0
WORKER_VERSION = "1"
STOP_EVENT = threading.Event()


class JobValidationError(ValueError):
    """Raised when a queued job contains parameters outside the allow-list."""


@dataclass(frozen=True)
class ScraperJob:
    id: int
    scraper: str
    mode: str
    torneo_id: int
    categoria: Optional[str]
    fecha: Optional[int]

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "ScraperJob":
        try:
            job_id = int(value["id"])
            torneo_id = int(value["torneo_id"])
        except (KeyError, TypeError, ValueError) as exc:
            raise JobValidationError("ID de trabajo o torneo inválido") from exc

        scraper = str(value.get("scraper") or "").strip().lower()
        mode = str(value.get("mode") or "").strip().lower()
        raw_category = value.get("categoria")
        categoria = str(raw_category).strip().lower() if raw_category else None
        raw_fecha = value.get("fecha")
        try:
            fecha = int(raw_fecha) if raw_fecha is not None else None
        except (TypeError, ValueError) as exc:
            raise JobValidationError("Fecha inválida") from exc

        if job_id <= 0 or torneo_id <= 0:
            raise JobValidationError("Los IDs deben ser enteros positivos")
        if scraper not in ALLOWED_SCRAPERS:
            raise JobValidationError(f"Scraper no permitido: {scraper or '-'}")
        if mode not in ALLOWED_MODES:
            raise JobValidationError(f"Modo no permitido: {mode or '-'}")
        if categoria is not None and categoria not in ALLOWED_CATEGORIES:
            raise JobValidationError(f"Categoría no permitida: {categoria}")
        if fecha is not None and fecha <= 0:
            raise JobValidationError("La fecha debe ser positiva")

        if scraper == "horarios" and (categoria is not None or fecha is not None):
            raise JobValidationError("Horarios no acepta categoría ni fecha")
        if scraper == "resultados" and fecha is not None:
            raise JobValidationError("Resultados no acepta fecha")
        if scraper == "alineaciones" and (categoria is not None or fecha is None):
            raise JobValidationError("Alineaciones exige fecha y no acepta categoría")
        if scraper == "resultados_alineaciones" and fecha is None:
            raise JobValidationError("Resultados + alineaciones exige fecha")

        return cls(
            id=job_id,
            scraper=scraper,
            mode=mode,
            torneo_id=torneo_id,
            categoria=categoria,
            fecha=fecha,
        )


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_job_commands(job: ScraperJob, *, python: str | Path = sys.executable) -> list[tuple[str, list[str]]]:
    """Translate one validated job into exact, shell-free command vectors."""

    def command(name: str) -> list[str]:
        result = [
            str(python),
            "-u",
            str(SCRIPTS_DIR / f"scraper_{name}.py"),
            "--torneo-id",
            str(job.torneo_id),
        ]
        if name == "resultados" and job.categoria:
            result.extend(["--category", job.categoria])
        if name == "alineaciones":
            result.extend(["--fecha", str(job.fecha)])
        if job.mode == "execute":
            result.append("--execute")
        return result

    if job.scraper == "resultados_alineaciones":
        return [("Resultados", command("resultados")), ("Alineaciones", command("alineaciones"))]
    display_name = {
        "horarios": "Horarios",
        "resultados": "Resultados",
        "alineaciones": "Alineaciones",
    }[job.scraper]
    return [(display_name, command(job.scraper))]


def _trim_output(value: str) -> str:
    if len(value) <= MAX_OUTPUT_CHARS:
        return value
    marker = "\n… salida anterior recortada …\n"
    return marker + value[-(MAX_OUTPUT_CHARS - len(marker)) :]


def run_command_streaming(
    command: Sequence[str],
    *,
    cwd: Path,
    timeout: float,
    on_output: Callable[[str], None],
) -> int:
    """Run without a shell and stream combined stdout/stderr to the caller."""
    environment = os.environ.copy()
    environment["PYTHONUNBUFFERED"] = "1"
    process = subprocess.Popen(  # noqa: S603 - command is built from an allow-list
        list(command),
        cwd=cwd,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )
    output_queue: queue.Queue[Optional[str]] = queue.Queue()

    def reader() -> None:
        assert process.stdout is not None
        for line in process.stdout:
            output_queue.put(line)
        output_queue.put(None)

    threading.Thread(target=reader, daemon=True).start()
    deadline = time.monotonic() + timeout
    reader_finished = False
    while not reader_finished or process.poll() is None:
        if STOP_EVENT.is_set():
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
            raise InterruptedError("El worker recibió una señal de apagado")
        if time.monotonic() >= deadline:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
            raise TimeoutError(f"El comando excedió el límite de {int(timeout)} segundos")
        try:
            item = output_queue.get(timeout=0.5)
        except queue.Empty:
            on_output("")
            continue
        if item is None:
            reader_finished = True
        else:
            on_output(item)
    return int(process.wait())


def _update_job(client: Any, job_id: int, values: Mapping[str, Any]) -> None:
    client.table("scraper_jobs").update(dict(values)).eq("id", job_id).execute()


def heartbeat(client: Any, worker_id: str, *, current_job_id: Optional[int] = None) -> None:
    client.table("scraper_workers").upsert(
        {
            "worker_id": worker_id,
            "hostname": socket.gethostname(),
            "last_seen_at": utc_now(),
            "current_job_id": current_job_id,
            "version": WORKER_VERSION,
        },
        on_conflict="worker_id",
    ).execute()


def claim_next_job(client: Any, worker_id: str) -> Optional[Mapping[str, Any]]:
    response = client.rpc("claim_scraper_job", {"p_worker_id": worker_id}).execute()
    data = response.data or []
    return data[0] if data else None


def fail_stale_jobs(client: Any, *, stale_minutes: int = 20) -> None:
    """Release the single-job lock after an interrupted or crashed worker."""
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=stale_minutes)).isoformat()
    client.table("scraper_jobs").update(
        {
            "status": "failed",
            "exit_code": 2,
            "error_message": "El worker anterior dejó de responder",
            "finished_at": utc_now(),
        }
    ).eq("status", "running").lt("heartbeat_at", cutoff).execute()


def execute_claimed_job(
    client: Any,
    raw_job: Mapping[str, Any],
    worker_id: str,
    *,
    python: str | Path = sys.executable,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    runner: Callable[..., int] = run_command_streaming,
) -> bool:
    """Execute one already-claimed job and persist its complete audit trail."""
    job_id = int(raw_job.get("id") or 0)
    output = ""
    last_flush = 0.0

    def flush(*, force: bool = False) -> None:
        nonlocal last_flush
        now = time.monotonic()
        if force or now - last_flush >= 1.0:
            _update_job(
                client,
                job_id,
                {"output": _trim_output(output), "heartbeat_at": utc_now()},
            )
            heartbeat(client, worker_id, current_job_id=job_id)
            last_flush = now

    def append(value: str) -> None:
        nonlocal output
        output = _trim_output(output + value)
        flush()

    try:
        job = ScraperJob.from_mapping(raw_job)
        heartbeat(client, worker_id, current_job_id=job.id)
        commands = build_job_commands(job, python=python)
        exit_code = 0
        for title, command in commands:
            append(f"\n=== {title} · {'EJECUTAR' if job.mode == 'execute' else 'PREVISUALIZAR'} ===\n")
            exit_code = runner(
                command,
                cwd=SCRIPTS_DIR,
                timeout=timeout,
                on_output=append,
            )
            flush(force=True)
            if exit_code != 0:
                break

        status = "succeeded" if exit_code == 0 else "failed"
        error_message = None if exit_code == 0 else f"El proceso terminó con código {exit_code}"
        _update_job(
            client,
            job.id,
            {
                "status": status,
                "exit_code": exit_code,
                "output": _trim_output(output),
                "error_message": error_message,
                "heartbeat_at": utc_now(),
                "finished_at": utc_now(),
            },
        )
        return exit_code == 0
    except Exception as exc:
        if job_id > 0:
            append(f"\nERROR DEL WORKER: {exc}\n")
            _update_job(
                client,
                job_id,
                {
                    "status": "failed",
                    "exit_code": 2,
                    "output": _trim_output(output),
                    "error_message": str(exc),
                    "heartbeat_at": utc_now(),
                    "finished_at": utc_now(),
                },
            )
        return False
    finally:
        heartbeat(client, worker_id, current_job_id=None)


def run_worker(
    client: Any,
    *,
    worker_id: str,
    poll_seconds: float,
    timeout: float,
    once: bool,
) -> int:
    fail_stale_jobs(client)
    heartbeat(client, worker_id)
    while not STOP_EVENT.is_set():
        raw_job = claim_next_job(client, worker_id)
        if raw_job is not None:
            execute_claimed_job(client, raw_job, worker_id, timeout=timeout)
            if once:
                return 0
            continue
        if once:
            return 0
        STOP_EVENT.wait(poll_seconds)
        heartbeat(client, worker_id)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Worker remoto de scrapers de la Liga de Lincoln")
    parser.add_argument("--once", action="store_true", help="Procesa como máximo un trabajo y termina")
    parser.add_argument("--poll-seconds", type=float, default=DEFAULT_POLL_SECONDS)
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument(
        "--worker-id",
        default=os.environ.get("LIGA_SCRAPER_WORKER_ID") or f"mint-{socket.gethostname()}",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if args.poll_seconds < 1 or args.timeout < 30:
        raise SystemExit("poll-seconds debe ser >= 1 y timeout >= 30")
    def request_stop(signum: int, frame: Any) -> None:
        del signum, frame
        STOP_EVENT.set()

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    return run_worker(
        supabase,
        worker_id=args.worker_id,
        poll_seconds=args.poll_seconds,
        timeout=args.timeout,
        once=args.once,
    )


if __name__ == "__main__":
    raise SystemExit(main())
