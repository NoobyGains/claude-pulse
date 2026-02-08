#!/usr/bin/env python3
"""Minimal Claude Code status line — fetches real usage data from Anthropic's OAuth API."""

VERSION = "2.2.0"

import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timedelta, timezone
from pathlib import Path

DEFAULT_CACHE_TTL = 60
BAR_SIZES = {"small": 4, "medium": 8, "large": 12}
DEFAULT_BAR_SIZE = "medium"
FILL = "\u2501"   # ━ (thin horizontal bar)
EMPTY = "\u2500"   # ─ (thin line)

# Bar styles — each maps to (filled_char, empty_char)
BAR_STYLES = {
    "classic": ("\u2501", "\u2500"),   # ━ ─
    "block":   ("\u2588", "\u2591"),   # █ ░
    "shade":   ("\u2593", "\u2591"),   # ▓ ░
    "pipe":    ("\u2503", "\u250A"),   # ┃ ┊
    "dot":     ("\u25CF", "\u25CB"),   # ● ○
    "square":  ("\u25A0", "\u25A1"),   # ■ □
    "star":    ("\u2605", "\u2606"),   # ★ ☆
}
DEFAULT_BAR_STYLE = "classic"

# Precompute all bar characters for shimmer detection
ALL_BAR_CHARS = set()
for _f, _e in BAR_STYLES.values():
    ALL_BAR_CHARS.add(_f)
    ALL_BAR_CHARS.add(_e)

# Text layouts — controls how labels, bars, and percentages are arranged
LAYOUTS = ("standard", "compact", "minimal", "percent-first")
DEFAULT_LAYOUT = "standard"

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

MODEL_SHORT_NAMES = {
    "claude-opus-4": "Opus",
    "claude-sonnet-4": "Sonnet",
    "claude-haiku-4": "Haiku",
    "claude-opus-4-6": "Opus",
    "claude-sonnet-4-5": "Sonnet",
    "claude-haiku-4-5": "Haiku",
    "claude-3-5-sonnet": "Sonnet",
    "claude-3-5-haiku": "Haiku",
    "claude-3-opus": "Opus",
}

# Context window sizes by model short name (used to derive token counts from %)
MODEL_CONTEXT_WINDOWS = {
    "Opus": 200_000,
    "Opus 4.6": 200_000,
    "Sonnet": 200_000,
    "Sonnet 4": 200_000,
    "Sonnet 4.5": 200_000,
    "Haiku": 200_000,
    "Haiku 4.5": 200_000,
}
DEFAULT_CONTEXT_WINDOW = 200_000

def _sanitize(text):
    """Strip ANSI escape sequences from untrusted strings."""
    return re.sub(r'\x1b\[[0-9;]*[a-zA-Z]', '', str(text))

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
    "sparkline": False,
    "runway": False,
    "status_message": False,
    "streak": False,
    "model": True,
    "context": True,
}

# Sparkline and history constants
SPARKLINE_CHARS = "\u2581\u2582\u2583\u2584\u2585\u2586\u2587\u2588"
SPARKLINE_DEFAULT_WIDTH = 8
HISTORY_MAX_AGE = 86400  # 24 hours in seconds


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

    shimmer=True  — Claude is processing: hue drifts each frame (smooth gradient shift).
    shimmer=False — Claude is idle: static rainbow gradient, no animation.

    color_all=True  — strip existing ANSI, rainbow every character.
    color_all=False — preserve ANSI-colored chars (bars), rainbow the rest.
    """
    now = time.time()

    if shimmer:
        # Rainbow hue drift — shifts the entire gradient each frame
        hue_drift = now * 0.8
    else:
        # Static mode — fixed hue offset so the rainbow looks clean when frozen
        hue_drift = 0.0

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
    """Post-process themed text with sweeping brightness waves.

    2-3 bright bands sweep left-to-right across the full status line,
    completing full passes so the animation is clearly visible.

    Skips bar characters (only animates labels, percentages, separators).
    """
    SWEEP_SPEED = 30.0  # chars per second — full sweep in ~2s
    BAND_WIDTH = 18     # how wide each bright band is (in characters)
    NUM_WAVES = 2       # number of simultaneous bright bands

    now = time.time()

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

    # Sweep loop length — band travels from off-screen left to off-screen right
    sweep_length = visible_count + BAND_WIDTH * 2

    # Precompute wave center positions for each band
    wave_centers = []
    for w in range(NUM_WAVES):
        offset = w * (sweep_length / NUM_WAVES)
        pos = (now * SWEEP_SPEED + offset) % sweep_length - BAND_WIDTH
        wave_centers.append(pos)

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

        is_bar_char = text[i] in ALL_BAR_CHARS
        if not is_bar_char:
            # Find the strongest wave influence on this character
            best_wave = 0.0
            for center in wave_centers:
                dist = abs(visible_idx - center)
                if dist < BAND_WIDTH:
                    w = 1.0 - (dist / BAND_WIDTH)
                    w = w * w  # smooth quadratic falloff
                    if w > best_wave:
                        best_wave = w

            # Base brightness 140, peaks at 255 — always visible,
            # bright bands clearly sweep across
            brightness = int(140 + best_wave * 115)
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
# Secure file helpers
# ---------------------------------------------------------------------------

def _secure_mkdir(path):
    """Create directory with 0o700 permissions on Unix. Normal mkdir on Windows."""
    path = Path(path)
    if path.is_symlink():
        path.unlink()
    if path.exists():
        return
    if sys.platform == "win32":
        path.mkdir(parents=True, exist_ok=True)
    else:
        old_umask = os.umask(0o077)
        try:
            path.mkdir(parents=True, exist_ok=True)
        finally:
            os.umask(old_umask)


def _secure_open_write(filepath):
    """Open file for writing with 0o600 permissions on Unix. Normal open on Windows."""
    filepath = Path(filepath)
    if filepath.is_symlink():
        filepath.unlink()
    if sys.platform == "win32":
        # Verify resolved path matches expected path (catch junction/symlink re-creation)
        resolved = filepath.resolve()
        expected = filepath.parent.resolve() / filepath.name
        if resolved != expected:
            raise OSError(f"Path resolves unexpectedly: {resolved}")
        return open(filepath, "w", encoding="utf-8")
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(str(filepath), flags, 0o600)
    return os.fdopen(fd, "w", encoding="utf-8")


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
    _secure_mkdir(config_dir)
    return config_dir / "config.json"


def load_config():
    user_path = get_config_path()
    repo_path = Path(__file__).parent / "config.json"

    # User config takes priority, fall back to repo template
    data = {}
    for path in (user_path, repo_path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            break
        except (FileNotFoundError, json.JSONDecodeError):
            continue

    # Clean up removed settings
    data.pop("rainbow_bars", None)
    data.pop("rainbow_mode", None)

    # Apply defaults
    data.setdefault("cache_ttl_seconds", DEFAULT_CACHE_TTL)
    data.setdefault("theme", "default")
    data.setdefault("animate", False)
    data.setdefault("text_color", "auto")
    data.setdefault("bar_size", DEFAULT_BAR_SIZE)
    data.setdefault("bar_style", DEFAULT_BAR_STYLE)
    data.setdefault("layout", DEFAULT_LAYOUT)
    data.setdefault("context_format", "percent")
    data.setdefault("extra_display", "auto")
    show = data.get("show", {})
    for key, default in DEFAULT_SHOW.items():
        show.setdefault(key, default)
    data["show"] = show
    return data


def save_config(config):
    config_path = get_config_path()
    # Only save user-facing keys, not internal ones
    save_data = {k: v for k, v in config.items() if not k.startswith("_")}
    with _secure_open_write(config_path) as f:
        json.dump(save_data, f, indent=2)


def _cleanup_hooks():
    """Remove any legacy claude-pulse hooks from settings.json.

    v2.2.0 removed all hooks — animation is now purely refresh-based.
    This runs once on upgrade and writes a marker to avoid repeat work.
    """
    state_dir = get_state_dir()
    marker = state_dir / "hooks_cleaned"
    if marker.exists():
        return
    settings_path = Path.home() / ".claude" / "settings.json"
    try:
        with open(settings_path, "r", encoding="utf-8") as f:
            settings = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        # No settings file or invalid — nothing to clean
        try:
            with _secure_open_write(marker) as f:
                pass
        except OSError:
            pass
        return

    changed = False
    script_name = "claude_status.py"
    for hook_type in ("UserPromptSubmit", "PreToolUse", "PostToolUse", "Stop"):
        hooks = settings.get("hooks", {}).get(hook_type, [])
        if hooks:
            filtered = [h for h in hooks if script_name not in h.get("command", "")]
            if len(filtered) != len(hooks):
                settings.setdefault("hooks", {})[hook_type] = filtered
                changed = True

    # Remove empty hook types and hooks key if empty
    if "hooks" in settings:
        settings["hooks"] = {k: v for k, v in settings["hooks"].items() if v}
        if not settings["hooks"]:
            del settings["hooks"]
            changed = True

    if changed:
        with _secure_open_write(settings_path) as f:
            json.dump(settings, f, indent=2)

    try:
        with _secure_open_write(marker) as f:
            pass
    except OSError:
        pass


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
    _secure_mkdir(state_dir)
    return state_dir


def get_cache_path():
    return get_state_dir() / "cache.json"




# ---------------------------------------------------------------------------
# Update checker — compares local git HEAD to GitHub remote (cached 1 hour)
# ---------------------------------------------------------------------------

UPDATE_CHECK_TTL = 3600  # check at most once per hour
GITHUB_REPO = "NoobyGains/claude-pulse"
_GIT_PATH = shutil.which("git") or "git"  # resolve once at import time


def get_local_commit():
    """Get the local git HEAD commit hash (short). Returns None on failure."""
    repo_dir = Path(__file__).resolve().parent
    try:
        result = subprocess.run(
            [_GIT_PATH, "rev-parse", "HEAD"],
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
            return resp.read(1024).decode().strip()  # SHA is ~40 bytes
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
        with open(update_cache, "r", encoding="utf-8") as f:
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
        with _secure_open_write(update_cache) as f:
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

    # Verify the git remote points to the expected repository
    try:
        origin_result = subprocess.run(
            [_GIT_PATH, "remote", "get-url", "origin"],
            capture_output=True, text=True, timeout=5,
            cwd=str(repo_dir),
        )
        origin_url = origin_result.stdout.strip().lower() if origin_result.returncode == 0 else ""
        expected_paths = [GITHUB_REPO.lower(), GITHUB_REPO.lower() + ".git"]
        if not any(origin_url.endswith(p) for p in expected_paths):
            utf8_print(f"  {RED}Origin URL does not match expected repository.{RESET}")
            utf8_print(f"  Expected: {GITHUB_REPO}")
            utf8_print(f"  Got:      {origin_url}")
            return
    except Exception:
        utf8_print(f"  {RED}Could not verify git remote.{RESET}")
        return

    # Check current status
    local = get_local_commit()
    remote = get_remote_commit()

    if remote is None:
        utf8_print(f"  {RED}Could not reach GitHub API to verify update integrity.{RESET}")
        utf8_print(f"  Check your network connection and try again.")
        return

    if local and local == remote:
        utf8_print(f"  {GREEN}No update found — you're on the latest version (v{VERSION}).{RESET}")
        return

    # Fetch remote version to show what's available
    remote_version = _fetch_remote_version()
    if remote_version and remote_version != VERSION:
        utf8_print(f"  {BRIGHT_YELLOW}Update found! v{VERSION} -> v{remote_version}{RESET}")
    else:
        utf8_print(f"  {BRIGHT_YELLOW}Update found! New changes available{RESET}")

    # Ask for confirmation unless --confirm was passed
    if "--confirm" not in sys.argv:
        if sys.stdin.isatty():
            try:
                answer = input(f"  Apply update? [y/N] ").strip().lower()
                if answer not in ("y", "yes"):
                    utf8_print(f"  {DIM}Update cancelled.{RESET}")
                    return
            except (EOFError, KeyboardInterrupt):
                utf8_print(f"\n  {DIM}Update cancelled.{RESET}")
                return
        else:
            utf8_print(f"  {DIM}Non-interactive mode. Run with --update --confirm to apply.{RESET}")
            return

    # Capture local commit before pulling so we can show changelog after
    pre_pull_commit = local

    # Run git pull
    utf8_print(f"  Pulling latest from GitHub...")
    try:
        result = subprocess.run(
            [_GIT_PATH, "pull", "origin", "master"],
            capture_output=True, text=True, timeout=30,
            cwd=str(repo_dir),
        )
        if result.returncode == 0:
            # Verify post-pull HEAD matches the expected remote commit
            post_pull_head = get_local_commit()
            if post_pull_head and post_pull_head != remote:
                utf8_print(f"  {RED}Integrity check failed: HEAD after pull ({post_pull_head[:8]}) does not match expected remote ({remote[:8]}).{RESET}")
                utf8_print(f"  Rolling back to previous commit ({pre_pull_commit[:8]})...")
                try:
                    subprocess.run(
                        [_GIT_PATH, "reset", "--hard", pre_pull_commit],
                        capture_output=True, text=True, timeout=10,
                        cwd=str(repo_dir),
                    )
                except Exception:
                    pass
                utf8_print(f"  {YELLOW}Update aborted. Please try again or re-clone the repository.{RESET}")
                return
            # Read the new version from the updated file on disk
            new_version = _read_version_from_file(script_path)
            if new_version and new_version != VERSION:
                utf8_print(f"  {GREEN}Updated to v{new_version}!{RESET}")
            else:
                utf8_print(f"  {GREEN}Updated successfully!{RESET}")
            if result.stdout.strip():
                for ln in result.stdout.strip().split("\n"):
                    utf8_print(f"  {DIM}{ln}{RESET}")
            # Show changelog — commits between old HEAD and new HEAD
            if pre_pull_commit:
                try:
                    log_result = subprocess.run(
                        [_GIT_PATH, "log", f"{pre_pull_commit}..HEAD", "--oneline", "--no-decorate", "-20"],
                        capture_output=True, text=True, timeout=5,
                        cwd=str(repo_dir),
                    )
                    if log_result.returncode == 0 and log_result.stdout.strip():
                        utf8_print(f"\n  {BOLD}Changelog:{RESET}")
                        for ln in log_result.stdout.strip().split("\n"):
                            utf8_print(f"    {DIM}{ln}{RESET}")
                except Exception:
                    pass
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
        utf8_print(f"  {RED}Update error: {type(e).__name__}{RESET}")


def read_cache(cache_path, ttl):
    """Return the full cache dict if fresh, else None."""
    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            cached = json.load(f)
        if time.time() - cached.get("timestamp", 0) < ttl:
            return cached
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        pass
    return None


_USAGE_CACHE_KEYS = {"five_hour", "seven_day", "extra_usage"}

def write_cache(cache_path, line, usage=None, plan=None):
    try:
        data = {"timestamp": time.time(), "line": line}
        if usage is not None:
            data["usage"] = {k: v for k, v in usage.items() if k in _USAGE_CACHE_KEYS}
        if plan is not None:
            data["plan"] = plan
        with _secure_open_write(cache_path) as f:
            json.dump(data, f)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Credentials & API
# ---------------------------------------------------------------------------

def get_credentials():
    """Read OAuth token from credentials file, macOS Keychain, or env var."""

    def _extract(data):
        oauth = data.get("claudeAiOauth", {})
        token = oauth.get("accessToken")
        tier = oauth.get("rateLimitTier", "")
        if not token:
            return None, None
        plan = PLAN_NAMES.get(tier, _sanitize(tier.replace("default_claude_", "").replace("_", " ").title()))
        return token, plan

    # 1. File-based (~/.claude/.credentials.json)
    creds_path = Path.home() / ".claude" / ".credentials.json"
    try:
        with open(creds_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        token, plan = _extract(data)
        if token:
            return token, plan
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        pass

    # 2. macOS Keychain fallback
    if sys.platform == "darwin":
        try:
            result = subprocess.run(
                ["/usr/bin/security", "find-generic-password",
                 "-s", "Claude Code-credentials", "-w"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                data = json.loads(result.stdout.strip())
                token, plan = _extract(data)
                if token:
                    return token, plan
        except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError, ValueError):
            pass

    # 3. Environment variable fallback (all platforms)
    env_token = os.environ.get("CLAUDE_CODE_OAUTH_TOKEN")
    if env_token:
        return env_token, ""

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
        return json.loads(resp.read(1_000_000))  # 1 MB max


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


def _fmt_tokens(n):
    """Format token count: 200000 -> '200k', 1000000 -> '1M'."""
    if n >= 1_000_000:
        return f"{n / 1_000_000:.0f}M" if n % 1_000_000 == 0 else f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.0f}k" if n % 1_000 == 0 else f"{n / 1_000:.1f}k"
    return str(n)


def make_bar(pct, theme=None, plain=False, width=None, bar_style=None):
    """Build a coloured bar. plain=True returns characters only (no ANSI)."""
    if theme is None:
        theme = THEMES["default"]
    if width is None:
        width = BAR_SIZES[DEFAULT_BAR_SIZE]
    fill_char, empty_char = BAR_STYLES.get(bar_style or DEFAULT_BAR_STYLE, BAR_STYLES[DEFAULT_BAR_STYLE])
    pct = pct or 0
    filled = round(pct / 100 * width)
    filled = max(0, min(width, filled))
    if plain:
        # Keep empty chars DIM so rainbow_colorize (color_all=False) preserves
        # the distinction: filled chars get rainbow, empty chars stay dim
        return f"{fill_char * filled}{DIM}{empty_char * (width - filled)}{RESET}"
    colour = bar_colour(pct, theme)
    return f"{colour}{fill_char * filled}{DIM}{empty_char * (width - filled)}{RESET}"


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


def _get_history_path():
    """Return path to usage history file."""
    return get_state_dir() / "history.json"


def _read_history():
    """Read usage history samples."""
    try:
        with open(_get_history_path(), "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _append_history(usage):
    """Append a usage sample to history and prune old entries."""
    five = usage.get("five_hour", {})
    seven = usage.get("seven_day", {})
    session_pct = five.get("utilization") or 0
    weekly_pct = seven.get("utilization") or 0

    samples = _read_history()
    now = time.time()
    samples.append({"t": now, "s": session_pct, "w": weekly_pct})

    # Prune entries older than 24 hours
    cutoff = now - HISTORY_MAX_AGE
    samples = [s for s in samples if s.get("t", 0) > cutoff]

    try:
        with _secure_open_write(_get_history_path()) as f:
            json.dump(samples, f)
    except OSError:
        pass


def _render_sparkline(samples, key="s", width=8):
    """Render a sparkline from usage samples."""
    if not samples:
        return ""
    # Take the last `width` samples
    recent = samples[-width:]
    chars = []
    for s in recent:
        val = s.get(key, 0)
        # Map 0-100 to index 0-6 (avoid █ at index 7 — it's in ALL_BAR_CHARS
        # and would be skipped by apply_shimmer)
        idx = min(6, max(0, int(val / 100 * 6.99)))
        chars.append(SPARKLINE_CHARS[idx])
    return "".join(chars)


def _estimate_runway(samples, current_pct):
    """Estimate time until 100% usage via linear regression over recent samples.

    Returns a string like '~2h 15m' or '~45m', or None if insufficient data.
    """
    if len(samples) < 2 or current_pct >= 100:
        return None

    now = time.time()
    # Use samples from the last 10 minutes
    cutoff = now - 600
    recent = [s for s in samples if s.get("t", 0) > cutoff]

    if len(recent) < 2:
        return None

    # Simple linear regression: pct vs time
    n = len(recent)
    sum_t = sum(s["t"] for s in recent)
    sum_s = sum(s.get("s", 0) for s in recent)
    sum_ts = sum(s["t"] * s.get("s", 0) for s in recent)
    sum_tt = sum(s["t"] ** 2 for s in recent)

    denom = n * sum_tt - sum_t ** 2
    if abs(denom) < 1e-10:
        return None

    slope = (n * sum_ts - sum_t * sum_s) / denom  # pct per second

    if slope <= 0.001:
        return None  # Usage is flat or declining

    remaining = 100.0 - current_pct
    seconds_to_full = remaining / slope

    if seconds_to_full > 86400:  # More than 24 hours, not useful
        return None

    hours = int(seconds_to_full // 3600)
    minutes = int((seconds_to_full % 3600) // 60)

    if hours > 0:
        return f"~{hours}h {minutes:02d}m"
    return f"~{minutes}m"


def _compute_velocity(samples):
    """Compute usage velocity in pct/min from recent history samples."""
    if len(samples) < 2:
        return None
    now = time.time()
    recent = [s for s in samples if s.get("t", 0) > now - 300]  # last 5 min
    if len(recent) < 2:
        return None
    dt = recent[-1]["t"] - recent[0]["t"]
    if dt < 10:  # less than 10 seconds of data
        return None
    dp = recent[-1].get("s", 0) - recent[0].get("s", 0)
    return (dp / dt) * 60  # pct per minute


def _get_status_message(pct, velocity=None):
    """Return a (message, severity) tuple based on usage percentage and velocity.

    Severity: 'low', 'mid', 'high'
    """
    if pct >= 95:
        return ("At the limit", "high")
    if pct >= 80:
        return ("Pace yourself", "high")
    if pct >= 60:
        if velocity is not None and velocity > 2.0:
            return ("Running hot", "high")
        return ("Steady pace", "mid")
    if pct >= 30:
        if velocity is not None and velocity > 2.0:
            return ("In the flow", "mid")
        return ("Cruising", "mid")
    if pct >= 10:
        return ("Warming up", "low")
    return ("Fresh start", "low")


# ---------------------------------------------------------------------------
# Session stats & streaks
# ---------------------------------------------------------------------------

STREAK_MILESTONES = {
    7: "Week!",
    30: "Month!",
    50: "Fifty!",
    100: "Century!",
    200: "200 club!",
    365: "Year!",
    500: "500!",
    1000: "Legend!",
}


def _today_local():
    """Return today's date as YYYY-MM-DD in local timezone."""
    return datetime.now().strftime("%Y-%m-%d")


def _get_stats_path():
    """Return path to stats file."""
    return get_state_dir() / "stats.json"


def _load_stats():
    """Load stats from disk with defaults."""
    try:
        with open(_get_stats_path(), "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {
            "first_seen": _today_local(),
            "total_sessions": 0,
            "daily_dates": [],
            "current_streak": 0,
            "longest_streak": 0,
            "last_date": "",
        }


def _save_stats(stats):
    """Save stats to disk."""
    try:
        with _secure_open_write(_get_stats_path()) as f:
            json.dump(stats, f, indent=2)
    except OSError:
        pass


def _calculate_streak(daily_dates, today):
    """Calculate current and longest streak from date strings.

    Current streak counts consecutive days ending at today or yesterday.
    Returns (current_streak, longest_streak).
    """
    if not daily_dates:
        return (0, 0)

    # Deduplicate and sort
    unique = sorted(set(daily_dates))
    dates = []
    for d in unique:
        try:
            dates.append(datetime.strptime(d, "%Y-%m-%d").date())
        except ValueError:
            continue

    if not dates:
        return (0, 0)

    try:
        today_date = datetime.strptime(today, "%Y-%m-%d").date()
    except ValueError:
        return (0, 0)

    # Calculate longest streak
    longest = 1
    run = 1
    for i in range(1, len(dates)):
        if (dates[i] - dates[i - 1]).days == 1:
            run += 1
            longest = max(longest, run)
        else:
            run = 1
    longest = max(longest, run)

    # Calculate current streak using ordinal day arithmetic
    current_streak = 0
    check_ord = today_date.toordinal()
    for d in reversed(dates):
        d_ord = d.toordinal()
        if d_ord == check_ord:
            current_streak += 1
            check_ord -= 1
        elif d_ord == check_ord + 1 and current_streak == 0:
            # Today not logged yet, start from yesterday
            current_streak = 1
            check_ord = d_ord - 1
        elif d_ord < check_ord:
            break

    return (current_streak, longest)


def _check_milestone(total):
    """Check if total sessions hit a milestone. Returns message or None."""
    return STREAK_MILESTONES.get(total)


def _update_stats():
    """Update daily stats on fresh fetch. Returns (stats, milestone_or_None)."""
    stats = _load_stats()
    today = _today_local()

    if stats.get("last_date") == today:
        return (stats, None)  # Already updated today

    if not stats.get("first_seen"):
        stats["first_seen"] = today

    daily_dates = stats.get("daily_dates", [])
    if today not in daily_dates:
        daily_dates.append(today)
    stats["daily_dates"] = daily_dates

    stats["total_sessions"] = stats.get("total_sessions", 0) + 1

    current, longest = _calculate_streak(daily_dates, today)
    stats["current_streak"] = current
    stats["longest_streak"] = max(stats.get("longest_streak", 0), longest)
    stats["last_date"] = today

    milestone = _check_milestone(stats["total_sessions"])

    _save_stats(stats)
    return (stats, milestone)


def _get_streak_display(config, stats):
    """Return formatted streak string like '7d streak' or ''."""
    show = config.get("show", DEFAULT_SHOW)
    if not show.get("streak", True):
        return ""
    streak = stats.get("current_streak", 0)
    if streak < 2:
        return ""
    style = config.get("streak_style", "text")
    if style == "fire":
        return f"\U0001f525{streak}"
    return f"{streak}d streak"


def cmd_stats():
    """Show full session stats summary."""
    stats = _load_stats()
    today = _today_local()
    current, longest = _calculate_streak(stats.get("daily_dates", []), today)

    utf8_print(f"\n{BOLD}claude-pulse stats{RESET}\n")
    utf8_print(f"  First seen:     {stats.get('first_seen', 'unknown')}")
    utf8_print(f"  Total sessions: {stats.get('total_sessions', 0)}")
    utf8_print(f"  Days active:    {len(set(stats.get('daily_dates', [])))}")
    utf8_print(f"  Current streak: {current}d")
    utf8_print(f"  Longest streak: {max(stats.get('longest_streak', 0), longest)}d")

    milestone = _check_milestone(stats.get("total_sessions", 0))
    if milestone:
        utf8_print(f"  Milestone:      {BRIGHT_YELLOW}{milestone}{RESET}")
    utf8_print("")


def _parse_stdin_context(raw_stdin):
    """Parse Claude Code's stdin JSON for session context.

    Extracts model name, context window usage, and cost.
    Returns dict with available keys, or empty dict on error.
    """
    if not raw_stdin or not raw_stdin.strip():
        return {}
    try:
        data = json.loads(raw_stdin)
    except (json.JSONDecodeError, TypeError):
        return {}

    result = {}

    # Model name
    try:
        model = data.get("data", data).get("model", {})
        display_name = _sanitize(model.get("display_name", ""))
        if display_name:
            # Strip "Claude " prefix: "Claude Opus 4.6" → "Opus 4.6"
            short = display_name.replace("Claude ", "").strip()
            result["model_name"] = short if short else display_name
        else:
            model_id = model.get("id", "")
            if model_id:
                result["model_name"] = MODEL_SHORT_NAMES.get(model_id, _sanitize(model_id.split("-")[-1].title()))
    except (AttributeError, KeyError):
        pass

    # Context window usage
    try:
        ctx = data.get("data", data).get("context_window", {})
        used_pct = ctx.get("used_percentage")
        if used_pct is not None:
            result["context_pct"] = float(used_pct)
        # Raw token counts for tokens display mode
        input_tok = ctx.get("total_input_tokens")
        output_tok = ctx.get("total_output_tokens")
        ctx_size = ctx.get("context_window_size")
        if input_tok is not None and ctx_size is not None:
            result["context_used"] = int(input_tok) + int(output_tok or 0)
            result["context_limit"] = int(ctx_size)
    except (AttributeError, KeyError, ValueError, TypeError):
        pass

    # Cost
    try:
        cost = data.get("data", data).get("cost", {})
        total = cost.get("total_cost_usd")
        if total is not None:
            result["cost_usd"] = float(total)
    except (AttributeError, KeyError, ValueError, TypeError):
        pass

    return result


def _get_heatmap_path():
    """Return path to heatmap data file."""
    return get_state_dir() / "heatmap.json"


def _update_heatmap(usage):
    """Update the activity heatmap with current usage data."""
    five = usage.get("five_hour", {})
    seven = usage.get("seven_day", {})
    session_pct = five.get("utilization") or 0
    weekly_pct = seven.get("utilization") or 0

    # Load existing heatmap
    try:
        with open(_get_heatmap_path(), "r", encoding="utf-8") as f:
            heatmap = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        heatmap = {}

    hours = heatmap.get("hours", {})

    # Current hour key in UTC: YYYY-MM-DDTHH
    now = datetime.now(timezone.utc)
    hour_key = now.strftime("%Y-%m-%dT%H")

    # Update entry for current hour — track peak session_pct
    entry = hours.get(hour_key, {"session_pct": 0, "weekly_pct": 0, "samples": 0})
    entry["session_pct"] = max(entry.get("session_pct", 0), session_pct)
    entry["weekly_pct"] = max(entry.get("weekly_pct", 0), weekly_pct)
    entry["samples"] = entry.get("samples", 0) + 1
    hours[hour_key] = entry

    # Prune entries older than 28 days (672 hours)
    cutoff = now - timedelta(days=28)
    cutoff_key = cutoff.strftime("%Y-%m-%dT%H")
    hours = {k: v for k, v in hours.items() if k >= cutoff_key}

    heatmap["hours"] = hours

    try:
        with _secure_open_write(_get_heatmap_path()) as f:
            json.dump(heatmap, f)
    except OSError:
        pass


def _heatmap_intensity(pct):
    """Return intensity level 0-4 from usage percentage."""
    if pct <= 0:
        return 0
    if pct <= 25:
        return 1
    if pct <= 50:
        return 2
    if pct <= 75:
        return 3
    return 4


def _render_heatmap(config=None):
    """Render a 7-row x 24-col activity heatmap from stored data.

    Rows = days of week (Mon-Sun), cols = hours (0-23).
    Returns a multi-line string.
    """
    if config is None:
        config = load_config()

    theme_name = config.get("theme", "default")
    theme = get_theme_colours(theme_name)

    intensity_chars = ["\u00b7", "\u2591", "\u2592", "\u2593", "\u2588"]  # ·, ░, ▒, ▓, █
    intensity_colors = ["", theme["low"], theme["low"], theme["mid"], theme["high"]]

    # Load heatmap data
    try:
        with open(_get_heatmap_path(), "r", encoding="utf-8") as f:
            heatmap = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        heatmap = {}

    hours_data = heatmap.get("hours", {})

    # Build a 7x24 grid (Mon=0 .. Sun=6, hours 0-23)
    # Use the last 7 days from today
    now = datetime.now(timezone.utc)
    grid = [[0] * 24 for _ in range(7)]

    for day_offset in range(7):
        day = now - timedelta(days=(6 - day_offset))
        weekday = day.weekday()  # Mon=0, Sun=6
        for hour in range(24):
            key = day.strftime("%Y-%m-%dT") + f"{hour:02d}"
            entry = hours_data.get(key, {})
            pct = entry.get("session_pct", 0)
            grid[weekday][hour] = _heatmap_intensity(pct)

    day_labels = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    lines = []

    # Hour labels header
    header = "     "
    for h in range(24):
        if h % 6 == 0:
            header += f"{h:<3}"
        else:
            header += "   "
    lines.append(header.rstrip())

    # Grid rows
    for weekday in range(7):
        row = f" {day_labels[weekday]} "
        for hour in range(24):
            level = grid[weekday][hour]
            ch = intensity_chars[level]
            color = intensity_colors[level]
            if color:
                row += f"{color}{ch}{RESET}  "
            else:
                row += f"{DIM}{ch}{RESET}  "
        lines.append(row.rstrip())

    return "\n".join(lines)


def cmd_heatmap():
    """Display the activity heatmap."""
    config = load_config()
    utf8_print(f"\n{BOLD}Activity Heatmap (last 7 days){RESET}\n")
    heatmap = _render_heatmap(config)
    utf8_print(heatmap)

    # Legend
    theme_name = config.get("theme", "default")
    theme = get_theme_colours(theme_name)
    utf8_print(f"\n  Legend: {DIM}\u00b7{RESET} none  {theme['low']}\u2591{RESET} low  {theme['low']}\u2592{RESET} med  {theme['mid']}\u2593{RESET} high  {theme['high']}\u2588{RESET} peak")
    utf8_print("")


def build_status_line(usage, plan, config=None, stdin_ctx=None):
    if config is None:
        config = load_config()

    theme_name = config.get("theme", "default")
    is_rainbow_theme = theme_name == "rainbow"
    animate = config.get("animate", False)

    # Rainbow rendering applies when:
    # 1. Theme is "rainbow", OR
    # 2. animate is on (rainbow animation overlay on any theme)
    use_rainbow = is_rainbow_theme or animate

    if use_rainbow:
        bar_plain = True
        theme = get_theme_colours(theme_name) if not is_rainbow_theme else THEMES["default"]
    else:
        bar_plain = False
        theme = get_theme_colours(theme_name)

    show = config.get("show", DEFAULT_SHOW)
    bar_size = config.get("bar_size", DEFAULT_BAR_SIZE)
    bw = BAR_SIZES.get(bar_size, BAR_SIZES[DEFAULT_BAR_SIZE])
    bstyle = config.get("bar_style", DEFAULT_BAR_STYLE)
    layout = config.get("layout", DEFAULT_LAYOUT)

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
            pct = five.get("utilization") or 0
            bar = make_bar(pct, theme, plain=bar_plain, width=bw, bar_style=bstyle)
            reset = format_reset_time(five.get("resets_at")) if show.get("timer", True) else None
            reset_str = f" {reset}" if reset else ""
            if layout == "compact":
                parts.append(f"S {bar} {pct:.0f}%{reset_str}")
            elif layout == "minimal":
                parts.append(f"{bar} {pct:.0f}%{reset_str}")
            elif layout == "percent-first":
                parts.append(f"{pct:.0f}% {bar}{reset_str}")
            else:  # standard
                # Load history once for sparkline, runway, and smart messages
                history = _read_history() if show.get("sparkline", True) or show.get("runway", True) or show.get("status_message", True) else []
                # Smart status message replaces "Session" label
                label = "Session"
                if show.get("status_message", True):
                    velocity = _compute_velocity(history)
                    msg, _ = _get_status_message(pct, velocity)
                    label = msg
                # Sparkline
                spark_str = ""
                if show.get("sparkline", True):
                    spark = _render_sparkline(history)
                    if spark:
                        spark_str = f" {spark}"
                # Runway
                runway_str = ""
                if show.get("runway", True):
                    runway = _estimate_runway(history, pct)
                    if runway:
                        runway_str = f" {runway}"
                # Separate timer from runway/sparkline with · when both present
                if reset_str and (runway_str or spark_str):
                    reset_str = f" \u00b7{reset}"
                parts.append(f"{label} {bar} {pct:.0f}%{spark_str}{runway_str}{reset_str}")
        else:
            bar = make_bar(0, theme, plain=bar_plain, width=bw, bar_style=bstyle)
            if layout == "compact":
                parts.append(f"S {bar} 0%")
            elif layout == "minimal":
                parts.append(f"{bar} 0%")
            elif layout == "percent-first":
                parts.append(f"0% {bar}")
            else:
                parts.append(f"Session {bar} 0%")

    # Weekly Limit (7-day all models)
    if show.get("weekly", True):
        seven = usage.get("seven_day")
        if seven:
            pct = seven.get("utilization") or 0
            bar = make_bar(pct, theme, plain=bar_plain, width=bw, bar_style=bstyle)
            if layout == "compact":
                parts.append(f"W {bar} {pct:.0f}%")
            elif layout == "minimal":
                parts.append(f"{bar} {pct:.0f}%")
            elif layout == "percent-first":
                parts.append(f"{pct:.0f}% {bar}")
            else:
                parts.append(f"Weekly {bar} {pct:.0f}%")

    # Extra usage (bonus/gifted credits)
    # Auto-shows when credits are gifted, unless user explicitly hid it
    extra = usage.get("extra_usage")
    extra_enabled_by_user = show.get("extra", False)
    extra_explicitly_hidden = config.get("extra_hidden", False)
    extra_has_credits = extra and extra.get("is_enabled") and (extra.get("monthly_limit") or 0) > 0
    if extra_enabled_by_user or (extra_has_credits and not extra_explicitly_hidden):
        currency = _sanitize(config.get("currency", "\u00a3"))[:5]
        if extra and extra.get("is_enabled"):
            pct = min(extra.get("utilization") or 0, 100)
            used = (extra.get("used_credits") or 0) / 100  # API returns pence/cents
            limit = (extra.get("monthly_limit") or 0) / 100
            extra_display = config.get("extra_display", "auto")
            if extra_display == "auto":
                extra_display = "amount" if limit == 0 else "full"
            if extra_display == "amount":
                if layout == "compact":
                    parts.append(f"E {currency}{used:.2f}")
                elif layout == "minimal":
                    parts.append(f"{currency}{used:.2f}")
                else:
                    parts.append(f"Extra {currency}{used:.2f}")
            else:
                bar = make_bar(pct, theme, plain=bar_plain, width=bw, bar_style=bstyle)
                if layout == "compact":
                    parts.append(f"E {bar} {currency}{used:.2f}/{currency}{limit:.2f}")
                elif layout == "minimal":
                    parts.append(f"{bar} {currency}{used:.2f}")
                elif layout == "percent-first":
                    parts.append(f"{currency}{used:.2f} {bar}")
                else:
                    parts.append(f"Extra {bar} {currency}{used:.2f}/{currency}{limit:.2f}")
        elif extra_enabled_by_user:
            bar = make_bar(0, theme, plain=bar_plain, bar_style=bstyle)
            if layout == "minimal":
                parts.append(f"{bar} none")
            else:
                parts.append(f"Extra {bar} none")

    # Context window usage from stdin context
    if stdin_ctx and show.get("context", True):
        ctx_pct = stdin_ctx.get("context_pct")
        if ctx_pct is not None:
            ctx_bar = make_bar(ctx_pct, theme, plain=bar_plain, width=bw, bar_style=bstyle)
            ctx_fmt = config.get("context_format", "percent")
            ctx_used = stdin_ctx.get("context_used")
            ctx_limit = stdin_ctx.get("context_limit")

            # Derive token counts from percentage + model when API doesn't provide them
            if ctx_used is None or ctx_limit is None:
                model_name = stdin_ctx.get("model_name", "")
                window = MODEL_CONTEXT_WINDOWS.get(model_name, DEFAULT_CONTEXT_WINDOW)
                ctx_limit = window
                ctx_used = int(ctx_pct / 100 * window)

            if ctx_fmt == "tokens":
                used_str = _fmt_tokens(ctx_used)
                limit_str = _fmt_tokens(ctx_limit)
                label = f"{used_str}/{limit_str}"
            else:
                label = f"{ctx_pct:.0f}%"

            if layout == "compact":
                parts.append(f"C {ctx_bar} {label}")
            elif layout == "minimal":
                parts.append(f"{ctx_bar} {label}")
            elif layout == "percent-first":
                parts.append(f"{label} {ctx_bar}")
            else:
                parts.append(f"Context {ctx_bar} {label}")

    # Plan name (hidden in minimal layout)
    if layout != "minimal" and show.get("plan", True) and plan:
        parts.append(_sanitize(plan))

    # Streak display
    if show.get("streak", True):
        try:
            stats = _load_stats()
            sd = _get_streak_display(config, stats)
            if sd:
                parts.append(sd)
        except Exception:
            pass

    # Model name from stdin context
    if stdin_ctx and show.get("model", True):
        model = stdin_ctx.get("model_name")
        if model:
            parts.append(model)

    line = " | ".join(parts)

    # Animation: on = rainbow always moving, off = static theme colours
    if use_rainbow:
        line = rainbow_colorize(line, color_all=False, shimmer=animate)
    else:
        text_color_code = resolve_text_color(config)
        if text_color_code:
            line = apply_text_color(line, text_color_code)

    return line


# ---------------------------------------------------------------------------
# Install
# ---------------------------------------------------------------------------

def _get_python_cmd():
    """Return the Python command to use in hooks/settings.

    Uses sys.executable to ensure we match whatever Python is running this script.
    On Linux this is typically 'python3', on Windows 'python'.
    """
    exe = sys.executable
    # If the executable path contains spaces, quote it
    if " " in exe:
        return f'"{exe}"'
    return exe


def install_status_line():
    settings_path = Path.home() / ".claude" / "settings.json"
    script_path = Path(__file__).resolve()
    python_cmd = _get_python_cmd()

    settings = {}
    if settings_path.exists():
        try:
            with open(settings_path, "r", encoding="utf-8") as f:
                settings = json.load(f)
        except (json.JSONDecodeError, OSError):
            pass

    # Status line command
    settings["statusLine"] = {
        "type": "command",
        "command": f'{python_cmd} "{script_path}"',
        "refresh": 150,
    }

    # No hooks installed here — static status bar by default.
    # Use --animate on for always-on animation (installs hooks automatically)
    # Use --install-hooks for animate-while-working mode

    _secure_mkdir(settings_path.parent)
    with _secure_open_write(settings_path) as f:
        json.dump(settings, f, indent=2)

    utf8_print(f"Installed status line to {settings_path}")
    utf8_print(f"Command: {python_cmd} \"{script_path}\"")
    utf8_print("Restart Claude Code to see the status line.")
    utf8_print("Tip: use --animate on for always-on rainbow animation.")


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
    user_bar_style = user_config.get("bar_style", DEFAULT_BAR_STYLE)
    for name in THEMES:
        demo_tc = THEME_DEMO_TEXT.get(name, "white")
        demo_config = {"theme": name, "bar_size": user_bar_size, "bar_style": user_bar_style, "text_color": demo_tc, "show": {"session": True, "weekly": True, "plan": True, "timer": False, "extra": False, "sparkline": False, "runway": False, "status_message": False, "streak": False, "model": False, "context": False}}
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
    user_bar_style = current_config.get("bar_style", DEFAULT_BAR_STYLE)
    for name in THEMES:
        # Use the accent colour so each theme looks distinct in the preview
        demo_tc = THEME_DEMO_TEXT.get(name, "white")
        demo_config = {"theme": name, "bar_size": user_bar_size, "bar_style": user_bar_style, "text_color": demo_tc, "show": {"session": True, "weekly": True, "plan": True, "timer": False, "extra": False, "sparkline": False, "runway": False, "status_message": False, "streak": False, "model": False, "context": False}}
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
            utf8_print(f"Unknown part: {part} (valid: {', '.join(sorted(valid))})")
            return
    for part in parts:
        config["show"][part] = True
        # Clear explicit hide flag so auto-show can work again
        if part == "extra":
            config.pop("extra_hidden", None)
    save_config(config)
    utf8_print(f"Enabled: {', '.join(parts)}")


def cmd_hide(parts_str):
    """Disable the given comma-separated parts."""
    config = load_config()
    parts = [p.strip().lower() for p in parts_str.split(",")]
    valid = set(DEFAULT_SHOW.keys())
    for part in parts:
        if part not in valid:
            utf8_print(f"Unknown part: {part} (valid: {', '.join(sorted(valid))})")
            return
    for part in parts:
        config["show"][part] = False
        # Mark extra as explicitly hidden so auto-show respects it
        if part == "extra":
            config["extra_hidden"] = True
    save_config(config)
    utf8_print(f"Disabled: {', '.join(parts)}")


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
    bst = config.get("bar_style", DEFAULT_BAR_STYLE)
    bst_chars = BAR_STYLES.get(bst, BAR_STYLES[DEFAULT_BAR_STYLE])
    utf8_print(f"  Bar style: {bst} ({bst_chars[0]}{bst_chars[1]})")
    ly = config.get("layout", DEFAULT_LAYOUT)
    utf8_print(f"  Layout:    {ly}")
    cf = config.get("context_format", "percent")
    utf8_print(f"  Context:   {cf}")
    ed = config.get("extra_display", "auto")
    utf8_print(f"  Extra display: {ed}")
    anim = config.get("animate", False)
    anim_state = f"{GREEN}on{RESET}" if anim else f"{RED}off{RESET}"
    utf8_print(f"  Animation:    {anim_state}  ({'rainbow always moving' if anim else 'static'})")
    tc = config.get("text_color", "auto")
    if tc == "auto":
        resolved = THEME_TEXT_DEFAULTS.get(theme_name, "white")
        tc_code = TEXT_COLORS.get(resolved, "")
        utf8_print(f"  Text colour:  {tc_code}auto{RESET}  (using {tc_code}{resolved}{RESET} for {theme_name} theme)")
    else:
        tc_code = TEXT_COLORS.get(tc, "")
        utf8_print(f"  Text colour:  {tc_code}{tc}{RESET}")
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
                used = (_extra.get("used_credits") or 0) / 100  # API returns pence/cents
                limit = (_extra.get("monthly_limit") or 0) / 100
                pct = min(_extra.get("utilization") or 0, 100)
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
    # Handle SIGPIPE gracefully on Unix (e.g. when piped to head)
    if hasattr(signal, "SIGPIPE"):
        signal.signal(signal.SIGPIPE, signal.SIG_DFL)

    args = sys.argv[1:]

    if "--update" in args:
        cmd_update()
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
            utf8_print("Usage: --theme <name>")
        return

    if "--show" in args:
        idx = args.index("--show")
        if idx + 1 < len(args):
            cmd_show(args[idx + 1])
        else:
            utf8_print("Usage: --show <parts>  (comma-separated: session,weekly,plan,timer,extra,update)")
        return

    if "--hide" in args:
        idx = args.index("--hide")
        if idx + 1 < len(args):
            cmd_hide(args[idx + 1])
        else:
            utf8_print("Usage: --hide <parts>  (comma-separated: session,weekly,plan,timer,extra,update)")
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
                utf8_print(f"Unknown value: {val}  (use on or off)")
                return
            config = load_config()
            config["animate"] = anim
            save_config(config)
            try:
                os.remove(get_cache_path())
            except OSError:
                pass
            if anim:
                utf8_print(f"Animation: {GREEN}on{RESET}  (rainbow always moving)")
            else:
                utf8_print(f"Animation: {RED}off{RESET}  (static)")
        else:
            utf8_print("Usage: --animate on|off")
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

    if "--bar-style" in args:
        idx = args.index("--bar-style")
        if idx + 1 < len(args):
            val = args[idx + 1].lower()
            if val not in BAR_STYLES:
                utf8_print(f"Unknown style: {val}")
                utf8_print(f"Available: {', '.join(BAR_STYLES.keys())}")
                return
            config = load_config()
            config["bar_style"] = val
            save_config(config)
            try:
                os.remove(get_cache_path())
            except OSError:
                pass
            fill_ch, empty_ch = BAR_STYLES[val]
            demo = f"{GREEN}{fill_ch * 4}{DIM}{empty_ch * 4}{RESET}"
            utf8_print(f"Bar style: {BOLD}{val}{RESET}  {demo}")
        else:
            utf8_print(f"Usage: --bar-style <name>\n")
            for name, (fc, ec) in BAR_STYLES.items():
                demo = f"{GREEN}{fc * 4}{DIM}{ec * 4}{RESET}"
                utf8_print(f"  {name:<10} {demo}")
        return

    if "--extra-display" in args:
        idx = args.index("--extra-display")
        if idx + 1 < len(args):
            val = args[idx + 1].lower()
            if val not in ("auto", "full", "amount"):
                utf8_print(f"Unknown value: {val}  (use auto, full, or amount)")
                return
            config = load_config()
            config["extra_display"] = val
            save_config(config)
            try:
                os.remove(get_cache_path())
            except OSError:
                pass
            descriptions = {
                "auto": "auto-detects (amount only if no spending limit, full bar otherwise)",
                "full": "progress bar with amount and limit",
                "amount": "spend amount only, no bar",
            }
            utf8_print(f"Extra display: {BOLD}{val}{RESET}  ({descriptions[val]})")
        else:
            utf8_print("Usage: --extra-display <auto|full|amount>")
            utf8_print(f"  {'auto':<8} Auto-detect (amount only if no spending limit)")
            utf8_print(f"  {'full':<8} Progress bar with amount and limit")
            utf8_print(f"  {'amount':<8} Spend amount only, no bar")
        return

    if "--context-format" in args:
        idx = args.index("--context-format")
        if idx + 1 < len(args):
            val = args[idx + 1].lower()
            if val not in ("percent", "tokens"):
                utf8_print(f"Unknown format: {val}  (use percent or tokens)")
                return
            config = load_config()
            config["context_format"] = val
            save_config(config)
            try:
                os.remove(get_cache_path())
            except OSError:
                pass
            utf8_print(f"Context format: {BOLD}{val}{RESET}")
            if val == "tokens":
                utf8_print(f"{DIM}  Note: Claude Code uses a 200k context window.")
                utf8_print(f"  The 1M window is an API-only beta feature and not used here.{RESET}")
        else:
            utf8_print("Usage: --context-format percent|tokens")
        return

    if "--layout" in args:
        idx = args.index("--layout")
        if idx + 1 < len(args):
            val = args[idx + 1].lower()
            if val not in LAYOUTS:
                utf8_print(f"Unknown layout: {val}")
                utf8_print(f"Available: {', '.join(LAYOUTS)}")
                return
            config = load_config()
            config["layout"] = val
            save_config(config)
            try:
                os.remove(get_cache_path())
            except OSError:
                pass
            utf8_print(f"Layout: {BOLD}{val}{RESET}")
        else:
            utf8_print(f"Usage: --layout <name>")
            utf8_print(f"Available: {', '.join(LAYOUTS)}")
        return

    if "--currency" in args:
        idx = args.index("--currency")
        if idx + 1 < len(args):
            val = _sanitize(args[idx + 1])[:5]  # strip escapes, max 5 chars
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

    if "--stats" in args:
        cmd_stats()
        return

    if "--streak-style" in args:
        idx = args.index("--streak-style")
        if idx + 1 < len(args):
            val = args[idx + 1].lower()
            if val not in ("fire", "text"):
                utf8_print(f"Unknown streak style: {val}  (use fire or text)")
                return
            config = load_config()
            config["streak_style"] = val
            save_config(config)
            utf8_print(f"Streak style: {BOLD}{val}{RESET}")
        else:
            utf8_print("Usage: --streak-style fire|text")
        return

    if "--debug-stdin" in args:
        raw = ""
        if sys.stdin.isatty():
            utf8_print("No stdin data (interactive terminal). Pipe data or use from Claude Code.")
            return
        try:
            raw = sys.stdin.read(65536)
        except Exception:
            pass
        debug_path = get_state_dir() / "stdin_debug.json"
        try:
            with _secure_open_write(debug_path) as f:
                f.write(raw if raw else "{}")
        except OSError:
            pass
        utf8_print(f"Stdin debug written to: {debug_path}")
        if raw.strip():
            ctx = _parse_stdin_context(raw)
            utf8_print(f"Parsed context: {json.dumps(ctx, indent=2)}")
        return

    if "--heatmap" in args:
        cmd_heatmap()
        return

    if "--config" in args:
        cmd_print_config()
        return

    # Normal status line mode
    config = load_config()
    cache_ttl = config.get("cache_ttl_seconds", DEFAULT_CACHE_TTL)
    animate = config.get("animate", False)

    # One-time cleanup of legacy hooks from pre-v2.2.0
    try:
        _cleanup_hooks()
    except Exception:
        pass

    raw_stdin = ""
    if not sys.stdin.isatty():
        try:
            raw_stdin = sys.stdin.read(65536)
        except Exception:
            pass
    stdin_ctx = _parse_stdin_context(raw_stdin)

    # Persist stdin context (model, context %) in a separate file so it
    # survives across refreshes that don't receive stdin data from Claude Code.
    # Merge new data into persisted data so partial updates (e.g. model but
    # no context_pct during thinking) don't wipe previously known fields.
    _STDIN_CTX_KEYS = {"model_name", "context_pct", "context_used", "context_limit", "cost_usd"}
    stdin_ctx_path = get_state_dir() / "stdin_ctx.json"
    persisted = {}
    try:
        with open(str(stdin_ctx_path), "r", encoding="utf-8") as f:
            raw_persisted = json.load(f)
            persisted = {k: v for k, v in raw_persisted.items() if k in _STDIN_CTX_KEYS}
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass
    if stdin_ctx:
        persisted.update(stdin_ctx)
        try:
            with _secure_open_write(stdin_ctx_path) as f:
                json.dump(persisted, f)
        except OSError:
            pass
    stdin_ctx = persisted

    cache_path = get_cache_path()
    cached = read_cache(cache_path, cache_ttl)

    if cached is not None:
        if "usage" in cached:
            line = build_status_line(cached["usage"], cached.get("plan", ""), config, stdin_ctx)
        else:
            line = cached.get("line", "")
        line = append_update_indicator(line, config)
        sys.stdout.buffer.write((line + RESET + "\n").encode("utf-8"))
        return

    token, plan = get_credentials()
    if not token:
        if os.environ.get("ANTHROPIC_API_KEY"):
            line = "API key detected \u2014 claude-pulse requires a Pro/Max subscription"
        else:
            line = "No credentials \u2014 run claude and /login"
        write_cache(cache_path, line)
        sys.stdout.buffer.write((line + RESET + "\n").encode("utf-8"))
        return

    try:
        usage = fetch_usage(token)
        line = build_status_line(usage, plan, config, stdin_ctx)
    except urllib.error.HTTPError as e:
        usage = None
        if e.code == 401:
            line = "Token expired \u2014 restart Claude to refresh"
        elif e.code == 403:
            line = "Access denied \u2014 check your subscription"
        else:
            line = f"API error: {e.code}"
    except urllib.error.URLError:
        usage = None
        line = "Network error \u2014 retrying next refresh"
    except json.JSONDecodeError:
        usage = None
        line = "API returned invalid data"
    except (TypeError, ValueError):
        usage = None
        line = "Data error"
    except Exception as e:
        usage = None
        line = f"Usage unavailable: {type(e).__name__}"

    write_cache(cache_path, line, usage, plan)
    if usage is not None:
        _append_history(usage)
        _update_heatmap(usage)
        try:
            stats, milestone = _update_stats()
            if milestone:
                line = line + f" {BRIGHT_YELLOW}{milestone}{RESET}"
        except Exception:
            pass
    line = append_update_indicator(line, config)
    sys.stdout.buffer.write((line + RESET + "\n").encode("utf-8"))


if __name__ == "__main__":
    main()
