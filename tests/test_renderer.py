import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
RENDERER = ROOT / "scripts" / "render_crossword_collage.py"


class RendererTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.work = Path(self.tempdir.name)
        self.input_a = self.work / "source-a.png"
        self.input_b = self.work / "source-b.png"
        self._make_source(self.input_a, (70, 145, 90), (235, 190, 135))
        self._make_source(self.input_b, (65, 105, 180), (225, 90, 110))
        self.spec = {
            "mode": "auto",
            "grid_rows": 22,
            "words": [
                {"text": "STRIPES", "anchor": [0.48, 0.62], "cluster": "fabric", "weight": 1.3},
                {"text": "SWEATER", "anchor": [0.56, 0.68], "cluster": "fabric", "weight": 1.1},
                {"text": "GREEN", "anchor": [0.16, 0.18], "cluster": "garden", "weight": 1.2},
                {"text": "LEAVES", "anchor": [0.20, 0.30], "cluster": "garden", "weight": 1.0},
                {"text": "CHAIR", "anchor": [0.80, 0.30], "cluster": "room", "weight": 0.9},
                {"text": "INDOOR", "anchor": [0.76, 0.44], "cluster": "room", "weight": 0.8}
            ]
        }

    def tearDown(self):
        self.tempdir.cleanup()

    @staticmethod
    def _make_source(path, background, accent):
        image = Image.new("RGB", (360, 480), background)
        draw = ImageDraw.Draw(image)
        draw.ellipse((90, 80, 290, 290), fill=accent)
        draw.rectangle((115, 265, 275, 450), fill=(235, 232, 220))
        for y in range(280, 440, 22):
            draw.line((115, y, 275, y), fill=(25, 25, 25), width=7)
        image.save(path)

    def _render(self, name, variant=0, inputs=None):
        spec_path = self.work / f"{name}.json"
        spec_path.write_text(json.dumps(self.spec), encoding="utf-8")
        output_path = self.work / f"{name}.png"
        command = [sys.executable, str(RENDERER)]
        for path in inputs or [self.input_a]:
            command.extend(["--input", str(path)])
        command.extend(
            ["--spec", str(spec_path), "--output", str(output_path), "--width", "640", "--variant", str(variant)]
        )
        completed = subprocess.run(command, check=True, capture_output=True, text=True)
        return output_path, json.loads(completed.stdout)

    def test_same_inputs_are_reproducible_and_variant_moves_words(self):
        first_path, first_summary = self._render("first", variant=2)
        second_path, second_summary = self._render("second", variant=2)
        variant_path, variant_summary = self._render("variant", variant=3)

        first_hash = hashlib.sha256(first_path.read_bytes()).hexdigest()
        second_hash = hashlib.sha256(second_path.read_bytes()).hexdigest()
        variant_hash = hashlib.sha256(variant_path.read_bytes()).hexdigest()
        self.assertEqual(first_hash, second_hash)
        self.assertNotEqual(first_hash, variant_hash)
        self.assertEqual(first_summary["placements"], second_summary["placements"])
        self.assertNotEqual(first_summary["placements"], variant_summary["placements"])
        self.assertEqual(first_summary["skipped_words"], [])

    def test_multiple_inputs_select_grid_board(self):
        output, summary = self._render("board", inputs=[self.input_a, self.input_b])
        self.assertTrue(output.is_file())
        self.assertEqual(summary["mode"], "grid-board")
        self.assertEqual(summary["grid_style"], "full")
        self.assertEqual(summary["canvas"], [640, 853])

    def test_random_grid_can_produce_both_reproducible_states(self):
        self.spec["grid_style"] = "random"
        self.spec["grid_chance"] = 0.5
        states = {
            self._render(f"random-{variant}", variant=variant)[1]["grid_style"]
            for variant in range(12)
        }
        self.assertEqual(states, {"full", "none"})

        self.spec["grid_style"] = "full"
        _, full_summary = self._render("forced-full")
        self.spec["grid_style"] = "none"
        _, none_summary = self._render("forced-none")
        self.assertEqual(full_summary["grid_style"], "full")
        self.assertEqual(none_summary["grid_style"], "none")


if __name__ == "__main__":
    unittest.main()
