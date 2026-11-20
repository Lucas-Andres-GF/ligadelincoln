from dataclasses import replace
from pathlib import Path
import sys
from unittest import TestCase
from unittest.mock import Mock, call, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import scraper_suspensiones as scraper
from scraper_resultados import FixtureRecord


NOTICE = """
<div class="cajablancayroja100">19-11-26<br>
    En virtud al clima reinante en la región, los encuentros que hoy debían disputarse entre
    C A Pintense y Dep Gral Pinto, en Novena y Octava división, han sido SUSPENDIDOS.
    Se reprogramarán oportunamente.
</div>
"""


class SuspensionTests(TestCase):
    def test_dated_notice_identifies_only_the_listed_divisions(self):
        unrelated = '<div class="cajablancayazul100left">Los árbitros pueden suspender partidos.</div>'
        notices, warnings = scraper.parse_notices(NOTICE + unrelated)
        self.assertEqual(notices, {("2026-11-19", 3, 4, 7), ("2026-11-19", 4, 4, 7)})
        self.assertEqual(warnings, [])

    def test_incomplete_notice_requires_review(self):
        notices, warnings = scraper.parse_notices(
            '<div class="cajablancayroja100">19-11-26<br>Todos los partidos están suspendidos.</div>'
        )
        self.assertFalse(notices)
        self.assertEqual(len(warnings), 1)

    def test_old_notice_clears_the_date_and_skips_rebooked_and_played_matches(self):
        octava = FixtureRecord(579, 3, 3, 4, 7, 9, "2026-11-19", "programado", None, None)
        rebooked = replace(octava, id=1, category_id=4, date="2026-11-25")
        played = replace(octava, id=2, category_id=4, state="jugado", local_goals=1, visitor_goals=0)
        with (
            patch.object(scraper, "fetch_result_html", return_value=NOTICE),
            patch.object(scraper, "read_fixture_inventory", return_value=[octava, rebooked, played]),
            patch.object(scraper, "argentina_today", return_value="2026-11-20"),
            patch("config.supabase", new_callable=Mock) as client,
        ):
            table = client.table.return_value
            update = Mock()
            table.update.return_value = update
            update.eq.return_value = update
            update.lt.return_value = update
            update.is_.return_value = update
            update.execute.return_value.data = [{"id": 579}]

            self.assertEqual(scraper.main(["--torneo-id", "3", "--execute"]), 0)

        awaiting_date = {"estado": "A reprogramar", "dia": None, "hora": None}
        self.assertEqual(table.update.call_args_list, [call(awaiting_date), call(awaiting_date)])
        update.lt.assert_called_once_with("dia", "2026-11-20")
        update.eq.assert_any_call("estado", "suspendido")
        update.eq.assert_any_call("id", 579)
        update.eq.assert_any_call("dia", "2026-11-19")
        update.eq.assert_any_call("estado", "programado")

    def test_dated_suspension_rolls_over_without_a_notice(self):
        with (
            patch.object(scraper, "fetch_result_html", return_value="<html></html>"),
            patch.object(scraper, "argentina_today", return_value="2026-11-20"),
            patch("config.supabase", new_callable=Mock) as client,
        ):
            update = client.table.return_value.update.return_value
            update.eq.return_value = update
            update.lt.return_value = update
            update.is_.return_value = update
            update.execute.return_value.data = [{"id": 579}]

            self.assertEqual(scraper.main(["--torneo-id", "3", "--execute"]), 0)

        client.table.return_value.update.assert_called_once_with(
            {"estado": "A reprogramar", "dia": None, "hora": None}
        )
        update.lt.assert_called_once_with("dia", "2026-11-20")
