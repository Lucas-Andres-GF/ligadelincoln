from pathlib import Path
import sys
from unittest import TestCase

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from scraper_goleadores import parse_report


def report_html(*, total="7", divisions=("Primera", "Séptima", "Octava", "Novena", "Décima")):
    sections = []
    for division in divisions:
        club = "CAEL" if division == "Novena" else "C A Pintense"
        sections.append(f"""
          <tr><th>{division} División</th></tr>
          <tr><th>APELLIDO Y NOMBRE</th><th>CLUB</th><th>F1</th><th>TOT</th></tr>
          <tr><td>Jugador de prueba</td><td>{club}</td><td>1</td><td>{total}</td></tr>
        """)
    return f"""
      <table>
        <tr><td>Actualizado al: Viernes, 20 Noviembre, 2026 11:43</td></tr>
        <tr><td>GOLEADORES DEL TORNEO PRIMAVERA/VERANO 2026</td></tr>
        <tr><td><table>{''.join(sections)}</table></td></tr>
      </table>
    """


class OfficialScorersTests(TestCase):
    def test_uses_tot_and_preserves_divisions_and_clubs(self):
        tournament, issued_at, rows = parse_report(report_html())
        self.assertEqual(tournament, "PRIMAVERA VERANO 2026")
        self.assertEqual(issued_at, "2026-11-20T11:43:00-03:00")
        self.assertEqual([row["goles"] for row in rows], [7] * 5)
        self.assertEqual([row["categoria_id"] for row in rows], [1, 2, 3, 4, 5])
        self.assertEqual(rows[3]["club_id"], 12)

    def test_rejects_incomplete_report(self):
        with self.assertRaisesRegex(ValueError, "cinco divisiones"):
            parse_report(report_html(divisions=("Primera", "Novena")))

    def test_rejects_unreadable_total(self):
        with self.assertRaisesRegex(ValueError, "total inválido"):
            parse_report(report_html(total="?"))
