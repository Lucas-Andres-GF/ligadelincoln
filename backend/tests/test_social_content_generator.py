from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[2]
SCRIPT_PATH = PROJECT_DIR / "scripts" / "generar_contenido_social.py"
PANEL_PATH = PROJECT_DIR / "scripts" / "control-panel" / "app.py"


def load_generator():
    spec = importlib.util.spec_from_file_location("social_content_generator_test", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"No se pudo cargar {SCRIPT_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


social = load_generator()


def load_panel():
    spec = importlib.util.spec_from_file_location("social_control_panel_test", PANEL_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"No se pudo cargar {PANEL_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


panel = load_panel()


class SocialContentGeneratorTests(unittest.TestCase):
    def test_instagram_formats_use_publication_and_story_dimensions(self):
        publication = social.FORMATS["publicacion"]
        story = social.FORMATS["historia"]
        self.assertEqual((publication.width, publication.height), (1080, 1350))
        self.assertEqual((story.width, story.height), (1080, 1920))

    def test_both_format_keeps_publication_first(self):
        self.assertEqual(
            [item.key for item in social.format_selection("ambos")],
            ["publicacion", "historia"],
        )

    def test_scorers_are_aggregated_and_sorted_like_the_frontend(self):
        rows = [
            {"equipo_id": 2, "nombre": "Juan Pérez", "goleo": 1},
            {"equipo_id": 2, "nombre": "  JUAN   PEREZ ", "goleo": 2},
            {"equipo_id": 1, "nombre": "Carlos", "goleo": 3},
            {"equipo_id": 3, "nombre": "Ignorado", "goleo": 0},
        ]
        result = social.build_scorers(rows, {1: "Argentino", 2: "Atl. Pasteur"})
        self.assertEqual([(row["club"], row["goals"]) for row in result], [("Argentino", 3), ("Atl. Pasteur", 3)])

    def test_cards_escape_database_text(self):
        markup = social.card_html(
            social.FORMATS["publicacion"],
            "fixture",
            "Primavera <Verano>",
            2,
            "PRIMERA",
            "DOM 11 OCT",
            "",
        )
        self.assertIn("Primavera &lt;Verano&gt;", markup)
        self.assertNotIn("Primavera <Verano>", markup)
        self.assertNotIn("guardar y compartir", markup.lower())

    def test_output_pages_never_drop_rows(self):
        rows = list(range(25))
        pages = social.chunks(rows, 9)
        self.assertEqual([item for page in pages for item in page], rows)
        self.assertEqual([len(page) for page in pages], [9, 9, 7])

    def test_recent_form_matches_the_web_order(self):
        self.assertEqual(
            social.recent_form('["G", "E", "P", "G", "P", "E"]'),
            ["E", "P", "G", "P", "E"],
        )
        self.assertEqual(social.recent_form("not-json"), [])

    def test_position_rows_highlight_the_leader_and_top_three(self):
        rows = [
            {"clubes": {"nombre": "San Martin"}, "pts": 21, "ultimos_5": ["G"]},
            {"clubes": {"nombre": "Dep. Arenaza"}, "pts": 14, "ultimos_5": ["E"]},
            {"clubes": {"nombre": "Villa Francia"}, "pts": 11, "ultimos_5": ["P"]},
        ]
        markup = social.positions_rows(rows, 0)
        self.assertIn("rank-first", markup)
        self.assertEqual(markup.count("rank-top"), 2)
        self.assertIn("form-g", markup)
        self.assertIn("form-e", markup)
        self.assertIn("form-p", markup)

    def test_panel_exposes_complete_pack_and_both_formats(self):
        action = panel.ACTIONS["crear_pack_social"]
        format_field = next(field for field in action["fields"] if field["name"] == "formato")
        self.assertEqual(format_field["options"], ["ambos", "publicacion", "historia"])
        command = action["command"]({"torneo_id": "3", "fecha": "4", "formato": "ambos"})
        self.assertIn(str(SCRIPT_PATH), command)
        self.assertEqual(command[command.index("--tipo") + 1], "todos")
        self.assertEqual(command[command.index("--formato") + 1], "ambos")


if __name__ == "__main__":
    unittest.main()
