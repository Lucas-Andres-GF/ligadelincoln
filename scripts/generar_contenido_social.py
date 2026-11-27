#!/usr/bin/env python3
"""Genera placas editoriales de la Liga en formato publicación o historia."""

from __future__ import annotations

import argparse
import base64
import html
import json
import os
import re
import sys
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Sequence

from dotenv import load_dotenv
from supabase import create_client


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


PROJECT_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = PROJECT_DIR / "backend" / ".env"
DEFAULT_OUTPUT_DIR = PROJECT_DIR / "social-images"
CRESTS_DIR = PROJECT_DIR / "frontend" / "public" / "escudos_hd"

load_dotenv(ENV_PATH)

CATEGORIES = {
    "primera": (1, "PRIMERA DIVISIÓN"),
    "septima": (2, "SÉPTIMA DIVISIÓN"),
    "octava": (3, "OCTAVA DIVISIÓN"),
    "novena": (4, "NOVENA DIVISIÓN"),
    "decima": (5, "DÉCIMA DIVISIÓN"),
}

CONTENT_TYPES = ("fixture", "resultados", "posiciones", "goleadores", "todos")


@dataclass(frozen=True)
class FormatSpec:
    key: str
    width: int
    height: int
    label: str
    page_rows: dict[str, int]


FORMATS = {
    "publicacion": FormatSpec(
        "publicacion",
        1080,
        1350,
        "Publicación 4:5",
        {"fixture": 6, "resultados": 6, "posiciones": 11, "goleadores": 10},
    ),
    "historia": FormatSpec(
        "historia",
        1080,
        1920,
        "Historia 9:16",
        {"fixture": 9, "resultados": 9, "posiciones": 16, "goleadores": 13},
    ),
}


CRESTS = {
    "argentino": "argentino.png",
    "atl pasteur": "atl.pasteur.png",
    "atletico pasteur": "atl.pasteur.png",
    "atl roberts": "atl.roberts.png",
    "atletico roberts": "atl.roberts.png",
    "ca pintense": "ca.pintense.png",
    "pintense": "ca.pintense.png",
    "caset": "caset.png",
    "dep arenaza": "dep.arenaza.png",
    "deportivo arenaza": "dep.arenaza.png",
    "dep gral pinto": "dep.pinto.png",
    "deportivo general pinto": "dep.pinto.png",
    "el linqueno": "el.linqueño.png",
    "cael": "el.linqueño.png",
    "juventud unida": "juventud.unida.png",
    "san martin": "san.martin.png",
    "villa francia": "villa.francia.png",
}


def compact_space(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def identity(value: Any) -> str:
    normalized = unicodedata.normalize("NFKD", compact_space(value).lower())
    ascii_value = "".join(char for char in normalized if not unicodedata.combining(char))
    return compact_space(re.sub(r"[^a-z0-9]+", " ", ascii_value))


def slugify(value: Any) -> str:
    return identity(value).replace(" ", "-") or "contenido"


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def positive_tournament_id(value: Any) -> int:
    torneo_id = safe_int(value)
    if torneo_id <= 0:
        raise ValueError("--torneo-id debe ser un entero positivo (o ACTIVE_TORNEO_ID en backend/.env)")
    return torneo_id


def chunks(items: Sequence[Any], size: int) -> list[list[Any]]:
    if size <= 0:
        raise ValueError("El tamaño de página debe ser positivo")
    return [list(items[index:index + size]) for index in range(0, len(items), size)] or [[]]


def relation_name(value: Any, fallback: str = "Club") -> str:
    if isinstance(value, dict):
        return compact_space(value.get("nombre")) or fallback
    if isinstance(value, list) and value and isinstance(value[0], dict):
        return compact_space(value[0].get("nombre")) or fallback
    return fallback


def crest_path(club_name: str) -> Path | None:
    filename = CRESTS.get(identity(club_name))
    if not filename:
        return None
    path = CRESTS_DIR / filename
    return path if path.exists() else None


def crest_data_uri(club_name: str) -> str:
    path = crest_path(club_name)
    if not path:
        return ""
    mime = "image/png"
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode('ascii')}"


def crest_html(club_name: str, css_class: str = "crest") -> str:
    source = crest_data_uri(club_name)
    if source:
        return f'<img class="{css_class}" src="{source}" alt="">'
    initials = "".join(part[:1] for part in compact_space(club_name).split()[:2]).upper() or "L"
    return f'<span class="{css_class} crest-fallback">{html.escape(initials)}</span>'


def parse_iso_date(value: Any) -> datetime | None:
    text = compact_space(value)
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(text[:10], fmt)
        except ValueError:
            continue
    return None


def date_label(value: Any, long: bool = False) -> str:
    parsed = parse_iso_date(value)
    if not parsed:
        return "A DEFINIR"
    weekdays = ("LUN", "MAR", "MIÉ", "JUE", "VIE", "SÁB", "DOM")
    months = ("ENE", "FEB", "MAR", "ABR", "MAY", "JUN", "JUL", "AGO", "SEP", "OCT", "NOV", "DIC")
    if long:
        return f"{weekdays[parsed.weekday()]} {parsed.day:02d} {months[parsed.month - 1]}"
    return f"{parsed.day:02d}/{parsed.month:02d}"


def time_label(value: Any) -> str:
    text = compact_space(value)
    if not text:
        return "A DEFINIR"
    return f"{text[:5]} HS"


def match_dates(matches: Iterable[dict[str, Any]]) -> str:
    values = sorted({row.get("dia") for row in matches if parse_iso_date(row.get("dia"))})
    if not values:
        return "DÍA Y HORARIO A CONFIRMAR"
    labels = [date_label(value, long=True) for value in values]
    if len(labels) == 1:
        return labels[0]
    return f"{labels[0]} — {labels[-1]}"


def build_scorers(lineups: Iterable[dict[str, Any]], clubs_by_id: dict[int, str]) -> list[dict[str, Any]]:
    grouped: dict[tuple[int, str], dict[str, Any]] = {}
    for row in lineups:
        team_id = safe_int(row.get("equipo_id"))
        name = compact_space(row.get("nombre"))
        goals = safe_int(row.get("goleo"))
        if team_id <= 0 or not name or goals <= 0:
            continue
        key = (team_id, identity(name))
        current = grouped.setdefault(
            key,
            {"name": name, "team_id": team_id, "club": clubs_by_id.get(team_id, "Club"), "goals": 0},
        )
        current["goals"] += goals
    return sorted(
        grouped.values(),
        key=lambda row: (-row["goals"], identity(row["club"]), identity(row["name"])),
    )


class SocialData:
    def __init__(self, client: Any, tournament_id: int):
        self.client = client
        self.tournament_id = tournament_id

    def tournament(self) -> dict[str, Any]:
        response = (
            self.client.table("torneos")
            .select("id,nombre,slug,temporada,activo")
            .eq("id", self.tournament_id)
            .limit(1)
            .execute()
        )
        if not response.data:
            raise RuntimeError(f"No existe el torneo {self.tournament_id}")
        return response.data[0]

    def matches(self, round_id: int, category_id: int) -> list[dict[str, Any]]:
        response = (
            self.client.table("partidos")
            .select(
                "id,fecha_id,categoria_id,local_id,visitante_id,dia,hora,cancha,estado,"
                "goles_local,goles_visitante,local:local_id(id,nombre),visitante:visitante_id(id,nombre)"
            )
            .eq("torneo_id", self.tournament_id)
            .eq("fecha_id", round_id)
            .eq("categoria_id", category_id)
            .order("dia")
            .order("hora")
            .order("id")
            .execute()
        )
        return response.data or []

    def positions(self, category_id: int) -> list[dict[str, Any]]:
        response = (
            self.client.table("posiciones")
            .select("club_id,pts,pj,pg,pe,pp,gf,gc,dif,ultimos_5,clubes(nombre)")
            .eq("torneo_id", self.tournament_id)
            .eq("categoria_id", category_id)
            .order("pts", desc=True)
            .order("dif", desc=True)
            .order("gf", desc=True)
            .execute()
        )
        return response.data or []

    def pending_matches(self, category_id: int, through_round: int) -> list[dict[str, Any]]:
        return (self.client.table("partidos")
                .select("fecha_id,local:local_id(nombre),visitante:visitante_id(nombre)")
                .eq("torneo_id", self.tournament_id).eq("categoria_id", category_id)
                .in_("estado", ["A reprogramar", "suspendido"]).lte("fecha_id", through_round)
                .not_.is_("local_id", "null").not_.is_("visitante_id", "null")
                .order("fecha_id").order("id").execute().data or [])

    def scorers(self) -> list[dict[str, Any]]:
        matches = (
            self.client.table("partidos")
            .select("id,local_id,visitante_id,local:local_id(id,nombre),visitante:visitante_id(id,nombre)")
            .eq("torneo_id", self.tournament_id)
            .eq("categoria_id", CATEGORIES["primera"][0])
            .execute()
        ).data or []
        match_ids = [row.get("id") for row in matches if row.get("id")]
        if not match_ids:
            return []
        clubs_by_id: dict[int, str] = {}
        for match in matches:
            for side, relation in (("local_id", "local"), ("visitante_id", "visitante")):
                club_id = safe_int(match.get(side))
                if club_id > 0:
                    clubs_by_id[club_id] = relation_name(match.get(relation))
        lineups = (
            self.client.table("alineaciones")
            .select("partido_id,equipo_id,nombre,goleo")
            .in_("partido_id", match_ids)
            .gt("goleo", 0)
            .execute()
        ).data or []
        return build_scorers(lineups, clubs_by_id)


def category_selection(value: str | None) -> list[tuple[str, int, str]]:
    if value:
        category_id, label = CATEGORIES[value]
        return [(value, category_id, label)]
    return [(slug, item[0], item[1]) for slug, item in CATEGORIES.items()]


def format_selection(value: str) -> list[FormatSpec]:
    if value == "ambos":
        return [FORMATS["publicacion"], FORMATS["historia"]]
    return [FORMATS[value]]


def page_title(content_type: str) -> str:
    return {
        "fixture": "PRÓXIMOS PARTIDOS",
        "resultados": "RESULTADOS",
        "posiciones": "TABLA DE POSICIONES",
        "goleadores": "TABLA DE GOLEADORES",
    }[content_type]


def shared_css(spec: FormatSpec) -> str:
    safe_top = 154 if spec.key == "historia" else 72
    safe_bottom = 160 if spec.key == "historia" else 72
    return f"""
    * {{ box-sizing:border-box; }}
    html, body {{ margin:0; width:{spec.width}px; height:{spec.height}px; overflow:hidden; }}
    body {{
      --green:#06361f; --deep:#031d12; --ink:#102016; --cream:#f4f0df; --acid:#d9ff3f;
      --line:rgba(217,255,63,.28); --muted:#aebba9;
      background:#06361f; color:var(--cream);
      font-family:"Arial Narrow","Liberation Sans Narrow","DejaVu Sans Condensed",Arial,sans-serif;
      padding:{safe_top}px 64px {safe_bottom}px; position:relative;
    }}
    body:before {{ content:""; position:absolute; inset:0; opacity:.16; pointer-events:none;
      background:linear-gradient(90deg,transparent 49.8%,rgba(255,255,255,.25) 50%,transparent 50.2%),
      radial-gradient(circle at 50% 52%,transparent 0 142px,rgba(255,255,255,.22) 143px 146px,transparent 147px),
      repeating-linear-gradient(0deg,rgba(255,255,255,.025) 0 2px,transparent 2px 8px); }}
    body:after {{ content:""; position:absolute; top:0; right:0; width:23px; height:100%;
      background:linear-gradient(var(--acid) 0 34%,#fff 34% 67%,#159449 67%); }}
    .sheet {{ height:100%; position:relative; z-index:1; display:flex; flex-direction:column; }}
    .brand {{ display:flex; align-items:center; justify-content:space-between; border-bottom:2px solid var(--line); padding-bottom:20px; }}
    .brand-name {{ font-size:30px; font-weight:950; letter-spacing:.03em; text-transform:uppercase; }}
    .brand-mark {{ display:inline-flex; align-items:center; gap:12px; }}
    .brand-dot {{ width:17px; height:17px; border-radius:50%; background:var(--acid); box-shadow:0 0 0 7px rgba(217,255,63,.12); }}
    .site {{ color:var(--acid); font-size:18px; font-weight:900; letter-spacing:.1em; text-transform:uppercase; }}
    .hero {{ display:grid; grid-template-columns:1fr auto; gap:22px; align-items:end; padding:26px 0 12px; }}
    .kicker {{ color:var(--acid); font-size:19px; font-weight:950; letter-spacing:.22em; text-transform:uppercase; }}
    h1 {{ margin:7px 0 0; font-size:{36 if spec.key == 'publicacion' else 40}px; line-height:.94; font-weight:1000; letter-spacing:.035em; text-transform:uppercase; color:#c5d0c4; }}
    .round {{ min-width:184px; background:var(--acid); color:var(--ink); padding:16px 18px 13px; text-align:right; clip-path:polygon(12px 0,100% 0,100% 100%,0 100%,0 12px); }}
    .round span {{ display:block; font-size:13px; font-weight:950; letter-spacing:.16em; text-transform:uppercase; }}
    .round strong {{ display:block; font-size:42px; line-height:.9; font-weight:1000; }}
    .meta {{ display:flex; justify-content:space-between; align-items:end; gap:24px; color:#d7dfd2; font-size:17px; font-weight:850; letter-spacing:.09em; text-transform:uppercase; padding:8px 0 20px; }}
    .category-title {{ max-width:72%; color:var(--cream); font-size:{58 if spec.key == 'publicacion' else 66}px; line-height:.84; font-weight:1000; letter-spacing:-.035em; }}
    .date-range {{ padding-bottom:3px; text-align:right; white-space:nowrap; }}
    .content {{ flex:1; min-height:0; display:flex; flex-direction:column; gap:12px; }}
    .footer {{ margin-top:auto; padding-top:18px; display:flex; justify-content:space-between; border-top:1px solid var(--line); color:#b8c7b8; font-size:15px; font-weight:800; letter-spacing:.08em; text-transform:uppercase; }}
    .footer-page {{ justify-content:flex-end; }}
    .footer strong {{ color:var(--acid); }}
    .page {{ color:var(--acid); }}
    .crest {{ width:66px; height:66px; object-fit:contain; flex:0 0 auto; filter:drop-shadow(0 5px 8px rgba(0,0,0,.35)); }}
    .crest.sm {{ width:46px; height:46px; }}
    .crest-fallback {{ display:inline-grid; place-items:center; border-radius:50%; background:#164e31; color:var(--acid); border:1px solid var(--line); font-weight:950; }}
    .empty {{ margin:auto; text-align:center; color:#c7d4c6; font-size:26px; font-weight:900; text-transform:uppercase; }}
    """


def fixture_rows(matches: Sequence[dict[str, Any]], results: bool = False) -> str:
    rows = []
    for match in matches:
        local = relation_name(match.get("local"), "LOCAL")
        visitor_id = safe_int(match.get("visitante_id"))
        visitor = relation_name(match.get("visitante"), "LIBRE") if visitor_id else "LIBRE"
        venue = compact_space(match.get("cancha"))
        if results:
            middle = (
                f'<div class="score"><strong>{safe_int(match.get("goles_local"))}</strong>'
                f'<span>—</span><strong>{safe_int(match.get("goles_visitante"))}</strong></div>'
            )
            timing = f'{date_label(match.get("dia"), long=True)} · JUGADO'
        elif not visitor_id:
            middle = '<div class="free">LIBRE</div>'
            timing = date_label(match.get("dia"), long=True)
        else:
            middle = '<div class="versus">VS</div>'
            timing = f'{date_label(match.get("dia"), long=True)} · {time_label(match.get("hora"))}'
        venue_html = f'<span class="venue">{html.escape(venue)}</span>' if venue else ""
        rows.append(f"""
        <article class="match">
          <div class="team local"><span>{html.escape(local)}</span>{crest_html(local)}</div>
          <div class="match-center">{middle}<div class="timing">{html.escape(timing)}</div>{venue_html}</div>
          <div class="team visitor">{crest_html(visitor)}<span>{html.escape(visitor)}</span></div>
        </article>""")
    return "".join(rows)


def recent_form(value: Any) -> list[str]:
    items = value
    if isinstance(value, str):
        try:
            items = json.loads(value)
        except (TypeError, ValueError, json.JSONDecodeError):
            return []
    if not isinstance(items, list):
        return []
    normalized = [compact_space(item).upper() for item in items]
    return [item for item in normalized if item in {"G", "E", "P"}][-5:][::-1]


def form_html(value: Any) -> str:
    results = recent_form(value)
    if not results:
        return '<span class="form-empty">—</span>'
    return "".join(
        f'<span class="form-dot form-{result.lower()}">{result}</span>'
        for result in results
    )


def positions_rows(rows: Sequence[dict[str, Any]], offset: int) -> str:
    output = []
    for index, row in enumerate(rows, start=offset + 1):
        club = relation_name(row.get("clubes"))
        rank_class = " rank-first" if index == 1 else " rank-top" if index <= 3 else ""
        row_class = " position-first" if index == 1 else ""
        output.append(f"""
        <div class="position-row{row_class}">
          <span class="rank{rank_class}">{index}</span>
          {crest_html(club, 'crest sm')}
          <span class="club">{html.escape(club)}</span>
          <strong class="points">{safe_int(row.get('pts'))}</strong>
          <span>{safe_int(row.get('pj'))}</span><span>{safe_int(row.get('pg'))}</span>
          <span>{safe_int(row.get('pe'))}</span><span>{safe_int(row.get('pp'))}</span>
          <span>{safe_int(row.get('gf'))}</span><span>{safe_int(row.get('gc'))}</span>
          <strong class="difference">{safe_int(row.get('dif'))}</strong>
          <span class="form">{form_html(row.get('ultimos_5'))}</span>
        </div>""")
    return "".join(output)


def scorer_rows(rows: Sequence[dict[str, Any]], offset: int) -> str:
    output = []
    for index, row in enumerate(rows, start=offset + 1):
        club = compact_space(row.get("club"))
        output.append(f"""
        <div class="scorer-row">
          <span class="rank">{index:02d}</span>{crest_html(club, 'crest sm')}
          <div class="player"><strong>{html.escape(compact_space(row.get('name')).upper())}</strong><span>{html.escape(club)}</span></div>
          <div class="goals"><strong>{safe_int(row.get('goals'))}</strong><span>GOLES</span></div>
        </div>""")
    return "".join(output)


def pending_note(matches):
    if not matches:
        return ""
    lines = []
    for match in matches:
        local = html.escape(relation_name(match.get("local")))
        visitor = html.escape(relation_name(match.get("visitante")))
        lines.append(f"<div>Fecha {safe_int(match['fecha_id'])} · {local} vs. {visitor}</div>")
    return '<aside class="pending-note"><strong>Partidos pendientes</strong>' + "".join(lines) + '</aside>'


def card_html(
    spec: FormatSpec,
    content_type: str,
    tournament_name: str,
    round_id: int,
    category_label: str,
    date_text: str,
    body: str,
    page_number: int = 1,
    total_pages: int = 1,
) -> str:
    extra_css = """
    .pending-note { border-top:1px solid var(--line); padding-top:10px; font-size:19px; line-height:1.35; }
    .pending-note strong { display:block; color:var(--acid); margin-bottom:4px; }
    .match { min-height:134px; background:rgba(2,26,15,.86); border:1px solid var(--line); display:grid; grid-template-columns:1fr 210px 1fr; align-items:center; padding:15px 22px; }
    .team { min-width:0; display:flex; align-items:center; gap:13px; font-size:22px; font-weight:950; line-height:.95; text-transform:uppercase; }
    .team.local { justify-content:flex-end; text-align:right; } .team.visitor { justify-content:flex-start; }
    .match-center { text-align:center; align-self:stretch; display:flex; flex-direction:column; justify-content:center; align-items:center; border-left:1px solid rgba(255,255,255,.1); border-right:1px solid rgba(255,255,255,.1); }
    .versus,.free { color:var(--acid); font-size:19px; font-weight:1000; letter-spacing:.12em; }
    .score { display:flex; gap:14px; align-items:center; font-size:41px; line-height:.8; } .score span { color:var(--acid); font-size:22px; }
    .timing { margin-top:10px; color:#d4ddd3; font-size:14px; font-weight:900; letter-spacing:.08em; }
    .venue { margin-top:5px; color:var(--acid); font-size:12px; font-weight:850; text-transform:uppercase; }
    .table-head,.position-row { display:grid; grid-template-columns:42px 48px minmax(170px,1fr) 52px repeat(7,43px) 142px; align-items:center; gap:4px; }
    .table-head { min-height:38px; padding:8px 10px; color:#39be73; background:#082817; border:1px solid rgba(36,145,79,.55); font-size:11px; font-weight:950; letter-spacing:.08em; text-align:center; }
    .table-head .club-head { grid-column:1 / 4; text-align:left; }
    .table-head .points-head { color:#f6e77e; }
    .position-row { min-height:{65 if spec.key == 'publicacion' else 70}px; padding:7px 10px; background:rgba(3,43,24,.9); border-bottom:1px solid rgba(29,117,64,.45); font-size:16px; text-align:center; }
    .position-row:nth-child(odd) { background:rgba(8,67,37,.78); }
    .position-row.position-first { background:rgba(230,210,53,.055); }
    .position-row .rank { width:29px; height:29px; display:grid; place-items:center; justify-self:center; border-radius:7px; background:rgba(0,0,0,.13); color:#22c66d; font-size:16px; font-weight:1000; }
    .position-row .rank.rank-first { background:#f5d92f; color:#082310; }
    .position-row .rank.rank-top { background:rgba(25,184,94,.2); color:#54d98d; }
    .position-row .club { min-width:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; text-align:left; font-size:18px; font-weight:950; text-transform:uppercase; }
    .position-row .points { color:#fff6a7; font-size:25px; }
    .position-row .difference { color:#f2f5e9; font-size:16px; }
    .form { display:flex; justify-content:center; gap:4px; }
    .form-dot { width:24px; height:24px; display:grid; place-items:center; border-radius:50%; font-size:11px; font-weight:1000; }
    .form-g { background:rgba(15,153,78,.28); color:#28d979; }
    .form-p { background:rgba(194,67,49,.27); color:#f17868; }
    .form-e { background:rgba(191,158,16,.28); color:#f0d34a; }
    .form-empty { color:#39754e; }
    .scorer-row { min-height:82px; padding:10px 16px; display:grid; grid-template-columns:50px 58px minmax(0,1fr) 90px; gap:12px; align-items:center; background:rgba(2,26,15,.88); border-top:1px solid rgba(217,255,63,.16); }
    .scorer-row:nth-child(odd) { background:rgba(12,65,38,.8); }
    .scorer-row .rank { color:var(--acid); font-size:20px; font-weight:950; }
    .player { min-width:0; display:flex; flex-direction:column; } .player strong { font-size:22px; line-height:1; } .player span { margin-top:5px; color:#aebba9; font-size:14px; font-weight:800; text-transform:uppercase; }
    .goals { text-align:center; border-left:1px solid var(--line); } .goals strong { display:block; color:var(--acid); font-size:35px; line-height:.9; } .goals span { font-size:11px; font-weight:950; letter-spacing:.1em; }
    """
    page_label = f"{page_number:02d}/{total_pages:02d}" if total_pages > 1 else ""
    footer_markup = f'<footer class="footer footer-page"><span class="page">{page_label}</span></footer>' if page_label else ""
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>{shared_css(spec)}{extra_css}</style></head>
    <body><main class="sheet">
      <header class="brand"><div class="brand-mark"><i class="brand-dot"></i><span class="brand-name">Liga de Lincoln</span></div><span class="site">ligadelincoln.com</span></header>
      <section class="hero"><div><div class="kicker">{html.escape(tournament_name)}</div><h1>{page_title(content_type)}</h1></div><div class="round"><span>Fecha</span><strong>{round_id:02d}</strong></div></section>
      <div class="meta"><span class="category-title">{html.escape(category_label)}</span><span class="date-range">{html.escape(date_text)}</span></div>
      <section class="content">{body or '<div class="empty">Todavía no hay información disponible</div>'}</section>
      {footer_markup}
    </main></body></html>"""


def cover_html(spec: FormatSpec, content_type: str, tournament_name: str, round_id: int, date_text: str) -> str:
    labels = {
        "fixture": ("Agenda", "TODO LO QUE TENÉS QUE SABER ANTES DE LA FECHA"),
        "resultados": ("Marcadores", "TODOS LOS RESULTADOS DE LA JORNADA"),
        "posiciones": ("Así están", "LAS TABLAS ACTUALIZADAS, DIVISIÓN POR DIVISIÓN"),
        "goleadores": ("Los que mandan", "RANKING DE GOLEADORES DE PRIMERA DIVISIÓN"),
        "todos": ("Guía de la fecha", "FIXTURE · RESULTADOS · POSICIONES · GOLEADORES"),
    }
    title, subtitle = labels[content_type]
    css = shared_css(spec) + """
    .cover { flex:1; display:flex; flex-direction:column; justify-content:center; padding:40px 0; }
    .cover-kicker { color:var(--acid); font-size:22px; font-weight:950; letter-spacing:.24em; text-transform:uppercase; }
    .cover h1 { max-width:900px; margin:22px 0 26px; font-size:126px; line-height:.78; letter-spacing:-.06em; }
    .cover-subtitle { max-width:760px; font-size:28px; line-height:1.15; font-weight:900; letter-spacing:.04em; text-transform:uppercase; }
    .cover-round { margin-top:48px; display:flex; align-items:center; gap:24px; }
    .cover-round strong { font-size:120px; line-height:.8; color:var(--acid); }
    .cover-round div { border-left:2px solid var(--line); padding-left:24px; font-size:25px; font-weight:950; text-transform:uppercase; }
    .cover-round span { display:block; color:#b8c7b8; font-size:16px; letter-spacing:.14em; margin-bottom:7px; }
    """
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>{css}</style></head><body><main class="sheet">
    <header class="brand"><div class="brand-mark"><i class="brand-dot"></i><span class="brand-name">Liga de Lincoln</span></div><span class="site">ligadelincoln.com</span></header>
    <section class="cover"><div class="cover-kicker">{html.escape(tournament_name)}</div><h1>{html.escape(title)}</h1><div class="cover-subtitle">{html.escape(subtitle)}</div>
    <div class="cover-round"><strong>{round_id:02d}</strong><div><span>Fecha</span>{html.escape(date_text)}</div></div></section>
    <footer class="footer"><span>Fútbol de nuestra región</span><span><strong>Lincoln</strong></span></footer></main></body></html>"""


class Renderer:
    def __init__(self):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise RuntimeError(
                "Falta Playwright. Instalá scripts/generador-placas/requirements.txt y ejecutá 'playwright install chromium'."
            ) from exc
        self.sync_playwright = sync_playwright

    def render_many(self, cards: Sequence[tuple[str, FormatSpec, str]]) -> None:
        with self.sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                for output_path, spec, markup in cards:
                    path = Path(output_path)
                    path.parent.mkdir(parents=True, exist_ok=True)
                    page = browser.new_page(viewport={"width": spec.width, "height": spec.height})
                    page.set_content(markup, wait_until="load")
                    page.screenshot(path=str(path), animations="disabled")
                    page.close()
                    print(f"  OK {path}")
            finally:
                browser.close()


def rows_for_positions(raw_rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        raw_rows,
        key=lambda row: (-safe_int(row.get("pts")), -safe_int(row.get("dif")), -safe_int(row.get("gf")), identity(relation_name(row.get("clubes")))),
    )


def make_cards(
    data: SocialData,
    tournament: dict[str, Any],
    round_id: int,
    content_type: str,
    categories: Sequence[tuple[str, int, str]],
    specs: Sequence[FormatSpec],
    output_root: Path,
    include_cover: bool = True,
) -> list[tuple[str, FormatSpec, str]]:
    tournament_name = compact_space(tournament.get("nombre")) or compact_space(os.getenv("ACTIVE_TORNEO_NAME")) or "Torneo actual"
    tournament_slug = compact_space(tournament.get("slug")) or slugify(tournament_name)
    matches_by_category = {slug: data.matches(round_id, category_id) for slug, category_id, _ in categories}
    all_matches = [match for matches in matches_by_category.values() for match in matches]
    global_dates = match_dates(all_matches)
    cards: list[tuple[str, FormatSpec, str]] = []

    requested_types = ["fixture", "resultados", "posiciones", "goleadores"] if content_type == "todos" else [content_type]
    pending = {slug: data.pending_matches(category_id, round_id) for slug, category_id, _ in categories} if "posiciones" in requested_types else {}
    for spec in specs:
        format_root = output_root / tournament_slug / f"fecha_{round_id}" / spec.key
        if include_cover:
            cover_path = format_root / f"00-portada-{content_type}.png"
            cards.append((str(cover_path), spec, cover_html(spec, content_type, tournament_name, round_id, global_dates)))

        for selected_type in requested_types:
            if selected_type == "goleadores":
                scorers = data.scorers()
                pages = chunks(scorers, spec.page_rows["goleadores"])
                for page_index, page_rows in enumerate(pages, start=1):
                    body = scorer_rows(page_rows, (page_index - 1) * spec.page_rows["goleadores"])
                    markup = card_html(spec, "goleadores", tournament_name, round_id, "PRIMERA DIVISIÓN", f"ACTUALIZADA · FECHA {round_id}", body, page_index, len(pages))
                    path = format_root / "goleadores" / f"goleadores-primera-{page_index:02d}.png"
                    cards.append((str(path), spec, markup))
                continue

            for slug, category_id, category_label in categories:
                if selected_type in {"fixture", "resultados"}:
                    raw_rows = matches_by_category[slug]
                    if selected_type == "resultados":
                        raw_rows = [
                            row
                            for row in raw_rows
                            if row.get("estado") == "jugado"
                            and row.get("visitante_id")
                            and row.get("goles_local") is not None
                            and row.get("goles_visitante") is not None
                        ]
                    page_size = spec.page_rows[selected_type]
                    pages = chunks(raw_rows, page_size)
                    for page_index, page_rows in enumerate(pages, start=1):
                        body = fixture_rows(page_rows, results=selected_type == "resultados")
                        markup = card_html(spec, selected_type, tournament_name, round_id, category_label, match_dates(raw_rows), body, page_index, len(pages))
                        path = format_root / selected_type / f"{selected_type}-{slug}-{page_index:02d}.png"
                        cards.append((str(path), spec, markup))
                elif selected_type == "posiciones":
                    raw_rows = rows_for_positions(data.positions(category_id))
                    page_size = spec.page_rows["posiciones"]
                    pages = chunks(raw_rows, page_size)
                    notes = chunks(pending[slug], 4)
                    total = max(len(pages), len(notes))
                    for index in range(total):
                        page_index = index + 1
                        page_rows = pages[index] if index < len(pages) else []
                        header = '<div class="table-head"><span class="club-head">POSICIÓN / CLUB</span><span class="points-head">PTS</span><span>PJ</span><span>PG</span><span>PE</span><span>PP</span><span>GF</span><span>GC</span><span>DIF</span><span>FORMA</span></div>'
                        body = header + positions_rows(page_rows, index * page_size) if page_rows else ""
                        if index < len(notes):
                            body += pending_note(notes[index])
                        markup = card_html(spec, "posiciones", tournament_name, round_id, category_label, f"ACTUALIZADA · FECHA {round_id}", body, page_index, total)
                        path = format_root / "posiciones" / f"posiciones-{slug}-{page_index:02d}.png"
                        cards.append((str(path), spec, markup))
    return cards


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Genera contenido social de la Liga de Lincoln")
    parser.add_argument("--tipo", choices=CONTENT_TYPES, default="todos", help="Contenido a generar")
    parser.add_argument("--formato", choices=("publicacion", "historia", "ambos"), default="ambos")
    parser.add_argument("--torneo-id", type=int, default=None, help="ID de torneo; usa ACTIVE_TORNEO_ID si se omite")
    parser.add_argument("--fecha", type=int, required=True, help="Número de fecha")
    parser.add_argument("--categoria", choices=tuple(CATEGORIES), default=None, help="Una división; por defecto todas")
    parser.add_argument("--sin-portada", action="store_true", help="No generar portada del carrusel")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--dry-run", action="store_true", help="Consulta datos y muestra archivos sin renderizarlos")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.fecha <= 0:
        raise ValueError("--fecha debe ser un entero positivo")
    tournament_id = positive_tournament_id(args.torneo_id or os.getenv("ACTIVE_TORNEO_ID"))
    url = compact_space(os.getenv("SUPABASE_URL"))
    key = compact_space(os.getenv("SUPABASE_KEY"))
    if not url or not key:
        raise RuntimeError("Faltan SUPABASE_URL o SUPABASE_KEY en backend/.env")

    data = SocialData(create_client(url, key), tournament_id)
    tournament = data.tournament()
    cards = make_cards(
        data=data,
        tournament=tournament,
        round_id=args.fecha,
        content_type=args.tipo,
        categories=category_selection(args.categoria),
        specs=format_selection(args.formato),
        output_root=args.output_dir.resolve(),
        include_cover=not args.sin_portada,
    )

    print(f"Contenido: {args.tipo} · torneo {tournament_id} ({tournament.get('nombre')}) · fecha {args.fecha}")
    print(f"Formatos: {', '.join(spec.label for spec in format_selection(args.formato))}")
    print(f"Placas planificadas: {len(cards)}")
    if args.dry_run:
        for path, _, _ in cards:
            print(f"  - {path}")
        return 0

    Renderer().render_many(cards)
    manifest = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "tournament_id": tournament_id,
        "tournament": tournament.get("nombre"),
        "round": args.fecha,
        "content_type": args.tipo,
        "formats": [spec.key for spec in format_selection(args.formato)],
        "files": [path for path, _, _ in cards],
    }
    manifest_path = args.output_dir.resolve() / (tournament.get("slug") or slugify(tournament.get("nombre"))) / f"fecha_{args.fecha}" / f"manifest-{args.tipo}.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Listo: {len(cards)} placas · manifiesto {manifest_path}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
