"""Provider detection and the --providers / --detect-providers CLI.

Detection runs against a fake HOME; the subprocess tests sandbox HOME,
USERPROFILE, CLAUDE_CONFIG_DIR, LOCALAPPDATA and the XDG dirs exactly like
test_install_command.py, so the developer's real accounts are never read.

Run: ``python -m unittest tests.test_provider_detect``
"""
import io
import json
import os
import subprocess
import sys
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
from provider_fixtures import ProviderSandbox, codex_line, cs, iso_z  # noqa: E402

SCRIPT = Path(cs.__file__).resolve()


def _build_home(sb):
    sb.claude_dir(".claude", token="tok-a")
    sb.claude_dir(".claude-b", token="tok-b", tier="default_claude_max_5x")
    sb.claude_dir(".claude-pulse", creds=False)          # not an account
    sb.claude_dir(".claude-old", expires_in=-3600)       # expired token
    (sb.home / ".claude-b" / ".claude.json").write_text(
        json.dumps({"oauthAccount": {"emailAddress": "secret@example.com",
                                     "displayName": "Secret Name"}}), encoding="utf-8")
    sb.accounts_file({"a": {"dir": "~/.claude", "label": "Work", "email": "w@example.com"},
                      "b": {"dir": "~/.claude-b", "label": "Home", "email": "h@example.com"}})
    sb.codex_rollout([codex_line(29.0, 5.0)])
    sb.gemini("antigravity-cli", quota={
        "gemini-5h": {"remaining_fraction": 0.9, "reset_time": iso_z(3600)}},
        email="g@example.com")
    sb.gemini("antigravity-cli-b", quota={}, plan_tier=None, email="g2@example.com",
              mtime=time.time() - 30 * 86400)


class DetectTest(unittest.TestCase):
    def setUp(self):
        self.sb = ProviderSandbox(self)
        _build_home(self.sb)

    def test_detects_accounts_and_files(self):
        with mock.patch.object(cs.shutil, "which", return_value=None):
            items = cs.detect_providers({"providers": []})
        by_id = {i["id"]: i for i in items}
        self.assertEqual(set(by_id), {"claude:default", "claude:b", "claude:old",
                                      "codex", "gemini", "gemini:b"})
        self.assertTrue(by_id["claude:default"]["active"])
        self.assertEqual(by_id["claude:default"]["label"], "Claude (Work)")
        self.assertEqual(by_id["claude:b"]["label"], "Claude (Home)")
        self.assertEqual(by_id["claude:b"]["tier"], "Max 5x")
        self.assertEqual(by_id["claude:b"]["path"], "~/.claude-b")
        self.assertEqual(by_id["claude:old"]["note"], "expired token")
        self.assertEqual(by_id["codex"]["tier"], "Plus")
        self.assertTrue(by_id["gemini"]["enabled"])
        self.assertFalse(by_id["gemini:b"]["enabled"])      # unused for 30 days
        self.assertTrue(by_id["gemini:b"]["note"].startswith("stale"))
        for item in items:
            self.assertEqual(set(item), {"id", "type", "label", "path", "active", "enabled",
                                         "tier", "age_seconds", "note"})
        blob = json.dumps(items)
        self.assertNotIn("@", blob)
        self.assertNotIn("Secret Name", blob)
        self.assertNotIn("tok-", blob)

    def test_minimax_detected_but_off(self):
        with mock.patch.object(cs.shutil, "which", return_value="/usr/bin/mmx"):
            items = {i["id"]: i for i in cs.detect_providers({"providers": []})}
        self.assertFalse(items["minimax"]["enabled"])

    def test_active_from_env_and_configured_state_wins(self):
        self.sb.set_active(self.sb.home / ".claude-b")
        config = {"providers": [{"id": "codex", "type": "codex", "enabled": False, "label": "Mine"},
                                {"id": "file:k", "type": "file", "path": "~/k.json"}]}
        with mock.patch.object(cs.shutil, "which", return_value=None):
            items = {i["id"]: i for i in cs.detect_providers(config)}
        self.assertTrue(items["claude:b"]["active"])
        self.assertFalse(items["claude:default"]["active"])
        self.assertFalse(items["codex"]["enabled"])
        self.assertEqual(items["codex"]["label"], "Mine")
        self.assertEqual(items["file:k"]["note"], "configured; source not found")

    def test_codex_home_env(self):
        other = self.sb.root / "codexhome"
        self.sb.codex_rollout([codex_line(1.0, 1.0)], home=other)
        os.environ["CODEX_HOME"] = str(other)
        with mock.patch.object(cs.shutil, "which", return_value=None):
            items = {i["id"]: i for i in cs.detect_providers({"providers": []})}
        self.assertEqual(items["codex"]["path"], str(other))

    def test_no_accounts_file_defaults(self):
        (self.sb.home / ".claude-accounts.json").unlink()
        cs._ACCOUNT_LABELS_MEMO.clear()
        with mock.patch.object(cs.shutil, "which", return_value=None):
            items = {i["id"]: i for i in cs.detect_providers({"providers": []})}
        self.assertEqual(items["claude:default"]["label"], "Claude")
        self.assertEqual(items["claude:b"]["label"], "Claude (b)")


class SetProvidersTest(unittest.TestCase):
    def setUp(self):
        self.sb = ProviderSandbox(self)
        _build_home(self.sb)
        p = mock.patch.object(cs.shutil, "which", return_value=None)
        p.start()
        self.addCleanup(p.stop)

    def test_enable_disable_label(self):
        config = {"providers": []}
        cs.set_providers(config, enable_ids=["claude:b", "CODEX"])
        ids = [(e["id"], e["enabled"]) for e in config["providers"]]
        self.assertEqual(ids, [("claude:b", True), ("codex", True)])
        self.assertEqual(config["providers"][0]["dir"], "~/.claude-b")
        self.assertEqual(config["providers"][0]["label"], "Claude (Home)")
        cs.set_providers(config, disable_ids=["codex"], labels={"claude:b": "Personal"})
        self.assertFalse(config["providers"][1]["enabled"])
        self.assertEqual(config["providers"][0]["label"], "Personal")
        cs.set_providers(config, labels={"claude:b": ""})
        self.assertNotIn("label", config["providers"][0])

    def test_label_only_adds_disabled(self):
        config = {"providers": []}
        cs.set_providers(config, labels={"gemini": "Ultra"})
        self.assertEqual(config["providers"], [{"id": "gemini", "type": "gemini", "enabled": False,
                                                "label": "Ultra",
                                                "path": "~/.gemini/antigravity-cli"}])

    def test_unknown_id_raises_and_leaves_config_alone(self):
        config = {"providers": [{"id": "codex", "type": "codex"}]}
        before = json.dumps(config)
        with self.assertRaises(ValueError) as ctx:
            cs.set_providers(config, enable_ids=["codex", "kimi"])
        self.assertIn("kimi", str(ctx.exception))
        self.assertEqual(json.dumps(config), before)
        with self.assertRaises(ValueError):
            cs.set_providers(config, enable_ids=["bad id!"])

    def test_max_entries(self):
        config = {"providers": [{"id": f"file:{i}", "type": "file", "path": f"/{i}"} for i in range(8)]}
        with self.assertRaises(ValueError):
            cs.set_providers(config, enable_ids=["codex"])


class CmdProvidersTest(unittest.TestCase):
    def setUp(self):
        self.sb = ProviderSandbox(self)
        _build_home(self.sb)
        for target, value in (("utf8_print", lambda *a, **k: None),
                              ("_claude_config_dir", lambda: self.sb.home / ".claude")):
            p = mock.patch.object(cs, target, value)
            p.start()
            self.addCleanup(p.stop)

    def _providers(self):
        return cs.load_config()["providers"]

    def test_add_file_label_remove(self):
        self.assertEqual(cs.cmd_providers(["add-file", "kimi", "~/kimi.json", "Kimi", "K3"]), 0)
        entry = self._providers()[0]
        self.assertEqual(entry, {"id": "file:kimi", "type": "file", "enabled": True,
                                 "label": "Kimi K3", "path": "~/kimi.json"})
        self.assertEqual(cs.cmd_providers(["label", "file:kimi", "Moonshot"]), 0)
        self.assertEqual(self._providers()[0]["label"], "Moonshot")
        self.assertEqual(cs.cmd_providers(["remove", "file:kimi"]), 0)
        self.assertEqual(self._providers(), [])
        self.assertEqual(cs.cmd_providers(["remove", "file:kimi"]), 1)

    def test_errors_return_nonzero(self):
        self.assertEqual(cs.cmd_providers(["enable", "nothing-here"]), 1)
        self.assertEqual(cs.cmd_providers(["enable"]), 2)
        self.assertEqual(cs.cmd_providers(["frobnicate"]), 2)
        self.assertEqual(cs.cmd_providers(["add-file", "bad id", "/x.json"]), 1)
        self.assertEqual(cs.cmd_providers([]), 0)          # list
        self.assertEqual(cs.cmd_providers(["help"]), 0)

    def test_enable_comma_and_space_separated(self):
        self.assertEqual(cs.cmd_providers(["enable", "codex,claude:b", "gemini"]), 0)
        self.assertEqual([e["id"] for e in self._providers()], ["codex", "claude:b", "gemini"])


class CliSubprocessTest(unittest.TestCase):
    """End to end through the real entry point with every location sandboxed."""

    def setUp(self):
        self.sb = ProviderSandbox(self)
        _build_home(self.sb)
        self.env = dict(os.environ)
        self.env.update({"HOME": str(self.sb.home), "USERPROFILE": str(self.sb.home),
                         "LOCALAPPDATA": str(self.sb.local),
                         "XDG_CACHE_HOME": str(self.sb.root / "xdg-cache"),
                         "XDG_CONFIG_HOME": str(self.sb.root / "xdg-config"),
                         "CLAUDE_CONFIG_DIR": str(self.sb.home / ".claude"),
                         "PYTHONIOENCODING": "utf-8"})
        self.env.pop("HOMEDRIVE", None)
        self.env.pop("HOMEPATH", None)
        self.env.pop("CODEX_HOME", None)

    def _run(self, *args, stdin=None):
        return subprocess.run([sys.executable, str(SCRIPT), *args], env=self.env,
                              capture_output=True, text=True, encoding="utf-8",
                              input=stdin, timeout=60)

    def test_detect_json_then_enable_then_render(self):
        r = self._run("--detect-providers", "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        items = json.loads(r.stdout)
        self.assertIn("claude:b", {i["id"] for i in items})
        self.assertNotIn("@", r.stdout)
        r = self._run("--providers", "enable", "codex,claude:b")
        self.assertEqual(r.returncode, 0, r.stderr)
        r = self._run("--providers", "enable", "nope")
        self.assertEqual(r.returncode, 1)
        cfg_files = list(self.sb.local.rglob("config.json")) + \
            list((self.sb.root / "xdg-config").rglob("config.json"))
        self.assertEqual(len(cfg_files), 1)
        saved = json.loads(cfg_files[0].read_text(encoding="utf-8"))
        self.assertEqual([p["id"] for p in saved["providers"]], ["codex", "claude:b"])
        # No network in the render below: update checks off, and claude:b
        # (a live fake token) gets a fresh cache so it is not fetched.
        saved["show"] = {"update": False, "claude_update": False}
        cfg_files[0].write_text(json.dumps(saved), encoding="utf-8")
        state_root = (self.sb.local if sys.platform == "win32"
                      else self.sb.root / "xdg-cache") / "claude-status" / "providers"
        state_root.mkdir(parents=True, exist_ok=True)
        (state_root / "claude.b.json").write_text(json.dumps({
            "timestamp": time.time(),
            "usage": {"five_hour": {"utilization": 3.0, "resets_at": None}}}), encoding="utf-8")
        now = int(time.time())
        payload = json.dumps({"rate_limits": {
            "five_hour": {"used_percentage": 29, "resets_at": now + 7800},
            "seven_day": {"used_percentage": 5, "resets_at": now + 400000}}})
        r = self._run(stdin=payload)
        self.assertEqual(r.returncode, 0, r.stderr)
        rows = r.stdout.rstrip("\n").split("\n")
        self.assertEqual(len(rows), 3, r.stdout)
        self.assertIn("Claude (Home)", rows[1] + rows[2])


if __name__ == "__main__":
    unittest.main()
