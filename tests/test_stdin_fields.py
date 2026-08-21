"""Tests for the Claude Code stdin payload parser (``_parse_stdin_context``).

The status line is fed a JSON blob on stdin every time Claude Code repaints.
That payload is the sole source of truth for the model, context window, cost,
rate limits, and — as of the Claude 5 era — reasoning effort, fast mode,
thinking state, the active subagent, and PR context.

Two properties matter most and are pinned here:

* every field is read from the shape Claude Code actually documents, including
  the ``{"data": {...}}`` envelope variant;
* a malformed, partial, or hostile payload never raises. The status line runs
  on every keystroke, so an exception here would blank the user's bar.

Run: ``python tests/test_stdin_fields.py``
"""
import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import claude_status as cs  # noqa: E402


def parse(payload):
    return cs._parse_stdin_context(json.dumps(payload))


class EffortFastModeThinkingTest(unittest.TestCase):
    """Effort now comes from stdin, not an env var Claude Code never exported."""

    def test_effort_level_read_from_stdin(self):
        self.assertEqual(parse({"effort": {"level": "xhigh"}})["effort"], "xhigh")

    def test_effort_unset_records_the_off_value(self):
        # Present-but-None, not absent: absent would mean "unchanged" to the
        # persistence layer and the previous level would stay pinned.
        self.assertIsNone(parse({"effort": {"level": "unset"}})["effort"])

    def test_effort_missing_is_absent(self):
        self.assertNotIn("effort", parse({}))

    def test_effort_wrong_type_does_not_raise(self):
        self.assertIsNone(parse({"effort": "high"})["effort"])
        self.assertIsNone(parse({"effort": None})["effort"])

    def test_fast_mode_records_both_states(self):
        self.assertIs(parse({"fast_mode": True})["fast_mode"], True)
        self.assertIs(parse({"fast_mode": False})["fast_mode"], False)
        # A fragment with no session identity says nothing either way.
        self.assertNotIn("fast_mode", parse({}))

    def test_thinking_records_both_states(self):
        self.assertIs(parse({"thinking": {"enabled": True}})["thinking"], True)
        self.assertIs(parse({"thinking": {"enabled": False}})["thinking"], False)
        self.assertIsNone(parse({"thinking": {}})["thinking"])


class AgentAndPrTest(unittest.TestCase):
    def test_agent_name(self):
        self.assertEqual(parse({"agent": {"name": "reviewer"}})["agent_name"], "reviewer")

    def test_agent_missing_or_blank(self):
        self.assertNotIn("agent_name", parse({"agent": {"name": ""}}))
        self.assertNotIn("agent_name", parse({}))

    def test_pr_fields(self):
        ctx = parse({"pr": {
            "number": 42,
            "url": "https://github.com/o/r/pull/42",
            "review_state": "approved",
        }})
        self.assertEqual(ctx["pr_number"], 42)
        self.assertEqual(ctx["pr_url"], "https://github.com/o/r/pull/42")
        self.assertEqual(ctx["pr_review_state"], "approved")

    def test_pr_rejects_non_http_url(self):
        """The URL is embedded in an OSC 8 escape — only http(s) may through."""
        for bad in ("javascript:alert(1)", "file:///etc/passwd", "data:text/html,x"):
            ctx = parse({"pr": {"number": 1, "url": bad}})
            self.assertEqual(ctx["pr_number"], 1)
            self.assertNotIn("pr_url", ctx, f"{bad} must not be linkified")

    def test_pr_without_number_clears_the_badge(self):
        self.assertIsNone(parse({"pr": {"url": "https://x/y"}})["pr_number"])

    def test_gitlab_mr_kind_parsed(self):
        """v2.1.234+ sets pr.kind to "mr" for GitLab merge requests."""
        ctx = parse({"pr": {"number": 7, "kind": "mr"}})
        self.assertEqual(ctx["pr_kind"], "mr")

    def test_github_pr_has_no_kind(self):
        # kind is omitted on GitHub; nothing should be recorded.
        self.assertNotIn("pr_kind", parse({"pr": {"number": 7}}))


class CacheEfficiencyTest(unittest.TestCase):
    def test_cache_hit_pct_over_billable_input(self):
        ctx = parse({"context_window": {"current_usage": {
            "input_tokens": 1000,
            "cache_creation_input_tokens": 1000,
            "cache_read_input_tokens": 8000,
        }}})
        # 8000 / (8000 + 1000 + 1000) == 80%
        self.assertAlmostEqual(ctx["cache_hit_pct"], 80.0, places=6)
        self.assertEqual(ctx["cache_read_tokens"], 8000)

    def test_zero_billable_yields_no_ratio(self):
        ctx = parse({"context_window": {"current_usage": {
            "input_tokens": 0,
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 0,
        }}})
        self.assertNotIn("cache_hit_pct", ctx)

    def test_missing_breakdown_is_absent(self):
        self.assertNotIn("cache_hit_pct", parse({"context_window": {}}))


class ModelAndWindowTest(unittest.TestCase):
    def test_display_name_strips_claude_prefix(self):
        ctx = parse({"model": {"id": "claude-opus-5", "display_name": "Claude Opus 5"}})
        self.assertEqual(ctx["model_name"], "Opus 5")

    def test_falls_back_to_id_mapping(self):
        self.assertEqual(parse({"model": {"id": "claude-fable-5"}})["model_name"], "Fable")

    def test_dated_variant_maps_to_family(self):
        ctx = parse({"model": {"id": "claude-haiku-4-5-20251001"}})
        self.assertEqual(ctx["model_name"], "Haiku")

    def test_longest_prefix_wins(self):
        """"claude-opus-4" must not shadow "claude-opus-4-8"."""
        self.assertEqual(cs._model_short_name("claude-opus-4-8"), "Opus")
        self.assertEqual(cs._model_short_name("claude-sonnet-5"), "Sonnet")
        self.assertIsNone(cs._model_short_name("gpt-4"))
        self.assertIsNone(cs._model_short_name(""))

    def test_context_window_size_is_trusted_from_stdin(self):
        ctx = parse({"context_window": {
            "used_percentage": 10,
            "total_input_tokens": 100_000,
            "total_output_tokens": 0,
            "context_window_size": 1_000_000,
        }})
        self.assertEqual(ctx["context_limit"], 1_000_000)


class RobustnessTest(unittest.TestCase):
    """A bad payload must degrade, never raise — an exception blanks the bar."""

    def test_empty_and_blank_input(self):
        self.assertEqual(cs._parse_stdin_context(""), {})
        self.assertEqual(cs._parse_stdin_context("   "), {})
        self.assertEqual(cs._parse_stdin_context(None), {})

    def test_invalid_json(self):
        self.assertEqual(cs._parse_stdin_context("{not json"), {})

    def test_data_envelope_variant(self):
        ctx = cs._parse_stdin_context(json.dumps({"data": {"effort": {"level": "max"}}}))
        self.assertEqual(ctx["effort"], "max")

    def test_hostile_types_do_not_raise(self):
        payload = {
            "effort": [], "thinking": 3, "agent": "x", "pr": 7,
            "fast_mode": "yes", "context_window": None, "cost": [],
            "model": 1, "worktree": "no", "rate_limits": "none",
        }
        # json.dumps then parse — must return a dict, not explode.
        self.assertIsInstance(cs._parse_stdin_context(json.dumps(payload)), dict)

    def test_json_scalar_payloads(self):
        for scalar in ("null", "3", '"text"', "[]"):
            self.assertIsInstance(cs._parse_stdin_context(scalar), dict)


class RateLimitWindowsTest(unittest.TestCase):
    """Every window Claude Code sends must survive into `_rate_limits`.

    Regression: the parser looped over a hardcoded tuple that listed only
    five_hour / seven_day / _opus / _sonnet, so a Fable weekly cap present on
    stdin was silently dropped and the bar never appeared.
    """

    def test_all_model_scoped_windows_are_kept(self):
        ctx = parse({"rate_limits": {
            "five_hour": {"used_percentage": 10, "resets_at": 1900000000},
            "seven_day": {"used_percentage": 20, "resets_at": 1900000000},
            "seven_day_opus": {"used_percentage": 30, "resets_at": 1900000000},
            "seven_day_sonnet": {"used_percentage": 40, "resets_at": 1900000000},
            "seven_day_fable": {"used_percentage": 50, "resets_at": 1900000000},
        }})
        self.assertEqual(
            sorted(ctx["_rate_limits"]),
            ["five_hour", "seven_day", "seven_day_fable",
             "seven_day_opus", "seven_day_sonnet"],
        )
        self.assertEqual(ctx["_rate_limits"]["seven_day_fable"]["utilization"], 50.0)

    def test_future_model_window_picked_up_without_code_change(self):
        ctx = parse({"rate_limits": {
            "seven_day_newmodel": {"used_percentage": 7, "resets_at": 1900000000},
        }})
        self.assertIn("seven_day_newmodel", ctx["_rate_limits"])

    def test_epoch_converted_to_iso(self):
        ctx = parse({"rate_limits": {"five_hour": {"used_percentage": 1, "resets_at": 1900000000}}})
        self.assertTrue(ctx["_rate_limits"]["five_hour"]["resets_at"].startswith("20"))

    def test_missing_percentage_skipped(self):
        ctx = parse({"rate_limits": {"five_hour": {"resets_at": 1900000000}}})
        self.assertNotIn("five_hour", ctx.get("_rate_limits", {}))

    def test_non_dict_window_skipped(self):
        ctx = parse({"rate_limits": {"seven_day_x": "nope", "five_hour": {"used_percentage": 1}}})
        self.assertNotIn("seven_day_x", ctx.get("_rate_limits", {}))

    def test_bad_resets_at_keeps_the_window(self):
        ctx = parse({"rate_limits": {"five_hour": {"used_percentage": 5, "resets_at": "junk"}}})
        self.assertEqual(ctx["_rate_limits"]["five_hour"]["utilization"], 5.0)

    def test_one_malformed_window_does_not_drop_the_others(self):
        """Regression: a shared try/except around the loop meant a single bad
        `used_percentage` aborted it, silently discarding every window after
        the poisoned one — the weekly and per-model bars would just vanish."""
        ctx = parse({"rate_limits": {
            "five_hour": {"used_percentage": 10, "resets_at": 1900000000},
            "seven_day": {"used_percentage": "not-a-number"},
            "seven_day_fable": {"used_percentage": 50, "resets_at": 1900000000},
            "seven_day_opus": {"used_percentage": 30, "resets_at": 1900000000},
        }})
        self.assertEqual(
            sorted(ctx["_rate_limits"]),
            ["five_hour", "seven_day_fable", "seven_day_opus"],
        )

    def test_bad_resets_at_does_not_drop_the_window(self):
        for bad in ("junk", None, [], {}, float("inf"), 10 ** 30):
            ctx = parse({"rate_limits": {"five_hour": {"used_percentage": 5, "resets_at": bad}}})
            self.assertEqual(ctx["_rate_limits"]["five_hour"]["utilization"], 5.0, repr(bad))


class SessionStateClearsTest(unittest.TestCase):
    """Session-state fields must be able to turn back off.

    Regression: these were recorded only when *on*, and main() persists stdin
    context across refreshes treating an absent key as "unchanged". So the
    ⚡fast badge stuck permanently after a single fast-mode turn — it was still
    displayed with Fast mode switched off in Claude Code. The same applied to
    effort and the PR badge.

    Both shapes must clear it: the field sent explicitly as false, and the
    field dropped from the payload entirely.
    """

    FULL = {"session_id": "s1", "model": {"id": "claude-opus-5"},
            "workspace": {"current_dir": "."}}

    def test_explicit_false_clears_fast_mode(self):
        self.assertIs(parse({**self.FULL, "fast_mode": True})["fast_mode"], True)
        self.assertIs(parse({**self.FULL, "fast_mode": False})["fast_mode"], False)

    def test_omitted_field_clears_on_a_full_payload(self):
        self.assertIs(parse(self.FULL)["fast_mode"], False)
        self.assertIsNone(parse(self.FULL)["effort"])
        self.assertIsNone(parse(self.FULL)["pr_number"])
        self.assertIsNone(parse(self.FULL)["agent_name"])

    def test_effort_clears(self):
        self.assertEqual(parse({**self.FULL, "effort": {"level": "max"}})["effort"], "max")
        self.assertIsNone(parse({**self.FULL, "effort": {"level": "unset"}})["effort"])
        self.assertIsNone(parse({**self.FULL, "effort": {}})["effort"])

    def test_pr_clears_when_leaving_the_branch(self):
        on = parse({**self.FULL, "pr": {"number": 7, "url": "https://x/y", "review_state": "approved"}})
        self.assertEqual(on["pr_number"], 7)
        off = parse({**self.FULL, "pr": None})
        self.assertIsNone(off["pr_number"])
        self.assertIsNone(off["pr_url"])

    def test_fragment_payload_does_not_clear(self):
        """A partial payload (no session identity) must not wipe known state —
        absent there really does mean 'unknown', not 'off'."""
        frag = parse({"cost": {"total_cost_usd": 1.0}})
        self.assertNotIn("fast_mode", frag)
        self.assertNotIn("effort", frag)

    def test_thinking_tri_state(self):
        self.assertIs(parse({**self.FULL, "thinking": {"enabled": True}})["thinking"], True)
        self.assertIs(parse({**self.FULL, "thinking": {"enabled": False}})["thinking"], False)
        self.assertIsNone(parse(self.FULL)["thinking"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
