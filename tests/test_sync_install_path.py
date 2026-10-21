"""``--sync-install-path`` keeps a marketplace install alive across updates.

Issue #54: a plugin installed from the marketplace lives in
``~/.claude/plugins/cache/<marketplace>/usage-pulse/<version>/``. The status
line is registered with that versioned path, Claude Code removes the old
folder a fortnight after an update, and the bar disappears. The plugin's
SessionStart hook runs ``--sync-install-path`` from the current folder: when
settings.json still runs the script from another plugin folder, everything is
re-registered from here. That includes the ``claude-pulse`` folders from
before the 3.5.0 rename. A git or manual install is never touched.

Run: ``python tests/test_sync_install_path.py``
"""
import io
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import claude_status as cs  # noqa: E402

PULSE_MD = REPO_ROOT / "commands" / "pulse.md"


class ParsingTest(unittest.TestCase):
    def test_script_path_is_found_in_every_command_form(self):
        cases = {
            '"$HOME/AppData/Local/Programs/Python/python.exe" "$HOME/.usage-pulse/claude_status.py"':
                "$HOME/.usage-pulse/claude_status.py",
            '/usr/bin/python3 "/home/u/.claude/plugins/cache/m/usage-pulse/3.5.0/claude_status.py"':
                "/home/u/.claude/plugins/cache/m/usage-pulse/3.5.0/claude_status.py",
            "python3 /opt/usage-pulse/claude_status.py --foo": "/opt/usage-pulse/claude_status.py",
            "python3 '/tmp/x y/claude_status.py'": "/tmp/x y/claude_status.py",
        }
        for command, expected in cases.items():
            self.assertEqual(cs._pulse_script_in_command(command), expected, command)
        self.assertIsNone(cs._pulse_script_in_command("~/.claude/statusline.sh"))
        self.assertIsNone(cs._pulse_script_in_command(""))

    def test_only_a_versioned_plugin_folder_counts_as_a_plugin_path(self):
        for path in ("/home/u/.claude/plugins/cache/mk/usage-pulse/3.5.0/claude_status.py",
                     r"C:\Users\u\.claude\plugins\cache\mk\usage-pulse\3.5.0\claude_status.py",
                     "/home/u/.claude/plugins/cache/claude-pulse/claude-pulse/3.4.2/claude_status.py"):
            self.assertTrue(cs._is_plugin_cache_path(path), path)
        for path in ("/home/u/.usage-pulse/claude_status.py",
                     "/home/u/.claude-pulse/claude_status.py",
                     "D:/Projects/usage-pulse/claude_status.py",
                     "/home/u/usage-pulse/claude_status.py",
                     "claude_status.py"):
            self.assertFalse(cs._is_plugin_cache_path(path), path)


class _Sandbox(unittest.TestCase):
    """A fake plugin cache: the pre-rename plugin folder and the current one."""

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        root = Path(self._td.name)
        self.cfg_dir = root / "claude"
        self.cfg_dir.mkdir()
        self.state = root / "state"
        self.state.mkdir()
        self.settings = self.cfg_dir / "settings.json"
        cache = self.cfg_dir / "plugins" / "cache"
        self.old = cache / "claude-pulse" / "claude-pulse" / "3.4.2" / "claude_status.py"
        self.new = cache / "usage-pulse" / "usage-pulse" / "3.5.0" / "claude_status.py"
        for script in (self.old, self.new):
            script.parent.mkdir(parents=True)
            script.write_text("# stand-in\n", encoding="utf-8")
            (script.parent / "commands").mkdir()
            shutil.copyfile(PULSE_MD, script.parent / "commands" / "pulse.md")
        self.out = io.StringIO()
        for target, value in (("_claude_config_dir", lambda: self.cfg_dir),
                              ("get_state_dir", lambda: self.state),
                              ("get_config_path", lambda: root / "config.json"),
                              ("__file__", str(self.new)),
                              ("utf8_print", lambda text: self.out.write(text + "\n"))):
            p = mock.patch.object(cs, target, value)
            p.start()
            self.addCleanup(p.stop)
        cs._settings_backed_up.clear()
        self.addCleanup(cs._settings_backed_up.clear)

    def write_settings(self, script, hooks=True):
        data = {
            "statusLine": {"type": "command", "command": f'/usr/bin/python3 "{script}"'},
            "subagentStatusLine": {"type": "command",
                                   "command": f'/usr/bin/python3 "{script}" --subagent-status-line'},
            "permissions": {"allow": ["Bash(git status)"]},
        }
        if hooks:
            data["hooks"] = {
                "SubagentStart": [{"hooks": [{"type": "command",
                                              "command": f'/usr/bin/python3 "{script}" --hook-subagent-start'}]}],
                "SubagentStop": [{"hooks": [{"type": "command",
                                             "command": f'/usr/bin/python3 "{script}" --hook-subagent-stop; exit 0'}]}],
                "UserPromptSubmit": [{"hooks": [{"type": "command", "command": "echo mine"}]}],
            }
        self.settings.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return self.settings.read_text(encoding="utf-8")

    def settings_data(self):
        return json.loads(self.settings.read_text(encoding="utf-8"))


class SyncInstallPathTest(_Sandbox):
    def test_pre_rename_plugin_folder_is_replaced_everywhere(self):
        self.write_settings(self.old)
        self.assertEqual(cs.cmd_sync_install_path(), 0)
        data = self.settings_data()
        for key in ("statusLine", "subagentStatusLine"):
            self.assertIn("usage-pulse", data[key]["command"], key)
            self.assertNotIn("claude-pulse", data[key]["command"], key)
        for event in ("SubagentStart", "SubagentStop"):
            cmds = [h["command"] for e in data["hooks"][event] for h in e["hooks"]]
            self.assertTrue(any("usage-pulse" in c for c in cmds), event)
            self.assertFalse(any("claude-pulse" in c for c in cmds), event)
        # Foreign settings and hooks are untouched, /pulse is refreshed, and
        # the previous settings.json is kept.
        self.assertEqual(data["permissions"], {"allow": ["Bash(git status)"]})
        self.assertEqual(data["hooks"]["UserPromptSubmit"][0]["hooks"][0]["command"], "echo mine")
        self.assertEqual((self.cfg_dir / "commands" / "pulse.md").read_text(encoding="utf-8"),
                         PULSE_MD.read_text(encoding="utf-8"))
        self.assertTrue(list((self.state / "settings-backups").glob("*settings.json.*")))
        self.assertIn("re-pointing", self.out.getvalue())

    def test_an_older_version_folder_of_the_same_plugin_is_replaced(self):
        older = self.new.parent.parent / "3.4.9" / "claude_status.py"
        older.parent.mkdir()
        self.write_settings(older)
        cs.cmd_sync_install_path()
        self.assertIn("3.5.0", self.settings_data()["statusLine"]["command"])

    def test_hook_groups_that_were_not_installed_stay_absent(self):
        self.write_settings(self.old, hooks=False)
        cs.cmd_sync_install_path()
        data = self.settings_data()
        self.assertIn("usage-pulse", data["statusLine"]["command"])
        self.assertNotIn("hooks", data)

    def test_nothing_happens_when_the_path_is_already_current(self):
        before = self.write_settings(self.new)
        self.assertEqual(cs.cmd_sync_install_path(), 0)
        self.assertEqual(self.settings.read_text(encoding="utf-8"), before)
        self.assertEqual(self.out.getvalue(), "")

    def test_a_git_install_is_never_hijacked(self):
        for folder in (".usage-pulse", ".claude-pulse"):
            clone = self.cfg_dir.parent / folder / "claude_status.py"
            before = self.write_settings(clone)
            self.assertEqual(cs.cmd_sync_install_path(), 0)
            self.assertEqual(self.settings.read_text(encoding="utf-8"), before, folder)
            self.assertEqual(self.out.getvalue(), "")

    def test_another_status_line_or_none_is_left_alone(self):
        self.settings.write_text(json.dumps({"statusLine": {"type": "command", "command": "~/bar.sh"}}),
                                 encoding="utf-8")
        before = self.settings.read_text(encoding="utf-8")
        self.assertEqual(cs.cmd_sync_install_path(), 0)
        self.assertEqual(self.settings.read_text(encoding="utf-8"), before)
        self.settings.unlink()
        self.assertEqual(cs.cmd_sync_install_path(), 0)
        self.assertFalse(self.settings.exists())
        self.assertEqual(self.out.getvalue(), "")

    def test_a_broken_settings_file_is_not_touched(self):
        self.settings.write_text("{not json", encoding="utf-8")
        self.assertEqual(cs.cmd_sync_install_path(), 0)
        self.assertEqual(self.settings.read_text(encoding="utf-8"), "{not json")

    def test_the_flag_is_wired_and_documented(self):
        self.assertTrue(any(row[0] == "--sync-install-path" for row in cs.CLI_FLAGS))
        self.write_settings(self.old)
        with mock.patch.object(sys, "argv", ["claude_status.py", "--sync-install-path"]):
            try:
                cs.main()
            except SystemExit as e:
                self.assertFalse(e.code)
        self.assertIn("usage-pulse", self.settings_data()["statusLine"]["command"])


class RepoAliasTest(unittest.TestCase):
    """Update checks must accept clones made under the old repository name."""

    def test_both_origins_track_upstream(self):
        for url in ("https://github.com/NoobyGains/usage-pulse.git", "git@github.com:NoobyGains/claude-pulse.git",
                    "https://github.com/noobygains/claude-pulse"):
            with mock.patch.object(cs, "_git", return_value=url):
                self.assertTrue(cs._tracks_upstream(), url)
        with mock.patch.object(cs, "_git", return_value="https://github.com/someone/fork.git"):
            self.assertFalse(cs._tracks_upstream())


if __name__ == "__main__":
    unittest.main(verbosity=2)
