"""Regression test: `claude_status.py --install` must install BOTH pieces.

Before this guard, running ``--install`` directly wrote the status-line into
settings.json but never copied the ``/pulse`` slash command into
``~/.claude/commands/``.  The meter worked while ``/pulse`` silently did
nothing.  This test pins both halves of a full install.

Run: ``python tests/test_install_command.py``
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "claude_status.py"
PULSE_SRC = REPO_ROOT / "pulse.md"


class InstallCommandTest(unittest.TestCase):
    def test_install_sets_up_statusline_and_pulse_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            env = dict(os.environ)
            # Point every home indicator at the sandbox so Path.home()/
            # expanduser("~") resolve inside it on both Windows and POSIX.
            env["HOME"] = str(home)
            env["USERPROFILE"] = str(home)
            # The config and state dirs too, or the subprocess reads (and may
            # migrate) the developer's real config.json.
            env["LOCALAPPDATA"] = str(home / "AppData" / "Local")
            env["XDG_CACHE_HOME"] = str(home / ".cache")
            env["XDG_CONFIG_HOME"] = str(home / ".config")
            for key in ("HOMEDRIVE", "HOMEPATH", "CLAUDE_CONFIG_DIR"):
                env.pop(key, None)

            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--install"],
                env=env,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)

            settings = home / ".claude" / "settings.json"
            self.assertTrue(settings.exists(), "settings.json was not written")
            data = json.loads(settings.read_text(encoding="utf-8"))
            self.assertIn("statusLine", data)
            self.assertIn("claude_status.py", data["statusLine"]["command"])

            command = home / ".claude" / "commands" / "pulse.md"
            self.assertTrue(command.exists(), "/pulse command was not installed")
            self.assertEqual(
                command.read_text(encoding="utf-8"),
                PULSE_SRC.read_text(encoding="utf-8"),
                "/pulse command content does not match source pulse.md",
            )

    def test_setup_non_interactive_installs_the_same_pieces(self):
        """The installers now call --setup --non-interactive instead of --install."""
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            env = dict(os.environ)
            env["HOME"] = str(home)
            env["USERPROFILE"] = str(home)
            env["LOCALAPPDATA"] = str(home / "AppData" / "Local")
            env["XDG_CACHE_HOME"] = str(home / ".cache")
            env["XDG_CONFIG_HOME"] = str(home / ".config")
            for key in ("HOMEDRIVE", "HOMEPATH", "CLAUDE_CONFIG_DIR"):
                env.pop(key, None)

            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--setup", "--non-interactive"],
                env=env, capture_output=True, text=True, encoding="utf-8",
                stdin=subprocess.DEVNULL,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            data = json.loads((home / ".claude" / "settings.json").read_text(encoding="utf-8"))
            self.assertIn("claude_status.py", data["statusLine"]["command"])
            self.assertIn("--subagent-status-line", data["subagentStatusLine"]["command"])
            self.assertNotIn("hooks", data, "unattended setup installs no hooks")
            command = home / ".claude" / "commands" / "pulse.md"
            self.assertEqual(command.read_text(encoding="utf-8"),
                             PULSE_SRC.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
