"""Render the README's pictures from the real script.

Every image in the README that shows the bar is produced here, so the pictures
cannot drift from what the code draws. The script runs ``claude_status.py``
in-process inside a throwaway sandbox (nothing of yours is read or written),
captures the ANSI output, and writes one HTML file per picture to
``assets/_build/``. Those pages are screenshotted into ``assets/*.png`` and
the wizard frames are joined into ``assets/wizard.gif``.

    python scripts/readme_assets.py            # write the HTML pages
    python scripts/readme_assets.py --gif      # join assets/_build/wizard-*.png into assets/wizard.gif (needs Pillow)

Screenshots: open each ``assets/_build/*.html`` in a browser at 1x and save the
page as PNG (the maintainer uses Playwright: full-page screenshot of the file).
The pages are drawn at twice the usual font size so the PNGs stay crisp when
the README scales them down.
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

# ---------------------------------------------------------------------------
# ANSI → HTML
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


def ansi_to_html(text):
    """Turn SGR-coloured text into spans. Other escapes are dropped."""
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
        params = [int(p) if p else 0 for p in m.group(1).split(";")] if m.group(1) and "?" not in m.group(1) else [0]
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


PAGE = """<!doctype html>
<meta charset="utf-8">
<title>{title}</title>
<style>
  html, body {{ margin: 0; background: #0c0c0c; }}
  body {{ width: fit-content; }}
  .term {{ display: block; width: fit-content; background: #0c0c0c; color: #cccccc;
           font: 28px/1.45 "Cascadia Mono", "Consolas", "Menlo", "DejaVu Sans Mono", monospace;
           padding: 30px 40px 32px; white-space: pre; }}
</style>
<div class="term">{body}</div>
"""


def write_page(name, ansi_text, title):
    BUILD.mkdir(parents=True, exist_ok=True)
    path = BUILD / f"{name}.html"
    path.write_text(PAGE.format(title=html.escape(title), body=ansi_to_html(ansi_text.rstrip("\n"))),
                    encoding="utf-8")
    print("wrote", path.relative_to(REPO_ROOT))
    return path


# ---------------------------------------------------------------------------
# Sandbox around claude_status
# ---------------------------------------------------------------------------

class _Out:
    """A stand-in for sys.stdout that records what the script prints."""

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
    def __init__(self):
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
            "COLUMNS": "200", "CLAUDE_PULSE_NONINTERACTIVE": "",
        })
        self.env.start()
        os.environ.pop("CLAUDE_PULSE_NONINTERACTIVE", None)
        import claude_status as cs
        self.cs = cs
        self.patches = []
        for target, value in (("get_state_dir", lambda: self.state),
                              ("_claude_config_dir", lambda: self.cfg),
                              ("get_config_path", lambda: self.root / "config.json"),
                              ("check_for_update", lambda: False),
                              ("check_claude_code_update", lambda *a, **k: False),
                              ("get_credentials", lambda: ("token", "Max 20x")),
                              ("fetch_usage", lambda token, timeout=10: None),
                              ("_enable_windows_ansi", lambda: None)):
            p = mock.patch.object(cs, target, value)
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
        """One repaint of the status line with *payload* on stdin."""
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

def _next_weekday(weekday, hour):
    """Epoch of the next given weekday (0=Mon) at *hour* local time."""
    t = time.localtime()
    days = (weekday - t.tm_wday) % 7 or 7
    target = time.mktime((t.tm_year, t.tm_mon, t.tm_mday + days, hour, 0, 0, 0, 0, -1))
    return int(target)


def _windows(five_pct, five_in, seven_pct, seven_at):
    return {"five_hour": {"used_percentage": five_pct, "resets_at": int(time.time() + five_in)},
            "seven_day": {"used_percentage": seven_pct, "resets_at": seven_at}}


SESSION = "readme-session"


def main_payload():
    return {
        "session_id": SESSION,
        "model": {"id": "claude-opus-5-5", "display_name": "Opus"},
        "workspace": {"current_dir": str(REPO_ROOT), "project_dir": str(REPO_ROOT)},
        "cwd": str(REPO_ROOT),
        "version": "2.1.305",
        "effort": {"level": "xhigh"},
        "context_window": {"used_percentage": 35, "context_window_size": 1000000},
        "cost": {"total_cost_usd": 38.75, "total_lines_added": 142, "total_lines_removed": 37},
        "rate_limits": _windows(27, 2 * 3600 + 53 * 60, 73, _next_weekday(4, 15)),
    }


def seed_team_and_agents(cs):
    """Three teammates with 7 tasks (4 done); 47 subagents spawned, 3 still live."""
    for name in ("planner", "implementer", "reviewer"):
        cs._record_team_event("idle", {"session_id": SESSION, "teammate_name": name})
    for i in range(1, 8):
        cs._record_team_event("created", {"session_id": SESSION, "task_id": str(i),
                                          "task_subject": f"Task {i}", "teammate_name": "planner"})
    for i in range(1, 5):
        cs._record_team_event("completed", {"session_id": SESSION, "task_id": str(i),
                                            "task_subject": f"Task {i}", "teammate_name": "implementer"})
    for i in range(1, 48):
        cs._record_subagent_event("start", {"agent_id": f"a{i}", "session_id": SESSION, "agent_type": "claude"})
        if i <= 44:
            cs._record_subagent_event("stop", {"agent_id": f"a{i}", "session_id": SESSION})


# A README picture must stay readable at ~900 px, so each one shows a focused
# set of widgets (about 90 columns) rather than everything at once.
_QUIET = {"lines": False, "effort": False, "branch": False, "subagents": False, "team": False,
          "cost": False, "model": False, "context": False, "providers": False}


def base_config(show=None, **extra):
    cfg = {"theme": "default", "layout": "standard", "bar_size": "medium", "bar_style": "classic",
           "currency": "$", "clock_format": "12h", "effort_format": "labeled",
           "show": dict(_QUIET, **(show or {})), "max_width": 0, "wrap": "off",
           "providers_label_main": True}
    cfg.update(extra)
    return cfg


HERO_SHOW = {"context": True, "cost": True, "model": True, "providers": True}


def provider_entries(sb):
    files = {
        "sunny": ("Claude (Sunny)", _windows(3, 50 * 60, 63, _next_weekday(2, 15))),
        "gemini": ("Gemini", _windows(1, 95 * 60, 66, _next_weekday(4, 23))),
        "codex": ("Codex", _windows(12, 70 * 60, 2, _next_weekday(6, 2))),
    }
    entries = [{"id": "claude:default", "type": "claude", "label": "Claude (Defend)", "enabled": True,
                "dir": str(sb.cfg)}]
    for pid, (label, data) in files.items():
        path = sb.root / f"{pid}.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        entries.append({"id": f"file:{pid}", "type": "file", "label": label, "enabled": True, "path": str(path)})
    return entries


def fake_login(sb):
    (sb.cfg / ".credentials.json").write_text(json.dumps({"claudeAiOauth": {
        "accessToken": "readme-token", "refreshToken": "readme-refresh",
        "rateLimitTier": "default_claude_max_20x", "expiresAt": int((time.time() + 3600) * 1000)}}),
        encoding="utf-8")


# ---------------------------------------------------------------------------
# Pictures
# ---------------------------------------------------------------------------

def picture_hero(sb):
    fake_login(sb)
    sb.write_config(base_config(HERO_SHOW, providers=provider_entries(sb)))
    seed_team_and_agents(sb.cs)
    text = sb.run_main(main_payload())
    write_page("providers", text, "claude-pulse: one line per account and tool")
    return text


def picture_layouts(sb):
    cs = sb.cs
    lines = []
    width = max(len(n) for n in cs.LAYOUTS) + 2
    show = dict(HERO_SHOW, providers=False)
    for layout in cs.LAYOUTS:
        sb.write_config(base_config(show, layout=layout, providers=[]))
        text = sb.run_main(main_payload()).splitlines()[0]
        lines.append(f"{cs.DIM}{layout:<{width}}{cs.RESET}{text}")
    write_page("layouts", "\n".join(lines), "claude-pulse layouts")


def picture_agents(sb):
    cs = sb.cs
    sb.write_config(base_config({"subagents": True, "team": True}, providers=[]))
    main_line = sb.run_main(main_payload()).splitlines()[0]
    now = time.time()
    tasks = [
        {"id": "t1", "name": "reviewer", "agentType": "code-reviewer", "status": "running",
         "model": "claude-opus-5-5", "effort": "high", "tokenCount": 47_000,
         "contextWindowSize": 200_000, "startTime": int((now - 130) * 1000)},
        {"id": "t2", "name": "implementer", "agentType": "general-purpose", "status": "running",
         "model": "claude-sonnet-5-5", "effort": "medium", "tokenCount": 112_000,
         "contextWindowSize": 1_000_000, "startTime": int((now - 610) * 1000)},
        {"id": "t3", "name": "", "agentType": "Explore", "status": "completed",
         "model": "claude-haiku-5-5", "tokenCount": 18_000, "contextWindowSize": 200_000,
         "startTime": int((now - 900) * 1000)},
    ]
    rows = sb.run_subagent_rows({"session_id": SESSION, "columns": 70, "tasks": tasks})
    body = [main_line, "", f"{cs.DIM}agent panel{cs.RESET}"] + [f"  {r}" for r in rows]
    write_page("agents", "\n".join(body), "claude-pulse agent panel")


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

# One entry per screen we want to show: (frame title fragment, keys pressed on it).
_WIZARD_KEYS = [
    ("Welcome", ["enter"]), ("Status line", ["enter"]), ("Hooks", ["enter"]),
    ("Providers", ["enter"]), ("Model caps", ["enter"]), ("Theme", ["down", "enter"]),
    ("Bar size", ["enter"]), ("Bar style", ["down", "enter"]), ("Layout", ["enter"]),
    ("Currency", ["enter"]), ("Clock", ["enter"]), ("Effort", ["enter"]),
    ("Widgets", [" ", "down", " ", "enter"]), ("Summary", ["esc"]),
]
_WIZARD_SHOW = ("Welcome", "Hooks", "Providers", "Model caps", "Theme", "Bar style", "Widgets", "Summary")


def picture_wizard(sb):
    cs = sb.cs
    sb.write_config(base_config(HERO_SHOW, providers=[]))
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
    # Every keypress redraws its screen; keep the last drawing of each screen
    # so the picture shows the choice made on it.
    screens = []
    for frame in out.text().split("\x1b[H\x1b[J"):
        if "claude-pulse setup" not in frame:
            continue
        header = frame.split("\n", 2)[1] if "\n" in frame else ""
        name = next((s for s in _WIZARD_SHOW if f"· {s}" in header), None)
        if not name:
            continue
        if screens and screens[-1][0] == name:
            screens[-1] = (name, frame)
        else:
            screens.append((name, frame))
    for n, (name, frame) in enumerate(screens):
        frame = re.sub(r"\x1b\[\?[0-9;]*[hl]", "", frame)
        frame = frame.replace("Nothing changed.", "").strip("\n")   # printed after Esc on the last screen
        write_page(f"wizard-{n:02d}-{name.lower().replace(' ', '-')}", frame, f"claude-pulse setup: {name}")


def make_gif():
    from PIL import Image
    frames = sorted(BUILD.glob("wizard-*.png"))
    if not frames:
        sys.exit("no assets/_build/wizard-*.png frames: screenshot the wizard pages first")
    images = [Image.open(p).convert("RGB") for p in frames]
    w = max(i.width for i in images)
    h = max(i.height for i in images)
    canvas = []
    for img in images:
        page = Image.new("RGB", (w, h), "#0c0c0c")
        page.paste(img, (0, 0))
        canvas.append(page.quantize(colors=96, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE))
    out = REPO_ROOT / "assets" / "wizard.gif"
    canvas[0].save(out, save_all=True, append_images=canvas[1:], duration=2200, loop=0, optimize=True)
    print("wrote", out.relative_to(REPO_ROOT), f"({out.stat().st_size // 1024} KB, {len(canvas)} frames)")


def main():
    if "--gif" in sys.argv:
        make_gif()
        return
    sb = Sandbox()
    try:
        picture_hero(sb)
        picture_layouts(sb)
        picture_agents(sb)
        picture_wizard(sb)
    finally:
        sb.close()


if __name__ == "__main__":
    main()
