"""Tests for status-line rendering: widths, hyperlinks, and row layout.

The status line writes raw ANSI to a terminal, so the width maths has to be
exactly right — a miscount either truncates visible text early or lets the line
spill into Claude Code's notification area.  Three things are pinned here:

* ``_visible_len`` / ``_skip_escape`` count only printable columns, including
  across OSC 8 hyperlinks (whose URLs contain letters that terminate a *CSI*
  sequence, so a colour-only scanner walks straight into the URL);
* ``_osc8`` refuses to linkify anything that could break out of the escape;
* ``_join_parts`` splits widgets across two rows per ``line1_widgets`` /
  ``line2_widgets``, and ``_fit_line`` fits each row against its own budget.

Run: ``python tests/test_rendering.py``
"""
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import claude_status as cs  # noqa: E402

URL = "https://github.com/owner/repo/pull/1234"


class VisibleLenTest(unittest.TestCase):
    def test_plain_text(self):
        self.assertEqual(cs._visible_len("hello"), 5)

    def test_colour_codes_are_free(self):
        self.assertEqual(cs._visible_len(f"{cs.GREEN}abc{cs.RESET}"), 3)

    def test_hyperlink_url_is_not_counted(self):
        """Regression: the CSI terminator set contains 'h', so a naive scanner
        stopped at the 'h' of 'https' and counted the whole URL as visible."""
        link = cs._osc8(URL, "#1234")
        self.assertEqual(cs._visible_len(link), len("#1234"))

    def test_hyperlink_embedded_in_a_line(self):
        line = f"ab{cs._osc8(URL, '#1')}cd"
        self.assertEqual(cs._visible_len(line), len("ab#1cd"))

    def test_unterminated_escape_does_not_hang(self):
        # Consumes the remainder rather than looping forever.
        self.assertEqual(cs._visible_len("\033]8;;no-terminator"), 0)

    def test_empty(self):
        self.assertEqual(cs._visible_len(""), 0)


class Osc8Test(unittest.TestCase):
    def test_wraps_label(self):
        link = cs._osc8(URL, "#1234")
        self.assertTrue(link.startswith(cs.OSC8_START))
        self.assertTrue(link.endswith(cs.OSC8_END))
        self.assertIn("#1234", link)

    def test_no_url_returns_bare_label(self):
        self.assertEqual(cs._osc8("", "#1"), "#1")
        self.assertEqual(cs._osc8(None, "#1"), "#1")

    def test_control_characters_are_refused(self):
        """A URL containing BEL/ESC/newline/; could terminate the escape early
        and let arbitrary text reach the terminal as a control sequence."""
        for bad in ("http://x\a", "http://x\033[0m", "http://x\ny", "http://x;y"):
            self.assertEqual(cs._osc8(bad, "L"), "L", f"{bad!r} must not be linkified")


class JoinPartsTest(unittest.TestCase):
    def _parts(self):
        return [
            ((10, "session"), "SESSION"),
            ((60, "context"), "CONTEXT"),
            ((110, "model"), "MODEL"),
            ((170, "branch"), "BRANCH"),
        ]

    def test_single_row_by_default(self):
        out = cs._join_parts(self._parts(), {})
        self.assertNotIn("\n", out)
        self.assertEqual(out, "SESSION | CONTEXT | MODEL | BRANCH")

    def test_line2_widgets_demotes_named_ids(self):
        out = cs._join_parts(self._parts(), {"line2_widgets": ["model", "branch"]})
        self.assertEqual(out.split("\n"), ["SESSION | CONTEXT", "MODEL | BRANCH"])

    def test_line1_widgets_is_an_allowlist(self):
        out = cs._join_parts(self._parts(), {"line1_widgets": ["session"]})
        self.assertEqual(out.split("\n"), ["SESSION", "CONTEXT | MODEL | BRANCH"])

    def test_line1_wins_when_both_set(self):
        out = cs._join_parts(
            self._parts(),
            {"line1_widgets": ["session"], "line2_widgets": ["context"]},
        )
        self.assertEqual(out.split("\n")[0], "SESSION")

    def test_empty_row_is_dropped_not_blank(self):
        out = cs._join_parts(self._parts(), {"line2_widgets": ["nothing-matches"]})
        self.assertNotIn("\n", out)

    def test_all_demoted_yields_one_row(self):
        ids = ["session", "context", "model", "branch"]
        out = cs._join_parts(self._parts(), {"line2_widgets": ids})
        self.assertNotIn("\n", out)

    def test_malformed_config_falls_back_to_one_row(self):
        for cfg in ({"line2_widgets": "model"}, {"line1_widgets": 7}, None, "nope"):
            self.assertNotIn("\n", cs._join_parts(self._parts(), cfg))


class FitLineTest(unittest.TestCase):
    def test_each_row_fitted_independently(self):
        cfg = {"max_width": 100}
        two = "AAAA | BBBB\nCCCC | DDDD"
        out = cs._fit_line(two, cfg)
        self.assertEqual(len(out.split("\n")), 2)

    def test_single_row_unchanged_when_it_fits(self):
        self.assertNotIn("\n", cs._fit_line("short", {"max_width": 100}))

    def test_truncation_closes_an_open_hyperlink(self):
        """Cutting inside an OSC 8 link without closing it makes the terminal
        treat everything after as part of the link target."""
        long_label = "X" * 400
        line = cs._osc8(URL, long_label)
        out = cs._truncate_line(line, {"max_width": 20})
        self.assertTrue(out.endswith(cs.OSC8_END + cs.RESET) or cs.OSC8_END in out)


class RefreshIntervalTest(unittest.TestCase):
    def test_animation_gets_the_fast_tick(self):
        self.assertEqual(
            cs._desired_refresh_interval({"animate": "rainbow"}), cs.REFRESH_ANIMATED
        )

    def test_time_based_widget_gets_the_slow_tick(self):
        cfg = {"animate": "off", "show": {"heartbeat": True, "pomodoro": False}}
        self.assertEqual(cs._desired_refresh_interval(cfg), cs.REFRESH_TIMED)

    def test_static_bar_needs_no_timer(self):
        cfg = {"animate": "off", "show": {"heartbeat": False, "pomodoro": False}}
        self.assertIsNone(cs._desired_refresh_interval(cfg))

    def test_garbage_config_is_safe(self):
        for cfg in (None, "x", 3, []):
            self.assertIsNone(cs._desired_refresh_interval(cfg))


class RateLimitBackoffTest(unittest.TestCase):
    def test_first_failure_waits_about_a_minute(self):
        delay, fails = cs._rate_limit_backoff(0)
        self.assertEqual(fails, 1)
        self.assertGreaterEqual(delay, cs._RATE_LIMIT_BACKOFF_BASE)
        self.assertLessEqual(delay, cs._RATE_LIMIT_BACKOFF_BASE + cs._RATE_LIMIT_JITTER)

    def test_backoff_doubles(self):
        d1, f1 = cs._rate_limit_backoff(0)
        d2, f2 = cs._rate_limit_backoff(f1)
        self.assertEqual(f2, 2)
        self.assertGreaterEqual(d2, 2 * cs._RATE_LIMIT_BACKOFF_BASE)

    def test_capped(self):
        delay, _ = cs._rate_limit_backoff(50)
        self.assertLessEqual(delay, cs._RATE_LIMIT_BACKOFF_MAX + cs._RATE_LIMIT_JITTER)

    def test_absurd_count_does_not_build_a_huge_int(self):
        delay, _ = cs._rate_limit_backoff(10 ** 9)
        self.assertLessEqual(delay, cs._RATE_LIMIT_BACKOFF_MAX + cs._RATE_LIMIT_JITTER)

    def test_garbage_count_treated_as_first_failure(self):
        for bad in (None, "x", -5, [], {}):
            delay, fails = cs._rate_limit_backoff(bad)
            self.assertEqual(fails, 1, f"{bad!r}")


class CorruptStateResilienceTest(unittest.TestCase):
    """Our own state files are still untrusted input.

    A truncated write, a disk error, or a hand-edit can leave *valid JSON of
    the wrong shape*. These paths run on every repaint, so raising blanks the
    user's status bar. All found by adversarial review.
    """

    def test_read_cache_survives_wrong_shaped_json(self):
        import json
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "c.json"
            for junk in ("[1, 2]", '"a string"', "42", "null",
                         '{"timestamp": "bad"}', '{"timestamp": null}'):
                p.write_text(junk, encoding="utf-8")
                self.assertIsNone(cs.read_cache(p, 60), junk)

    def test_write_cache_survives_non_dict_usage(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "c.json"
            for bad in ("not-a-dict", [1, 2], 7, True):
                cs.write_cache(p, "line", usage=bad)  # must not raise

    def test_sync_refresh_survives_wrong_shaped_settings(self):
        import os
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            os.environ["CLAUDE_CONFIG_DIR"] = td
            try:
                for junk in ("[]", '"x"', "5", "null"):
                    (Path(td) / "settings.json").write_text(junk, encoding="utf-8")
                    self.assertIs(cs.sync_status_line_refresh({"animate": "off"}), False, junk)
            finally:
                os.environ.pop("CLAUDE_CONFIG_DIR", None)

    def test_cache_age_of_corrupt_entry_is_infinite(self):
        self.assertEqual(cs._cache_age({"timestamp": "bad"}), float("inf"))
        self.assertEqual(cs._cache_age([]), float("inf"))
        self.assertLess(cs._cache_age({"timestamp": __import__("time").time()}), 5)


class CsiGrammarTest(unittest.TestCase):
    """_skip_escape follows the ECMA-48 CSI grammar, not a hand-listed set.

    A long true-colour SGR exceeded the old 25-byte scan cap, so the tail was
    counted as visible width and the line truncated far too early.
    """

    def test_long_truecolour_sgr_is_consumed_whole(self):
        seq = "[38;2;255;128;64;48;2;0;0;0;1;4;7m"
        self.assertEqual(cs._visible_len(seq + "AB"), 2)

    def test_ordinary_sgr(self):
        self.assertEqual(cs._visible_len("[0m" + "abc"), 3)
        self.assertEqual(cs._visible_len("[1;31mX"), 1)

    def test_csi_with_intermediate_bytes(self):
        self.assertEqual(cs._visible_len("[?25lZ"), 1)

    def test_bare_escape_and_trailing_escape(self):
        self.assertEqual(cs._visible_len("cQ"), 1)
        self.assertEqual(cs._visible_len("ab"), 2)

    def test_unterminated_csi_does_not_overrun(self):
        self.assertEqual(cs._visible_len("[38;2;255"), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
