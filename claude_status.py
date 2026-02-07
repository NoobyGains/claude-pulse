#!/usr/bin/env python3
"""Minimal Claude Code status line — fetches real usage data from Anthropic's OAuth API."""

VERSION = "1.8.0"

import json
import math
import os
import shutil
import subprocess
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_CACHE_TTL = 30
BAR_SIZES = {"small": 4, "medium": 8, "large": 12}
DEFAULT_BAR_SIZE = "medium"
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
FROST_ICE = "\033[38;5;159m"
FROST_STEEL = "\033[38;5;75m"
EMBER_GOLD = "\033[38;5;220m"
EMBER_HOT = "\033[38;5;202m"
CANDY_PINK = "\033[38;5;213m"
CANDY_PURPLE = "\033[38;5;141m"
CANDY_CYAN = "\033[38;5;51m"

# Theme definitions — each maps usage levels to ANSI colour codes
# "rainbow" uses representative colours for previews; actual rendering is animated
THEMES = {
    "default": {"low": GREEN, "mid": YELLOW, "high": RED},
    "ocean":   {"low": CYAN, "mid": BLUE, "high": MAGENTA},
    "sunset":  {"low": YELLOW, "mid": ORANGE_256, "high": RED},
    "mono":    {"low": WHITE, "mid": WHITE, "high": BRIGHT_WHITE},
    "neon":    {"low": BRIGHT_GREEN, "mid": BRIGHT_YELLOW, "high": BRIGHT_RED},
    "pride":   {"low": PRIDE_VIOLET, "mid": PRIDE_GREEN, "high": PRIDE_PINK},
    "frost":   {"low": FROST_ICE, "mid": FROST_STEEL, "high": BRIGHT_WHITE},
    "ember":   {"low": EMBER_GOLD, "mid": EMBER_HOT, "high": BRIGHT_RED},
    "candy":   {"low": CANDY_PINK, "mid": CANDY_PURPLE, "high": CANDY_CYAN},
    "rainbow": {"low": BRIGHT_GREEN, "mid": BRIGHT_YELLOW, "high": MAGENTA},
}

PLAN_NAMES = {
    "default_claude_pro": "Pro",
    "default_claude_max_5x": "Max 5x",
    "default_claude_max_20x": "Max 20x",
}

# Named text colours for non-bar text (labels, percentages, separators)
TEXT_COLORS = {
    "white": "\033[37m",
    "bright_white": "\033[97m",
    "cyan": "\033[36m",
    "blue": "\033[34m",
    "green": "\033[32m",
    "yellow": "\033[33m",
    "magenta": "\033[35m",
    "red": "\033[31m",
    "orange": "\033[38;5;208m",
    "violet": "\033[38;5;135m",
    "pink": "\033[38;5;199m",
    "dim": "\033[2;37m",
    "default": "\033[39m",
    "none": "",
}

# Accent text colour per theme — used in previews/demos to make each theme look distinct
THEME_DEMO_TEXT = {
    "default": "green",
    "ocean":   "cyan",
    "sunset":  "yellow",
    "mono":    "dim",
    "neon":    "green",
    "pride":   "violet",
    "frost":   "cyan",
    "ember":   "yellow",
    "candy":   "pink",
    "rainbow": "none",
}

# Recommended text colour per theme — chosen for good contrast with bars
# so the shimmer (white overlay on coloured text) is clearly visible
THEME_TEXT_DEFAULTS = {
    "default": "white",
    "ocean":   "white",
    "sunset":  "white",
    "mono":    "dim",
    "neon":    "white",
    "pride":   "white",
    "frost":   "white",
    "ember":   "white",
    "candy":   "white",
    "rainbow": "none",
}

DEFAULT_SHOW = {
    "session": True,
    "weekly": True,
    "plan": True,
    "timer": True,
    "extra": False,
    "update": True,
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


def rainbow_colorize(text, color_all=True, shimmer=True):
    """Apply rainbow colouring — animated when processing, clean static when idle.

    shimmer=True  — Claude is processing: hue drifts each frame + white glint sweep.
    shimmer=False — Claude is idle: static rainbow gradient, no animation artifacts.

    color_all=True  — strip existing ANSI, rainbow every character.
    color_all=False — preserve ANSI-colored chars (bars), rainbow the rest.
    """
    now = time.time()

    if shimmer:
        # Rainbow hue drift — shifts the colour gradient each frame
        # At 300ms refresh: 0.25 * 0.3 = 0.075 per frame ≈ 27° of hue wheel
        hue_drift = now * 0.25
    else:
        # Static mode — fixed hue offset so the rainbow looks clean when frozen
        hue_drift = 0.0

    # Shimmer timing — fast wide sweep like Claude's "Crafting…" animation
    CYCLE = 2.5            # total cycle length
    GLINT_DURATION = 0.7   # short flash — ~2-3 frames at 300ms refresh
    HIGHLIGHT_WIDTH = 20   # wide band — covers enough chars to look smooth between frames

    phase = now % CYCLE
    glint_active = shimmer and phase >= (CYCLE - GLINT_DURATION)

    # Count visible characters (skip ANSI escapes)
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

    # Shimmer position — sweeps across during the glint window
    if glint_active:
        sweep = (phase - (CYCLE - GLINT_DURATION)) / GLINT_DURATION  # 0.0 → 1.0
        total_range = visible_count + HIGHLIGHT_WIDTH * 2
        highlight_center = sweep * total_range - HIGHLIGHT_WIDTH
    else:
        highlight_center = -9999  # off-screen

    result = []
    visible_idx = 0
    has_existing_color = False
    i = 0

    while i < len(text):
        # Handle ANSI escape sequences
        if text[i] == "\033":
            j = i
            while j < len(text) and text[j] != "m":
                j += 1
            seq = text[i : j + 1]

            if color_all:
                i = j + 1
                continue
            else:
                if seq == "\033[0m":
                    has_existing_color = False
                else:
                    has_existing_color = True
                result.append(seq)
                i = j + 1
                continue

        # Visible character
        if not color_all and has_existing_color:
            result.append(text[i])
        else:
            # Wider bands: 0.025 per char = full rainbow every ~40 chars
            hue = ((visible_idx * 0.025) + hue_drift) % 1.0

            # Vivid rainbow: high saturation and brightness
            r, g, b = hsv_to_rgb(hue, 0.92, 0.95)

            # Shimmer: blend directly toward white in RGB space
            # This produces a clean bright flash, not the muddy gray that
            # HSV desaturation creates
            dist = abs(visible_idx - highlight_center)
            if glint_active and dist < HIGHLIGHT_WIDTH:
                blend = 1.0 - (dist / HIGHLIGHT_WIDTH)
                blend = blend * blend  # quadratic falloff for soft edges
                # Blend from rainbow color toward bright white (210-255 range)
                target = int(210 + blend * 45)
                r = int(r + (target - r) * blend)
                g = int(g + (target - g) * blend)
                b = int(b + (target - b) * blend)

            result.append(f"\033[38;2;{r};{g};{b}m{text[i]}")

        visible_idx += 1
        i += 1

    result.append(RESET)
    return "".join(result)


def resolve_text_color(config):
    """Return the ANSI code for the configured text colour."""
    theme_name = config.get("theme", "default")
    tc = config.get("text_color", "auto")
    if tc == "auto":
        tc = THEME_TEXT_DEFAULTS.get(theme_name, "white")
    return TEXT_COLORS.get(tc, TEXT_COLORS["white"])


def apply_text_color(line, color_code):
    """Wrap non-bar text in a base colour so the shimmer has something to contrast against.

    Prepends the colour, re-applies it after every RESET, and appends a final RESET.
    Bar colours override this inline; after their RESET the base colour resumes.
    """
    if not color_code:
        return line
    # Prepend base colour, replace every \033[0m with \033[0m + base colour,
    # then append a final reset at the end
    return color_code + line.replace("\033[0m", "\033[0m" + color_code) + "\033[0m"


def apply_shimmer(text):
    """Post-process any ANSI-coloured text to add a white shimmer glint.

    Works on all themes — walks through the text, tracks the active ANSI
    state, and overlays a white highlight in the shimmer zone, then restores
    the original colour after each shimmer character.

    Fast wide sweep like Claude's "Crafting…" animation.
    72% of the time returns text unchanged (no glint visible).
    """
    CYCLE = 2.5
    GLINT_DURATION = 0.7
    HIGHLIGHT_WIDTH = 20

    now = time.time()
    phase = now % CYCLE
    glint_active = phase >= (CYCLE - GLINT_DURATION)

    if not glint_active:
        return text  # fast path — 75% of the time

    # Count visible characters
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

    # Shimmer position
    sweep = (phase - (CYCLE - GLINT_DURATION)) / GLINT_DURATION
    total_range = visible_count + HIGHLIGHT_WIDTH * 2
    highlight_center = sweep * total_range - HIGHLIGHT_WIDTH

    result = []
    visible_idx = 0
    # Track all active ANSI codes so we can restore after shimmer chars
    active_codes = []
    i = 0

    while i < len(text):
        if text[i] == "\033":
            j = i
            while j < len(text) and text[j] != "m":
                j += 1
            seq = text[i : j + 1]
            result.append(seq)
            # Track ANSI state
            if seq == "\033[0m":
                active_codes = []
            else:
                active_codes.append(seq)
            i = j + 1
            continue

        dist = abs(visible_idx - highlight_center)
        # Skip shimmer on bar characters — only animate text (labels, %, separators)
        is_bar_char = text[i] in (FILL, EMPTY)
        if not is_bar_char and dist < HIGHLIGHT_WIDTH:
            # White shimmer overlay — quadratic falloff
            blend = 1.0 - (dist / HIGHLIGHT_WIDTH)
            blend = blend * blend
            brightness = int(210 + blend * 45)  # 210 to 255 — always brighter than \033[37m (~187)
            result.append(f"\033[38;2;{brightness};{brightness};{brightness}m")
            result.append(text[i])
            # Restore original ANSI state
            if active_codes:
                result.extend(active_codes)
            else:
                result.append("\033[0m")
        else:
            result.append(text[i])

        visible_idx += 1
        i += 1

    return "".join(result)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def get_config_path():
    """Return path to user config — stored alongside cache, outside the repo."""
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    config_dir = base / "claude-status"
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir / "config.json"


def load_config():
    user_path = get_config_path()
    repo_path = Path(__file__).parent / "config.json"

    # User config takes priority, fall back to repo template
    data = {}
    for path in (user_path, repo_path):
        try:
            with open(path, "r") as f:
                data = json.load(f)
            break
        except (FileNotFoundError, json.JSONDecodeError):
            continue

    # Apply defaults
    data.setdefault("cache_ttl_seconds", DEFAULT_CACHE_TTL)
    data.setdefault("theme", "default")
    data.setdefault("rainbow_bars", True)
    data.setdefault("rainbow_mode", False)
    data.setdefault("animate", True)
    data.setdefault("text_color", "auto")
    data.setdefault("bar_size", DEFAULT_BAR_SIZE)
    show = data.get("show", {})
    for key, default in DEFAULT_SHOW.items():
        show.setdefault(key, default)
    data["show"] = show
    return data


def save_config(config):
    config_path = get_config_path()
    # Only save user-facing keys, not internal ones
    save_data = {k: v for k, v in config.items() if not k.startswith("_")}
    with open(config_path, "w") as f:
        json.dump(save_data, f, indent=2)


# ---------------------------------------------------------------------------
# Cache — stores usage data alongside the rendered line so rainbow can
# re-render each call without re-hitting the API.
# ---------------------------------------------------------------------------

def get_state_dir():
    """Return the shared state/cache directory."""
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    state_dir = base / "claude-status"
    state_dir.mkdir(parents=True, exist_ok=True)
    return state_dir


def get_cache_path():
    return get_state_dir() / "cache.json"


# ---------------------------------------------------------------------------
# Animation state — hooks write this to signal processing start/stop
# ---------------------------------------------------------------------------

def get_animation_state_path():
    return get_state_dir() / "animating"


def hooks_installed():
    """Check if animation hooks have ever been used (state file has been created before)."""
    # The stop hook creates a "stopped" marker; the start hook creates the "animating" file.
    # If neither has ever existed, hooks aren't installed.
    state_dir = get_state_dir()
    return (state_dir / "animating").exists() or (state_dir / "hooks_installed").exists()


def is_claude_processing():
    """Check if Claude is actively processing (set by hooks).

    Returns True if:
    - Hooks aren't installed (fallback: always animate, old behaviour)
    - Hooks are installed AND the animating flag is set
    """
    if not hooks_installed():
        return True  # No hooks → always animate (backwards compatible)
    state_path = get_animation_state_path()
    try:
        if not state_path.exists():
            return False
        # Stale guard: if the flag is older than 5 minutes, assume it's orphaned
        age = time.time() - state_path.stat().st_mtime
        if age > 300:
            try:
                state_path.unlink()
            except OSError:
                pass
            return False
        return True
    except OSError:
        return False


def set_processing(active):
    """Write or remove the animation state flag."""
    state_dir = get_state_dir()
    state_path = get_animation_state_path()
    marker = state_dir / "hooks_installed"
    try:
        # Mark that hooks are installed (so we know to check the flag)
        if not marker.exists():
            marker.write_text("1")
        if active:
            state_path.write_text("1")
        else:
            state_path.unlink(missing_ok=True)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Update checker — compares local git HEAD to GitHub remote (cached 1 hour)
# ---------------------------------------------------------------------------

UPDATE_CHECK_TTL = 3600  # check at most once per hour
GITHUB_REPO = "NoobyGains/claude-pulse"


def get_local_commit():
    """Get the local git HEAD commit hash (short). Returns None on failure."""
    repo_dir = Path(__file__).resolve().parent
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=5,
            cwd=str(repo_dir),
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return None


def get_remote_commit():
    """Fetch the latest commit hash from GitHub API. Returns None on failure."""
    try:
        url = f"https://api.github.com/repos/{GITHUB_REPO}/commits/master"
        req = urllib.request.Request(url, headers={
            "Accept": "application/vnd.github.sha",
            "User-Agent": "claude-pulse-update-checker",
        })
        with urllib.request.urlopen(req, timeout=3) as resp:
            return resp.read().decode().strip()
    except Exception:
        return None


def check_for_update():
    """Check if a newer version is available on GitHub. Returns True/False/None.

    Cached for 1 hour. Fully silent on any error — never blocks the status line.
    """
    state_dir = get_state_dir()
    update_cache = state_dir / "update_check.json"

    # Read cached result
    try:
        with open(update_cache, "r") as f:
            cached = json.load(f)
        if time.time() - cached.get("timestamp", 0) < UPDATE_CHECK_TTL:
            return cached.get("update_available", False)
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        pass

    # Perform the check
    local = get_local_commit()
    if not local:
        return None  # not a git install, skip silently

    remote = get_remote_commit()
    if not remote:
        return None  # network error, skip silently

    update_available = local != remote

    # Cache the result
    try:
        with open(update_cache, "w") as f:
            json.dump({
                "timestamp": time.time(),
                "update_available": update_available,
                "local": local[:8],
                "remote": remote[:8],
            }, f)
    except OSError:
        pass

    return update_available


def append_update_indicator(line, config=None):
    """Append a visible update indicator if a newer version is available."""
    try:
        if config:
            show = config.get("show", DEFAULT_SHOW)
            if not show.get("update", True):
                return line
        if check_for_update():
            return line + f" {BRIGHT_YELLOW}\u2191 Pulse Update{RESET}"
    except Exception:
        pass  # never break the status line for an update check
    return line


def _read_version_from_file(script_path):
    """Read VERSION from a script file on disk (may differ from in-memory VERSION after git pull)."""
    try:
        with open(script_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("VERSION"):
                    # VERSION = "1.7.0"
                    return line.split('"')[1]
    except Exception:
        pass
    return None


def _fetch_remote_version():
    """Fetch the VERSION string from the latest master on GitHub. Returns None on failure."""
    try:
        url = f"https://raw.githubusercontent.com/{GITHUB_REPO}/master/claude_status.py"
        req = urllib.request.Request(url, headers={"User-Agent": "claude-pulse-update-checker"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            for raw_line in resp:
                line = raw_line.decode("utf-8", errors="replace")
                if line.startswith("VERSION"):
                    return line.split('"')[1]
    except Exception:
        pass
    return None


def cmd_update():
    """Pull the latest version from GitHub."""
    repo_dir = Path(__file__).resolve().parent
    script_path = Path(__file__).resolve()
    utf8_print(f"{BRIGHT_WHITE}claude-pulse update{RESET}\n")
    utf8_print(f"  Current version: {BRIGHT_WHITE}v{VERSION}{RESET}")

    # Check if we're in a git repo
    git_dir = repo_dir / ".git"
    if not git_dir.exists():
        utf8_print(f"  {RED}Not a git repository.{RESET}")
        utf8_print(f"  Re-clone from: https://github.com/{GITHUB_REPO}")
        return

    # Check current status
    local = get_local_commit()
    remote = get_remote_commit()

    if local and remote and local == remote:
        utf8_print(f"  {GREEN}No update found — you're on the latest version (v{VERSION}).{RESET}")
        return

    # Fetch remote version to show what's available
    remote_version = _fetch_remote_version()
    if remote_version and remote_version != VERSION:
        utf8_print(f"  {BRIGHT_YELLOW}Update found! v{VERSION} -> v{remote_version}{RESET}")
    else:
        utf8_print(f"  {BRIGHT_YELLOW}Update found! New changes available{RESET}")

    # Run git pull
    utf8_print(f"  Pulling latest from GitHub...")
    try:
        result = subprocess.run(
            ["git", "pull", "origin", "master"],
            capture_output=True, text=True, timeout=30,
            cwd=str(repo_dir),
        )
        if result.returncode == 0:
            # Read the new version from the updated file on disk
            new_version = _read_version_from_file(script_path)
            if new_version and new_version != VERSION:
                utf8_print(f"  {GREEN}Updated to v{new_version}!{RESET}")
            else:
                utf8_print(f"  {GREEN}Updated successfully!{RESET}")
            if result.stdout.strip():
                for ln in result.stdout.strip().split("\n"):
                    utf8_print(f"  {DIM}{ln}{RESET}")
            # Clear all caches so the update indicator disappears immediately
            state_dir = get_state_dir()
            for cache_name in ("update_check.json", "cache.json"):
                try:
                    (state_dir / cache_name).unlink()
                except OSError:
                    pass
            utf8_print(f"\n  Restart Claude Code to use v{new_version or 'latest'}.")
        else:
            utf8_print(f"  {RED}Update failed:{RESET}")
            if result.stderr.strip():
                for ln in result.stderr.strip().split("\n"):
                    utf8_print(f"  {DIM}{ln}{RESET}")
    except subprocess.TimeoutExpired:
        utf8_print(f"  {RED}Timed out. Check your network connection.{RESET}")
    except Exception as e:
        utf8_print(f"  {RED}Error: {e}{RESET}")


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


def make_bar(pct, theme=None, plain=False, width=None):
    """Build a thin coloured bar. plain=True returns characters only (no ANSI)."""
    if theme is None:
        theme = THEMES["default"]
    if width is None:
        width = BAR_SIZES[DEFAULT_BAR_SIZE]
    filled = round(pct / 100 * width)
    filled = max(0, min(width, filled))
    if plain:
        return f"{FILL * filled}{EMPTY * (width - filled)}"
    colour = bar_colour(pct, theme)
    return f"{colour}{FILL * filled}{DIM}{EMPTY * (width - filled)}{RESET}"


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
    is_rainbow_theme = theme_name == "rainbow"
    rainbow_mode = config.get("rainbow_mode", False)
    rainbow_bars = config.get("rainbow_bars", True)

    # Rainbow rendering applies when:
    # 1. Theme is "rainbow" (classic behaviour), OR
    # 2. rainbow_mode is enabled (rainbow animation on any theme)
    use_rainbow = is_rainbow_theme or rainbow_mode

    # When rainbow + bars: build plain text, rainbow everything
    # When rainbow - bars: build bars with theme colours, rainbow text only
    # Otherwise: normal themed rendering
    if use_rainbow and rainbow_bars:
        bar_plain = True
        theme = get_theme_colours(theme_name) if not is_rainbow_theme else THEMES["default"]
    elif use_rainbow:
        bar_plain = False
        theme = get_theme_colours(theme_name) if not is_rainbow_theme else THEMES["default"]
    else:
        bar_plain = False
        theme = get_theme_colours(theme_name)

    show = config.get("show", DEFAULT_SHOW)
    bar_size = config.get("bar_size", DEFAULT_BAR_SIZE)
    bw = BAR_SIZES.get(bar_size, BAR_SIZES[DEFAULT_BAR_SIZE])

    # Terminal width clamping — prevent bars from causing line wrapping
    # Estimate: each section ≈ bw + 15 chars of text, up to 4 sections + separators
    try:
        term_width = shutil.get_terminal_size((120, 24)).columns
        # Count how many bar sections we'll render
        num_bars = sum(1 for k in ("session", "weekly") if show.get(k, True))
        extra = usage.get("extra_usage")
        if extra and extra.get("is_enabled") and not config.get("extra_hidden", False):
            num_bars += 1
        # Each bar section: "Label " + bar + " XX% Xh XXm" ≈ bw + 20
        # Separators: " | " = 3 chars each
        # Plan name: ~10 chars, update indicator: ~20 chars
        overhead = num_bars * 20 + (num_bars - 1) * 3 + 30
        max_bar_width = max(2, (term_width - overhead) // max(num_bars, 1))
        if bw > max_bar_width:
            bw = max_bar_width
    except Exception:
        pass  # if terminal size detection fails, use configured size

    parts = []

    # Current Session (5-hour block)
    if show.get("session", True):
        five = usage.get("five_hour")
        if five:
            pct = five.get("utilization", 0)
            bar = make_bar(pct, theme, plain=bar_plain, width=bw)
            reset = format_reset_time(five.get("resets_at")) if show.get("timer", True) else None
            reset_str = f" {reset}" if reset else ""
            parts.append(f"Session {bar} {pct:.0f}%{reset_str}")
        else:
            parts.append(f"Session {make_bar(0, theme, plain=bar_plain, width=bw)} 0%")

    # Weekly Limit (7-day all models)
    if show.get("weekly", True):
        seven = usage.get("seven_day")
        if seven:
            pct = seven.get("utilization", 0)
            bar = make_bar(pct, theme, plain=bar_plain, width=bw)
            parts.append(f"Weekly {bar} {pct:.0f}%")

    # Extra usage (bonus/gifted credits)
    # Auto-shows when credits are gifted, unless user explicitly hid it
    extra = usage.get("extra_usage")
    extra_enabled_by_user = show.get("extra", False)
    extra_explicitly_hidden = config.get("extra_hidden", False)
    extra_has_credits = extra and extra.get("is_enabled") and extra.get("monthly_limit", 0) > 0
    if extra_enabled_by_user or (extra_has_credits and not extra_explicitly_hidden):
        currency = config.get("currency", "\u00a3")
        if extra and extra.get("is_enabled"):
            pct = min(extra.get("utilization", 0), 100)
            used = extra.get("used_credits", 0) / 100  # API returns pence/cents
            limit = extra.get("monthly_limit", 0) / 100
            bar = make_bar(pct, theme, plain=bar_plain, width=bw)
            parts.append(f"Extra {bar} {currency}{used:.2f}/{currency}{limit:.2f}")
        elif extra_enabled_by_user:
            # User explicitly enabled but no credits gifted
            parts.append(f"Extra {make_bar(0, theme, plain=bar_plain)} none")

    # Plan name
    if show.get("plan", True) and plan:
        parts.append(plan)

    line = " | ".join(parts)

    animate = config.get("animate", True)
    # Only animate when Claude is actively processing (hooks set this flag)
    # Falls back to always-animate if hooks aren't installed (flag missing = process)
    processing = is_claude_processing()
    should_animate = animate and processing

    if use_rainbow:
        line = rainbow_colorize(line, color_all=rainbow_bars, shimmer=should_animate)
    else:
        # Apply text colour to labels/percentages/separators
        text_color_code = resolve_text_color(config)
        if text_color_code:
            line = apply_text_color(line, text_color_code)
        # Shimmer overlays white on the now-coloured text
        if should_animate:
            line = apply_shimmer(line)

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

    # Status line command
    settings["statusLine"] = {
        "type": "command",
        "command": f'python "{script_path}"',
    }

    # Animation lifecycle hooks — animate only while Claude is writing
    _install_hooks_into(settings, script_path)

    settings_path.parent.mkdir(parents=True, exist_ok=True)
    with open(settings_path, "w") as f:
        json.dump(settings, f, indent=2)

    print(f"Installed status line + animation hooks to {settings_path}")
    print(f"Command: python \"{script_path}\"")
    print("Restart Claude Code to see the status line.")


def _install_hooks_into(settings, script_path):
    """Wire animation lifecycle hooks into a settings dict (no file I/O)."""
    hooks = settings.get("hooks", {})

    start_hook = {
        "type": "command",
        "command": f'python "{script_path}" --hook-start',
    }
    stop_hook = {
        "type": "command",
        "command": f'python "{script_path}" --hook-stop',
    }

    # Add to UserPromptSubmit — fires when the user presses Enter
    submit_hooks = hooks.get("UserPromptSubmit", [])
    our_cmd = f'python "{script_path}" --hook-start'
    already = any(
        h.get("hooks", [{}])[0].get("command", "") == our_cmd
        if isinstance(h, dict) and "hooks" in h else False
        for h in submit_hooks
    )
    if not already:
        submit_hooks.append({"hooks": [start_hook]})
    hooks["UserPromptSubmit"] = submit_hooks

    # Add to Stop — fires when Claude finishes responding
    stop_hooks = hooks.get("Stop", [])
    our_cmd_stop = f'python "{script_path}" --hook-stop'
    already_stop = any(
        h.get("hooks", [{}])[0].get("command", "") == our_cmd_stop
        if isinstance(h, dict) and "hooks" in h else False
        for h in stop_hooks
    )
    if not already_stop:
        stop_hooks.append({"hooks": [stop_hook]})
    hooks["Stop"] = stop_hooks

    settings["hooks"] = hooks


def install_hooks():
    """Install animation lifecycle hooks into Claude Code settings (standalone)."""
    settings_path = Path.home() / ".claude" / "settings.json"
    script_path = Path(__file__).resolve()

    settings = {}
    if settings_path.exists():
        try:
            with open(settings_path, "r") as f:
                settings = json.load(f)
        except (json.JSONDecodeError, OSError):
            pass

    _install_hooks_into(settings, script_path)

    with open(settings_path, "w") as f:
        json.dump(settings, f, indent=2)

    utf8_print(f"{BOLD}Animation hooks installed!{RESET}")
    utf8_print(f"  UserPromptSubmit → --hook-start (animation ON)")
    utf8_print(f"  Stop             → --hook-stop  (animation OFF)")
    utf8_print(f"  Settings: {settings_path}")
    utf8_print(f"\nRestart Claude Code for hooks to take effect.")
    utf8_print(f"The shimmer will now only animate while Claude is writing.")


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
    user_config = load_config()
    current = user_config.get("theme", "default")
    user_bar_size = user_config.get("bar_size", DEFAULT_BAR_SIZE)
    for name in THEMES:
        demo_tc = THEME_DEMO_TEXT.get(name, "white")
        demo_config = {"theme": name, "bar_size": user_bar_size, "text_color": demo_tc, "show": {"session": True, "weekly": True, "plan": True, "timer": False, "extra": False}}
        line = build_status_line(demo_usage, "Max 20x", demo_config)
        marker = " <<" if name == current else ""
        utf8_print(f"  {BOLD}{name:<10}{RESET} {line}{marker}")
    utf8_print(f"\n  Set with: python claude_status.py --theme <name>\n")


def cmd_show_themes():
    """Show all themes with live status line previews using accent colours."""
    current_config = load_config()
    current_theme = current_config.get("theme", "default")
    user_bar_size = current_config.get("bar_size", DEFAULT_BAR_SIZE)

    utf8_print(f"\n{BOLD}Themes:{RESET}\n")
    demo_usage = {
        "five_hour": {"utilization": 42, "resets_at": None},
        "seven_day": {"utilization": 67},
    }
    for name in THEMES:
        # Use the accent colour so each theme looks distinct in the preview
        demo_tc = THEME_DEMO_TEXT.get(name, "white")
        demo_config = {"theme": name, "bar_size": user_bar_size, "text_color": demo_tc, "show": {"session": True, "weekly": True, "plan": True, "timer": False, "extra": False}}
        line = build_status_line(demo_usage, "Max 20x", demo_config)
        marker = f" {GREEN}<< current{RESET}" if name == current_theme else ""
        # Colour the theme name with its accent colour
        name_colour = TEXT_COLORS.get(demo_tc, "") if name != "rainbow" else ""
        if name == "rainbow":
            coloured_name = rainbow_colorize(f"{name:<10}", shimmer=False)
        else:
            coloured_name = f"{name_colour}{BOLD}{name:<10}{RESET}"
        utf8_print(f"  {coloured_name} {line}{marker}")
    utf8_print("")


def cmd_show_colors():
    """Show all text colours with sample text."""
    current_config = load_config()
    current_theme = current_config.get("theme", "default")
    current_tc = current_config.get("text_color", "auto")

    utf8_print(f"\n{BOLD}Text colours:{RESET}\n")
    sample = "Session 42% | Weekly 67%"
    for tc_name, tc_code in TEXT_COLORS.items():
        # Colour the name label with its own colour
        if tc_name == "none":
            coloured_label = f"{DIM}{tc_name:<14}{RESET}"
            utf8_print(f"  {coloured_label} {DIM}(no colour applied){RESET}")
        elif tc_name == "default":
            coloured_label = f"\033[39m{tc_name:<14}{RESET}"
            utf8_print(f"  {coloured_label} \033[39m{sample}{RESET}")
        elif tc_name == "dim":
            coloured_label = f"{tc_code}{tc_name:<14}{RESET}"
            utf8_print(f"  {coloured_label} {tc_code}{sample}{RESET}")
        else:
            coloured_label = f"{tc_code}{BOLD}{tc_name:<14}{RESET}"
            utf8_print(f"  {coloured_label} {tc_code}{sample}{RESET}")
    if current_tc == "auto":
        resolved = THEME_TEXT_DEFAULTS.get(current_theme, "white")
        utf8_print(f"\n  Current: {BOLD}auto{RESET} (using {resolved} for {current_theme} theme)")
    else:
        utf8_print(f"\n  Current: {BOLD}{current_tc}{RESET}")
    utf8_print("")


def cmd_show_all():
    """Show all themes and text colours with visual previews."""
    cmd_show_themes()
    cmd_show_colors()


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
        # Clear explicit hide flag so auto-show can work again
        if part == "extra":
            config.pop("extra_hidden", None)
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
        # Mark extra as explicitly hidden so auto-show respects it
        if part == "extra":
            config["extra_hidden"] = True
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

    utf8_print(f"\n{BOLD}claude-pulse v{VERSION}{RESET}\n")
    utf8_print(f"  Theme:     {theme_name}  {preview}")
    utf8_print(f"  Cache TTL: {config.get('cache_ttl_seconds', DEFAULT_CACHE_TTL)}s")
    utf8_print(f"  Currency:  {config.get('currency', chr(163))}")
    bs = config.get("bar_size", DEFAULT_BAR_SIZE)
    bw_display = BAR_SIZES.get(bs, BAR_SIZES[DEFAULT_BAR_SIZE])
    utf8_print(f"  Bar size:  {bs} ({bw_display} chars)")
    rb = config.get("rainbow_bars", True)
    rb_state = f"{GREEN}on{RESET}" if rb else f"{RED}off{RESET}"
    utf8_print(f"  Rainbow bars: {rb_state}  (rainbow colours {'include' if rb else 'skip'} the progress bars)")
    rm = config.get("rainbow_mode", False)
    rm_state = f"{GREEN}on{RESET}" if rm else f"{RED}off{RESET}"
    utf8_print(f"  Rainbow mode: {rm_state}  (rainbow animation {'on any theme' if rm else 'only when theme is rainbow'})")
    anim = config.get("animate", True)
    anim_state = f"{GREEN}on{RESET}" if anim else f"{RED}off{RESET}"
    utf8_print(f"  Animation:    {anim_state}  (white shimmer {'sweeps across' if anim else 'disabled'} while Claude is writing)")
    tc = config.get("text_color", "auto")
    if tc == "auto":
        resolved = THEME_TEXT_DEFAULTS.get(theme_name, "white")
        tc_code = TEXT_COLORS.get(resolved, "")
        utf8_print(f"  Text colour:  {tc_code}auto{RESET}  (using {tc_code}{resolved}{RESET} for {theme_name} theme)")
    else:
        tc_code = TEXT_COLORS.get(tc, "")
        utf8_print(f"  Text colour:  {tc_code}{tc}{RESET}")
    has_hooks = hooks_installed()
    hook_state = f"{GREEN}installed{RESET}" if has_hooks else f"{DIM}not installed{RESET}"
    utf8_print(f"  Hooks:        {hook_state}  (animation {'only while Claude writes' if has_hooks else 'always on — run --install-hooks'})")
    if has_hooks:
        processing = is_claude_processing()
        proc_state = f"{GREEN}processing{RESET}" if processing else f"{DIM}idle{RESET}"
        utf8_print(f"  Status:       {proc_state}")
    # Update check
    local = get_local_commit()
    if local:
        update = check_for_update()
        if update:
            utf8_print(f"  Update:       {BRIGHT_YELLOW}available{RESET}  (run {BOLD}/pulse update{RESET} or {BOLD}--update{RESET})")
        elif update is False:
            utf8_print(f"  Update:       {GREEN}up to date (v{VERSION}){RESET}")
        else:
            utf8_print(f"  Update:       {DIM}check failed{RESET}")
    show = config.get("show", DEFAULT_SHOW)

    # Extra credits status — check the API
    utf8_print(f"\n  {BOLD}Extra Credits:{RESET}")
    try:
        token, _ = get_credentials()
        if token:
            _usage = fetch_usage(token)
            _extra = _usage.get("extra_usage")
            if _extra and _extra.get("is_enabled"):
                currency = config.get("currency", "\u00a3")
                used = _extra.get("used_credits", 0) / 100  # API returns pence/cents
                limit = _extra.get("monthly_limit", 0) / 100
                pct = min(_extra.get("utilization", 0), 100)
                utf8_print(f"    Status:    {GREEN}active{RESET}")
                utf8_print(f"    Used:      {currency}{used:.2f} / {currency}{limit:.2f} ({pct:.0f}%)")
                if config.get("extra_hidden"):
                    utf8_print(f"    Display:   {RED}hidden{RESET}  (run {BOLD}--show extra{RESET} to re-enable)")
                else:
                    utf8_print(f"    Display:   {GREEN}auto-shown{RESET}  (run {BOLD}--hide extra{RESET} to suppress)")
            else:
                utf8_print(f"    Status:    {DIM}not active{RESET}")
                if show.get("extra", False):
                    utf8_print(f"    Display:   {GREEN}on{RESET} (forced)  — will show 'none' until credits are gifted")
                else:
                    utf8_print(f"    Display:   {DIM}auto{RESET} — will appear when credits are gifted")
        else:
            utf8_print(f"    Status:    {DIM}unknown{RESET} (no credentials)")
    except Exception:
        utf8_print(f"    Status:    {DIM}check failed{RESET}")

    utf8_print(f"\n  {BOLD}Visibility:{RESET}")
    for key in DEFAULT_SHOW:
        state = f"{GREEN}on{RESET}" if show.get(key, DEFAULT_SHOW[key]) else f"{RED}off{RESET}"
        utf8_print(f"    {key:<10} {state}")
    utf8_print("")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    args = sys.argv[1:]

    # Hook commands — called by Claude Code lifecycle hooks (fast, no output)
    if "--hook-start" in args:
        set_processing(True)
        return

    if "--hook-stop" in args:
        set_processing(False)
        return

    if "--update" in args:
        cmd_update()
        return

    if "--install-hooks" in args:
        install_hooks()
        return

    if "--install" in args:
        install_status_line()
        return

    if "--show-all" in args:
        cmd_show_all()
        return

    if "--show-themes" in args:
        cmd_show_themes()
        return

    if "--show-colors" in args:
        cmd_show_colors()
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
            print("Usage: --show <parts>  (comma-separated: session,weekly,plan,timer,extra,update)")
        return

    if "--hide" in args:
        idx = args.index("--hide")
        if idx + 1 < len(args):
            cmd_hide(args[idx + 1])
        else:
            print("Usage: --hide <parts>  (comma-separated: session,weekly,plan,timer,extra,update)")
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

    if "--rainbow-mode" in args:
        idx = args.index("--rainbow-mode")
        if idx + 1 < len(args):
            val = args[idx + 1].lower()
            if val in ("on", "true", "yes", "1"):
                rm = True
            elif val in ("off", "false", "no", "0"):
                rm = False
            else:
                print(f"Unknown value: {val}  (use on or off)")
                return
            config = load_config()
            config["rainbow_mode"] = rm
            save_config(config)
            try:
                os.remove(get_cache_path())
            except OSError:
                pass
            state = f"{GREEN}on{RESET}" if rm else f"{RED}off{RESET}"
            theme = config.get("theme", "default")
            utf8_print(f"Rainbow animation: {state}  (theme: {theme})")
        else:
            print("Usage: --rainbow-mode on|off")
        return

    if "--text-color" in args:
        idx = args.index("--text-color")
        if idx + 1 < len(args):
            val = args[idx + 1].lower()
            if val not in TEXT_COLORS and val != "auto":
                utf8_print(f"Unknown colour: {val}")
                utf8_print(f"Available: auto, {', '.join(TEXT_COLORS.keys())}")
                return
            config = load_config()
            config["text_color"] = val
            save_config(config)
            try:
                os.remove(get_cache_path())
            except OSError:
                pass
            if val == "auto":
                resolved = THEME_TEXT_DEFAULTS.get(config.get("theme", "default"), "white")
                utf8_print(f"Text colour: {BOLD}auto{RESET} (using {resolved} for {config.get('theme', 'default')} theme)")
            else:
                code = TEXT_COLORS.get(val, "")
                utf8_print(f"Text colour: {code}{BOLD}{val}{RESET}")
        else:
            utf8_print(f"Usage: --text-color <name>")
            utf8_print(f"Available: auto, {', '.join(TEXT_COLORS.keys())}")
        return

    if "--animate" in args:
        idx = args.index("--animate")
        if idx + 1 < len(args):
            val = args[idx + 1].lower()
            if val in ("on", "true", "yes", "1"):
                anim = True
            elif val in ("off", "false", "no", "0"):
                anim = False
            else:
                print(f"Unknown value: {val}  (use on or off)")
                return
            config = load_config()
            config["animate"] = anim
            save_config(config)
            try:
                os.remove(get_cache_path())
            except OSError:
                pass
            state = f"{GREEN}on{RESET}" if anim else f"{RED}off{RESET}"
            utf8_print(f"Animation: {state}")
        else:
            print("Usage: --animate on|off")
        return

    if "--bar-size" in args:
        idx = args.index("--bar-size")
        if idx + 1 < len(args):
            val = args[idx + 1].lower()
            if val not in BAR_SIZES:
                utf8_print(f"Unknown size: {val}")
                utf8_print(f"Available: {', '.join(BAR_SIZES.keys())}")
                return
            config = load_config()
            config["bar_size"] = val
            save_config(config)
            try:
                os.remove(get_cache_path())
            except OSError:
                pass
            bw = BAR_SIZES[val]
            demo_bar = f"{GREEN}{FILL * bw}{RESET}"
            utf8_print(f"Bar size: {BOLD}{val}{RESET} ({bw} chars)  {demo_bar}")
        else:
            utf8_print(f"Usage: --bar-size <small|medium|large>")
            for name, width in BAR_SIZES.items():
                demo = f"{GREEN}{FILL * width}{RESET}"
                utf8_print(f"  {name:<8} {demo}  ({width} chars)")
        return

    if "--currency" in args:
        idx = args.index("--currency")
        if idx + 1 < len(args):
            val = args[idx + 1]
            config = load_config()
            config["currency"] = val
            save_config(config)
            try:
                os.remove(get_cache_path())
            except OSError:
                pass
            utf8_print(f"Currency symbol: {BOLD}{val}{RESET}")
        else:
            utf8_print("Usage: --currency <symbol>  (e.g. \u00a3, $, \u20ac, \u00a5)")
        return

    if "--config" in args:
        cmd_print_config()
        return

    # Normal status line mode
    config = load_config()
    cache_ttl = config.get("cache_ttl_seconds", DEFAULT_CACHE_TTL)
    animate = config.get("animate", True)

    try:
        sys.stdin.read()
    except Exception:
        pass

    cache_path = get_cache_path()
    cached = read_cache(cache_path, cache_ttl)

    if cached is not None:
        if animate and "usage" in cached:
            # Always re-render from cached data — this ensures:
            # - During processing: fresh animation frame (hue drift + shimmer)
            # - After stop: clean static render (no frozen shimmer artifacts)
            line = build_status_line(cached["usage"], cached.get("plan", ""), config)
        else:
            line = cached.get("line", "")
        line = append_update_indicator(line, config)
        sys.stdout.buffer.write((line + RESET + "\n").encode("utf-8"))
        return

    token, plan = get_credentials()
    if not token:
        line = "No credentials found"
        write_cache(cache_path, line)
        sys.stdout.buffer.write((line + RESET + "\n").encode("utf-8"))
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
    line = append_update_indicator(line, config)
    sys.stdout.buffer.write((line + RESET + "\n").encode("utf-8"))


if __name__ == "__main__":
    main()
