"""Network-free tests for the shared historical official-source core."""

from __future__ import annotations

import copy
import io
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock


BACKEND_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = BACKEND_DIR / "scripts"
FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "historico_sample.html"
sys.path.insert(0, str(SCRIPTS_DIR))

import auditar_torneo_oficial as standings_audit  # noqa: E402
import comparar_partidos_oficiales as match_comparator  # noqa: E402
import fuente_oficial_historica as source  # noqa: E402


CLUBS = {
    "ARGENTINO": 1,
    "EL LINQUEÑO": 8,
    "JUVENTUD UNIDA": 9,
    "CA. PINTENSE": 4,
    "C A PINTENSE": 4,
}
URL = "fixture://octava-apertura"


def fixture_rows() -> list[list[str]]:
    return source.extract_rows(FIXTURE_PATH.read_text(encoding="utf-8"), URL)


def parsed_fixture() -> dict[str, object]:
    return source.parse_official_fixture(fixture_rows(), URL, "octava", CLUBS)


def find_row(rows: list[list[str]], first_cell: str) -> list[str]:
    return next(row for row in rows if row and row[0] == first_cell)


class HistoricalTextAndCatalogTests(unittest.TestCase):
    def test_decodes_cp1252_and_extracts_nested_table_text(self) -> None:
        raw = "<table><tr><td>ÚLTIMOS ENCUENTROS</td><td>EL LINQUEÑO</td></tr></table>".encode(
            "cp1252"
        )

        decoded = source.decode_official_html(raw)
        rows = source.extract_rows(decoded, "cp1252 fixture")

        self.assertIn("ÚLTIMOS ENCUENTROS", decoded)
        self.assertEqual(rows, [["ÚLTIMOS ENCUENTROS", "EL LINQUEÑO"]])

    def test_aliases_and_accents_resolve_to_authoritative_club_ids(self) -> None:
        mapped = source.normalized_club_map(CLUBS)

        self.assertEqual(mapped[source.normalize_team_name("C.A. Pintense")], 4)
        self.assertEqual(mapped[source.normalize_team_name("C A PINTENSE")], 4)
        self.assertEqual(mapped[source.normalize_team_name("El Linqueño")], 8)

    def test_source_catalog_resolves_every_supported_historical_url(self) -> None:
        self.assertEqual(
            source.source_url("apertura-2026", "octava"),
            source.HISTORICAL_DIRECTORY + "z2026apertura8va.html",
        )
        self.assertEqual(
            source.source_url("clausura-2026", "primera"),
            source.HISTORICAL_DIRECTORY + "z2026clausura1ra.html",
        )
        with self.assertRaisesRegex(source.HistoricalSourceError, "no soportada"):
            source.source_url("desconocida", "octava")

    def test_authoritative_identity_loader_does_not_initialize_supabase(self) -> None:
        club_map, category_ids = source.load_authoritative_identities()

        self.assertEqual(club_map["JUVENTUD UNIDA"], 9)
        self.assertEqual(category_ids["octava"], 3)


class HistoricalFixtureParsingTests(unittest.TestCase):
    def test_parses_played_programmed_byes_dates_and_full_fixture_participants(self) -> None:
        official = parsed_fixture()

        self.assertEqual(official["date_numbers"], [1, 2])
        self.assertEqual(len(official["matches"]), 2)
        self.assertEqual(official["matches"][0]["estado"], "jugado")
        self.assertEqual(
            (official["matches"][0]["goles_local"], official["matches"][0]["goles_visitante"]),
            (2, 1),
        )
        self.assertEqual(official["matches"][1]["estado"], "programado")
        self.assertEqual(len(official["byes"]), 2)
        self.assertEqual({row["club_id"] for row in official["participants"]}, {1, 8, 9})

    def test_preserves_octava_juventud_unida_full_fixture_discovery(self) -> None:
        official = parsed_fixture()

        self.assertEqual([row["club_id"] for row in official["final_standings"]], [1, 8])
        self.assertEqual(
            official["final_table_omissions"],
            [{"club_id": 9, "team": "Juventud Unida"}],
        )
        self.assertEqual(official["final_standings_source"], "pre_fixture_final_table")

    def test_valid_libre_placeholders_are_accepted_without_scores(self) -> None:
        official = parsed_fixture()

        self.assertEqual(
            official["byes"],
            [
                {"fecha_id": 1, "dia": "2026-03-10", "club_id": 9, "team": "Juventud Unida"},
                {"fecha_id": 2, "dia": "2026-03-17", "club_id": 1, "team": "ARGENTINO"},
            ],
        )

    def test_extracts_required_audit_standings(self) -> None:
        standings = source.parse_official_standings(fixture_rows(), URL, "octava", CLUBS)

        self.assertEqual(len(standings), 2)
        self.assertEqual(standings[0]["pts"], 3)
        self.assertEqual(standings[1]["gc"], 2)

    def test_absent_final_table_remains_an_explicit_reportable_condition(self) -> None:
        rows = fixture_rows()
        fixture_marker = next(
            index
            for index, row in enumerate(rows)
            if "FIXTURE COMPLETO" in source.folded_text(" | ".join(row))
        )
        fixture_only = rows[fixture_marker:]

        official = source.parse_official_fixture(fixture_only, URL, "octava", CLUBS)

        self.assertEqual(official["final_standings"], [])
        self.assertEqual(official["final_standings_source"], "not_found")
        self.assertEqual(len(official["final_table_omissions"]), 3)


class HistoricalSourceIntegrityTests(unittest.TestCase):
    def test_scored_and_malformed_libre_rows_fail_with_source_evidence(self) -> None:
        cases = (("1", "0"), ("1", ""), ("VS", "-"))
        for left, right in cases:
            with self.subTest(scores=(left, right)):
                rows = fixture_rows()
                bye = next(row for row in rows if len(row) >= 4 and row[3] == "LIBRE")
                bye[1:3] = [left, right]

                with self.assertRaises(source.HistoricalSourceError) as captured:
                    source.parse_official_fixture(rows, URL, "octava", CLUBS)

                message = str(captured.exception)
                self.assertIn("Fila LIBRE", message)
                self.assertIn("Juventud Unida", message)
                self.assertIn(repr(left), message)
                self.assertIn(repr(right), message)
                self.assertIn(URL, message)

    def test_standings_only_club_is_a_blocking_integrity_error(self) -> None:
        rows = fixture_rows()
        fixture_marker = next(
            index
            for index, row in enumerate(rows)
            if "FIXTURE COMPLETO" in source.folded_text(" | ".join(row))
        )
        rows.insert(
            fixture_marker,
            ["CA. PINTENSE", "0", "0", "0", "0", "0", "0", "0"],
        )

        with self.assertRaises(source.HistoricalSourceError) as captured:
            source.parse_official_fixture(rows, URL, "octava", CLUBS)

        message = str(captured.exception)
        self.assertIn("ausentes del fixture completo", message)
        self.assertIn("CA. PINTENSE", message)
        self.assertIn(URL, message)

    def test_unknown_club_fails_closed(self) -> None:
        rows = fixture_rows()
        find_row(rows, "ARGENTINO")[0] = "CLUB DESCONOCIDO"

        with self.assertRaisesRegex(source.HistoricalSourceError, "sin MAPEO_CLUBES"):
            source.parse_official_fixture(rows, URL, "octava", CLUBS)

    def test_malformed_match_score_fails_closed(self) -> None:
        rows = fixture_rows()
        played = next(row for row in rows if len(row) >= 4 and row[1:3] == ["2", "1"])
        played[2] = ""

        with self.assertRaisesRegex(source.HistoricalSourceError, "Resultado oficial malformado"):
            source.parse_official_fixture(rows, URL, "octava", CLUBS)

    def test_malformed_required_standings_row_fails_closed(self) -> None:
        rows = fixture_rows()
        standing = find_row(rows, "ARGENTINO")
        standing.pop()

        with self.assertRaisesRegex(source.HistoricalSourceError, "posiciones oficial malformada"):
            source.parse_official_standings(rows, URL, "octava", CLUBS)

    def test_duplicate_official_match_key_fails_closed(self) -> None:
        rows = fixture_rows()
        played = next(row for row in rows if len(row) >= 4 and row[1:3] == ["2", "1"])
        second_date = next(index for index, row in enumerate(rows) if source.fecha_number(row) == 2)
        rows.insert(second_date, copy.deepcopy(played))

        with self.assertRaisesRegex(source.HistoricalSourceError, "clave oficial duplicada"):
            source.parse_official_fixture(rows, URL, "octava", CLUBS)

    def test_conflicting_result_rows_fail_closed(self) -> None:
        rows = fixture_rows()
        played = next(row for row in rows if len(row) >= 4 and row[1:3] == ["2", "1"])
        conflict = copy.deepcopy(played)
        conflict[1] = "3"
        second_date = next(index for index, row in enumerate(rows) if source.fecha_number(row) == 2)
        rows.insert(second_date, conflict)

        with self.assertRaisesRegex(source.HistoricalSourceError, "resultados oficiales conflictivos"):
            source.parse_official_fixture(rows, URL, "octava", CLUBS)

    def test_missing_fixture_section_fails_closed(self) -> None:
        with self.assertRaisesRegex(source.HistoricalSourceError, "FIXTURE COMPLETO"):
            source.parse_official_fixture([["ÚLTIMOS ENCUENTROS"]], URL, "octava", CLUBS)


class DriftExitContractTests(unittest.TestCase):
    def comparator_category(self, drift: bool = False) -> dict[str, object]:
        return {
            "category": "octava",
            "source_url": URL,
            "official_participants": [{"club_id": 1, "team": "ARGENTINO"}],
            "fixture_dates": [1],
            "official_match_count": 1,
            "final_table_omissions": [],
            "official_scheduled_without_score": 0,
            "official_byes": [],
            "db_bye_row_count": 0,
            "missing_in_db": (
                [
                    {
                        "fecha_id": 1,
                        "local": "ARGENTINO",
                        "visitante": "EL LINQUEÑO",
                    }
                ]
                if drift
                else []
            ),
            "extra_in_db": [],
            "mismatches": [],
            "score_or_state_mismatches": [],
            "date_only_mismatches": [],
            "duplicate_official_keys": [],
            "duplicate_db_keys": [],
            "invalid_db_rows": [],
            "bye_count_difference": 0,
        }

    def standings_category(self, drift: bool = False) -> dict[str, object]:
        return {
            "category": "octava",
            "source_url": URL,
            "official_rows": [{"club_id": 1, "team": "ARGENTINO"}],
            "db_rows": [{"club_id": 1}],
            "differences": (
                [
                    {
                        "club_id": 1,
                        "team": "ARGENTINO",
                        "fields": {"pts": {"official": 3, "db": 2}},
                    }
                ]
                if drift
                else []
            ),
            "missing_in_db": [],
            "extra_in_db": [],
            "duplicate_db_club_ids": [],
            "invalid_db_rows": [],
            "match_inventory": {
                "total": 1,
                "played": 1,
                "scheduled_or_not_played": 0,
                "distinct_played_pairings": 1,
                "official_pj_sum": 2,
                "official_pj_implied_matches": 1.0,
                "official_pj_minus_db_played_twice": 0,
            },
        }

    def test_pure_drift_helpers_distinguish_clean_and_different_reports(self) -> None:
        self.assertFalse(
            match_comparator.report_has_drift({"categories": [self.comparator_category()]})
        )
        self.assertTrue(
            match_comparator.report_has_drift(
                {"categories": [self.comparator_category(drift=True)]}
            )
        )
        self.assertFalse(
            standings_audit.report_has_drift({"categories": [self.standings_category()]})
        )
        self.assertTrue(
            standings_audit.report_has_drift(
                {"categories": [self.standings_category(drift=True)]}
            )
        )

    def test_comparison_command_returns_zero_one_and_two_without_io(self) -> None:
        arguments = [
            "--torneo-id",
            "7",
            "--competencia",
            "apertura-2026",
            "--categoria",
            "octava",
            "--json",
        ]
        dependencies = (object(), CLUBS, {"octava": 3})
        with mock.patch.object(match_comparator, "load_supabase_dependencies", return_value=dependencies), mock.patch.object(
            match_comparator, "audit_category", return_value=self.comparator_category()
        ), redirect_stdout(io.StringIO()):
            self.assertEqual(match_comparator.main(arguments), 0)
        with mock.patch.object(match_comparator, "load_supabase_dependencies", return_value=dependencies), mock.patch.object(
            match_comparator, "audit_category", return_value=self.comparator_category(drift=True)
        ), redirect_stdout(io.StringIO()):
            self.assertEqual(match_comparator.main(arguments), 1)
        with mock.patch.object(
            match_comparator, "load_supabase_dependencies", side_effect=RuntimeError("no credentials")
        ), redirect_stdout(io.StringIO()):
            self.assertEqual(match_comparator.main(arguments), 2)

    def test_audit_command_returns_zero_one_and_two_without_io(self) -> None:
        arguments = [
            "--torneo-id",
            "7",
            "--competencia",
            "apertura-2026",
            "--categoria",
            "octava",
            "--json",
        ]
        dependencies = (object(), CLUBS, {"octava": 3})
        with mock.patch.object(standings_audit, "load_supabase_dependencies", return_value=dependencies), mock.patch.object(
            standings_audit, "audit_category", return_value=self.standings_category()
        ), redirect_stdout(io.StringIO()):
            self.assertEqual(standings_audit.main(arguments), 0)
        with mock.patch.object(standings_audit, "load_supabase_dependencies", return_value=dependencies), mock.patch.object(
            standings_audit, "audit_category", return_value=self.standings_category(drift=True)
        ), redirect_stdout(io.StringIO()):
            self.assertEqual(standings_audit.main(arguments), 1)
        with mock.patch.object(
            standings_audit, "load_supabase_dependencies", side_effect=RuntimeError("no credentials")
        ), redirect_stdout(io.StringIO()):
            self.assertEqual(standings_audit.main(arguments), 2)

    def test_comparison_text_mode_reports_clean_drift_and_operational_failure(self) -> None:
        arguments = [
            "--torneo-id",
            "7",
            "--competencia",
            "apertura-2026",
            "--categoria",
            "octava",
        ]
        dependencies = (object(), CLUBS, {"octava": 3})
        for drift, expected_code in ((False, 0), (True, 1)):
            with self.subTest(drift=drift):
                stdout = io.StringIO()
                with mock.patch.object(
                    match_comparator,
                    "load_supabase_dependencies",
                    return_value=dependencies,
                ), mock.patch.object(
                    match_comparator,
                    "audit_category",
                    return_value=self.comparator_category(drift),
                ), redirect_stdout(stdout):
                    self.assertEqual(match_comparator.main(arguments), expected_code)
                output = stdout.getvalue()
                self.assertIn("Comparación oficial de partidos", output)
                self.assertIn("Modo solo lectura", output)
                if drift:
                    self.assertIn("Faltan en DB (1)", output)

        stderr = io.StringIO()
        with mock.patch.object(
            match_comparator,
            "load_supabase_dependencies",
            side_effect=RuntimeError("no credentials"),
        ), redirect_stderr(stderr):
            self.assertEqual(match_comparator.main(arguments), 2)
        self.assertIn("ERROR: No se pudo completar la comparación", stderr.getvalue())
        self.assertIn("no credentials", stderr.getvalue())

    def test_audit_text_mode_reports_clean_drift_and_operational_failure(self) -> None:
        arguments = [
            "--torneo-id",
            "7",
            "--competencia",
            "apertura-2026",
            "--categoria",
            "octava",
        ]
        dependencies = (object(), CLUBS, {"octava": 3})
        for drift, expected_code in ((False, 0), (True, 1)):
            with self.subTest(drift=drift):
                stdout = io.StringIO()
                with mock.patch.object(
                    standings_audit,
                    "load_supabase_dependencies",
                    return_value=dependencies,
                ), mock.patch.object(
                    standings_audit,
                    "audit_category",
                    return_value=self.standings_category(drift),
                ), redirect_stdout(stdout):
                    self.assertEqual(standings_audit.main(arguments), expected_code)
                output = stdout.getvalue()
                self.assertIn("Auditoría oficial", output)
                self.assertIn("Modo solo lectura", output)
                if drift:
                    self.assertIn("Diferencia ARGENTINO", output)

        stderr = io.StringIO()
        with mock.patch.object(
            standings_audit,
            "load_supabase_dependencies",
            side_effect=RuntimeError("no credentials"),
        ), redirect_stderr(stderr):
            self.assertEqual(standings_audit.main(arguments), 2)
        self.assertIn("ERROR: No se pudo completar la auditoría", stderr.getvalue())
        self.assertIn("no credentials", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
