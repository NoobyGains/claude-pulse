#!/usr/bin/env python3
"""Minimal Claude Code status line — fetches real usage data from Anthropic's OAuth API."""

import json
import math
import os
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_CACHE_TTL = 30
BAR_WIDTH = 8
FILL = "\u2501"   # ━ (thin horizontal bar)
EMPTY = "\u2500"   # ─ (thin line)

# ANSI colour codes
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
DIM = "\033[2m"
RESET = "\033[0m"
BOLD = "\033[1m"
CYAN = "\033[36m"
BLUE = "\033[34m"
MAGENTA = "\033[35m"
WHITE = "\033[37m"
BRIGHT_WHITE = "\033[97m"
BRIGHT_GREEN = "\033[92m"
BRIGHT_YELLOW = "\033[93m"
BRIGHT_RED = "\033[91m"
ORANGE_256 = "\033[38;5;208m"
BRIGHT_ORANGE_256 = "\033[38;5;214m"
PRIDE_VIOLET = "\033[38;5;135m"
PRIDE_GREEN = "\033[38;5;49m"
PRIDE_PINK = "\033[38;5;199m"

# Theme definitions — each maps usage levels to ANSI colour codes
# "rainbow" uses representative colours for previews; actual rendering is animated
THEMES = {
    "default": {"low": GREEN, "mid": YELLOW, "high": RED},
    "ocean":   {"low": CYAN, "mid": BLUE, "high": MAGENTA},
    "sunset":  {"low": YELLOW, "mid": ORANGE_256, "high": RED},
    "mono":    {"low": WHITE, "mid": WHITE, "high": BRIGHT_WHITE},
    "neon":    {"low": BRIGHT_GREEN, "mid": BRIGHT_YELLOW, "high": BRIGHT_RED},
    "pride":   {"low": PRIDE_VIOLET, "mid": PRIDE_GREEN, "high": PRIDE_PINK},
    "rainbow": {"low": BRIGHT_GREEN, "mid": BRIGHT_YELLOW, "high": MAGENTA},
}

PLAN_NAMES = {
    "default_claude_pro": "Pro",
    "default_claude_max_5x": "Max 5x",
    "default_claude_max_20x": "Max 20x",
}

DEFAULT_SHOW = {
    "session": True,
    "weekly": True,
    "plan": True,
    "timer": True,
    "extra": False,
}


# ---------------------------------------------------------------------------
# Rainbow animation helpers
# ---------------------------------------------------------------------------

def hsv_to_rgb(h, s, v):
    """Convert HSV (all 0-1) to RGB (0-255 ints)."""
    if s == 0.0:
        c = int(v * 255)
        return c, c, c
    h6 = h * 6.0
    i = int(h6)
    f = h6 - i
    p = int(v * (1.0 - s) * 255)
    q = int(v * (1.0 - s * f) * 255)
    t = int(v * (1.0 - s * (1.0 - f)) * 255)
    vi = int(v * 255)
    i %= 6
    if i == 0:
        return vi, t, p
    if i == 1:
        return q, vi, p
    if i == 2:
        return p, vi, t
    if i == 3:
        return p, q, vi
    if i == 4:
        return t, p, vi
    return vi, p, q


def detect_activity():
    """Detect if Claude is actively thinking based on call frequency.

    The status line is called every ~300ms during generation but less often
    when idle.  We touch a file each call and check how recently the previous
    call happened.  Rapid calls (< 1.5 s apart) → active/thinking.
    """
    cache_dir = get_cache_path().parent
    state_path = cache_dir / ".last_render"
    now = time.time()
    try:
        last_time = state_path.stat().st_mtime
    except (FileNotFoundError, OSError):
        last_time = 0
    try:
        state_path.touch()
    except OSError:
        pass
    return (now - last_time) < 1.5


def rainbow_colorize(text, color_all=True, is_active=False):
    """Apply animated rainbow with two modes.

    Active/thinking — fast colour drift + rapid 3-second shimmer.
    Idle            — nearly static colours + soft 10-second white glimmer.

    color_all=True  — strip existing ANSI, rainbow every character (bars + text).
    color_all=False — preserve existing ANSI-colored chars (bars), only rainbow
                      the uncolored text around them.
    """
    now = time.time()

    # Count visible characters (skip ANSI escapes) for highlight math
    visible_count = 0
    idx = 0
    while idx < len(text):
        if text[idx] == "\033":
            while idx < len(text) and text[idx] != "m":
                idx += 1
            idx += 1
            continue
        visible_count += 1
        idx += 1

    if visible_count == 0:
        return text

    # Animation parameters — active vs idle
    if is_active:
        hue_drift = now * 0.15          # fast colour shifting
        cycle = 3.0                     # rapid shimmer
        highlight_width = 5
        shimmer_desat = 0.75            # strong white flash
        shimmer_val_boost = 0.05
    else:
        hue_drift = now * 0.02          # barely perceptible drift
        cycle = 10.0                    # slow, calm glimmer
        highlight_width = 8             # wider, softer gradient
        shimmer_desat = 0.60            # gentler white wash
        shimmer_val_boost = 0.05

    highlight_center = (now % cycle) / cycle * (visible_count + highlight_width * 2) - highlight_width

    result = []
    visible_idx = 0
    has_existing_color = False  # tracks ANSI color state for color_all=False
    i = 0

    while i < len(text):
        # Handle ANSI escape sequences
        if text[i] == "\033":
            j = i
            while j < len(text) and text[j] != "m":
                j += 1
            seq = text[i : j + 1]

            if color_all:
                # Strip all existing ANSI — we'll re-color everything
                i = j + 1
                continue
            else:
                # Preserve existing ANSI; track color state
                if seq == "\033[0m":
                    has_existing_color = False
                else:
                    has_existing_color = True
                result.append(seq)
                i = j + 1
                continue

        # Visible character
        if not color_all and has_existing_color:
            # Already styled by the bar — pass through unchanged
            result.append(text[i])
        else:
            # Apply rainbow
            hue = ((visible_idx * 0.04) + hue_drift) % 1.0
            dist = abs(visible_idx - highlight_center)

            if dist < highlight_width:
                # Shimmer band — desaturate toward white
                blend = 1.0 - (dist / highlight_width)
                if not is_active:
                    blend = blend * blend  # quadratic falloff for softer edge
                sat = 0.85 * (1.0 - blend * shimmer_desat)
                val = 0.95 + blend * shimmer_val_boost
            else:
                sat = 0.85
                val = 0.95

            r, g, b = hsv_to_rgb(hue, sat, val)
            result.append(f"\033[38;2;{r};{g};{b}m{text[i]}")

        visible_idx += 1
        i += 1

    result.append(RESET)
    return "".join(result)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def load_config():
    config_path = Path(__file__).parent / "config.json"
    try:
        with open(config_path, "r") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        data = {}
    # Apply defaults
    data.setdefault("cache_ttl_seconds", DEFAULT_CACHE_TTL)
    data.setdefault("theme", "default")
    data.setdefault("rainbow_bars", True)
    show = data.get("show", {})
    for key, default in DEFAULT_SHOW.items():
        show.setdefault(key, default)
    data["show"] = show
    return data


def save_config(config):
    config_path = Path(__file__).parent / "config.json"
    with open(config_path, "w") as f:
        json.dump(config, f, indent=2)


# ---------------------------------------------------------------------------
# Cache — stores usage data alongside the rendered line so rainbow can
# re-render each call without re-hitting the API.
# ---------------------------------------------------------------------------

def get_cache_path():
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    cache_dir = base / "claude-status"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / "cache.json"


def read_cache(cache_path, ttl):
    """Return the full cache dict if fresh, else None."""
    try:
        with open(cache_path, "r") as f:
            cached = json.load(f)
        if time.time() - cached.get("timestamp", 0) < ttl:
            return cached
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        pass
    return None


def write_cache(cache_path, line, usage=None, plan=None):
    try:
        data = {"timestamp": time.time(), "line": line}
        if usage is not None:
            data["usage"] = usage
        if plan is not None:
            data["plan"] = plan
        with open(cache_path, "w") as f:
            json.dump(data, f)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Credentials & API
# ---------------------------------------------------------------------------

def get_credentials():
    """Read OAuth token and plan info from Claude Code's credentials file."""
    creds_path = Path.home() / ".claude" / ".credentials.json"
    try:
        with open(creds_path, "r") as f:
            data = json.load(f)
        oauth = data.get("claudeAiOauth", {})
        token = oauth.get("accessToken")
        tier = oauth.get("rateLimitTier", "")
        if not token:
            return None, None
        plan = PLAN_NAMES.get(tier, tier.replace("default_claude_", "").replace("_", " ").title())
        return token, plan
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        return None, None


def fetch_usage(token):
    req = urllib.request.Request(
        "https://api.anthropic.com/api/oauth/usage",
        headers={
            "Authorization": f"Bearer {token}",
            "anthropic-beta": "oauth-2025-04-20",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=5) as resp:
        return json.loads(resp.read())


# ---------------------------------------------------------------------------
# Status line rendering
# ---------------------------------------------------------------------------

def get_theme_colours(theme_name):
    """Return the colour dict for the given theme name."""
    return THEMES.get(theme_name, THEMES["default"])


def bar_colour(pct, theme):
    """Return ANSI colour based on usage percentage using theme colours."""
    if pct >= 80:
        return theme["high"]
    if pct >= 50:
        return theme["mid"]
    return theme["low"]


def make_bar(pct, theme=None, plain=False):
    """Build a thin coloured bar. plain=True returns characters only (no ANSI)."""
    if theme is None:
        theme = THEMES["default"]
    filled = round(pct / 100 * BAR_WIDTH)
    filled = max(0, min(BAR_WIDTH, filled))
    if plain:
        return f"{FILL * filled}{EMPTY * (BAR_WIDTH - filled)}"
    colour = bar_colour(pct, theme)
    return f"{colour}{FILL * filled}{DIM}{EMPTY * (BAR_WIDTH - filled)}{RESET}"


def format_reset_time(resets_at_str):
    if not resets_at_str:
        return None
    try:
        resets_at = datetime.fromisoformat(resets_at_str)
        now = datetime.now(timezone.utc)
        total_seconds = int((resets_at - now).total_seconds())
        if total_seconds <= 0:
            return "now"
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        if hours > 0:
            return f"{hours}h {minutes:02d}m"
        return f"{minutes}m"
    except (ValueError, TypeError):
        return None


def build_status_line(usage, plan, config=None):
    if config is None:
        config = load_config()

    theme_name = config.get("theme", "default")
    is_rainbow = theme_name == "rainbow"
    rainbow_bars = config.get("rainbow_bars", True)

    # When rainbow + bars: build plain text, rainbow everything
    # When rainbow - bars: build bars with default colours, rainbow text only
    # Otherwise: normal themed rendering
    if is_rainbow and rainbow_bars:
        bar_plain = True
        theme = THEMES["default"]
    elif is_rainbow:
        bar_plain = False
        theme = THEMES["default"]
    else:
        bar_plain = False
        theme = get_theme_colours(theme_name)

    show = config.get("show", DEFAULT_SHOW)
    parts = []

    # Current Session (5-hour block)
    if show.get("session", True):
        five = usage.get("five_hour")
        if five:
            pct = five.get("utilization", 0)
            bar = make_bar(pct, theme, plain=bar_plain)
            reset = format_reset_time(five.get("resets_at")) if show.get("timer", True) else None
            reset_str = f" {reset}" if reset else ""
            parts.append(f"Session {bar} {pct:.0f}%{reset_str}")
        else:
            parts.append(f"Session {make_bar(0, theme, plain=bar_plain)} 0%")

    # Weekly Limit (7-day all models)
    if show.get("weekly", True):
        seven = usage.get("seven_day")
        if seven:
            pct = seven.get("utilization", 0)
            bar = make_bar(pct, theme, plain=bar_plain)
            parts.append(f"Weekly {bar} {pct:.0f}%")

    # Extra usage (bonus/overflow credits) — off by default
    if show.get("extra", False):
        extra = usage.get("extra")
        if extra:
            pct = extra.get("utilization", 0)
            bar = make_bar(pct, theme, plain=bar_plain)
            parts.append(f"Extra {bar} {pct:.0f}%")
        else:
            parts.append(f"Extra {make_bar(0, theme, plain=bar_plain)} 0%")

    # Plan name
    if show.get("plan", True) and plan:
        parts.append(plan)

    line = " | ".join(parts)

    if is_rainbow:
        is_active = config.get("_is_active", False)
        line = rainbow_colorize(line, color_all=rainbow_bars, is_active=is_active)

    return line


# ---------------------------------------------------------------------------
# Install
# ---------------------------------------------------------------------------

def install_status_line():
    settings_path = Path.home() / ".claude" / "settings.json"
    script_path = Path(__file__).resolve()

    settings = {}
    if settings_path.exists():
        try:
            with open(settings_path, "r") as f:
                settings = json.load(f)
        except (json.JSONDecodeError, OSError):
            pass

    settings["statusLine"] = {
        "type": "command",
        "command": f'python "{script_path}"',
    }

    settings_path.parent.mkdir(parents=True, exist_ok=True)
    with open(settings_path, "w") as f:
        json.dump(settings, f, indent=2)

    print(f"Installed status line to {settings_path}")
    print(f"Command: python \"{script_path}\"")
    print("Restart Claude Code to see the status line.")


# ---------------------------------------------------------------------------
# CLI commands
# ---------------------------------------------------------------------------

def utf8_print(text):
    """Print text with UTF-8 encoding (avoids Windows cp1252 errors)."""
    sys.stdout.buffer.write((text + "\n").encode("utf-8"))


def cmd_list_themes():
    """Print all available themes with a colour preview."""
    utf8_print(f"\n{BOLD}Available themes:{RESET}\n")
    for name, colours in THEMES.items():
        if name == "rainbow":
            # Show a mini rainbow preview
            preview = rainbow_colorize(FILL * 8)
            utf8_print(f"  {name:<10} {preview}  (animated rainbow shimmer)")
        else:
            low_bar = f"{colours['low']}{FILL * 3}{RESET}"
            mid_bar = f"{colours['mid']}{FILL * 3}{RESET}"
            high_bar = f"{colours['high']}{FILL * 2}{RESET}"
            preview = f"{low_bar}{mid_bar}{high_bar}"
            utf8_print(f"  {name:<10} {preview}  ({colours['low']}low{RESET} {colours['mid']}mid{RESET} {colours['high']}high{RESET})")
    utf8_print("")


def cmd_themes_demo():
    """Print a simulated status line for each theme so users can see them in action."""
    utf8_print(f"\n{BOLD}Theme previews:{RESET}\n")
    demo_usage = {
        "five_hour": {"utilization": 42, "resets_at": None},
        "seven_day": {"utilization": 67},
    }
    current = load_config().get("theme", "default")
    for name in THEMES:
        demo_config = {"theme": name, "show": {"session": True, "weekly": True, "plan": True, "timer": False, "extra": False}}
        line = build_status_line(demo_usage, "Max 20x", demo_config)
        marker = " <<" if name == current else ""
        utf8_print(f"  {BOLD}{name:<10}{RESET} {line}{marker}")
    utf8_print(f"\n  Set with: python claude_status.py --theme <name>\n")


def cmd_set_theme(name):
    """Set the active theme and save to config."""
    if name not in THEMES:
        utf8_print(f"Unknown theme: {name}")
        utf8_print(f"Available: {', '.join(THEMES.keys())}")
        return
    config = load_config()
    config["theme"] = name
    save_config(config)
    # Clear the cache so the new theme takes effect immediately
    try:
        os.remove(get_cache_path())
    except OSError:
        pass
    if name == "rainbow":
        preview = rainbow_colorize(FILL * 8)
    else:
        colours = THEMES[name]
        preview = f"{colours['low']}{FILL * 3}{colours['mid']}{FILL * 3}{colours['high']}{FILL * 2}{RESET}"
    utf8_print(f"Theme set to {BOLD}{name}{RESET}  {preview}")


def cmd_show(parts_str):
    """Enable the given comma-separated parts."""
    config = load_config()
    parts = [p.strip().lower() for p in parts_str.split(",")]
    valid = set(DEFAULT_SHOW.keys())
    for part in parts:
        if part not in valid:
            print(f"Unknown part: {part} (valid: {', '.join(sorted(valid))})")
            return
    for part in parts:
        config["show"][part] = True
    save_config(config)
    print(f"Enabled: {', '.join(parts)}")


def cmd_hide(parts_str):
    """Disable the given comma-separated parts."""
    config = load_config()
    parts = [p.strip().lower() for p in parts_str.split(",")]
    valid = set(DEFAULT_SHOW.keys())
    for part in parts:
        if part not in valid:
            print(f"Unknown part: {part} (valid: {', '.join(sorted(valid))})")
            return
    for part in parts:
        config["show"][part] = False
    save_config(config)
    print(f"Disabled: {', '.join(parts)}")


def cmd_print_config():
    """Print the current configuration summary."""
    config = load_config()
    theme_name = config.get("theme", "default")

    if theme_name == "rainbow":
        preview = rainbow_colorize(FILL * 8)
    else:
        colours = THEMES.get(theme_name, THEMES["default"])
        preview = f"{colours['low']}{FILL * 3}{colours['mid']}{FILL * 3}{colours['high']}{FILL * 2}{RESET}"

    utf8_print(f"\n{BOLD}claude-pulse config{RESET}\n")
    utf8_print(f"  Theme:     {theme_name}  {preview}")
    utf8_print(f"  Cache TTL: {config.get('cache_ttl_seconds', DEFAULT_CACHE_TTL)}s")
    rb = config.get("rainbow_bars", True)
    rb_state = f"{GREEN}on{RESET}" if rb else f"{RED}off{RESET}"
    utf8_print(f"  Rainbow bars: {rb_state}  (rainbow colours {'include' if rb else 'skip'} the progress bars)")
    utf8_print(f"\n  {BOLD}Visibility:{RESET}")
    show = config.get("show", DEFAULT_SHOW)
    for key in DEFAULT_SHOW:
        state = f"{GREEN}on{RESET}" if show.get(key, DEFAULT_SHOW[key]) else f"{RED}off{RESET}"
        utf8_print(f"    {key:<10} {state}")
    utf8_print("")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    args = sys.argv[1:]

    if "--install" in args:
        install_status_line()
        return

    if "--themes-demo" in args:
        cmd_themes_demo()
        return

    if "--themes" in args:
        cmd_list_themes()
        return

    if "--theme" in args:
        idx = args.index("--theme")
        if idx + 1 < len(args):
            cmd_set_theme(args[idx + 1])
        else:
            print("Usage: --theme <name>")
        return

    if "--show" in args:
        idx = args.index("--show")
        if idx + 1 < len(args):
            cmd_show(args[idx + 1])
        else:
            print("Usage: --show <parts>  (comma-separated: session,weekly,plan,timer,extra)")
        return

    if "--hide" in args:
        idx = args.index("--hide")
        if idx + 1 < len(args):
            cmd_hide(args[idx + 1])
        else:
            print("Usage: --hide <parts>  (comma-separated: session,weekly,plan,timer,extra)")
        return

    if "--rainbow-bars" in args:
        idx = args.index("--rainbow-bars")
        if idx + 1 < len(args):
            val = args[idx + 1].lower()
            if val in ("on", "true", "yes", "1"):
                rb = True
            elif val in ("off", "false", "no", "0"):
                rb = False
            else:
                print(f"Unknown value: {val}  (use on or off)")
                return
            config = load_config()
            config["rainbow_bars"] = rb
            save_config(config)
            try:
                os.remove(get_cache_path())
            except OSError:
                pass
            state = f"{GREEN}on{RESET}" if rb else f"{RED}off{RESET}"
            utf8_print(f"Rainbow bars: {state}")
        else:
            print("Usage: --rainbow-bars on|off")
        return

    if "--config" in args:
        cmd_print_config()
        return

    # Normal status line mode
    config = load_config()
    cache_ttl = config.get("cache_ttl_seconds", DEFAULT_CACHE_TTL)
    is_rainbow = config.get("theme") == "rainbow"

    # Detect thinking vs idle for rainbow animation style
    if is_rainbow:
        config["_is_active"] = detect_activity()

    try:
        sys.stdin.read()
    except Exception:
        pass

    cache_path = get_cache_path()
    cached = read_cache(cache_path, cache_ttl)

    if cached is not None:
        if is_rainbow and "usage" in cached:
            # Re-render with fresh timestamp for animation
            line = build_status_line(cached["usage"], cached.get("plan", ""), config)
        else:
            line = cached.get("line", "")
        sys.stdout.buffer.write((line + "\n").encode("utf-8"))
        return

    token, plan = get_credentials()
    if not token:
        line = "No credentials found"
        write_cache(cache_path, line)
        sys.stdout.buffer.write((line + "\n").encode("utf-8"))
        return

    try:
        usage = fetch_usage(token)
        line = build_status_line(usage, plan, config)
    except urllib.error.HTTPError as e:
        usage = None
        line = f"API error: {e.code}"
    except Exception:
        usage = None
        line = "Usage unavailable"

    write_cache(cache_path, line, usage, plan)
    sys.stdout.buffer.write((line + "\n").encode("utf-8"))


if __name__ == "__main__":
    main()
