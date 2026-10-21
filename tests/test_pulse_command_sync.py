"""``pulse.md`` (copied by the installers) and ``commands/pulse.md`` (the
plugin's copy) must be byte-identical, and every flag /pulse tells Claude to
run must be one the script handles.

Run: ``python tests/test_pulse_command_sync.py``
"""
import re
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import claude_status as cs  # noqa: E402

# Provider flags are documented ahead of the providers feature landing in
# CLI_FLAGS (added at integration); they are checked once present.
_PENDING = {"--providers", "--detect-providers"}


class PulseCommandSyncTest(unittest.TestCase):
    def test_copies_are_identical(self):
        a = (REPO_ROOT / "pulse.md").read_bytes()
        b = (REPO_ROOT / "commands" / "pulse.md").read_bytes()
        self.assertEqual(a, b, "pulse.md and commands/pulse.md differ; copy one over the other")

    def test_documented_flags_exist(self):
        text = (REPO_ROOT / "pulse.md").read_text(encoding="utf-8")
        known = {row[0] for row in cs.CLI_FLAGS} | set(cs._CLI_SUBOPTIONS)
        documented = set(re.findall(r"(?<![\w-])(--[a-z][a-z0-9-]+)", text))
        documented -= {"--max-budget-usd"}           # Claude Code's own flag
        unknown = documented - known - (_PENDING - known)
        self.assertEqual(unknown, set(), "pulse.md mentions flags the script does not handle")

    def test_documented_widgets_exist(self):
        text = (REPO_ROOT / "pulse.md").read_text(encoding="utf-8")
        m = re.search(r"Valid parts:\s*(.+)", text)
        self.assertTrue(m, "pulse.md lists the valid --show/--hide parts")
        parts = {p.strip(" `.") for p in m.group(1).split(",")}
        # Widgets from the parallel stdin work are listed ahead of time.
        pending = {"cache_warm", "spend_limit", "repo", "session_name", "providers"}
        unknown = {p for p in parts if p and p not in cs.DEFAULT_SHOW} - pending
        self.assertEqual(unknown, set())


if __name__ == "__main__":
    unittest.main(verbosity=2)
