import json
import re
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


class SkillStructureTests(unittest.TestCase):
    def test_skill_frontmatter(self):
        content = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
        self.assertIsNotNone(match)
        frontmatter = yaml.safe_load(match.group(1))
        self.assertEqual(frontmatter["name"], "image-crossword-collage")
        self.assertEqual(frontmatter["license"], "MIT")
        self.assertNotIn("TODO", content)

    def test_interface_metadata_and_example(self):
        interface = yaml.safe_load((ROOT / "agents" / "openai.yaml").read_text(encoding="utf-8"))
        self.assertIn("$image-crossword-collage", interface["interface"]["default_prompt"])
        spec = json.loads((ROOT / "examples" / "example-spec.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(spec["words"]), 6)
        self.assertGreaterEqual(len({word["cluster"] for word in spec["words"]}), 2)


if __name__ == "__main__":
    unittest.main()
