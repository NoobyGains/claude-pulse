"""The update check's time budget must bound the blocking calls themselves.

``check_for_update`` advertises a hard ceiling (_UPDATE_CHECK_BUDGET) on one
check, but only inspecting the deadline *between* operations doesn't enforce
it: five sequential calls that each run just under their own fixed timeout
(2s + 3s + 3s + 3s + 2s) can stall a repaint for ~13 seconds. Every blocking
call must receive a timeout capped by the budget that remains.

The fakes here model exactly that adversarial-but-realistic case: each git or
HTTP call succeeds after consuming 90% of whatever timeout it was allowed.

Run: ``python tests/test_update_check_budget.py``
"""
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import claude_status as cs  # noqa: E402

LOCAL_SHA = "a" * 40
REMOTE_SHA = "b" * 40


class _FakeClock:
    def __init__(self):
        self.now = 1_000_000.0

    def time(self):
        return self.now


class UpdateCheckBudgetTest(unittest.TestCase):
    def _run_check(self, op_cost_fraction):
        """Run check_for_update with ops that consume the given fraction of
        whatever timeout they are granted. Returns (verdict, elapsed)."""
        clock = _FakeClock()

        def fake_run(cmd, capture_output=None, text=None, timeout=None, cwd=None):
            clock.now += timeout * op_cost_fraction
            if "rev-parse" in cmd:
                out = LOCAL_SHA
            elif "get-url" in cmd:
                out = f"https://github.com/{cs.GITHUB_REPO}"
            else:  # cat-file / merge-base
                out = ""
            return SimpleNamespace(returncode=0, stdout=out, stderr="")

        class _FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def read(self, n=-1):
                return REMOTE_SHA.encode()

        def fake_urlopen(req, timeout=None):
            clock.now += timeout * op_cost_fraction
            return _FakeResponse()

        with tempfile.TemporaryDirectory() as td, \
                mock.patch.object(cs, "time", clock), \
                mock.patch.object(cs.subprocess, "run", fake_run), \
                mock.patch.object(cs.urllib.request, "urlopen", fake_urlopen), \
                mock.patch.object(cs, "get_state_dir", lambda: Path(td)):
            start = clock.time()
            verdict = cs.check_for_update()
            return verdict, clock.time() - start

    def test_slow_operations_cannot_exceed_the_advertised_budget(self):
        verdict, elapsed = self._run_check(op_cost_fraction=0.9)
        self.assertLessEqual(
            elapsed, cs._UPDATE_CHECK_BUDGET + 0.5,
            f"one update check consumed {elapsed:.1f}s of blocking calls — the "
            f"budget of {cs._UPDATE_CHECK_BUDGET}s must cap each call, not just "
            "be glanced at between calls",
        )

    def test_fast_operations_still_produce_a_verdict(self):
        verdict, elapsed = self._run_check(op_cost_fraction=0.01)
        # Remote differs from local but merge-base exits 0 (remote is an
        # ancestor → this checkout is ahead → no update to offer).
        self.assertIs(verdict, False)
        self.assertLess(elapsed, cs._UPDATE_CHECK_BUDGET)


if __name__ == "__main__":
    unittest.main(verbosity=2)
