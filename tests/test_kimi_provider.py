"""Tests for the optional Kimi provider extension.

When Claude Code is pointed at Kimi's Anthropic-compatible endpoints via
``kimiclaude``, the same four stdin fields the MiniMax block corrects are wrong
again — but the two Kimi backends are wrong in different ways, so both are
pinned here:

* **Kimi Code subscription** (``api.kimi.ai``/``api.kimi.com``) — a flat-rate
  plan: 256K window, zero marginal cost, quota from ``GET {base}/v1/usages``.
* **Kimi open platform** (``api.moonshot.ai``) — pay-per-token: 1M window for
  K3, cost recomputed from published rates, no plan quota.

These tests pin four things:

* the env gate (the block must be inert for normal Anthropic sessions, and for
  a Kimi host with a non-Kimi model);
* the corrections (context %, token counts, per-backend cost);
* the quota reshape, including the string-typed counts the API really returns;
* robustness — malformed stdin, malformed quota JSON, an expired token or a
  dead endpoint must never raise, because a status line that throws crashes
  Claude Code's status bar.

Run: ``python tests/test_kimi_provider.py``
"""
import json
import sys
import tempfile
import time
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import claude_status as cs  # noqa: E402


SUBSCRIPTION_ENV = {
    "ANTHROPIC_BASE_URL": "https://api.kimi.ai/coding",
    "ANTHROPIC_MODEL": "k3",
}
PLATFORM_ENV = {
    "ANTHROPIC_BASE_URL": "https://api.moonshot.ai/anthropic",
    "ANTHROPIC_MODEL": "kimi-k3",
}

# The shape of a real `GET https://api.kimi.ai/coding/v1/usages` response, with
# the account fields replaced by placeholders. Note every count is a *string* —
# the parser has to coerce them.
LIVE_USAGE = {
    "user": {"userId": "example-user", "membership": {"level": "LEVEL_BASIC"}},
    "limited": True,
    "usage": {
        "limit": "100", "used": "21", "remaining": "79",
        "resetTime": "2026-08-29T18:31:10.072847Z",
    },
    "limits": [{
        "window": {"duration": 300, "timeUnit": "TIME_UNIT_MINUTE"},
        "detail": {
            "limit": "100", "used": "100",
            "resetTime": "2026-08-22T23:31:10.072847Z",
        },
    }],
    "parallel": {"limit": "10"},
}


def _stdin(input_tokens, output_tokens, used_percentage=12.0, cost=9.99):
    """Build a Claude Code stdin JSON blob with a context_window + cost."""
    return json.dumps({
        "context_window": {
            "used_percentage": used_percentage,
            "total_input_tokens": input_tokens,
            "total_output_tokens": output_tokens,
            "context_window_size": 200_000,  # the shim's wrong value
        },
        "cost": {"total_cost_usd": cost},
    })


class _KimiTestCase(unittest.TestCase):
    """Base case that isolates the module-level quota cache.

    ``_kimi_usage_mem`` is process-global, so without this a cached result from
    one test leaks into the next (and into whatever the developer's real
    machine cached).
    """

    def setUp(self):
        self._saved_mem = dict(cs._kimi_usage_mem)
        cs._kimi_usage_mem.update(ts=0, data=None)
        self.addCleanup(lambda: cs._kimi_usage_mem.update(self._saved_mem))


class UsageParserTest(_KimiTestCase):
    def test_live_payload_maps_both_windows(self):
        out = cs._parse_kimi_usage(LIVE_USAGE)
        # 300-minute rolling window, fully spent -> Session bar at 100%.
        self.assertAlmostEqual(out["five_hour"]["utilization"], 100.0)
        # Plan period 21/100 -> Weekly bar at 21%.
        self.assertAlmostEqual(out["seven_day"]["utilization"], 21.0)
        # Reset stamps normalised to something datetime.fromisoformat accepts.
        self.assertTrue(out["seven_day"]["resets_at"].startswith("2026-08-29"))
        from datetime import datetime
        datetime.fromisoformat(out["five_hour"]["resets_at"])  # must not raise

    def test_shortest_window_wins(self):
        payload = {"limits": [
            {"window": {"duration": 7, "timeUnit": "TIME_UNIT_DAY"},
             "detail": {"limit": "100", "used": "10"}},
            {"window": {"duration": 300, "timeUnit": "TIME_UNIT_MINUTE"},
             "detail": {"limit": "100", "used": "90"}},
        ]}
        out = cs._parse_kimi_usage(payload)
        # The 5-hour window, not the first entry, drives the Session bar.
        self.assertAlmostEqual(out["five_hour"]["utilization"], 90.0)

    def test_one_bad_bucket_does_not_lose_the_other(self):
        payload = {
            "usage": {"limit": "not-a-number", "used": "5"},
            "limits": [{"window": {"duration": 300, "timeUnit": "TIME_UNIT_MINUTE"},
                        "detail": {"limit": "100", "used": "40"}}],
        }
        out = cs._parse_kimi_usage(payload)
        self.assertNotIn("seven_day", out)
        self.assertAlmostEqual(out["five_hour"]["utilization"], 40.0)

    def test_bad_reset_time_keeps_the_percentage(self):
        out = cs._parse_kimi_usage(
            {"usage": {"limit": "100", "used": "50", "resetTime": "garbage"}})
        self.assertAlmostEqual(out["seven_day"]["utilization"], 50.0)
        self.assertIsNone(out["seven_day"]["resets_at"])

    def test_zero_limit_is_dropped_not_divided(self):
        out = cs._parse_kimi_usage({"usage": {"limit": "0", "used": "0"}})
        self.assertEqual(out, {})

    def test_utilization_is_clamped(self):
        out = cs._parse_kimi_usage({"usage": {"limit": "100", "used": "150"}})
        self.assertAlmostEqual(out["seven_day"]["utilization"], 100.0)

    def test_non_dict_input_returns_empty(self):
        self.assertEqual(cs._parse_kimi_usage([]), {})
        self.assertEqual(cs._parse_kimi_usage("nope"), {})
        self.assertEqual(cs._parse_kimi_usage(None), {})

    def test_junk_shapes_do_not_raise(self):
        self.assertEqual(cs._parse_kimi_usage({"limits": "not-a-list"}), {})
        self.assertEqual(cs._parse_kimi_usage({"limits": [None, 3, "x"]}), {})
        self.assertEqual(cs._parse_kimi_usage({"usage": []}), {})


class ContextSizeTest(_KimiTestCase):
    def test_known_ids(self):
        self.assertEqual(cs._kimi_context_size("k3"), 262_144)
        self.assertEqual(cs._kimi_context_size("k3-256k"), 262_144)
        self.assertEqual(cs._kimi_context_size("kimi-for-coding"), 262_144)
        self.assertEqual(cs._kimi_context_size("kimi-k3"), 1_048_576)

    def test_one_megabyte_suffix(self):
        # Claude Code's "[1m]" notation selects the 1M variant.
        self.assertEqual(cs._kimi_context_size("kimi-k3[1m]"), 1_048_576)

    def test_unknown_id_falls_back_to_256k(self):
        self.assertEqual(cs._kimi_context_size("kimi-k9-future"), 262_144)

    def test_backend_detection(self):
        self.assertEqual(cs._kimi_backend("https://api.kimi.ai/coding"), "subscription")
        self.assertEqual(cs._kimi_backend("https://api.kimi.com/coding"), "subscription")
        self.assertEqual(cs._kimi_backend("https://api.moonshot.ai/anthropic"), "platform")
        self.assertIsNone(cs._kimi_backend("https://api.anthropic.com"))
        self.assertIsNone(cs._kimi_backend(""))

    def test_backend_matches_host_not_substring(self):
        """A lookalike host must not be mistaken for Kimi."""
        self.assertIsNone(cs._kimi_backend("https://api.kimi.ai.evil.example/coding"))


class StdinGateTest(_KimiTestCase):
    def test_inactive_without_kimi_env(self):
        # No Kimi env -> block is inert, Anthropic values pass through.
        with mock.patch.dict("os.environ", {}, clear=True):
            res = cs._parse_stdin_context(_stdin(100_000, 50_000, used_percentage=12.0))
        self.assertAlmostEqual(res["context_pct"], 12.0)   # unchanged
        self.assertEqual(res["context_limit"], 200_000)     # unchanged
        self.assertAlmostEqual(res["cost_usd"], 9.99)       # unchanged

    def test_inactive_for_non_kimi_model_on_kimi_host(self):
        env = {"ANTHROPIC_BASE_URL": "https://api.kimi.ai/coding",
               "ANTHROPIC_MODEL": "claude-opus-5"}
        with mock.patch.dict("os.environ", env, clear=True):
            res = cs._parse_stdin_context(_stdin(100_000, 50_000))
        self.assertEqual(res["context_limit"], 200_000)     # unchanged
        self.assertAlmostEqual(res["cost_usd"], 9.99)       # unchanged

    def test_subscription_corrects_context_and_zeroes_cost(self):
        with mock.patch.dict("os.environ", SUBSCRIPTION_ENV, clear=True), \
                mock.patch.object(cs, "_get_cached_kimi_usage", return_value={}):
            res = cs._parse_stdin_context(_stdin(100_000, 31_072, used_percentage=12.0))
        # 131,072 / 262,144 = 50%, not the shim's 12% against 200K.
        self.assertAlmostEqual(res["context_pct"], 50.0)
        self.assertEqual(res["context_used"], 131_072)
        self.assertEqual(res["context_limit"], 262_144)
        # Flat-rate plan: no marginal per-token cost.
        self.assertAlmostEqual(res["cost_usd"], 0.0)

    def test_platform_recomputes_cost_at_published_rates(self):
        with mock.patch.dict("os.environ", PLATFORM_ENV, clear=True):
            res = cs._parse_stdin_context(_stdin(100_000, 50_000, cost=9.99))
        self.assertEqual(res["context_limit"], 1_048_576)   # real K3 window
        # 100k * $3.00/1M + 50k * $15.00/1M = 0.30 + 0.75 = 1.05
        self.assertAlmostEqual(res["cost_usd"], 1.05)
        self.assertNotAlmostEqual(res["cost_usd"], 9.99)    # not Anthropic price

    def test_platform_never_fetches_quota(self):
        """There is no plan quota on the pay-per-token platform, so the block
        must not reach for the subscription endpoint."""
        with mock.patch.dict("os.environ", PLATFORM_ENV, clear=True), \
                mock.patch.object(cs, "_get_cached_kimi_usage") as fetch:
            cs._parse_stdin_context(_stdin(10, 10))
        fetch.assert_not_called()

    def test_quota_populates_rate_limits(self):
        with mock.patch.dict("os.environ", SUBSCRIPTION_ENV, clear=True), \
                mock.patch.object(cs, "_kimi_access_token", return_value="tok"), \
                mock.patch.object(cs, "_fetch_kimi_usage", return_value=LIVE_USAGE), \
                mock.patch.object(cs, "get_state_dir", return_value=Path(tempfile.mkdtemp())):
            res = cs._parse_stdin_context(_stdin(10, 10))
        self.assertAlmostEqual(res["_rate_limits"]["five_hour"]["utilization"], 100.0)
        self.assertAlmostEqual(res["_rate_limits"]["seven_day"]["utilization"], 21.0)

    def test_stdin_rate_limits_win_over_the_plan_endpoint(self):
        """Only fill the gap — never override rate_limits Claude Code supplied."""
        blob = json.loads(_stdin(10, 10))
        blob["rate_limits"] = {
            "five_hour": {"used_percentage": 42, "resets_at": 1_900_000_000},
        }
        with mock.patch.dict("os.environ", SUBSCRIPTION_ENV, clear=True), \
                mock.patch.object(cs, "_get_cached_kimi_usage") as fetch:
            res = cs._parse_stdin_context(json.dumps(blob))
        fetch.assert_not_called()
        self.assertAlmostEqual(res["_rate_limits"]["five_hour"]["utilization"], 42)

    def test_malformed_tokens_do_not_raise(self):
        bad = json.dumps({"context_window": {"total_input_tokens": "oops"},
                          "cost": {"total_cost_usd": 1.0}})
        with mock.patch.dict("os.environ", SUBSCRIPTION_ENV, clear=True), \
                mock.patch.object(cs, "_get_cached_kimi_usage", return_value={}):
            res = cs._parse_stdin_context(bad)  # must not raise
        self.assertIsInstance(res, dict)

    def test_dead_endpoint_is_silent(self):
        with mock.patch.dict("os.environ", SUBSCRIPTION_ENV, clear=True), \
                mock.patch.object(cs, "_kimi_access_token", return_value="tok"), \
                mock.patch.object(cs, "get_state_dir", return_value=Path(tempfile.mkdtemp())), \
                mock.patch.object(cs.urllib.request, "Request",
                                  side_effect=urllib.error.URLError("down")):
            res = cs._parse_stdin_context(_stdin(10, 10))  # must not raise
        self.assertNotIn("_rate_limits", res)


class AccessTokenTest(_KimiTestCase):
    def _write_creds(self, tmp, token, expires_at):
        cred_dir = Path(tmp) / "credentials"
        cred_dir.mkdir(parents=True, exist_ok=True)
        (cred_dir / "kimi-code-env-abc.json").write_text(
            json.dumps({"access_token": token, "expires_at": expires_at}),
            encoding="utf-8")
        return tmp

    def test_reads_a_valid_token(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._write_creds(tmp, "live-token", time.time() + 600)
            with mock.patch.dict("os.environ", {"KIMI_CODE_HOME": tmp}, clear=True):
                self.assertEqual(cs._kimi_access_token(), "live-token")

    def test_expired_token_is_skipped(self):
        """Pulse must never refresh: Kimi rotates both tokens on refresh, so a
        status line racing the CLI would invalidate the user's session."""
        with tempfile.TemporaryDirectory() as tmp:
            self._write_creds(tmp, "stale-token", time.time() - 1)
            with mock.patch.dict("os.environ", {"KIMI_CODE_HOME": tmp}, clear=True):
                self.assertIsNone(cs._kimi_access_token())

    def test_missing_or_corrupt_credentials_return_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict("os.environ", {"KIMI_CODE_HOME": tmp}, clear=True):
                self.assertIsNone(cs._kimi_access_token())  # no credentials dir
            cred_dir = Path(tmp) / "credentials"
            cred_dir.mkdir()
            (cred_dir / "broken.json").write_text("{not json", encoding="utf-8")
            with mock.patch.dict("os.environ", {"KIMI_CODE_HOME": tmp}, clear=True):
                self.assertIsNone(cs._kimi_access_token())


class FetchSafetyTest(_KimiTestCase):
    def test_refuses_to_send_the_token_off_a_kimi_host(self):
        """The bearer token must only ever reach a Kimi host — a misconfigured
        ANTHROPIC_BASE_URL must not turn into token exfiltration."""
        with mock.patch.object(cs.urllib.request, "Request") as req:
            self.assertIsNone(
                cs._fetch_kimi_usage("https://evil.example/coding", "tok"))
        req.assert_not_called()

    def test_builds_the_usages_url_once(self):
        """Base URLs are written both with and without a trailing /v1."""
        seen = []

        class _Resp:
            def read(self):
                return b"{}"

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        def _fake_open(req, timeout=None):
            seen.append(req.full_url)
            return _Resp()

        with mock.patch.object(cs._safe_opener, "open", side_effect=_fake_open):
            cs._fetch_kimi_usage("https://api.kimi.ai/coding", "tok")
            cs._fetch_kimi_usage("https://api.kimi.ai/coding/", "tok")
            cs._fetch_kimi_usage("https://api.kimi.ai/coding/v1", "tok")
        self.assertEqual(seen, ["https://api.kimi.ai/coding/v1/usages"] * 3)

    def test_redirects_are_blocked_by_the_shared_opener(self):
        """_safe_opener's allowlist is Anthropic-only, so any redirect — even
        to another Kimi host — is refused before the token is re-sent."""
        handler = cs._NoRedirectHandler()
        with self.assertRaises(urllib.error.HTTPError):
            handler.redirect_request(
                mock.Mock(), mock.Mock(), 302, "Found", {},
                "https://evil.example/steal")


class UsageCacheTest(_KimiTestCase):
    def test_second_call_within_ttl_does_not_refetch(self):
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(cs, "get_state_dir", return_value=Path(tmp)), \
                mock.patch.object(cs, "_kimi_access_token", return_value="tok"), \
                mock.patch.object(cs, "_fetch_kimi_usage",
                                  return_value=LIVE_USAGE) as fetch:
            first = cs._get_cached_kimi_usage("https://api.kimi.ai/coding")
            second = cs._get_cached_kimi_usage("https://api.kimi.ai/coding")
        self.assertEqual(fetch.call_count, 1)   # one request, not two
        self.assertEqual(first, second)
        self.assertAlmostEqual(first["seven_day"]["utilization"], 21.0)

    def test_cache_is_keyed_on_host(self):
        """The global and mainland hosts are separate accounts, so a cached
        answer for one must never be served for the other."""
        other = {"usage": {"limit": "100", "used": "60"}}
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(cs, "get_state_dir", return_value=Path(tmp)), \
                mock.patch.object(cs, "_kimi_access_token", return_value="tok"), \
                mock.patch.object(cs, "_fetch_kimi_usage",
                                  side_effect=[LIVE_USAGE, other]) as fetch:
            first = cs._get_cached_kimi_usage("https://api.kimi.ai/coding")
            second = cs._get_cached_kimi_usage("https://api.kimi.com/coding")
        self.assertEqual(fetch.call_count, 2)   # not served from the .ai entry
        self.assertAlmostEqual(first["seven_day"]["utilization"], 21.0)
        self.assertAlmostEqual(second["seven_day"]["utilization"], 60.0)

    def test_failures_are_cached_too(self):
        """A missing token must not mean an HTTP attempt on every repaint."""
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(cs, "get_state_dir", return_value=Path(tmp)), \
                mock.patch.object(cs, "_kimi_access_token",
                                  return_value=None) as token:
            self.assertEqual(cs._get_cached_kimi_usage("https://api.kimi.ai/coding"), {})
            self.assertEqual(cs._get_cached_kimi_usage("https://api.kimi.ai/coding"), {})
        self.assertEqual(token.call_count, 1)

    def test_unwritable_state_dir_is_not_fatal(self):
        """A read-only or full disk costs the cache tier, not the bars."""
        with mock.patch.object(cs, "get_state_dir", side_effect=OSError("read-only")), \
                mock.patch.object(cs, "_kimi_access_token", return_value="tok"), \
                mock.patch.object(cs, "_fetch_kimi_usage", return_value=LIVE_USAGE):
            data = cs._get_cached_kimi_usage("https://api.kimi.ai/coding")
        self.assertAlmostEqual(data["seven_day"]["utilization"], 21.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
