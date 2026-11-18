"""Preview or archive official Tribunal bulletins."""

import argparse
from datetime import date
from hashlib import sha256
import json
from pathlib import Path
import re
import unicodedata
from urllib.parse import urljoin

from bs4 import BeautifulSoup
import requests


INDEX_URL = "https://www.ligaamateurdedeportes.com.ar/sanciones.html"
LINK_PATTERN = re.compile(r"sanc(?: |%20)indiv/sanciones(\d+)\.html", re.I)
HEADER = ("FUNCION", "APELLIDO Y NOMBRE", "CLUB", "DIVISION", "CANT", "SANCION")
MONTHS = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
          "septiembre", "octubre", "noviembre", "diciembre")


def normalize(text):
    return "".join(c for c in unicodedata.normalize("NFD", text.upper())
                   if not unicodedata.combining(c))


def read_html(session, url):
    response = session.get(url, timeout=15)
    response.raise_for_status()
    doc = BeautifulSoup(response.content, "html.parser")
    return doc, response.content.decode(doc.original_encoding or "utf-8")


def parse_date(label):
    match = re.fullmatch(r"(\d{1,2}) de (\w+) de (\d{4})", label.lower())
    if not match or match[2] not in MONTHS:
        raise ValueError(f"Fecha de boletín inesperada: {label!r}")
    return date(int(match[3]), MONTHS.index(match[2]) + 1, int(match[1])).isoformat()


def parse_resolutions(document):
    for tr in document.find_all("tr"):
        cells = tuple(normalize(" ".join(cell.stripped_strings))
                      for cell in tr.find_all(["td", "th"], recursive=False))
        if cells == HEADER:
            table = tr.find_parent("table")
            break
    else:
        raise ValueError("No se encontró la tabla de resoluciones.")
    entries = []
    for row in table.find_all("tr"):
        if row.find_parent("table") is not table:
            continue
        values = [" ".join(" ".join(cell.stripped_strings).split())
                  for cell in row.find_all(["td", "th"], recursive=False)]
        if not any(values) or tuple(map(normalize, values)) == HEADER:
            continue
        if len(values) != len(HEADER):
            if len(values) <= 2 and normalize(values[0]).startswith("RESOLUCIONES DEL TRIBUNAL"):
                continue
            raise ValueError("Fila inesperada en la tabla de resoluciones.")
        role, name, club, division, quantity, sanction = values
        if not all((role, name, club, division, sanction)):
            raise ValueError("Resolución incompleta.")
        if quantity.isdigit() and normalize(sanction) in {"FECHA/S", "FECHA", "FECHAS"}:
            sanction = f"{quantity} fecha" if int(quantity) == 1 else f"{quantity} fechas"
        else:
            sanction = " ".join(part for part in (quantity, sanction) if part)
        entries.append(dict(funcion=role, nombre=name, club=club, division=normalize(division),
                            sancion=sanction))
    if not entries:
        raise ValueError("La tabla de resoluciones está vacía.")
    return entries


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=12, choices=range(1, 51), metavar="1–50")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--preview-json", type=Path)
    mode.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    with requests.Session() as session:
        index, _ = read_html(session, INDEX_URL)
        links = {}
        for anchor in index.find_all("a", href=True):
            href = anchor["href"].strip()
            match = LINK_PATTERN.fullmatch(href)
            if match:
                links[int(match[1])] = (" ".join(anchor.get_text(" ", strip=True).split()), urljoin(INDEX_URL, href.replace(" ", "%20")))
        if not links:
            raise ValueError("No se encontraron enlaces a boletines en el índice.")
        bulletins = []
        for number in sorted(links, reverse=True)[:args.limit]:
            title, url = links[number]
            document, html = read_html(session, url)
            entries = parse_resolutions(document)
            bulletin = dict(numero=number, fecha=parse_date(title), fuente=url, resoluciones=entries)
            if args.execute:
                fingerprint = json.dumps(bulletin, ensure_ascii=False, sort_keys=True)
                bulletin.update(html=html, sha256=sha256(fingerprint.encode("utf-8")).hexdigest())
            bulletins.append(bulletin)
            print(f"{title}: {len(entries)} resoluciones")
    if args.preview_json:
        args.preview_json.parent.mkdir(parents=True, exist_ok=True)
        args.preview_json.write_text(json.dumps(bulletins, ensure_ascii=False), encoding="utf-8")
    if args.execute:
        from config import supabase

        response = supabase.rpc("archivar_boletines_tribunal", {"p_boletines": bulletins}).execute()
        print(f"Versiones nuevas archivadas: {response.data}")


if __name__ == "__main__":
    main()
