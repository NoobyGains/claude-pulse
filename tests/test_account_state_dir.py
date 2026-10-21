"""Per-account state: a second CLAUDE_CONFIG_DIR stops sharing the usage cache.

The default account (~/.claude) keeps today's paths, so nothing moves for a
single-account user. Shared files (config, providers, teams, exchange rate)
stay shared.

Run: ``python -m unittest tests.test_account_state_dir``
"""
import io
import json
import os
import sys
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
from provider_fixtures import ProviderSandbox, cs  # noqa: E402


class AccountStateDirTest(unittest.TestCase):
    def setUp(self):
        self.sb = ProviderSandbox(self)
        self.sb.claude_dir(".claude")
        self.b = self.sb.claude_dir(".claude-b")

    def test_default_account_keeps_shared_paths(self):
        self.assertEqual(cs.get_account_state_dir(), self.sb.state)
        self.assertEqual(cs.get_cache_path(), self.sb.state / "cache.json")
        # an explicit CLAUDE_CONFIG_DIR that *is* ~/.claude changes nothing
        self.sb.set_active(str(self.sb.home / ".claude") + os.sep)
        self.assertEqual(cs.get_account_state_dir(), self.sb.state)
        self.sb.set_active("   ")
        self.assertEqual(cs.get_account_state_dir(), self.sb.state)

    def test_second_account_gets_own_dir(self):
        self.sb.set_active(self.b)
        d = cs.get_account_state_dir()
        self.assertEqual(d.parent, self.sb.state / "accounts")
        self.assertRegex(d.name, r"^claude-b-[0-9a-f]{8}$")
        self.assertTrue(d.is_dir())
        for path in (cs.get_cache_path(), cs._get_history_path(),
                     cs._get_context_history_path(), cs._get_heatmap_path(),
                     cs._get_anim_state_path(), cs._get_sessions_dir()):
            self.assertEqual(Path(path).parent, d, path)

    def test_same_basename_different_parents(self):
        one = self.sb.root / "a" / "work"
        two = self.sb.root / "b" / "work"
        one.mkdir(parents=True)
        two.mkdir(parents=True)
        self.sb.set_active(one)
        d1 = cs.get_account_state_dir()
        self.sb.set_active(two)
        d2 = cs.get_account_state_dir()
        self.assertNotEqual(d1, d2)
        self.assertTrue(d1.name.startswith("work-") and d2.name.startswith("work-"))

    def test_shared_files_stay_shared(self):
        self.sb.set_active(self.b)
        self.assertEqual(cs._team_root(), self.sb.state / "teams")
        self.assertEqual(cs._subagent_root(), self.sb.state / "subagents")
        self.assertEqual(cs._get_hook_state_path(), self.sb.state / "hook_state.json")
        self.assertEqual(cs._get_stats_path(), self.sb.state / "stats.json")
        self.assertNotIn("accounts", str(cs.get_config_path()))

    def test_main_stdin_path_writes_into_account_dir(self):
        self.sb.set_active(self.b)
        now = int(time.time())
        payload = json.dumps({"model": {"display_name": "Fable 5.1"}, "rate_limits": {
            "five_hour": {"used_percentage": 17, "resets_at": now + 3600},
            "seven_day": {"used_percentage": 2, "resets_at": now + 86400}}})
        out = io.BytesIO()

        class _Stdout:
            buffer = out

        with mock.patch.object(cs, "check_for_update", lambda: False), \
                mock.patch.object(cs, "check_claude_code_update", lambda *a, **k: False), \
                mock.patch.object(cs, "fetch_usage", side_effect=AssertionError("network")), \
                mock.patch.object(cs.sys, "argv", ["claude_status.py"]), \
                mock.patch.object(cs.sys, "stdin", io.StringIO(payload)), \
                mock.patch.object(cs.sys, "stdout", _Stdout()):
            cs.main()
        d = cs.get_account_state_dir()
        self.assertTrue((d / "cache.json").exists())
        self.assertTrue((d / "stdin_ctx.json").exists())
        self.assertFalse((self.sb.state / "cache.json").exists())
        self.assertFalse((self.sb.state / "stdin_ctx.json").exists())
        cached = json.loads((d / "cache.json").read_text(encoding="utf-8"))
        self.assertEqual(cached["usage"]["five_hour"]["utilization"], 17.0)


if __name__ == "__main__":
    unittest.main()
