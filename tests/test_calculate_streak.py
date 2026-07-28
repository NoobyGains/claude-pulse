"""Tests for the daily-usage streak calculator (``_calculate_streak``).

The stats view shows a "current" and "longest" streak of consecutive days on
which Claude was used.  The function is pure — it takes a list of ``YYYY-MM-DD``
strings plus a "today" string and returns ``(current, longest)`` — so it can be
exercised without touching the filesystem or the clock.

Cases pinned here:

* the empty / all-garbage inputs return ``(0, 0)`` instead of raising;
* the current streak counts back from *today*, and also from *yesterday* when
  today has not been logged yet (so an active streak isn't dropped mid-day);
* a gap breaks the current streak but the longest run is still reported;
* duplicate and unsorted dates are deduplicated and ordered first;
* an unparseable ``today`` is handled, and stray bad entries are skipped.

Run: ``python tests/test_calculate_streak.py``
"""
import sys
import unittest
from datetime import date, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import claude_status as cs  # noqa: E402


def _days(anchor, offsets):
    """Return ``YYYY-MM-DD`` strings ``offsets`` days before ``anchor``."""
    return [(anchor - timedelta(days=n)).strftime("%Y-%m-%d") for n in offsets]


class CalculateStreakTest(unittest.TestCase):
    def setUp(self):
        self.today = date(2026, 7, 17)
        self.today_str = self.today.strftime("%Y-%m-%d")

    def test_empty_input_is_zero_zero(self):
        self.assertEqual(cs._calculate_streak([], self.today_str), (0, 0))

    def test_all_unparseable_dates_is_zero_zero(self):
        self.assertEqual(
            cs._calculate_streak(["not-a-date", "2026-13-99"], self.today_str),
            (0, 0),
        )

    def test_bad_today_is_zero_zero(self):
        # A valid history but a garbage "today" cannot anchor a current streak.
        self.assertEqual(
            cs._calculate_streak(_days(self.today, [0, 1, 2]), "garbage"),
            (0, 0),
        )

    def test_streak_ending_today(self):
        # today, yesterday, day-before => 3 consecutive ending on today.
        dates = _days(self.today, [0, 1, 2])
        self.assertEqual(cs._calculate_streak(dates, self.today_str), (3, 3))

    def test_streak_ending_yesterday_when_today_not_logged(self):
        # Today isn't in the list yet; a run ending yesterday still counts as
        # the current streak so an active streak isn't lost before you log today.
        # Regression: the fallback compared against `check_ord + 1` (tomorrow),
        # so it never matched and an active streak read as 0 all morning.
        dates = _days(self.today, [1, 2, 3])
        self.assertEqual(cs._calculate_streak(dates, self.today_str), (3, 3))

    def test_gap_breaks_current_but_longest_survives(self):
        # A 4-day run two weeks ago, then today alone.
        old = _days(self.today, [10, 11, 12, 13])
        dates = old + _days(self.today, [0])
        current, longest = cs._calculate_streak(dates, self.today_str)
        self.assertEqual(current, 1, "only today is current after the gap")
        self.assertEqual(longest, 4, "the old 4-day run is the longest")

    def test_stale_history_has_no_current_streak(self):
        # Newest entry is two days before today (not today, not yesterday).
        dates = _days(self.today, [2, 3, 4])
        current, longest = cs._calculate_streak(dates, self.today_str)
        self.assertEqual(current, 0, "nothing logged today or yesterday")
        self.assertEqual(longest, 3)

    def test_duplicates_and_unsorted_are_normalised(self):
        dates = _days(self.today, [1, 0, 2, 1, 0])  # shuffled + repeats
        self.assertEqual(cs._calculate_streak(dates, self.today_str), (3, 3))

    def test_single_day_today(self):
        self.assertEqual(
            cs._calculate_streak([self.today_str], self.today_str), (1, 1)
        )

    def test_mixed_valid_and_garbage_entries(self):
        dates = _days(self.today, [0, 1]) + ["oops", "2026-99-99"]
        self.assertEqual(cs._calculate_streak(dates, self.today_str), (2, 2))


if __name__ == "__main__":
    unittest.main(verbosity=2)
