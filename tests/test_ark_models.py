import base64
import importlib.util
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("ark_models", ROOT / "scripts" / "ark_models.py")
ark = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ark)


class ArkModelsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.work = Path(self.temp.name)
        self.source = self.work / "source.jpg"
        exif = Image.Exif()
        exif[270] = "private image metadata"
        Image.new("RGB", (64, 96), "green").save(self.source, exif=exif)
        self.config = ark.load_config()
        # Never read real shared credential files during unit tests.
        self.config["analysis"].update(api_key_env="DOUBAO_API_KEY",
                                      api_key_file=".env.doubao.local", api_key_file_format="dotenv")
        self.config["image_generation"].update(api_key_env="SEEDREAM_API_KEY",
                                              api_key_file=".env.seedream.local", api_key_file_format="dotenv")
        root_patch = patch.object(ark, "ROOT", self.work)
        root_patch.start()
        self.addCleanup(root_patch.stop)
        env_patch = patch.dict(os.environ, {"DOUBAO_API_KEY": "", "SEEDREAM_API_KEY": ""})
        env_patch.start()
        self.addCleanup(env_patch.stop)
        self.plan = {"words": [
            {"text": text, "cluster": "objects" if i < 3 else "room",
             "evidence": "synthetic visible object", "anchor": [0.2, 0.3]}
            for i, text in enumerate(("POTS", "FLOWER", "LEAVES", "WINDOW", "FRAME", "GREEN"))
        ], "protect_regions": [[0.2, 0.3, 0.2, 0.2]]}

    def tearDown(self):
        self.temp.cleanup()

    def test_requested_endpoints_and_base_url(self):
        self.assertEqual(self.config["analysis"]["endpoint"], "ep-20260914174304-5d8v2")
        self.assertEqual(self.config["image_generation"]["endpoint"], "ep-20260914155654-cjmcd")
        self.assertEqual(self.config["base_url"], "https://ark.cn-beijing.volces.com/api/v3")
        actual = ark.load_config()
        self.assertEqual(actual["analysis"]["api_key_env"], "ARK_TEXT_API_KEY")
        self.assertEqual(actual["image_generation"]["api_key_env"], "ARK_IMAGE_API_KEY")
        self.assertEqual(actual["analysis"]["api_key_file_format"], "raw_key_text")
        self.assertEqual(actual["image_generation"]["api_key_file_format"], "raw_key_text")

    def test_preview_strips_exif_and_bounds_size(self):
        exif = Image.Exif()
        exif[270] = "private image metadata"
        Image.new("RGB", (3000, 100), "blue").save(self.source, exif=exif)
        with Image.open(self.source) as original:
            self.assertTrue(original.getexif())
        preview = ark.image_data_url(self.source)
        self.assertTrue(preview.startswith("data:image/jpeg;base64,"))
        with Image.open(io.BytesIO(base64.b64decode(preview.split(",", 1)[1]))) as image:
            self.assertLessEqual(max(image.size), 2048)
            self.assertEqual(len(image.getexif()), 0)

    def test_analysis_sends_doubao_model_and_preserves_random_default(self):
        response = {"choices": [{"finish_reason": "stop", "message": {
            "content": "```json\n" + json.dumps(self.plan) + "\n```"}}]}
        with patch.object(ark, "post_json", return_value=response) as call:
            plan = ark.analyze(self.config, [self.source], variant=7)
        self.assertEqual(call.call_args.args[1], "/chat/completions")
        payload = call.call_args.args[2]
        self.assertEqual(payload["model"], self.config["analysis"]["endpoint"])
        self.assertEqual(payload["messages"][1]["content"][1]["type"], "image_url")
        self.assertEqual(plan["variant"], 7)
        self.assertEqual(plan["grid_style"], "random")
        self.assertEqual(plan["mode"], "photo-overlay")
        with patch.object(ark, "post_json", return_value=response):
            board = ark.analyze(self.config, [self.source, self.source], grid_style="full")
        self.assertEqual(board["mode"], "grid-board")
        self.assertEqual(board["grid_style"], "full")

    def test_invalid_model_plans_are_rejected(self):
        self.plan["words"][0]["anchor"] = [float("nan"), 0.5]
        with self.assertRaises(ValueError):
            ark.validate_plan(self.plan)
        self.plan["words"][0]["anchor"] = [0.2, 0.5]
        self.plan["words"][0]["evidence"] = ""
        with self.assertRaises(ValueError):
            ark.validate_plan(self.plan)
        with patch.object(ark, "post_json", return_value={"choices": [{
                "finish_reason": "length", "message": {"content": json.dumps(self.plan)}}]}):
            with self.assertRaises(ValueError):
                ark.analyze(self.config, [self.source])

    def test_generation_sends_seedream_and_writes_real_png(self):
        buffer = io.BytesIO()
        Image.new("RGB", (40, 60), "pink").save(buffer, format="JPEG")
        response = {"data": [{"b64_json": base64.b64encode(buffer.getvalue()).decode()}]}
        output = self.work / "generated.png"
        with patch.object(ark, "post_json", return_value=response) as call:
            ark.generate(self.config, [self.source], "Preserve the subject. No text.", output)
        payload = call.call_args.args[2]
        self.assertEqual(call.call_args.args[1], "/images/generations")
        self.assertEqual(payload["model"], self.config["image_generation"]["endpoint"])
        self.assertEqual(payload["response_format"], "b64_json")
        self.assertEqual(payload["sequential_image_generation"], "disabled")
        with Image.open(output) as image:
            self.assertEqual(image.format, "PNG")
        with patch.object(ark, "post_json", return_value={"data": [{"url": "https://example.com"}]}):
            with self.assertRaises(ValueError):
                ark.generate(self.config, [self.source], "No text.", self.work / "bad.png")

    def test_auth_http_errors_and_no_automatic_retry(self):
        with patch.dict(os.environ, {"DOUBAO_API_KEY": ""}), patch.object(ark, "build_opener") as opener:
            with self.assertRaises(ValueError):
                ark.post_json(self.config, "/chat/completions", {})
            opener.assert_not_called()
        with patch.dict(os.environ, {"DOUBAO_API_KEY": "synthetic-test-key"}), \
                patch.object(ark, "build_opener") as opener:
            opener.return_value.open.side_effect = HTTPError("https://example.com", 429, "", {}, None)
            with self.assertRaisesRegex(RuntimeError, "HTTP 429"):
                ark.post_json(self.config, "/chat/completions", {})
            opener.return_value.open.assert_called_once()
            request = opener.return_value.open.call_args.args[0]
            self.assertEqual(request.get_header("Authorization"), "Bearer synthetic-test-key")
        self.assertIsNone(ark.NoRedirect().redirect_request(None, None, 302, "", {}, "https://example.com"))

    def test_two_local_keys_are_routed_separately(self):
        (self.work / ".env.doubao.local").write_text(
            '# local only\nDOUBAO_API_KEY="synthetic-doubao-key"\n', encoding="utf-8")
        (self.work / ".env.seedream.local").write_text(
            "SEEDREAM_API_KEY='synthetic-seedream-key=tail'\n", encoding="utf-8")
        for route, expected in (("/chat/completions", "synthetic-doubao-key"),
                                ("/images/generations", "synthetic-seedream-key=tail")):
            with patch.object(ark, "build_opener") as opener:
                opener.return_value.open.side_effect = HTTPError("https://example.com", 429, "", {}, None)
                with self.assertRaises(RuntimeError):
                    ark.post_json(self.config, route, {})
                request = opener.return_value.open.call_args.args[0]
                self.assertEqual(request.get_header("Authorization"), f"Bearer {expected}")
        with patch.dict(os.environ, {"DOUBAO_API_KEY": "synthetic-environment-override"}):
            self.assertEqual(ark.get_api_key(self.config, "analysis"), "synthetic-environment-override")
            self.assertEqual(ark.get_api_key(self.config, "image_generation"), "synthetic-seedream-key=tail")

    def test_missing_model_key_does_not_use_other_or_shared_key(self):
        (self.work / ".env.doubao.local").write_text("DOUBAO_API_KEY=synthetic-doubao-key\n", encoding="utf-8")
        with patch.dict(os.environ, {"ARK_API_KEY": "synthetic-shared-key"}):
            self.assertEqual(ark.get_api_key(self.config, "analysis"), "synthetic-doubao-key")
            with self.assertRaises(ValueError):
                ark.get_api_key(self.config, "image_generation")
            with patch.object(ark, "build_opener") as opener:
                with self.assertRaises(ValueError):
                    ark.post_json(self.config, "/images/generations", {})
                opener.assert_not_called()

    def test_check_keys_does_not_print_secrets_or_send_requests(self):
        (self.work / ".env.doubao.local").write_text("DOUBAO_API_KEY=synthetic-doubao-key\n", encoding="utf-8")
        with patch.object(ark, "load_config", return_value=self.config), \
                patch.object(ark, "post_json") as call, patch("sys.stdout", new_callable=io.StringIO) as stdout:
            status = ark.main(["check-keys"])
        self.assertEqual(status, 0)
        call.assert_not_called()
        self.assertEqual(json.loads(stdout.getvalue()), {"analysis": True, "image_generation": False})
        self.assertNotIn("synthetic-doubao-key", stdout.getvalue())

    def test_shared_raw_key_files_and_role_environment_precedence(self):
        text_key = self.work / "text-api-key.txt"
        image_key = self.work / "image-api-key.txt"
        text_key.write_text("synthetic-text-key\n", encoding="utf-8")
        image_key.write_text("synthetic-image-key\n", encoding="utf-8")
        self.config["analysis"].update(api_key_env="ARK_TEXT_API_KEY",
                                      api_key_file=str(text_key), api_key_file_format="raw_key_text")
        self.config["image_generation"].update(api_key_env="ARK_IMAGE_API_KEY",
                                              api_key_file=str(image_key), api_key_file_format="raw_key_text")
        with patch.dict(os.environ, {"ARK_TEXT_API_KEY": "", "ARK_IMAGE_API_KEY": ""}):
            self.assertEqual(ark.get_api_key(self.config, "analysis"), "synthetic-text-key")
            self.assertEqual(ark.get_api_key(self.config, "image_generation"), "synthetic-image-key")
        with patch.dict(os.environ, {"ARK_TEXT_API_KEY": "synthetic-text-override", "ARK_IMAGE_API_KEY": ""}):
            self.assertEqual(ark.get_api_key(self.config, "analysis"), "synthetic-text-override")
            self.assertEqual(ark.get_api_key(self.config, "image_generation"), "synthetic-image-key")
        text_key.write_text("first\nsecond\n", encoding="utf-8")
        with patch.dict(os.environ, {"ARK_TEXT_API_KEY": ""}):
            with self.assertRaises(ValueError):
                ark.get_api_key(self.config, "analysis")

    def test_blank_duplicate_and_control_character_keys_are_refused(self):
        file = self.work / ".env.doubao.local"
        for content in ("DOUBAO_API_KEY=\n", "DOUBAO_API_KEY=''\n",
                        "DOUBAO_API_KEY=one\nDOUBAO_API_KEY=two\n",
                        "DOUBAO_API_KEY=invalid\tkey\n"):
            file.write_text(content, encoding="utf-8")
            with self.assertRaises(ValueError):
                ark.get_api_key(self.config, "analysis")

    def test_cli_refuses_existing_output_before_model_call(self):
        output = self.work / "existing.json"
        output.write_text("preserve", encoding="utf-8")
        with patch.object(ark, "post_json") as call, patch("sys.stderr", new_callable=io.StringIO):
            status = ark.main(["analyze", "--input", str(self.source), "--output", str(output)])
        self.assertEqual(status, 1)
        call.assert_not_called()
        self.assertEqual(output.read_text(), "preserve")

    def test_config_rejects_untrusted_auth_destination(self):
        self.config["base_url"] = "https://example.com/api/v3"
        path = self.work / "bad-config.json"
        path.write_text(json.dumps(self.config), encoding="utf-8")
        with self.assertRaises(ValueError):
            ark.load_config(path)


if __name__ == "__main__":
    unittest.main()
