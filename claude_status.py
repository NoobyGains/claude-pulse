#!/usr/bin/env python3
"""Minimal Claude Code status line — fetches real usage data from Anthropic's OAuth API."""

import json
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

# Theme definitions — each maps usage levels to ANSI colour codes
THEMES = {
    "default": {"low": GREEN, "mid": YELLOW, "high": RED},
    "ocean":   {"low": CYAN, "mid": BLUE, "high": MAGENTA},
    "sunset":  {"low": YELLOW, "mid": ORANGE_256, "high": RED},
    "mono":    {"low": WHITE, "mid": WHITE, "high": BRIGHT_WHITE},
    "neon":    {"low": BRIGHT_GREEN, "mid": BRIGHT_YELLOW, "high": BRIGHT_RED},
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
    show = data.get("show", {})
    for key, default in DEFAULT_SHOW.items():
        show.setdefault(key, default)
    data["show"] = show
    return data


def save_config(config):
    config_path = Path(__file__).parent / "config.json"
    with open(config_path, "w") as f:
        json.dump(config, f, indent=2)


def get_cache_path():
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    cache_dir = base / "claude-status"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / "cache.json"


def read_cache(cache_path, ttl):
    try:
        with open(cache_path, "r") as f:
            cached = json.load(f)
        if time.time() - cached.get("timestamp", 0) < ttl:
            return cached.get("line", "")
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        pass
    return None


def write_cache(cache_path, line):
    try:
        with open(cache_path, "w") as f:
            json.dump({"timestamp": time.time(), "line": line}, f)
    except OSError:
        pass


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


def make_bar(pct, theme=None):
    """Build a thin coloured bar."""
    if theme is None:
        theme = THEMES["default"]
    filled = round(pct / 100 * BAR_WIDTH)
    filled = max(0, min(BAR_WIDTH, filled))
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

    theme = get_theme_colours(config.get("theme", "default"))
    show = config.get("show", DEFAULT_SHOW)
    parts = []

    # Current Session (5-hour block)
    if show.get("session", True):
        five = usage.get("five_hour")
        if five:
            pct = five.get("utilization", 0)
            bar = make_bar(pct, theme)
            reset = format_reset_time(five.get("resets_at")) if show.get("timer", True) else None
            reset_str = f" {reset}" if reset else ""
            parts.append(f"Session {bar} {pct:.0f}%{reset_str}")
        else:
            parts.append(f"Session {make_bar(0, theme)} 0%")

    # Weekly Limit (7-day all models)
    if show.get("weekly", True):
        seven = usage.get("seven_day")
        if seven:
            pct = seven.get("utilization", 0)
            bar = make_bar(pct, theme)
            parts.append(f"Weekly {bar} {pct:.0f}%")

    # Extra usage (bonus/overflow credits) — off by default
    if show.get("extra", False):
        extra = usage.get("extra")
        if extra:
            pct = extra.get("utilization", 0)
            bar = make_bar(pct, theme)
            parts.append(f"Extra {bar} {pct:.0f}%")
        else:
            # Show placeholder if enabled but no data
            parts.append(f"Extra {make_bar(0, theme)} 0%")

    # Plan name
    if show.get("plan", True) and plan:
        parts.append(plan)

    return " | ".join(parts)


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


def utf8_print(text):
    """Print text with UTF-8 encoding (avoids Windows cp1252 errors)."""
    sys.stdout.buffer.write((text + "\n").encode("utf-8"))


def cmd_list_themes():
    """Print all available themes with a colour preview."""
    utf8_print(f"\n{BOLD}Available themes:{RESET}\n")
    for name, colours in THEMES.items():
        low_bar = f"{colours['low']}{FILL * 3}{RESET}"
        mid_bar = f"{colours['mid']}{FILL * 3}{RESET}"
        high_bar = f"{colours['high']}{FILL * 2}{RESET}"
        preview = f"{low_bar}{mid_bar}{high_bar}"
        utf8_print(f"  {name:<10} {preview}  ({colours['low']}low{RESET} {colours['mid']}mid{RESET} {colours['high']}high{RESET})")
    utf8_print("")


def cmd_set_theme(name):
    """Set the active theme and save to config."""
    if name not in THEMES:
        utf8_print(f"Unknown theme: {name}")
        utf8_print(f"Available: {', '.join(THEMES.keys())}")
        return
    config = load_config()
    config["theme"] = name
    save_config(config)
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
    colours = THEMES.get(theme_name, THEMES["default"])
    preview = f"{colours['low']}{FILL * 3}{colours['mid']}{FILL * 3}{colours['high']}{FILL * 2}{RESET}"

    utf8_print(f"\n{BOLD}claude-pulse config{RESET}\n")
    utf8_print(f"  Theme:     {theme_name}  {preview}")
    utf8_print(f"  Cache TTL: {config.get('cache_ttl_seconds', DEFAULT_CACHE_TTL)}s")
    utf8_print(f"\n  {BOLD}Visibility:{RESET}")
    show = config.get("show", DEFAULT_SHOW)
    for key in DEFAULT_SHOW:
        state = f"{GREEN}on{RESET}" if show.get(key, DEFAULT_SHOW[key]) else f"{RED}off{RESET}"
        utf8_print(f"    {key:<10} {state}")
    utf8_print("")


def main():
    args = sys.argv[1:]

    if "--install" in args:
        install_status_line()
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

    if "--config" in args:
        cmd_print_config()
        return

    # Normal status line mode
    config = load_config()
    cache_ttl = config.get("cache_ttl_seconds", DEFAULT_CACHE_TTL)

    try:
        sys.stdin.read()
    except Exception:
        pass

    cache_path = get_cache_path()
    cached = read_cache(cache_path, cache_ttl)
    if cached is not None:
        sys.stdout.buffer.write((cached + "\n").encode("utf-8"))
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
        line = f"API error: {e.code}"
    except Exception:
        line = "Usage unavailable"

    write_cache(cache_path, line)
    sys.stdout.buffer.write((line + "\n").encode("utf-8"))


if __name__ == "__main__":
    main()
