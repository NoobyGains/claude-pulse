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
    """Marker-file bookkeeping: one dir per session, one file per agent.

    The previous design (one global JSON, read-modify-write, reset whenever a
    hook arrived from a different session) had two proven failure modes: lost
    increments when several agents spawn in parallel, and one session's counts
    being clobbered or displayed by another. Marker files make every write an
    atomic create/rename of a distinct path, so neither can happen.
    """

    def setUp(self):
        import tempfile
        self._td = tempfile.TemporaryDirectory()
        self._patch = mock.patch.object(
            cs, "get_state_dir", lambda: Path(self._td.name))
        self._patch.start()
        self.addCleanup(self._patch.stop)
        self.addCleanup(self._td.cleanup)

    def _start(self, agent_id="a1", session="s1", agent_type="claude"):
        cs._record_subagent_event("start", {
            "agent_id": agent_id, "session_id": session, "agent_type": agent_type})

    def _stop(self, agent_id="a1", session="s1"):
        cs._record_subagent_event("stop", {
            "agent_id": agent_id, "session_id": session})

    def test_start_makes_agent_live(self):
        self._start()
        self.assertEqual(cs._count_subagents("s1"), (1, 1))

    def test_stop_keeps_spawn_but_not_live(self):
        self._start()
        self._stop()
        self.assertEqual(cs._count_subagents("s1"), (0, 1))

    def test_parallel_starts_lose_no_increments(self):
        """30 simultaneous SubagentStart hooks must all be counted. The old
        read-modify-write JSON lost most of them to the race."""
        import threading
        threads = [threading.Thread(target=self._start, args=(f"agent{i}",))
                   for i in range(30)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(cs._count_subagents("s1"), (30, 30))

    def test_sessions_never_clobber_each_other(self):
        """A hook from session B must not reset or leak into session A."""
        self._start("a1", session="sessA")
        self._start("b1", session="sessB")
        self._stop("b1", session="sessB")
        self.assertEqual(cs._count_subagents("sessA"), (1, 1))
        self.assertEqual(cs._count_subagents("sessB"), (0, 1))

    def test_stop_before_start_never_goes_live(self):
        """Hook processes race: a fast agent's Stop can land before its Start.
        The late Start must not resurrect it as live-forever."""
        self._stop("quick")
        self._start("quick")
        self.assertEqual(cs._count_subagents("s1"), (0, 1))

    def test_straggler_live_marker_is_not_live(self):
        """A crashed subagent never fires Stop; past the TTL its marker must
        stop counting as live (but the spawn still happened)."""
        self._start("ghost")
        marker = cs._subagent_root() / "s1" / "ghost.live"
        old = time.time() - cs.SUBAGENT_STATE_TTL - 60
        import os
        os.utime(marker, (old, old))
        self.assertEqual(cs._count_subagents("s1"), (0, 1))

    def test_prune_removes_dead_session_dirs(self):
        self._start("a", session="dead")
        self._start("b", session="alive")
        import os
        old = time.time() - cs.SUBAGENT_STATE_TTL - 60
        dead = cs._subagent_root() / "dead"
        for child in dead.iterdir():
            os.utime(child, (old, old))
        cs._prune_subagent_dirs(cs._subagent_root())
        self.assertFalse(dead.exists())
        self.assertEqual(cs._count_subagents("alive"), (1, 1))

    def test_missing_agent_id_still_counts_the_spawn(self):
        cs._record_subagent_event("start", {"session_id": "s1"})
        live, spawned = cs._count_subagents("s1")
        self.assertEqual(spawned, 1)

    def test_missing_session_id_is_a_noop(self):
        cs._record_subagent_event("start", {"agent_id": "a1"})
        self.assertFalse((cs._subagent_root()).exists() and
                         any(cs._subagent_root().iterdir()))

    def test_hostile_ids_cannot_escape_the_state_dir(self):
        cs._record_subagent_event("start", {
            "agent_id": "..", "session_id": "../../evil"})
        root = cs._subagent_root()
        if root.exists():
            for p in root.rglob("*"):
                self.assertIn(str(root), str(p))

    def test_malformed_event_data_never_raises(self):
        for bad in ({}, {"agent_id": None}, {"session_id": 7, "agent_id": []},
                    {"session_id": "s", "agent_id": {"x": 1}}):
            cs._record_subagent_event("start", bad)
            cs._record_subagent_event("stop", bad)

    def test_legacy_single_file_state_is_cleaned_up(self):
        legacy = Path(self._td.name) / "subagents.json"
        legacy.write_text("{}", encoding="utf-8")
        self._start()
        self.assertFalse(legacy.exists())

    def test_render_is_scoped_to_the_painting_session(self):
        """The status line must show the counts of the session being painted,
        never whichever session last wrote."""
        self._start("a1", session="mine")
        self._start("b1", session="theirs")
        self._start("b2", session="theirs")
        out = cs._render_subagents({}, "mine")
        self.assertIsNotNone(out)
        # _sanitize strips the ANSI colouring for a readable assertion.
        self.assertIn("1/200", cs._sanitize(out))   # mine: 1 spawn — not theirs: 2
        self.assertIsNone(cs._render_subagents({}, "unknown-session"))

    def test_render_without_a_session_id_shows_nothing(self):
        self._start()
        self.assertIsNone(cs._render_subagents({}, None))
        self.assertIsNone(cs._render_subagents({}, ""))


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
        with mock.patch.object(cs, "_count_subagents", return_value=(0, 5)):
            out = cs._render_subagents({"limits": {"subagent_spawns": 0}}, "s")
        self.assertIsNotNone(out)
        self.assertNotIn("/", out)

    def test_nothing_rendered_before_any_subagent_runs(self):
        with mock.patch.object(cs, "_count_subagents", return_value=(0, 0)):
            self.assertIsNone(cs._render_subagents({}, "s"))

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
