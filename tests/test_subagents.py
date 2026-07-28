"""Tests for subagent tracking, the agent-panel rows, caps and the budget bar.

Claude Code runs subagents in the background by default and lets them nest, so
a session accumulates them quietly. Four surfaces are covered here:

* ``SubagentStart`` / ``SubagentStop`` bookkeeping — including the two ways it
  can drift: a Stop hook that never fires, and a session change;
* ``subagentStatusLine`` row rendering, which must degrade to Claude Code's own
  rendering rather than emit a broken row;
* the caps widget, whose denominators come from config because Claude Code
  enforces its limits without reporting them;
* the budget bar, whose ceiling is a claude-pulse setting because
  ``--max-budget-usd`` is CLI-only with no settings key or env var.

Run: ``python tests/test_subagents.py``
"""
import json
import sys
import time
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import claude_status as cs  # noqa: E402


class SubagentStateTest(unittest.TestCase):
    def test_prune_drops_stragglers(self):
        """A crashed subagent never fires Stop; without pruning the live count
        would drift upward for the rest of the session."""
        now = time.time()
        active = {
            "fresh": {"started": now - 10},
            "stale": {"started": now - cs.SUBAGENT_STATE_TTL - 1},
        }
        pruned = cs._prune_subagents(active, now)
        self.assertIn("fresh", pruned)
        self.assertNotIn("stale", pruned)

    def test_prune_survives_malformed_records(self):
        for bad in ({"x": "y"}, {"x": {"started": "nope"}}, {"x": None}, {}):
            cs._prune_subagents(bad)  # must not raise

    def test_read_state_tolerates_corruption(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "s.json"
            with mock.patch.object(cs, "_get_subagent_state_path", return_value=p):
                for junk in ("[]", "42", '"s"', "null", '{"active": 5}', "{not json"):
                    p.write_text(junk, encoding="utf-8")
                    state = cs._read_subagent_state()
                    self.assertIsInstance(state, dict, junk)
                    self.assertIsInstance(state.get("active"), dict, junk)


class SubagentRowTest(unittest.TestCase):
    def _cfg(self):
        return {"theme": "default", "bar_size": "medium", "bar_style": "classic",
                "layout": "standard", "effort_format": "labeled"}

    def test_running_row_has_name_model_and_bar(self):
        row = cs._render_subagent_row({
            "id": "t1", "name": "reviewer", "status": "running",
            "model": "claude-opus-5", "contextWindowSize": 1_000_000,
            "tokenCount": 250_000,
        }, self._cfg())
        self.assertIn("reviewer", row)
        self.assertIn("Opus", row)
        self.assertIn("25%", row)

    def test_numeric_effort_is_shown_as_a_token_budget(self):
        row = cs._render_subagent_row(
            {"id": "t", "name": "x", "status": "running", "effort": 30000}, self._cfg())
        self.assertIn("30k", row)

    def test_missing_window_falls_back_to_raw_tokens(self):
        row = cs._render_subagent_row(
            {"id": "t", "name": "x", "status": "running", "tokenCount": 1500}, self._cfg())
        self.assertIn("1", row)
        self.assertNotIn("%", row)

    def test_row_is_clipped_to_columns(self):
        row = cs._render_subagent_row(
            {"id": "t", "name": "n" * 40, "status": "running"}, self._cfg(), columns=20)
        self.assertLessEqual(cs._visible_len(row), 20)

    def test_garbage_task_returns_empty(self):
        for bad in (None, "str", 7, []):
            self.assertEqual(cs._render_subagent_row(bad, self._cfg()), "")

    def test_status_glyphs_differ_by_state(self):
        cfg = self._cfg()
        rows = {s: cs._render_subagent_row({"id": "t", "name": "x", "status": s}, cfg)
                for s in ("running", "completed", "failed", "pending")}
        self.assertEqual(len({r.split()[0] for r in rows.values()}), 4)


class SubagentStatusLineOutputTest(unittest.TestCase):
    """Output contract: one JSON line per overridden row, id + content."""

    def _run(self, payload):
        import io
        buf = io.BytesIO()
        stdin = mock.MagicMock()
        stdin.isatty.return_value = False
        stdin.read.return_value = json.dumps(payload)
        stdout = mock.MagicMock()
        stdout.buffer = buf
        with mock.patch.object(cs.sys, "stdin", stdin), \
             mock.patch.object(cs.sys, "stdout", stdout):
            cs.cmd_subagent_status_line()
        return [json.loads(l) for l in buf.getvalue().decode("utf-8").strip().split("\n") if l]

    def test_emits_one_line_per_task(self):
        out = self._run({"columns": 100, "tasks": [
            {"id": "a", "name": "one", "status": "running"},
            {"id": "b", "name": "two", "status": "completed"},
        ]})
        self.assertEqual([r["id"] for r in out], ["a", "b"])
        self.assertTrue(all(r["content"] for r in out))

    def test_task_without_id_is_skipped(self):
        out = self._run({"tasks": [{"name": "no id"}, {"id": "b", "name": "ok"}]})
        self.assertEqual([r["id"] for r in out], ["b"])

    def test_malformed_payloads_emit_nothing(self):
        import io
        for payload in ({"tasks": "nope"}, {}, {"tasks": [None, "x", 7]}, []):
            buf = io.BytesIO()
            stdin = mock.MagicMock()
            stdin.isatty.return_value = False
            stdin.read.return_value = json.dumps(payload)
            stdout = mock.MagicMock(); stdout.buffer = buf
            with mock.patch.object(cs.sys, "stdin", stdin), \
                 mock.patch.object(cs.sys, "stdout", stdout):
                cs.cmd_subagent_status_line()   # must not raise
            self.assertEqual(buf.getvalue(), b"", repr(payload))

    def test_invalid_json_is_silent(self):
        import io
        buf = io.BytesIO()
        stdin = mock.MagicMock()
        stdin.isatty.return_value = False
        stdin.read.return_value = "{not json"
        stdout = mock.MagicMock(); stdout.buffer = buf
        with mock.patch.object(cs.sys, "stdin", stdin), \
             mock.patch.object(cs.sys, "stdout", stdout):
            cs.cmd_subagent_status_line()
        self.assertEqual(buf.getvalue(), b"")


class CapsAndBudgetTest(unittest.TestCase):
    def test_defaults_match_documented_claude_code_values(self):
        self.assertEqual(cs.DEFAULT_LIMITS["subagent_spawns"], 200)
        self.assertEqual(cs.DEFAULT_LIMITS["subagent_concurrent"], 20)
        self.assertEqual(cs.DEFAULT_LIMITS["web_searches"], 200)

    def test_zero_cap_hides_the_denominator(self):
        state = {"session_id": "s", "active": {}, "spawned": 5}
        with mock.patch.object(cs, "_read_subagent_state", return_value=state):
            out = cs._render_subagents({"limits": {"subagent_spawns": 0}})
        self.assertIsNotNone(out)
        self.assertNotIn("/", out)

    def test_nothing_rendered_before_any_subagent_runs(self):
        with mock.patch.object(cs, "_read_subagent_state",
                               return_value={"active": {}, "spawned": 0}):
            self.assertIsNone(cs._render_subagents({}))

    def test_budget_off_by_default(self):
        self.assertIsNone(cs._render_budget({}, {"cost_usd": 10}))
        self.assertIsNone(cs._render_budget({"budget_usd": 0}, {"cost_usd": 10}))

    def test_budget_renders_when_configured(self):
        out = cs._render_budget({"budget_usd": 25, "currency": "$"}, {"cost_usd": 5})
        self.assertIsNotNone(out)
        self.assertIn("budget", out)

    def test_budget_needs_a_cost(self):
        self.assertIsNone(cs._render_budget({"budget_usd": 25}, {}))
        self.assertIsNone(cs._render_budget({"budget_usd": 25}, None))

    def test_budget_tolerates_junk(self):
        for cfg in ({"budget_usd": "abc"}, {"budget_usd": None}, {"budget_usd": -5}):
            self.assertIsNone(cs._render_budget(cfg, {"cost_usd": 5}))
        self.assertIsNone(cs._render_budget({"budget_usd": 25}, {"cost_usd": "abc"}))


class ElapsedParsingTest(unittest.TestCase):
    """startTime may arrive as epoch ms, epoch seconds, or ISO-8601."""

    def test_epoch_milliseconds(self):
        self.assertAlmostEqual(cs._elapsed_from_start((time.time() - 60) * 1000), 60, delta=2)

    def test_epoch_seconds(self):
        self.assertAlmostEqual(cs._elapsed_from_start(time.time() - 60), 60, delta=2)

    def test_iso_string(self):
        self.assertIsNotNone(cs._elapsed_from_start("2026-07-18T15:01:07.532Z"))

    def test_garbage_and_future(self):
        for bad in (None, "nope", [], {}):
            self.assertIsNone(cs._elapsed_from_start(bad))
        self.assertIsNone(cs._elapsed_from_start((time.time() + 3600) * 1000))


if __name__ == "__main__":
    unittest.main(verbosity=2)
