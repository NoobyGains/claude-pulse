"""Provider config validation: garbage in never raises, defaults hold.

Run: ``python -m unittest tests.test_providers_config``
"""
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
from provider_fixtures import ProviderSandbox, cs  # noqa: E402


class NormalizeProvidersTest(unittest.TestCase):
    def test_non_list_values_yield_empty(self):
        for raw in (None, "codex", 42, {"id": "codex"}, True, 3.5):
            self.assertEqual(cs._normalize_providers(raw), [])

    def test_garbage_items_are_dropped_not_raised(self):
        raw = [1, "a", [], [["nested"]], None, {"type": "bogus", "id": "x"},
               {"type": "claude"},                       # claude needs an id
               {"type": "codex", "id": "x" * 40},       # id too long
               {"type": "codex", "id": "bad id!"},      # invalid chars
               {"type": "codex", "id": ":lead"},        # must start alnum
               {"type": "file", "id": "file:k"},        # file without path
               {"type": "codex", "id": 7},
               {"type": "codex", "id": "codex", "label": {"x": 1}, "path": ["no"]}]
        out = cs._normalize_providers(raw)
        self.assertEqual(out, [{"id": "codex", "type": "codex", "enabled": True}])

    def test_label_sanitised_and_capped(self):
        out = cs._normalize_providers([{"type": "codex", "id": "codex",
                                        "label": "\x1b[31mRed\x1b[0m\nlabel " + "x" * 40}])
        label = out[0]["label"]
        self.assertNotIn("\x1b", label)
        self.assertNotIn("\n", label)
        self.assertLessEqual(len(label), 24)
        self.assertTrue(label.startswith("Red label"))

    def test_caps_at_eight_and_dedupes_first_wins(self):
        raw = [{"type": "file", "id": f"file:{i}", "path": f"/x/{i}.json"} for i in range(20)]
        self.assertEqual(len(cs._normalize_providers(raw)), 8)
        out = cs._normalize_providers([
            {"type": "codex", "id": "CODEX", "label": "First"},
            {"type": "codex", "id": "codex", "label": "Second"}])
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["id"], "codex")
        self.assertEqual(out[0]["label"], "First")

    def test_enabled_coercion(self):
        out = cs._normalize_providers([
            {"type": "codex", "id": "a", "enabled": "false"},
            {"type": "codex", "id": "b", "enabled": 0},
            {"type": "codex", "id": "c", "enabled": "yes"},
            {"type": "codex", "id": "d"}])
        self.assertEqual([e["enabled"] for e in out], [False, False, True, True])

    def test_paths_kept_as_written_and_bucket(self):
        out = cs._normalize_providers([
            {"type": "claude", "id": "claude:b", "dir": "~/.claude-b"},
            {"type": "claude", "id": "claude:c", "path": "~/.claude-c"},
            {"type": "gemini", "id": "gemini", "bucket": "3p"},
            {"type": "gemini", "id": "gemini:x", "bucket": "nonsense"}])
        self.assertEqual(out[0]["dir"], "~/.claude-b")
        self.assertEqual(out[1]["dir"], "~/.claude-c")
        self.assertEqual(out[2]["bucket"], "3p")
        self.assertNotIn("bucket", out[3])

    def test_missing_id_defaults_for_singletons(self):
        out = cs._normalize_providers([{"type": "codex"}, {"type": "minimax"}])
        self.assertEqual([e["id"] for e in out], ["codex", "minimax"])


class LoadConfigTest(unittest.TestCase):
    def setUp(self):
        self.sb = ProviderSandbox(self)

    def _write_config(self, data):
        path = cs.get_config_path()
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    def test_defaults(self):
        self._write_config({})
        config = cs.load_config()
        self.assertEqual(config["providers"], [])
        self.assertTrue(config["providers_label_main"])
        self.assertEqual(config["providers_refresh_seconds"], 300)
        self.assertTrue(config["show"]["providers"])
        self.assertEqual(list(cs.DEFAULT_SHOW)[-1], "providers")

    def test_garbage_providers_normalised_on_load(self):
        self._write_config({"providers": [{"type": "codex", "id": "codex"}, "junk", 5]})
        self.assertEqual(cs.load_config()["providers"],
                         [{"id": "codex", "type": "codex", "enabled": True}])
        self._write_config({"providers": "not a list"})
        self.assertEqual(cs.load_config()["providers"], [])

    def test_round_trip_and_hide(self):
        self._write_config({"providers": [{"type": "codex", "id": "codex", "label": "Mine"}]})
        config = cs.load_config()
        with mock.patch.object(cs, "_claude_config_dir", lambda: self.sb.root / "noclaude"):
            cs.save_config(config)
            self.assertEqual(cs.load_config()["providers"][0]["label"], "Mine")
            with mock.patch.object(cs, "utf8_print"):
                cs.cmd_hide("providers")
            self.assertFalse(cs.load_config()["show"]["providers"])

    def test_refresh_seconds_floor(self):
        self.assertEqual(cs._provider_refresh_seconds({"providers_refresh_seconds": 5}), 60)
        self.assertEqual(cs._provider_refresh_seconds({"providers_refresh_seconds": "x"}), 300)
        self.assertEqual(cs._provider_refresh_seconds({}), 300)
        self.assertEqual(cs._provider_refresh_seconds({"providers_refresh_seconds": 900}), 900)


if __name__ == "__main__":
    unittest.main()
