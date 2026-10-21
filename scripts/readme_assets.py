"""Render the README's animated demos from the real script.

Every picture in the README is produced here, so it cannot drift from what the
code draws. The script runs ``claude_status.py`` in-process inside a throwaway
sandbox (nothing of yours is read or written), captures the ANSI output of each
frame, and writes one HTML page per demo to ``assets/_build/``: the frames of a
demo stacked vertically, each drawn inside a terminal window. A screenshot of
each page is sliced into frames and joined into ``assets/<demo>.gif``.

    python scripts/readme_assets.py          # write assets/_build/<demo>.html + .json
    # screenshot each page's <body> at 1x to assets/_build/<demo>.png
    python scripts/readme_assets.py --gif    # slice the PNGs into assets/<demo>.gif (needs Pillow)

The maintainer takes the screenshots with Playwright (an element screenshot of
``body``); any browser that saves the page as a PNG at 1x will do.
"""
import html
import io
import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
BUILD = REPO_ROOT / "assets" / "_build"
ASSETS = REPO_ROOT / "assets"

# ---------------------------------------------------------------------------
# ANSI -> HTML
# ---------------------------------------------------------------------------

# Windows Terminal's "Campbell" scheme, the default most readers see.
_SYSTEM = ["#0c0c0c", "#c50f1f", "#13a10e", "#c19c00", "#0037da", "#881798", "#3a96dd", "#cccccc",
           "#767676", "#e74856", "#16c60c", "#f9f1a5", "#3b78ff", "#b4009e", "#61d6d6", "#f2f2f2"]


def _xterm256(n):
    if n < 16:
        return _SYSTEM[n]
    if n < 232:
        n -= 16
        r, g, b = n // 36, (n // 6) % 6, n % 6
        lv = [0, 95, 135, 175, 215, 255]
        return "#%02x%02x%02x" % (lv[r], lv[g], lv[b])
    v = 8 + 10 * (n - 232)
    return "#%02x%02x%02x" % (v, v, v)


_CSI = re.compile(r"\x1b\[([0-9;?]*)([A-Za-z])")


_OSC = re.compile(r"\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)")   # window titles, OSC 8 hyperlinks


def ansi_to_html(text):
    """Turn SGR-coloured text into spans. Other escapes are dropped."""
    text = _OSC.sub("", text)        # a hyperlinked `#57` keeps its text, loses the link
    out, pos = [], 0
    state = {"fg": None, "bg": None, "bold": False, "dim": False, "rev": False}

    def flush(chunk):
        if not chunk:
            return
        css = []
        fg, bg = state["fg"], state["bg"]
        if state["rev"]:
            fg, bg = (bg or "#0c0c0c"), (fg or "#cccccc")
        if fg:
            css.append(f"color:{fg}")
        if bg:
            css.append(f"background:{bg}")
        if state["bold"]:
            css.append("font-weight:700")
        if state["dim"]:
            css.append("opacity:.55")
        body = html.escape(chunk)
        out.append(f'<span style="{";".join(css)}">{body}</span>' if css else body)

    for m in _CSI.finditer(text):
        flush(text[pos:m.start()])
        pos = m.end()
        if m.group(2) != "m":
            continue
        raw = m.group(1)
        params = [int(p) if p else 0 for p in raw.split(";")] if raw and "?" not in raw else [0]
        i = 0
        while i < len(params):
            p = params[i]
            if p == 0:
                state.update(fg=None, bg=None, bold=False, dim=False, rev=False)
            elif p == 1:
                state["bold"] = True
            elif p == 2:
                state["dim"] = True
            elif p == 7:
                state["rev"] = True
            elif p == 22:
                state["bold"] = state["dim"] = False
            elif p == 27:
                state["rev"] = False
            elif 30 <= p <= 37:
                state["fg"] = _SYSTEM[p - 30]
            elif 90 <= p <= 97:
                state["fg"] = _SYSTEM[p - 90 + 8]
            elif 40 <= p <= 47:
                state["bg"] = _SYSTEM[p - 40]
            elif 100 <= p <= 107:
                state["bg"] = _SYSTEM[p - 100 + 8]
            elif p == 39:
                state["fg"] = None
            elif p == 49:
                state["bg"] = None
            elif p in (38, 48) and i + 1 < len(params):
                key = "fg" if p == 38 else "bg"
                if params[i + 1] == 5 and i + 2 < len(params):
                    state[key] = _xterm256(params[i + 2])
                    i += 2
                elif params[i + 1] == 2 and i + 4 < len(params):
                    state[key] = "#%02x%02x%02x" % tuple(params[i + 2:i + 5])
                    i += 4
            i += 1
    flush(text[pos:])
    return "".join(out)


# ---------------------------------------------------------------------------
# Pages: one demo = a stack of equally sized terminal windows
# ---------------------------------------------------------------------------

LINE_PX = 36          # font 24px / line-height 36px: integers keep the slices exact
CHROME_PX = 130       # frame padding + window border + title bar + terminal padding

PAGE = """<!doctype html>
<meta charset="utf-8">
<title>{title}</title>
<style>
  html, body {{ margin: 0; background: #0b0d12; }}
  body {{ width: max-content; }}
  .frame {{ box-sizing: border-box; padding: 24px 28px; height: {height}px; overflow: hidden;
            background: linear-gradient(135deg, #171b24 0%, #0d1016 100%); }}
  .win {{ border-radius: 12px; overflow: hidden; border: 1px solid #2b313d; background: #0c0c0c;
          box-shadow: 0 18px 40px rgba(0, 0, 0, .55); }}
  .bar {{ box-sizing: border-box; height: 40px; background: #161a21; border-bottom: 1px solid #1f242e;
          display: flex; align-items: center; padding: 0 16px; gap: 8px; }}
  .dot {{ width: 13px; height: 13px; border-radius: 50%; }}
  .r {{ background: #ff5f57; }} .y {{ background: #febc2e; }} .g {{ background: #28c840; }}
  .title {{ margin-left: 10px; color: #8b93a3; font: 500 15px/1 "Segoe UI", system-ui, sans-serif; }}
  .term {{ color: #cccccc; font: 24px/{line}px "Cascadia Mono", "Consolas", "Menlo", "DejaVu Sans Mono", monospace;
           padding: 20px 28px; white-space: pre; height: {lines}px; overflow: hidden; }}
</style>
{frames}
"""

FRAME = """<div class="frame"><div class="win"><div class="bar"><span class="dot r"></span><span class="dot y"></span><span class="dot g"></span><span class="title">{title}</span></div><div class="term">{body}</div></div></div>"""


class Demo:
    """Collects frames (ansi text, title bar text, duration in ms) for one GIF."""

    def __init__(self, name, quantize=128):
        self.name = name
        self.frames = []
        self.quantize = quantize

    def add(self, ansi, title, ms):
        self.frames.append((ansi.rstrip("\n"), title, int(ms)))

    def write(self):
        BUILD.mkdir(parents=True, exist_ok=True)
        lines = max(len(f[0].split("\n")) for f in self.frames)
        blocks = [FRAME.format(title=html.escape(t), body=ansi_to_html(a)) for a, t, _ in self.frames]
        # Every frame is exactly this tall, whatever fallback glyphs do to a
        # line box, so the screenshot slices cleanly.
        page = PAGE.format(title=html.escape(f"usage-pulse: {self.name}"), line=LINE_PX,
                           lines=lines * LINE_PX, height=lines * LINE_PX + CHROME_PX,
                           frames="\n".join(blocks))
        (BUILD / f"{self.name}.html").write_text(page, encoding="utf-8")
        meta = {"frames": len(self.frames), "height": lines * LINE_PX + CHROME_PX,
                "durations": [ms for _, _, ms in self.frames], "quantize": self.quantize,
                "out": f"assets/{self.name}.gif"}
        (BUILD / f"{self.name}.json").write_text(json.dumps(meta), encoding="utf-8")
        cols = max(len(_plain(a).split("\n")[0]) for a, _, _ in self.frames)
        print(f"wrote assets/_build/{self.name}.html  {len(self.frames)} frames, {lines} lines, ~{cols} cols")


def _plain(ansi):
    return _CSI.sub("", ansi)


# ---------------------------------------------------------------------------
# Sandbox around claude_status
# ---------------------------------------------------------------------------

class _Out:
    def __init__(self):
        self.buffer = io.BytesIO()

    def write(self, text):
        self.buffer.write(text.encode("utf-8"))

    def flush(self):
        pass

    def isatty(self):
        return True

    def text(self):
        return self.buffer.getvalue().decode("utf-8")


class Sandbox:
    # Wide enough that nothing is truncated: each frame clips the line at its
    # own edge, the way a terminal does.
    def __init__(self, columns=240):
        self.td = tempfile.TemporaryDirectory(prefix="pulse-readme-")
        self.root = Path(self.td.name)
        self.home = self.root / "home"
        self.cfg = self.home / ".claude"
        self.state = self.root / "state"
        for d in (self.home, self.cfg, self.state):
            d.mkdir(parents=True)
        self.env = mock.patch.dict(os.environ, {
            "HOME": str(self.home), "USERPROFILE": str(self.home),
            "LOCALAPPDATA": str(self.root / "local"),
            "XDG_CACHE_HOME": str(self.root / "xdg-cache"),
            "XDG_CONFIG_HOME": str(self.root / "xdg-config"),
            "CLAUDE_CONFIG_DIR": str(self.cfg), "CODEX_HOME": str(self.root / "codex"),
            "COLUMNS": str(columns),
        })
        self.env.start()
        for k in ("USAGE_PULSE_NONINTERACTIVE", "CLAUDE_PULSE_NONINTERACTIVE"):
            os.environ.pop(k, None)
        import claude_status as cs
        self.cs = cs
        self.now = time.time()
        self.base = self.now      # reset times are relative to this; frames advance self.now
        self.updates = {"pulse": False, "claude": False}
        self.patches = []
        for target, value in (("get_state_dir", lambda: self.state),
                              ("_claude_config_dir", lambda: self.cfg),
                              ("get_config_path", lambda: self.root / "config.json"),
                              ("check_for_update", lambda: self.updates["pulse"]),
                              ("check_claude_code_update", lambda *a, **k: self.updates["claude"]),
                              ("get_credentials", lambda: ("token", "Max 20x")),
                              ("fetch_usage", lambda token, timeout=10: None),
                              ("_enable_windows_ansi", lambda: None)):
            p = mock.patch.object(cs, target, value)
            p.start()
            self.patches.append(p)
        # The script reads the clock for countdowns and animation phases; a
        # frame is one tick of this clock, so the GIFs are reproducible.
        p = mock.patch.object(time, "time", lambda: self.now)
        p.start()
        self.patches.append(p)

    def close(self):
        for p in self.patches:
            p.stop()
        self.env.stop()
        self.td.cleanup()

    def write_config(self, data):
        (self.root / "config.json").write_text(json.dumps(data), encoding="utf-8")

    def run_main(self, payload):
        out, old_out, old_in = _Out(), sys.stdout, sys.stdin
        sys.stdout, sys.stdin = out, io.StringIO(json.dumps(payload))
        try:
            self.cs.main()
        except SystemExit:
            pass
        finally:
            sys.stdout, sys.stdin = old_out, old_in
        return out.text()

    def run_subagent_rows(self, payload):
        out, old_out, old_in = _Out(), sys.stdout, sys.stdin
        sys.stdout, sys.stdin = out, io.StringIO(json.dumps(payload))
        try:
            self.cs.cmd_subagent_status_line()
        finally:
            sys.stdout, sys.stdin = old_out, old_in
        return [json.loads(line)["content"] for line in out.text().splitlines() if line.strip()]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SESSION = "readme-session"


def _next_weekday(weekday, hour):
    t = time.localtime()
    days = (weekday - t.tm_wday) % 7 or 7
    return int(time.mktime((t.tm_year, t.tm_mon, t.tm_mday + days, hour, 0, 0, 0, 0, -1)))


def _windows(five_pct, five_in, seven_pct, seven_at, now):
    return {"five_hour": {"used_percentage": five_pct, "resets_at": int(now + five_in)},
            "seven_day": {"used_percentage": seven_pct, "resets_at": seven_at}}


def payload(sb, session=27, weekly=73, context=35, cost=38.75, added=142, removed=37, **extra):
    p = {
        "session_id": SESSION,
        "model": {"id": "claude-opus-5-5", "display_name": "Opus"},
        "workspace": {"current_dir": str(REPO_ROOT), "project_dir": str(REPO_ROOT),
                      "repo": {"host": "github.com", "owner": "NoobyGains", "name": "usage-pulse"}},
        "cwd": str(REPO_ROOT),
        "version": "2.1.305",
        "effort": {"level": "xhigh"},
        "context_window": {"used_percentage": context, "context_window_size": 1000000},
        "cost": {"total_cost_usd": cost, "total_lines_added": added, "total_lines_removed": removed},
        "rate_limits": _windows(session, 2 * 3600 + 53 * 60, weekly, _next_weekday(4, 15), sb.base),
    }
    p.update(extra)
    return p


_QUIET = {k: False for k in ("lines", "effort", "branch", "subagents", "team", "cost", "model",
                              "context", "providers", "fast_mode", "cache_warm", "repo",
                              "session_name", "burn_rate", "runway", "pace", "pr", "git_drift",
                              "files_changed", "budget", "streak", "sessions")}
CORE = {"context": True, "cost": True, "model": True}


def config(show=None, **extra):
    cfg = {"theme": "default", "layout": "standard", "bar_size": "medium", "bar_style": "classic",
           "currency": "$", "clock_format": "12h", "effort_format": "labeled",
           "show": dict(_QUIET, **(show or {})), "max_width": 0, "wrap": "off",
           "providers_label_main": True, "animate": "off"}
    cfg.update(extra)
    return cfg


def provider_entries(sb, sunny=3, gemini=1, codex=12):
    rows = {
        "sunny": ("Claude (Sunny)", _windows(sunny, 49 * 60, 63, _next_weekday(2, 15), sb.base)),
        "gemini": ("Gemini", _windows(gemini, 94 * 60, 66, _next_weekday(4, 23), sb.base)),
        "codex": ("Codex", _windows(codex, 69 * 60, 2, _next_weekday(6, 2), sb.base)),
    }
    entries = [{"id": "claude:default", "type": "claude", "label": "Claude (Defend)", "enabled": True,
                "dir": str(sb.cfg)}]
    for pid, (label, data) in rows.items():
        path = sb.root / f"{pid}.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        entries.append({"id": f"file:{pid}", "type": "file", "label": label, "enabled": True, "path": str(path)})
    return entries


def fake_login(sb):
    (sb.cfg / ".credentials.json").write_text(json.dumps({"claudeAiOauth": {
        "accessToken": "readme-token", "refreshToken": "readme-refresh",
        "rateLimitTier": "default_claude_max_20x", "expiresAt": int((sb.now + 3600) * 1000)}}),
        encoding="utf-8")


def seed_agents(cs, live, spawned, tasks_done, tasks_total=7, mates=("planner", "implementer", "reviewer")):
    """Reset and replay the hook events that give a given counter state."""
    import shutil
    for sub in ("subagents", "teams"):
        shutil.rmtree(cs.get_state_dir() / sub, ignore_errors=True)
    for name in mates:
        cs._record_team_event("idle", {"session_id": SESSION, "teammate_name": name})
    for i in range(1, tasks_total + 1):
        cs._record_team_event("created", {"session_id": SESSION, "task_id": str(i),
                                          "task_subject": f"Task {i}", "teammate_name": "planner"})
    for i in range(1, tasks_done + 1):
        cs._record_team_event("completed", {"session_id": SESSION, "task_id": str(i),
                                            "task_subject": f"Task {i}", "teammate_name": "implementer"})
    for i in range(1, spawned + 1):
        cs._record_subagent_event("start", {"agent_id": f"a{i}", "session_id": SESSION, "agent_type": "claude"})
        if i <= spawned - live:
            cs._record_subagent_event("stop", {"agent_id": f"a{i}", "session_id": SESSION})


# ---------------------------------------------------------------------------
# Demos
# ---------------------------------------------------------------------------

def demo_hero(sb):
    """A session unfolding: usage climbs, cost ticks, the other rows move too."""
    fake_login(sb)
    d = Demo("hero")
    steps = [  # session, weekly, context, cost, sunny, gemini, codex
        (24, 71, 8, 31.20, 3, 1, 12), (24, 71, 13, 32.05, 3, 1, 12), (25, 71, 19, 33.40, 3, 1, 13),
        (26, 72, 24, 34.90, 4, 1, 13), (27, 72, 29, 36.15, 4, 2, 13), (28, 73, 33, 37.60, 4, 2, 14),
        (29, 73, 35, 38.75, 4, 2, 14), (30, 74, 38, 39.80, 5, 2, 14), (31, 74, 41, 40.65, 5, 2, 15),
    ]
    for i, (s, w, c, cost, su, ge, co) in enumerate(steps):
        sb.now += 60 * 4        # four minutes a frame: well inside every row's reset time
        sb.write_config(config(dict(CORE, providers=True), providers=provider_entries(sb, su, ge, co)))
        d.add(sb.run_main(payload(sb, s, w, c, cost)), "usage-pulse · live", 2600 if i == len(steps) - 1 else 1000)
    d.write()


def demo_themes(sb):
    cs = sb.cs
    fake_login(sb)
    d = Demo("themes")
    for name in cs.THEMES:
        sb.write_config(config(dict(CORE, providers=True), theme=name,
                               providers=provider_entries(sb)[:2]))   # main line + one row
        d.add(sb.run_main(payload(sb, 42, 67, 35)), f"usage-pulse · theme: {name}", 1100)
    d.write()


def demo_rainbow(sb):
    """The rainbow animation: the hue drifts with the clock, one tick per frame."""
    d = Demo("rainbow", quantize=256)
    sb.write_config(config(CORE, animate="rainbow", animation_speed="normal"))
    for _ in range(20):
        sb.now += 0.0625        # hue_drift = t * 0.8: twenty ticks make one full cycle
        d.add(sb.run_main(payload(sb, 42, 67, 35)), "usage-pulse · --animate rainbow", 90)
    d.write()


def demo_layouts(sb):
    cs = sb.cs
    d = Demo("layouts")
    for layout in cs.LAYOUTS:
        sb.write_config(config(CORE, layout=layout))
        d.add(sb.run_main(payload(sb)), f"usage-pulse · --layout {layout}", 1500)
    d.write()


def demo_widgets(sb):
    """The same bar with more and more widgets switched on."""
    d = Demo("widgets")
    base = dict(CORE, lines=True, effort=True, branch=True)
    stages = [  # title, extra widgets (they go to row 2), extra stdin fields
        ("the defaults", {}, {}),
        ("+ repo · session name · cache warmth", {"repo": True, "session_name": True, "cache_warm": True},
         {"session_name": "refactor auth",
          "prompt_cache": {"warm": True, "hit_ratio": 0.92, "expires_at": sb.base + 180}}),
        ("+ pace · plan · fast mode · thinking", {"pace": True, "plan": True, "fast_mode": True, "thinking": True},
         {"fast_mode": True, "thinking": {"enabled": True}}),
        ("+ pull request · files changed · budget", {"pr": True, "files_changed": True, "budget": True},
         {"pr": {"number": 57, "url": "https://github.com/NoobyGains/usage-pulse/pull/57", "reviewState": "approved"}}),
    ]
    for i, (title, extra_show, extra) in enumerate(stages):
        sb.write_config(config(dict(base, **extra_show), budget_usd=50 if extra_show.get("budget") else 0,
                               line2_widgets=[k for k in extra_show if k != "pace"]))
        d.add(sb.run_main(payload(sb, **extra)), f"usage-pulse · widgets: {title}",
              2600 if i in (0, len(stages) - 1) else 2000)
    d.write()


def demo_agents(sb):
    cs = sb.cs
    d = Demo("agents")
    stages = [  # live, spawned, tasks done, (reviewer tokens, impl tokens, explore status)
        (1, 44, 2, 6000, 0, None), (2, 45, 2, 14000, 9000, None), (3, 46, 3, 23000, 31000, "running"),
        (3, 47, 4, 31000, 58000, "running"), (2, 47, 5, 40000, 84000, "completed"),
        (2, 47, 6, 47000, 112000, "completed"), (1, 47, 7, 47000, 131000, "completed"),
    ]
    for i, (live, spawned, done, rev, impl, explore) in enumerate(stages):
        sb.now += 95
        seed_agents(cs, live, spawned, done)
        sb.write_config(config({"subagents": True, "team": True}))
        main_line = sb.run_main(payload(sb)).splitlines()[0]
        tasks = [{"id": "t1", "name": "reviewer", "agentType": "code-reviewer", "status": "running",
                  "model": "claude-opus-5-5", "effort": "high", "tokenCount": rev,
                  "contextWindowSize": 200_000, "startTime": int((sb.now - 95 * (i + 1)) * 1000)}]
        if impl:
            tasks.append({"id": "t2", "name": "implementer", "agentType": "general-purpose", "status": "running",
                          "model": "claude-sonnet-5-5", "effort": "medium", "tokenCount": impl,
                          "contextWindowSize": 1_000_000, "startTime": int((sb.now - 95 * i) * 1000)})
        if explore:
            tasks.append({"id": "t3", "name": "", "agentType": "Explore", "status": explore,
                          "model": "claude-haiku-5-5", "tokenCount": 18_000, "contextWindowSize": 200_000,
                          "startTime": int((sb.now - 95 * (i - 1)) * 1000)})
        rows = sb.run_subagent_rows({"session_id": SESSION, "columns": 70, "tasks": tasks})
        body = [main_line, "", f"{cs.DIM}agent panel{cs.RESET}"] + [f"  {r}" for r in rows]
        d.add("\n".join(body), "usage-pulse · agents and teams", 2400 if i == len(stages) - 1 else 900)
    d.write()


def demo_update(sb):
    d = Demo("update")
    sb.write_config(config(CORE))
    for pulse, claude, title, ms in ((False, False, "usage-pulse", 1400),
                                     (True, False, "usage-pulse · a new release", 1800),
                                     (True, True, "usage-pulse · Claude Code update too", 2200)):
        sb.updates.update(pulse=pulse, claude=claude)
        d.add(sb.run_main(payload(sb)), title, ms)
    sb.updates.update(pulse=False, claude=False)
    d.write()


_WIZARD_PROVIDERS = [
    {"id": "claude:default", "type": "claude", "label": "Claude (Defend)", "path": "~/.claude",
     "active": True, "enabled": True, "tier": "Max 20x", "age_seconds": 0, "note": ""},
    {"id": "claude:b", "type": "claude", "label": "Claude (Sunny)", "path": "~/.claude-b",
     "active": False, "enabled": True, "tier": "Max 20x", "age_seconds": 0, "note": ""},
    {"id": "codex", "type": "codex", "label": "Codex", "path": "~/.codex",
     "active": False, "enabled": True, "tier": "plus", "age_seconds": 300, "note": ""},
    {"id": "gemini", "type": "gemini", "label": "Gemini", "path": "~/.gemini/antigravity-cli",
     "active": False, "enabled": True, "tier": "Google AI Ultra", "age_seconds": 20, "note": ""},
    {"id": "minimax", "type": "minimax", "label": "MiniMax", "path": "mmx",
     "active": False, "enabled": False, "tier": "", "age_seconds": 0, "note": "runs the mmx CLI"},
]

# (screen, keys pressed on it). Every key redraws, and every redraw is a frame.
_WIZARD_KEYS = [
    ("Welcome", ["enter"]), ("Status line", ["enter"]), ("Hooks", ["enter"]),
    ("Providers", ["down", " ", "enter"]), ("Model caps", ["enter"]),
    ("Theme", ["down", "down", "enter"]), ("Bar size", ["enter"]), ("Bar style", ["down", "enter"]),
    ("Layout", ["enter"]), ("Currency", ["enter"]), ("Clock", ["enter"]), ("Effort", ["enter"]),
    ("Widgets", [" ", "down", " ", "enter"]), ("Summary", ["esc"]),
]
_WIZARD_SHOW = ("Welcome", "Hooks", "Providers", "Model caps", "Theme", "Bar style", "Widgets", "Summary")


def demo_wizard(sb):
    cs = sb.cs
    sb.write_config(config(CORE))
    keys = [k for _screen, ks in _WIZARD_KEYS for k in ks]
    it = iter(keys)
    out, old_out = _Out(), sys.stdout
    sys.stdout = out
    try:
        with mock.patch.object(cs, "_read_key", lambda: next(it)), \
                mock.patch.object(cs, "_stdio_is_tty", lambda: True), \
                mock.patch.object(cs, "detect_providers", lambda config=None: [dict(r) for r in _WIZARD_PROVIDERS]), \
                mock.patch.object(cs, "set_providers", lambda *a, **k: None):
            cs.cmd_setup([])
    finally:
        sys.stdout = old_out
    frames = []
    for frame in out.text().split("\x1b[H\x1b[J"):
        if "usage-pulse setup" not in frame:
            continue
        header = frame.split("\n", 2)[1] if "\n" in frame else ""
        name = next((s for s in _WIZARD_SHOW if f"· {s}" in header), None)
        if name:
            frame = re.sub(r"\x1b\[\?[0-9;]*[hl]", "", frame).replace("Nothing changed.", "")
            frames.append((name, frame.strip("\n")))
    d = Demo("wizard", quantize=96)
    for i, (name, frame) in enumerate(frames):
        last_of_screen = i + 1 == len(frames) or frames[i + 1][0] != name
        ms = 2600 if name == "Summary" else (1500 if last_of_screen else 420)
        d.add(frame, f"usage-pulse · setup: {name.lower()}", ms)
    d.write()


# ---------------------------------------------------------------------------
# GIF assembly
# ---------------------------------------------------------------------------

def make_gifs():
    from PIL import Image
    made = 0
    for meta_path in sorted(BUILD.glob("*.json")):
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        png = meta_path.with_suffix(".png")
        if not png.exists():
            print(f"skip {meta_path.stem}: no {png.name} (screenshot the page first)")
            continue
        sheet = Image.open(png).convert("RGB")
        n, h = meta["frames"], meta["height"]
        if sheet.height < n * h:
            sys.exit(f"{png.name}: expected {n} frames of {h}px, got {sheet.height}px")
        frames = []
        for i in range(n):
            frame = sheet.crop((0, i * h, sheet.width, (i + 1) * h))
            frames.append(frame.quantize(colors=meta["quantize"], method=Image.Quantize.MEDIANCUT,
                                         dither=Image.Dither.NONE))
        out = REPO_ROOT / meta["out"]
        frames[0].save(out, save_all=True, append_images=frames[1:], duration=meta["durations"],
                       loop=0, optimize=True)
        print(f"wrote {meta['out']}  {sheet.width}x{h}, {n} frames, {out.stat().st_size // 1024} KB")
        made += 1
    if not made:
        sys.exit("nothing to do")


def main():
    if "--gif" in sys.argv:
        make_gifs()
        return
    BUILD.mkdir(parents=True, exist_ok=True)
    for stale in BUILD.glob("*"):
        if stale.suffix in (".html", ".json"):
            stale.unlink()
    for demo in (demo_hero, demo_themes, demo_rainbow, demo_layouts, demo_widgets, demo_agents,
                 demo_update, demo_wizard):
        sb = Sandbox()
        try:
            demo(sb)
        finally:
            sb.close()


if __name__ == "__main__":
    main()
