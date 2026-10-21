"""``commands/pulse.md`` is the ``/pulse`` command the installers copy into
``~/.claude/commands/`` and the plugin exposes as ``/usage-pulse:pulse``. It
must only advertise flags and widget names the script really has.

Run: ``python tests/test_pulse_command_sync.py``
"""
import re
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import claude_status as cs  # noqa: E402

PULSE_MD = REPO_ROOT / "commands" / "pulse.md"


class PulseCommandTest(unittest.TestCase):
    def test_there_is_exactly_one_copy(self):
        self.assertTrue(PULSE_MD.exists())
        self.assertFalse((REPO_ROOT / "pulse.md").exists(),
                         "the /pulse command lives in commands/ only; a root copy drifts")

    def test_installed_copy_is_the_commands_file(self):
        self.assertTrue(PULSE_MD.read_text(encoding="utf-8").startswith("---\n"),
                        "slash commands carry frontmatter")

    def test_documented_flags_exist(self):
        text = PULSE_MD.read_text(encoding="utf-8")
        known = {row[0] for row in cs.CLI_FLAGS} | set(cs._CLI_SUBOPTIONS)
        known.add("--max-budget-usd")   # Claude Code's own flag, which the budget widget mirrors
        used = set(re.findall(r"`(--[a-z][a-z0-9-]*)", text))
        unknown = used - known
        self.assertEqual(unknown, set(), "pulse.md mentions flags the script does not handle")

    def test_documented_widgets_exist(self):
        text = PULSE_MD.read_text(encoding="utf-8")
        m = re.search(r"Valid parts: (.+)", text)
        self.assertTrue(m, "pulse.md lists the valid --show/--hide parts")
        listed = {p.strip() for p in m.group(1).split(",")}
        self.assertEqual(listed - set(cs.DEFAULT_SHOW), set(), "pulse.md lists unknown parts")
        self.assertEqual(set(cs.DEFAULT_SHOW) - listed, set(), "pulse.md misses parts the script has")


if __name__ == "__main__":
    unittest.main(verbosity=2)
