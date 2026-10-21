"""``--help`` and the CLI_FLAGS table it prints.

CLI_FLAGS is the single list of flags that --help, the README audit and the
/pulse docs rely on, so it must match main()'s ``"--flag" in args`` chain in
both directions.

Run: ``python tests/test_help.py``
"""
import inspect
import io
import re
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import claude_status as cs  # noqa: E402


def _main_flags():
    src = inspect.getsource(cs.main)
    return set(re.findall(r'"(--?[a-z][a-z0-9-]*)" in args', src))


class CliFlagsTableTest(unittest.TestCase):
    def test_rows_are_well_formed(self):
        seen = set()
        for row in cs.CLI_FLAGS:
            self.assertEqual(len(row), 4, row)
            flag, _args, group, text = row
            self.assertIn(group, cs.CLI_GROUPS, row)
            self.assertTrue(text, row)
            self.assertNotIn(flag, seen, f"duplicate {flag}")
            seen.add(flag)

    def test_every_main_flag_is_listed(self):
        listed = {row[0] for row in cs.CLI_FLAGS}
        missing = _main_flags() - listed - set(cs._CLI_SUBOPTIONS)
        self.assertEqual(missing, set(), "flags handled in main() but missing from CLI_FLAGS")

    def test_every_listed_flag_is_handled(self):
        stale = {row[0] for row in cs.CLI_FLAGS} - _main_flags()
        self.assertEqual(stale, set(), "flags in CLI_FLAGS that main() does not handle")


class HelpOutputTest(unittest.TestCase):
    def _run(self, *args, stdin=subprocess.DEVNULL):
        return subprocess.run([sys.executable, str(REPO_ROOT / "claude_status.py"), *args],
                              capture_output=True, text=True, encoding="utf-8",
                              stdin=stdin, timeout=60)

    def test_help_lists_every_flag_and_exits_zero(self):
        for flag in ("--help", "-h"):
            result = self._run(flag)
            self.assertEqual(result.returncode, 0, result.stderr)
            for row in cs.CLI_FLAGS:
                if row[0] != "-h":
                    self.assertIn(row[0], result.stdout)
            for group in ("Setup", "Look", "Widgets", "Hooks", "Info", "Internal"):
                self.assertIn(f"\n{group}\n", result.stdout)

    def test_unknown_flag_on_a_terminal_points_at_help(self):
        out = io.BytesIO()
        fake_out = mock.Mock()
        fake_out.buffer = out
        with mock.patch.object(sys, "argv", ["x", "--frobnicate"]), \
                mock.patch("sys.stdin") as fake_in, \
                mock.patch.object(sys, "stdout", fake_out):
            fake_in.isatty.return_value = True
            with self.assertRaises(SystemExit) as ctx:
                cs.main()
        self.assertEqual(ctx.exception.code, 2)
        self.assertIn("--help", out.getvalue().decode("utf-8"))

    def test_unknown_flag_with_piped_stdin_still_draws_a_line(self):
        # Status-line mode is always piped; the guard must never block it.
        self.assertEqual(cs._unknown_cli_flags(["--setup", "--only", "--json"]), [])
        self.assertEqual(cs._unknown_cli_flags(["--frobnicate"]), ["--frobnicate"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
