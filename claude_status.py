#!/usr/bin/env python3
"""Claude Code status line — reads usage data from Claude Code's stdin and displays real-time bars."""

VERSION = "3.1.0"

import json
import math
import os
import re
import shutil
import signal
import subprocess
import sys
import time
import urllib.request
import urllib.error
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

DEFAULT_CACHE_TTL = 60
BAR_SIZES = {"small": 4, "small-medium": 6, "medium": 8, "medium-large": 10, "large": 12}
DEFAULT_BAR_SIZE = "large"
DEFAULT_MAX_WIDTH_PCT = 80  # percentage of terminal width to use
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

# Gradient bar styles — each maps to (gradient_string, empty_char).
# gradient_string: chars from empty to full; gives (len - 1) sub-levels per position.
# empty_char: visible placeholder for unfilled slots (rendered DIM).
BAR_GRADIENT_STYLES = {
    "braille": ("\u28C0\u28C4\u28E4\u28E6\u28F6\u28F7\u28FF", "\u28C0"),
    #  gradient: ⣀     ⣄     ⣤     ⣦     ⣶     ⣷     ⣿   empty: ⣀
}

# Auto-register gradient styles into BAR_STYLES (last char = filled, empty_char)
for _gname, (_gchars, _gempty) in BAR_GRADIENT_STYLES.items():
    BAR_STYLES[_gname] = (_gchars[-1], _gempty)

# Precompute all bar characters for rainbow detection
ALL_BAR_CHARS = set()
for _f, _e in BAR_STYLES.values():
    ALL_BAR_CHARS.add(_f)
    ALL_BAR_CHARS.add(_e)
for _gchars, _gempty in BAR_GRADIENT_STYLES.values():
    for _gc in _gchars:
        ALL_BAR_CHARS.add(_gc)


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
    "default_claude_ai": "Pro",
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

# API pricing per million tokens (USD) — updated 2025
# https://docs.anthropic.com/en/docs/about-claude/pricing
API_PRICING = {
    "claude-opus-4-6": {"input": 15.0, "output": 75.0, "cache_read": 1.5, "cache_write": 18.75},
    "claude-opus-4": {"input": 15.0, "output": 75.0, "cache_read": 1.5, "cache_write": 18.75},
    "claude-sonnet-4-6": {"input": 3.0, "output": 15.0, "cache_read": 0.30, "cache_write": 3.75},
    "claude-sonnet-4-5": {"input": 3.0, "output": 15.0, "cache_read": 0.30, "cache_write": 3.75},
    "claude-sonnet-4": {"input": 3.0, "output": 15.0, "cache_read": 0.30, "cache_write": 3.75},
    "claude-haiku-4-5-20251001": {"input": 0.80, "output": 4.0, "cache_read": 0.08, "cache_write": 1.0},
    "claude-haiku-4-5": {"input": 0.80, "output": 4.0, "cache_read": 0.08, "cache_write": 1.0},
    "claude-3-5-sonnet": {"input": 3.0, "output": 15.0, "cache_read": 0.30, "cache_write": 3.75},
    "claude-3-5-haiku": {"input": 0.80, "output": 4.0, "cache_read": 0.08, "cache_write": 1.0},
    "claude-3-opus": {"input": 15.0, "output": 75.0, "cache_read": 1.5, "cache_write": 18.75},
}
# Display names for pricing table
API_PRICING_DISPLAY = {
    "claude-opus-4-6": "Opus 4.6",
    "claude-opus-4": "Opus 4",
    "claude-sonnet-4-6": "Sonnet 4.6",
    "claude-sonnet-4-5": "Sonnet 4.5",
    "claude-sonnet-4": "Sonnet 4",
    "claude-haiku-4-5-20251001": "Haiku 4.5",
    "claude-haiku-4-5": "Haiku 4.5",
    "claude-3-5-sonnet": "Sonnet 3.5",
    "claude-3-5-haiku": "Haiku 3.5",
    "claude-3-opus": "Opus 3",
}

# ---------------------------------------------------------------------------
# Hook infrastructure constants
# ---------------------------------------------------------------------------
HEARTBEAT_SPINNER = ["|", "/", "-", "\\"]  # Classic ASCII spinner — renders on every terminal
HOOK_STATE_FRESH_TTL = 300  # 5 minutes — keeps heartbeat visible between interactions
RAPID_CALL_WINDOW = 10
GIT_BRANCH_CACHE_TTL = 60

# ---------------------------------------------------------------------------
# Analytics constants
# ---------------------------------------------------------------------------
VELOCITY_ARROW_UP = "\u2191"    # ↑
VELOCITY_ARROW_FLAT = "\u2192"  # →
VELOCITY_ARROW_DOWN = "\u2193"  # ↓
STALENESS_WARN = 120
STALENESS_YELLOW = 300
STALENESS_RED = 600
CONTEXT_PRESSURE_PCT = 70
CONTEXT_PRESSURE_CRITICAL = 90
CONTEXT_PRESSURE_VELOCITY = 5.0

# ---------------------------------------------------------------------------
# Animation constants
# ---------------------------------------------------------------------------
ANIMATION_SPEEDS = {"slow": 0.5, "normal": 1.0, "fast": 2.0}
DEFAULT_ANIMATION_SPEED = "normal"
FLASH_THRESHOLDS = (50, 75, 90)
FLASH_DURATION = 3
FLASH_RENDER_TTL = 45.0
CELEBRATION_DURATION = 5
CELEBRATION_DROP_THRESHOLD = 20.0
CELEBRATION_CHAR = "\u2726"  # ✦

# ---------------------------------------------------------------------------
# Multi-session / Focus / Git drift constants
# ---------------------------------------------------------------------------
SESSION_STALE_SECONDS = 300
SESSION_DIR_NAME = "sessions"
POMODORO_DEFAULT_MINUTES = 25
POMODORO_BREAK_MINUTES = 5
POMODORO_FILE = "pomodoro.json"
GIT_DRIFT_CACHE_TTL = 300
GIT_DRIFT_FILE = "git_drift.json"
FILES_CHANGED_CACHE_TTL = 30
FILES_CHANGED_FILE = "files_changed.json"

_cached_terminal_width = None

def _detect_terminal_width():
    """Detect the real terminal width, even when stdout is piped.

    Tries progressively heavier approaches, returning the first success:
      1. os.get_terminal_size(stdout)  — direct TTY
      2. os.get_terminal_size(stderr)  — works when only stdout is piped
      3. os.get_terminal_size(stdin)   — same
      4. /dev/tty via os.get_terminal_size — POSIX controlling terminal
      5. COLUMNS env var               — honours explicit overrides
      6. /proc walk (Linux only)        — last resort; walks parent pids
         to find an ancestor with a terminal fd

    Returns the column count (int), or None if undetectable.
    The result is cached for the lifetime of the process (a single
    status-line render), avoiding repeated /proc I/O.
    """
    global _cached_terminal_width
    if _cached_terminal_width is not None:
        return _cached_terminal_width if _cached_terminal_width > 0 else None

    cols = _detect_terminal_width_uncached()
    _cached_terminal_width = cols if cols is not None else -1
    return cols


def _detect_terminal_width_uncached():
    """Internal: attempt each detection method in order."""
    # 1-3. Try each standard fd — stderr/stdin may still be a TTY
    for fd in (sys.stdout, sys.stderr, sys.stdin):
        try:
            return os.get_terminal_size(fd.fileno()).columns
        except (OSError, ValueError, AttributeError):
            pass
    # 4. POSIX controlling terminal — works on Linux + macOS even with piped stdio
    try:
        tty_fd = os.open("/dev/tty", os.O_RDONLY | os.O_NOCTTY)
        try:
            return os.get_terminal_size(tty_fd).columns
        finally:
            os.close(tty_fd)
    except OSError:
        pass
    # 5. Explicit COLUMNS environment variable
    try:
        cols = int(os.environ["COLUMNS"])
        if cols > 0:
            return cols
    except (KeyError, ValueError):
        pass
    # 6. Linux /proc walk — last resort (see _detect_width_from_proc)
    return _detect_width_from_proc()


def _detect_width_from_proc():
    """Query terminal width by walking the Linux process tree via /proc.

    When all standard detection methods fail (common inside Claude Code where
    stdout/stderr/stdin are all pipes and /dev/tty is unavailable), this walks
    up the parent process chain looking for an ancestor that holds an open
    file descriptor to a PTY.  It then queries TIOCGWINSZ on that fd to get
    the real terminal dimensions.

    Linux-only (/proc is not available on macOS/Windows).  Returns None on
    non-Linux platforms or if no terminal fd is found.  All filesystem and
    ioctl operations are individually caught so a failure at any point
    (permissions, process exit, container restrictions) is silently skipped.

    This function is self-contained — it can be removed without affecting
    the rest of the detection cascade, which will fall back to shutil.
    """
    if sys.platform != "linux":
        return None
    try:
        import fcntl, termios, struct  # Linux-only modules
        pid = os.getpid()
        for _ in range(10):
            with open(f"/proc/{pid}/stat") as f:
                raw = f.read()
            # Parse ppid safely: comm field "(name)" can contain spaces
            # and parens, so find the *last* ')' before splitting.
            ppid = int(raw[raw.rfind(")") + 2:].split()[1])
            if ppid <= 1:
                break
            fd_dir = f"/proc/{ppid}/fd"
            try:
                for fd_name in os.listdir(fd_dir):
                    try:
                        target = os.readlink(f"{fd_dir}/{fd_name}")
                        if "/pts/" not in target and "/tty" not in target:
                            continue
                        fd = os.open(f"{fd_dir}/{fd_name}", os.O_RDONLY)
                        try:
                            buf = fcntl.ioctl(fd, termios.TIOCGWINSZ, b"\x00" * 8)
                            cols = struct.unpack("HHHH", buf)[1]
                            if cols > 0:
                                return cols
                        finally:
                            os.close(fd)
                    except (OSError, PermissionError):
                        continue
            except (OSError, PermissionError):
                pass
            pid = ppid
    except (OSError, ValueError):
        pass
    return None

def _sanitize(text):
    """Strip ANSI/terminal escape sequences and control characters from untrusted strings."""
    # Strip CSI (\x1b[...), OSC (\x1b]...), DCS (\x1bP...) and other escape sequences
    cleaned = re.sub(r'\x1b[^a-zA-Z]*[a-zA-Z]', '', str(text))
    # Strip remaining control characters (keep \n for multi-line contexts)
    return re.sub(r'[\x00-\x09\x0b-\x1f\x7f-\x9f]', '', cleaned)

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
# so the rainbow has something to contrast against
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

# Widget priorities — lower number = rendered first (leftmost).
# Users can override via config["widget_priority"] = {"session": 1, "weekly": 2, ...}
WIDGET_PRIORITY = {
    "session": 10, "weekly": 20, "opus": 30, "sonnet": 40, "extra": 50,
    "context": 60, "cost": 70, "cumulative_cost": 72, "lines": 75, "peak": 80, "plan": 90,
    "streak": 100, "model": 110, "effort": 120, "worktree": 130,
    "heartbeat": 140, "activity": 150, "last_tool": 160, "branch": 170,
    "sessions": 180, "pomodoro": 190, "git_drift": 200, "files_changed": 210,
}

DEFAULT_SHOW = {
    # Core bars — always visible
    "session": True,
    "weekly": True,
    "context": True,
    "timer": True,
    "weekly_timer": True,
    # Info line
    "cost": True,
    "model": True,
    "branch": True,
    "heartbeat": True,
    "activity": True,
    "update": True,
    "claude_update": True,
    # Per-model caps (show when available)
    "opus": True,
    "sonnet": True,
    # Opt-in features
    "plan": False,
    "extra": False,
    "effort": True,
    "worktree": True,
    "pomodoro": True,
    "context_warning": True,
    "staleness": True,
    "lines": True,
    # Hidden by default — opt-in with --show
    "cumulative_cost": False,
    "burn_rate": False,
    "sessions": False,
    "last_tool": False,
    "sparkline": False,
    "runway": False,
    "status_message": False,
    "streak": False,
    "pace": False,
    "git_drift": False,
    "files_changed": False,
}

# Presets — one-command config bundles
PRESETS = {
    "minimal": {
        "description": "Compact bar that leaves room for Claude Code notifications",
        "config": {
            "bar_size": "small",
            "layout": "compact",
            "max_width": 60,
        },
        "show_overrides": {
            "plan": False,
            "model": False,
            "context": False,
            "sparkline": False,
            "runway": False,
            "status_message": False,
            "streak": False,
        },
    },
    "default": {
        "description": "Factory reset — all settings back to defaults",
        "config": {
            "theme": "default",
            "text_color": "auto",
            "animate": "off",
            "animation_speed": DEFAULT_ANIMATION_SPEED,
            "bar_size": DEFAULT_BAR_SIZE,
            "bar_style": DEFAULT_BAR_STYLE,
            "layout": DEFAULT_LAYOUT,
            "max_width": DEFAULT_MAX_WIDTH_PCT,
            "context_format": "percent",
            "extra_display": "auto",
            "currency": "$",
        },
        "show_overrides": dict(DEFAULT_SHOW),
    },
}

# Sparkline and history constants
SPARKLINE_CHARS = "\u2581\u2582\u2583\u2584\u2585\u2586\u2587\u2588"
HISTORY_MAX_AGE = 86400  # 24 hours in seconds


# ---------------------------------------------------------------------------
# Rainbow animation helpers
# ---------------------------------------------------------------------------

# Ultrathink rainbow palette — matches Claude Code's ultrathink colors
_ULTRATHINK_BASE = [
    (235, 95, 87),   # red
    (245, 139, 87),  # orange
    (250, 195, 95),  # yellow
    (145, 200, 130), # green
    (130, 170, 220), # blue
    (155, 130, 200), # indigo
    (200, 130, 180), # violet
]

_ULTRATHINK_SHIMMER = [
    (250, 155, 147), # red shimmer
    (255, 185, 137), # orange shimmer
    (255, 225, 155), # yellow shimmer
    (185, 230, 180), # green shimmer
    (180, 205, 240), # blue shimmer
    (195, 180, 230), # indigo shimmer
    (230, 180, 210), # violet shimmer
]


def _lerp_color(c1, c2, t):
    """Linearly interpolate between two RGB tuples."""
    return (
        int(c1[0] + (c2[0] - c1[0]) * t),
        int(c1[1] + (c2[1] - c1[1]) * t),
        int(c1[2] + (c2[2] - c1[2]) * t),
    )


def _ultrathink_color(pos, shimmer_t=0.0):
    """Map position (0.0-1.0) to an ultrathink rainbow color.

    shimmer_t: 0.0 = base colors, 1.0 = full shimmer colors.
    """
    n = len(_ULTRATHINK_BASE)
    scaled = pos * n
    idx = int(scaled) % n
    frac = scaled - int(scaled)
    next_idx = (idx + 1) % n
    base = _lerp_color(_ULTRATHINK_BASE[idx], _ULTRATHINK_BASE[next_idx], frac)
    if shimmer_t > 0.0:
        shimmer = _lerp_color(_ULTRATHINK_SHIMMER[idx], _ULTRATHINK_SHIMMER[next_idx], frac)
        return _lerp_color(base, shimmer, shimmer_t)
    return base


def _get_animation_speed(config=None):
    """Return the animation speed multiplier from config."""
    if config is None:
        config = load_config()
    speed_name = config.get("animation_speed", DEFAULT_ANIMATION_SPEED)
    return ANIMATION_SPEEDS.get(speed_name, 1.0)


def rainbow_colorize(text, color_all=True, shimmer=True, config=None):
    """Apply rainbow colouring — animated when processing, clean static when idle.

    shimmer=True  — Claude is processing: hue drifts each frame (smooth gradient shift).
    shimmer=False — Claude is idle: static rainbow gradient, no animation.

    color_all=True  — strip existing ANSI, rainbow every character.
    color_all=False — preserve ANSI-colored chars (bars), rainbow the rest.
    """
    now = time.time()
    speed = _get_animation_speed(config) if config else 1.0

    if shimmer:
        hue_drift = now * 0.8 * speed
    else:
        hue_drift = 0.0

    result = []
    visible_idx = 0
    has_existing_color = False
    i = 0

    while i < len(text):
        if text[i] == "\033":
            j = i
            while j < len(text) and j - i < 25 and text[j] != "m":
                j += 1
            if j >= len(text) or text[j] != "m":
                result.append(text[i])
                i += 1
                visible_idx += 1
                continue
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

        if not color_all and has_existing_color:
            result.append(text[i])
        else:
            pos = ((visible_idx * 0.025) + hue_drift) % 1.0
            if shimmer:
                pulse = abs((now * 1.5 * speed) % 2.0 - 1.0)
            else:
                pulse = 0.0
            r, g, b = _ultrathink_color(pos, pulse)
            result.append(f"\033[38;2;{r};{g};{b}m{text[i]}\033[0m")

        visible_idx += 1
        i += 1

    result.append(RESET)
    return "".join(result)


def _brighten_rgb(r, g, b, factor):
    """Brighten an RGB colour by a multiplicative factor, clamped to 255."""
    return (min(255, int(r * factor)), min(255, int(g * factor)), min(255, int(b * factor)))


def _parse_ansi_color_rgb(ansi_code):
    """Extract RGB from an ANSI escape code, or return None."""
    if not ansi_code:
        return None
    m = re.match(r'\033\[38;2;(\d+);(\d+);(\d+)m', ansi_code)
    if m:
        return (int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = re.match(r'\033\[38;5;(\d+)m', ansi_code)
    if m:
        n = int(m.group(1))
        if n < 16:
            _B16 = [(0,0,0),(128,0,0),(0,128,0),(128,128,0),(0,0,128),(128,0,128),(0,128,128),(192,192,192),
                    (128,128,128),(255,0,0),(0,255,0),(255,255,0),(0,0,255),(255,0,255),(0,255,255),(255,255,255)]
            return _B16[n]
        elif n < 232:
            n -= 16
            return ((n // 36) * 51, ((n % 36) // 6) * 51, (n % 6) * 51)
        else:
            v = 8 + (n - 232) * 10
            return (v, v, v)
    m = re.match(r'\033\[(\d+)m', ansi_code)
    if m:
        code = int(m.group(1))
        _BM = {30:(0,0,0),31:(170,0,0),32:(0,170,0),33:(170,170,0),34:(0,0,170),35:(170,0,170),
               36:(0,170,170),37:(170,170,170),90:(85,85,85),91:(255,85,85),92:(85,255,85),
               93:(255,255,85),94:(85,85,255),95:(255,85,255),96:(85,255,255),97:(255,255,255)}
        return _BM.get(code)
    return None


ANIMATE_MODES = ("off", "rainbow", "pulse", "glow", "shift")


def _anim_phase(config=None, freq=2.0):
    """Return a phase (0.0 to 1.0) based on time and animation speed."""
    speed = _get_animation_speed(config) if config else 1.0
    return 0.5 + 0.5 * math.sin(time.time() * freq * speed)


def _apply_bar_animation(colour, char_idx, bar_width, anim_mode, config=None):
    """Apply animation effect to a single bar character's colour.

    Returns an ANSI colour string, or None to keep original.
    """
    if not colour or anim_mode in ("off", "rainbow"):
        return None
    rgb = _parse_ansi_color_rgb(colour)
    if not rgb:
        return None
    speed = _get_animation_speed(config) if config else 1.0
    now = time.time()

    if anim_mode == "pulse":
        # Bar cycles through theme's low → mid → high colours over time
        # Each frame is a distinctly different colour
        phase = (now * 0.5 * speed) % 1.0  # slow cycle
        # Cycle: low(0) → mid(0.33) → high(0.66) → low(1.0)
        return None  # handled at bar level with _pulse_theme_color

    elif anim_mode == "glow":
        # Each character is a different colour — gradient across the bar
        # Creates a visible multi-colour effect like a toned-down rainbow
        if bar_width <= 0:
            return None
        # Map char position + time offset to a hue shift
        pos = ((char_idx / max(bar_width, 1)) + now * 0.3 * speed) % 1.0
        # Lerp through a warm/cool version of the base colour
        warm = (min(255, rgb[0] + 80), max(0, rgb[1] - 40), max(0, rgb[2] - 60))
        cool = (max(0, rgb[0] - 60), min(255, rgb[1] + 40), min(255, rgb[2] + 80))
        if pos < 0.5:
            t = pos * 2
            r, g, b = int(rgb[0] + (warm[0] - rgb[0]) * t), int(rgb[1] + (warm[1] - rgb[1]) * t), int(rgb[2] + (warm[2] - rgb[2]) * t)
        else:
            t = (pos - 0.5) * 2
            r, g, b = int(warm[0] + (cool[0] - warm[0]) * t), int(warm[1] + (cool[1] - warm[1]) * t), int(warm[2] + (cool[2] - warm[2]) * t)
        return f"\033[38;2;{max(0,min(255,r))};{max(0,min(255,g))};{max(0,min(255,b))}m"

    elif anim_mode == "shift":
        # Bright highlight slides across — each char a different brightness
        if bar_width <= 0:
            return None
        pos = (now * 3.0 * speed) % bar_width
        dist = abs(char_idx - pos)
        if dist > bar_width / 2:
            dist = bar_width - dist
        # Sharp highlight: bright white at center, theme colour at edges
        intensity = max(0.0, 1.0 - dist / 2.0)
        intensity = intensity * intensity  # sharper falloff
        r = min(255, int(rgb[0] + (255 - rgb[0]) * intensity))
        g = min(255, int(rgb[1] + (255 - rgb[1]) * intensity))
        b = min(255, int(rgb[2] + (255 - rgb[2]) * intensity))
        return f"\033[38;2;{r};{g};{b}m"

    return None


def resolve_text_color(config):
    """Return the ANSI code for the configured text colour."""
    theme_name = config.get("theme", "default")
    tc = config.get("text_color", "auto")
    if tc == "auto":
        tc = THEME_TEXT_DEFAULTS.get(theme_name, "white")
    return TEXT_COLORS.get(tc, TEXT_COLORS["white"])


def apply_text_color(line, color_code):
    """Wrap non-bar text in a base colour so the rainbow has something to contrast against.

    Prepends the colour, re-applies it after every RESET, and appends a final RESET.
    Bar colours override this inline; after their RESET the base colour resumes.
    """
    if not color_code:
        return line
    # Prepend base colour, replace every \033[0m with \033[0m + base colour,
    # then append a final reset at the end
    return color_code + line.replace("\033[0m", "\033[0m" + color_code) + "\033[0m"



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


def _atomic_json_write(filepath, data, indent=2):
    """Atomically write JSON with 0o600 permissions on Unix.

    Writes to a .tmp sibling first, then uses os.replace() for an atomic swap.
    Cleans up the temp file on failure.
    """
    filepath = Path(filepath)
    tmp_path = filepath.with_suffix(".tmp")
    try:
        with _secure_open_write(tmp_path) as f:
            json.dump(data, f, indent=indent)
        os.replace(str(tmp_path), str(filepath))
    except BaseException:
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def get_config_path():
    """Return path to user config — stored under XDG_CONFIG_HOME, outside the repo."""
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    config_dir = base / "claude-status"
    _secure_mkdir(config_dir)
    return config_dir / "config.json"


def _migrate_config_from_cache():
    """One-time migration: move config.json from ~/.cache to ~/.config."""
    new_path = get_config_path()
    if new_path.exists():
        return  # already migrated or user created config at new location
    # Build the old path (XDG_CACHE_HOME based)
    if sys.platform == "win32":
        return  # Windows uses LOCALAPPDATA for both; no migration needed
    old_base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    old_path = old_base / "claude-status" / "config.json"
    if old_path.exists():
        try:
            shutil.move(str(old_path), str(new_path))
        except OSError:
            pass


def _detect_default_currency():
    """Auto-detect currency symbol from system locale/timezone."""
    import locale as _locale

    # Try locale-based detection
    country = ""
    try:
        # getdefaultlocale deprecated in 3.13 but still works on Windows
        loc = _locale.getdefaultlocale()[0] or ""
        if "_" in loc:
            country = loc.split("_")[-1].upper()
    except (ValueError, AttributeError):
        pass
    if not country:
        try:
            loc = _locale.getlocale()[0] or ""
            if "_" in loc:
                country = loc.split("_")[-1].upper()
        except (ValueError, AttributeError):
            pass

    _COUNTRY_CURRENCY = {
        "GB": "\u00a3", "UK": "\u00a3",
        "US": "$",
        "DE": "\u20ac", "FR": "\u20ac", "IT": "\u20ac", "ES": "\u20ac", "NL": "\u20ac",
        "BE": "\u20ac", "AT": "\u20ac", "IE": "\u20ac", "FI": "\u20ac", "PT": "\u20ac", "GR": "\u20ac",
        "JP": "\u00a5",
        "CA": "C$", "AU": "A$", "NZ": "NZ$",
        "CH": "Fr", "SE": "kr", "NO": "kr", "DK": "kr",
        "IN": "\u20b9", "KR": "\u20a9", "BR": "R$", "ZA": "R",
        "PL": "z\u0142", "CZ": "K\u010d", "TR": "\u20ba", "IL": "\u20aa",
        "SG": "S$", "HK": "HK$", "MX": "$",
    }

    if country in _COUNTRY_CURRENCY:
        return _COUNTRY_CURRENCY[country]

    # Fallback: timezone-based detection
    try:
        tz_name = datetime.now(timezone.utc).astimezone().tzinfo.tzname(None) or ""
        if tz_name in ("GMT", "BST"):
            return "\u00a3"
        if tz_name in ("CET", "CEST"):
            return "\u20ac"
        if tz_name == "JST":
            return "\u00a5"
    except (AttributeError, OSError):
        pass

    return "$"


def load_config():
    _migrate_config_from_cache()
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
    data.setdefault("animate", "off")
    # Legacy compat: True → "rainbow", False → "off"
    if data["animate"] is True:
        data["animate"] = "rainbow"
    elif data["animate"] is False:
        data["animate"] = "off"
    data.setdefault("animation_speed", DEFAULT_ANIMATION_SPEED)
    data.setdefault("text_color", "auto")
    data.setdefault("bar_size", DEFAULT_BAR_SIZE)
    data.setdefault("max_width", DEFAULT_MAX_WIDTH_PCT)
    data.setdefault("bar_style", DEFAULT_BAR_STYLE)
    data.setdefault("layout", DEFAULT_LAYOUT)
    data.setdefault("context_format", "percent")
    data.setdefault("extra_display", "auto")
    if "currency" not in data:
        data["currency"] = _detect_default_currency()
    peak = data.get("peak_hours", {})
    peak.setdefault("enabled", True)
    peak.setdefault("start", "13:00")
    peak.setdefault("end", "19:00")
    data["peak_hours"] = peak
    show = data.get("show", {})
    for key, default in DEFAULT_SHOW.items():
        show.setdefault(key, default)
    data["show"] = show
    return data


def save_config(config):
    config_path = get_config_path()
    # Only save user-facing keys, not internal ones
    save_data = {k: v for k, v in config.items() if not k.startswith("_")}
    _atomic_json_write(config_path, save_data)


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
            filtered = []
            for h in hooks:
                is_pulse = False
                # Old format: {"command": "...claude_status.py..."}
                if script_name in h.get("command", ""):
                    is_pulse = True
                # New nested format: {"hooks": [{"command": "...claude_status.py..."}]}
                for inner in h.get("hooks", []):
                    if script_name in inner.get("command", ""):
                        is_pulse = True
                if not is_pulse:
                    filtered.append(h)
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
        _atomic_json_write(settings_path, settings)

    try:
        with _secure_open_write(marker) as f:
            pass
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Hook infrastructure — PostToolUse hook for live refresh
# ---------------------------------------------------------------------------

def _get_hook_state_path():
    return get_state_dir() / "hook_state.json"


def _read_hook_state():
    try:
        with open(_get_hook_state_path(), "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


def _is_hook_state_fresh(hook_state, ttl=HOOK_STATE_FRESH_TTL):
    if not hook_state:
        return False
    return (time.time() - hook_state.get("last_refresh", 0)) < ttl


def _format_elapsed(seconds):
    if seconds < 60:
        return f"{int(seconds)}s"
    minutes = int(seconds) // 60
    hours = minutes // 60
    mins = minutes % 60
    if hours > 0:
        return f"{hours}h {mins}m" if mins > 0 else f"{hours}h"
    return f"{mins}m"


def _get_git_branch():
    hook_state = _read_hook_state()
    if hook_state:
        cached_branch = hook_state.get("git_branch")
        branch_ts = hook_state.get("git_branch_ts", 0)
        if cached_branch is not None and (time.time() - branch_ts) < GIT_BRANCH_CACHE_TTL:
            return cached_branch if cached_branch else None
    try:
        result = subprocess.run(
            [_GIT_PATH, "branch", "--show-current"],
            capture_output=True, text=True, timeout=3,
        )
        branch = result.stdout.strip() if result.returncode == 0 else ""
    except Exception:
        branch = ""
    try:
        state = hook_state if hook_state else {}
        state["git_branch"] = branch
        state["git_branch_ts"] = time.time()
        _atomic_json_write(_get_hook_state_path(), state, indent=None)
    except OSError:
        pass
    return branch if branch else None


def hook_refresh(tool_name_arg):
    """Handle --hook-refresh: update hook state silently (no stdout).

    Tool name comes from stdin JSON (PostToolUse event data), not env vars.
    Falls back to tool_name_arg if stdin is unavailable.
    """
    # Parse tool name from stdin JSON (best practice per Claude Code docs)
    tool_name = tool_name_arg or "unknown"
    if not sys.stdin.isatty():
        try:
            raw = sys.stdin.read(65536)
            if raw.strip():
                data = json.loads(raw)
                tool_name = _sanitize(data.get("tool_name", tool_name))
        except (json.JSONDecodeError, OSError, ValueError):
            pass

    hook_state_path = _get_hook_state_path()
    now = time.time()
    state = {}
    try:
        with open(hook_state_path, "r", encoding="utf-8") as f:
            state = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass
    state["last_tool"] = _sanitize(str(tool_name))[:50]
    state["tool_count"] = state.get("tool_count", 0) + 1
    if "session_start" not in state:
        state["session_start"] = now
    state["last_refresh"] = now
    call_times = state.get("_call_times", [])
    call_times.append(now)
    call_times = [t for t in call_times if t > now - RAPID_CALL_WINDOW]
    state["_call_times"] = call_times
    state["rapid_calls"] = len(call_times)
    try:
        _atomic_json_write(hook_state_path, state, indent=None)
    except OSError:
        pass


def install_hooks():
    """Install a PostToolUse hook into ~/.claude/settings.json."""
    settings_path = Path.home() / ".claude" / "settings.json"
    script_path = _win_portable_path(Path(__file__).resolve())
    python_cmd = _get_python_cmd()
    settings = {}
    if settings_path.exists():
        try:
            with open(settings_path, "r", encoding="utf-8") as f:
                settings = json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    hook_command = f'{python_cmd} "{script_path}" --hook-refresh'
    hook_entry = {
        "matcher": "",
        "hooks": [
            {"type": "command", "command": hook_command}
        ],
    }
    hooks = settings.setdefault("hooks", {})
    post_tool_hooks = hooks.setdefault("PostToolUse", [])
    # Remove existing pulse hook-refresh entries to avoid dupes
    filtered = []
    for h in post_tool_hooks:
        is_pulse = False
        for inner in h.get("hooks", []):
            if "claude_status.py" in inner.get("command", "") and "--hook-refresh" in inner.get("command", ""):
                is_pulse = True
        if not is_pulse:
            filtered.append(h)
    filtered.append(hook_entry)
    hooks["PostToolUse"] = filtered
    settings["hooks"] = hooks
    _secure_mkdir(settings_path.parent)
    _atomic_json_write(settings_path, settings)
    utf8_print(f"{GREEN}Installed PostToolUse hook to {settings_path}{RESET}")
    utf8_print(f"  Command: {hook_command}")
    utf8_print(f"")
    utf8_print(f"This enables:")
    utf8_print(f"  {BOLD}Heartbeat{RESET}    \u2014 live spinner with tool count & elapsed time")
    utf8_print(f"  {BOLD}Activity{RESET}     \u2014 {BRIGHT_YELLOW}\u26a1 Active{RESET} indicator during rapid tool calls")
    utf8_print(f"  {BOLD}Last tool{RESET}    \u2014 shows last tool used (opt-in: --show last_tool)")
    utf8_print(f"  {BOLD}Git branch{RESET}   \u2014 current branch name")
    utf8_print(f"")
    utf8_print(f"Restart Claude Code for hooks to take effect.")


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
_CLAUDE_PATH = shutil.which("claude")  # resolve once at import time


def _detect_status_bar_conflict():
    """Detect conditions where Claude Code's status bar is too crowded for pulse.

    When Claude Code migrates from npm to native installer, it shows a long
    notification that fills the entire status bar area, causing pulse output
    to wrap.  Suppress output until the user resolves the migration.

    Recent npm versions also show this notification to encourage migration,
    so we check for the npm package presence regardless of which binary
    ``shutil.which("claude")`` resolves to (the npm shim may shadow the
    native binary on PATH).
    """
    try:
        if sys.platform == "win32":
            appdata = os.environ.get("APPDATA", "")
            if not appdata:
                return False
            npm_pkg = os.path.join(appdata, "npm", "node_modules",
                                   "@anthropic-ai", "claude-code")
            return os.path.isdir(npm_pkg)
        elif sys.platform == "darwin":
            for prefix in ("/usr/local", "/opt/homebrew"):
                npm_pkg = os.path.join(prefix, "lib", "node_modules",
                                       "@anthropic-ai", "claude-code")
                if os.path.isdir(npm_pkg):
                    return True
    except Exception:
        pass
    return False


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
        url = f"https://api.github.com/repos/{GITHUB_REPO}/commits/main"
        req = urllib.request.Request(url, headers={
            "Accept": "application/vnd.github.sha",
            "User-Agent": "claude-pulse-update-checker",
        })
        with urllib.request.urlopen(req, timeout=3) as resp:
            sha = resp.read(1024).decode().strip()
        if re.fullmatch(r'[0-9a-f]{40}', sha):
            return sha
        return None  # not a valid SHA — rate-limited, error page, etc.
    except Exception:
        return None


def check_for_update():
    """Check if a newer version is available on GitHub. Returns True/False/None.

    Cached for 1 hour. Fully silent on any error — never blocks the status line.
    """
    state_dir = get_state_dir()
    update_cache = state_dir / "update_check.json"

    # Get local commit first so we can validate cache
    local = get_local_commit()
    if not local:
        return None  # not a git install, skip silently

    # Read cached result — skip if local version changed (e.g. after update)
    try:
        with open(update_cache, "r", encoding="utf-8") as f:
            cached = json.load(f)
        if (time.time() - cached.get("timestamp", 0) < UPDATE_CHECK_TTL
                and cached.get("local") == local[:8]):
            return cached.get("update_available", False)
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        pass

    # Perform the check
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


def check_claude_code_update():
    """Check if a newer Claude Code version is available on npm. Returns True/False/None.

    Cached for 1 hour. Fully silent on any error — never blocks the status line.
    """
    if not _CLAUDE_PATH:
        return None

    state_dir = get_state_dir()
    update_cache = state_dir / "claude_code_update.json"

    # Get installed version first so we can validate cache
    try:
        result = subprocess.run(
            [_CLAUDE_PATH, "--version"],
            capture_output=True, text=True, timeout=3,
        )
        if result.returncode != 0:
            return None
        # Parse "2.1.37 (Claude Code)" → "2.1.37"
        local_version = result.stdout.strip().split()[0]
    except Exception:
        return None

    # Read cached result — skip if local version changed (e.g. after claude update)
    try:
        with open(update_cache, "r", encoding="utf-8") as f:
            cached = json.load(f)
        if (time.time() - cached.get("timestamp", 0) < UPDATE_CHECK_TTL
                and cached.get("local") == _sanitize(local_version)):
            return cached.get("update_available", False)
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        pass

    # Get latest version from npm registry
    try:
        req = urllib.request.Request(
            "https://registry.npmjs.org/@anthropic-ai/claude-code/latest",
            headers={"User-Agent": "claude-pulse-update-checker"},
        )
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read(100_000).decode("utf-8"))
        remote_version = _sanitize(str(data.get("version", "")))
        if not remote_version:
            return None
    except Exception:
        return None

    update_available = _sanitize(local_version) != remote_version

    # Cache the result
    try:
        with _secure_open_write(update_cache) as f:
            json.dump({
                "timestamp": time.time(),
                "update_available": update_available,
                "local": _sanitize(local_version),
                "remote": remote_version,
            }, f)
    except OSError:
        pass

    return update_available


def append_claude_update_indicator(line, config=None):
    """Append a visible Claude Code update indicator if a newer version is available."""
    try:
        if config:
            show = config.get("show", DEFAULT_SHOW)
            if not show.get("claude_update", True):
                return line
        if check_claude_code_update():
            return line + f" {BRIGHT_YELLOW}\u2191 Claude Update{RESET}"
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
    """Fetch the VERSION string from the latest main on GitHub. Returns None on failure."""
    try:
        url = f"https://raw.githubusercontent.com/{GITHUB_REPO}/main/claude_status.py"
        req = urllib.request.Request(url, headers={"User-Agent": "claude-pulse-update-checker"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            for raw_line in resp:
                line = raw_line.decode("utf-8", errors="replace")
                if line.startswith("VERSION"):
                    version = line.split('"')[1]
                    return re.sub(r'[^a-zA-Z0-9.\-]', '', version) or None
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
        repo_lower = GITHUB_REPO.lower()
        expected_suffixes = [
            "/" + repo_lower, "/" + repo_lower + ".git",
            ":" + repo_lower, ":" + repo_lower + ".git",  # SSH git@github.com:user/repo
        ]
        if not any(origin_url.endswith(s) for s in expected_suffixes):
            utf8_print(f"  {RED}Origin URL does not match expected repository.{RESET}")
            utf8_print(f"  Expected: {GITHUB_REPO}")
            utf8_print(f"  Got:      {_sanitize(origin_url)}")
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
        utf8_print(f"  {BRIGHT_YELLOW}Update found! v{VERSION} -> v{_sanitize(remote_version)}{RESET}")
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
            [_GIT_PATH, "pull", "origin", "main"],
            capture_output=True, text=True, timeout=30,
            cwd=str(repo_dir),
        )
        if result.returncode == 0:
            # Verify post-pull HEAD matches the expected remote commit
            post_pull_head = get_local_commit()
            if post_pull_head and post_pull_head != remote:
                utf8_print(f"  {RED}Integrity check failed: HEAD after pull ({post_pull_head[:8]}) does not match expected remote ({remote[:8]}).{RESET}")
                if pre_pull_commit:
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
            new_version = _sanitize(_read_version_from_file(script_path) or "")
            if new_version and new_version != VERSION:
                utf8_print(f"  {GREEN}Updated to v{new_version}!{RESET}")
            else:
                utf8_print(f"  {GREEN}Updated successfully!{RESET}")
            if result.stdout.strip():
                for ln in result.stdout.strip().split("\n"):
                    utf8_print(f"  {DIM}{_sanitize(ln)}{RESET}")
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
                            utf8_print(f"    {DIM}{_sanitize(ln)}{RESET}")
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
                    utf8_print(f"  {DIM}{_sanitize(ln)}{RESET}")
    except subprocess.TimeoutExpired:
        utf8_print(f"  {RED}Timed out. Check your network connection.{RESET}")
    except Exception as e:
        utf8_print(f"  {RED}Update error: {type(e).__name__}{RESET}")


_ERROR_CACHE_TTL = 10   # seconds — retry errors faster than normal data
_RATE_LIMIT_CACHE_TTL = 120  # seconds — back off longer on 429 to avoid retry storms


def read_cache(cache_path, ttl):
    """Return the full cache dict if fresh, else None."""
    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            cached = json.load(f)
        # Error-only entries expire faster, except rate limit errors which back off longer
        if "usage" in cached:
            effective_ttl = ttl
        elif cached.get("rate_limited"):
            effective_ttl = _RATE_LIMIT_CACHE_TTL
        else:
            effective_ttl = _ERROR_CACHE_TTL
        if time.time() - cached.get("timestamp", 0) < effective_ttl:
            return cached
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        pass
    return None


def _read_stale_cache(cache_path):
    """Return cached data regardless of age, or None if unavailable.

    Prefers entries with 'usage' data, but also accepts entries with just
    a rendered 'line' — this prevents sticky error states when a 429 hits
    before any usage data has been cached.
    """
    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            cached = json.load(f)
        if "usage" in cached or "line" in cached:
            return cached
    except (FileNotFoundError, json.JSONDecodeError, KeyError, OSError):
        pass
    return None


_USAGE_CACHE_KEYS = {"five_hour", "seven_day", "seven_day_opus", "seven_day_sonnet", "extra_usage"}

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
# SECURITY: OAuth tokens are ONLY sent to these Anthropic-owned domains.
# They are never written to cache/state files, never logged, and never
# sent anywhere else. The _authorized_request() guard enforces this.
_TOKEN_ALLOWED_DOMAINS = frozenset({"api.anthropic.com", "console.anthropic.com", "platform.claude.com"})


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Block HTTP redirects to prevent tokens from leaking to third-party domains."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        target_domain = urlparse(newurl).hostname
        if target_domain not in _TOKEN_ALLOWED_DOMAINS:
            raise urllib.error.HTTPError(
                newurl, code, f"Redirect to non-allowed domain blocked", headers, fp
            )
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_safe_opener = urllib.request.build_opener(_NoRedirectHandler)


def _authorized_request(url, token, headers=None, data=None, method=None, timeout=10):
    """Make an HTTP request with an auth token, but ONLY to allowed Anthropic domains.

    Raises ValueError if the URL domain is not in the allowlist.
    This prevents tokens from ever being sent to third-party servers,
    even if the code is modified or a URL is misconfigured.
    Redirects to non-allowed domains are blocked to prevent token exfiltration.
    """
    domain = urlparse(url).hostname
    if domain not in _TOKEN_ALLOWED_DOMAINS:
        raise ValueError(f"Token request blocked: {_sanitize(domain)} is not an allowed domain")
    hdrs = dict(headers) if headers else {}
    if token:
        hdrs["Authorization"] = f"Bearer {token}"
    hdrs.setdefault("User-Agent", f"claude-pulse/{VERSION}")
    req = urllib.request.Request(url, headers=hdrs, data=data, method=method)
    return _safe_opener.open(req, timeout=timeout)

def _read_credential_data():
    """Read raw credential data from file or macOS Keychain. Returns (dict, source)."""
    # 1. File-based (~/.claude/.credentials.json)
    creds_path = Path.home() / ".claude" / ".credentials.json"
    try:
        with open(creds_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if data.get("claudeAiOauth", {}).get("accessToken"):
            return data, "file"
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
                if data.get("claudeAiOauth", {}).get("accessToken"):
                    return data, "keychain"
        except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError, ValueError):
            pass

    return None, None


def _extract_credentials(data):
    """Extract token and plan from credential data dict."""
    if not data:
        return None, None
    oauth = data.get("claudeAiOauth", {})
    token = oauth.get("accessToken")
    tier = oauth.get("rateLimitTier", "")
    if not token:
        return None, None
    plan = PLAN_NAMES.get(tier, _sanitize(tier.replace("default_claude_", "").replace("_", " ").title()))
    return token, plan



def _refresh_oauth_token(refresh_token):
    """Use refresh token to obtain a new access token. Returns new token data or None."""
    try:
        body = json.dumps({
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        }).encode("utf-8")
        with _authorized_request(
            "https://platform.claude.com/v1/oauth/token",
            None,  # no Bearer token — this uses the refresh token in the body
            data=body,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        ) as resp:
            return json.loads(resp.read(100_000))
    except Exception:
        return None


def get_credentials():
    """Read OAuth token from credentials file, macOS Keychain, or env var."""
    data, source = _read_credential_data()
    if data:
        token, plan = _extract_credentials(data)
        if token:
            return token, plan

    # Environment variable fallback (all platforms)
    env_token = os.environ.get("CLAUDE_CODE_OAUTH_TOKEN")
    if env_token:
        return env_token, ""

    return None, None


def refresh_and_retry(plan):
    """Attempt to refresh expired OAuth token. Returns (new_token, plan) or (None, plan)."""
    data, source = _read_credential_data()
    if not data:
        return None, plan
    oauth = data.get("claudeAiOauth", {})
    refresh_token = oauth.get("refreshToken")
    if not refresh_token:
        return None, plan

    token_data = _refresh_oauth_token(refresh_token)
    if not token_data or "access_token" not in token_data:
        return None, plan

    # Return refreshed token in-memory only — don't write back to
    # credential store to avoid race conditions with Claude Code
    return token_data["access_token"], plan


def fetch_usage(token):
    with _authorized_request(
        "https://api.anthropic.com/api/oauth/usage",
        token,
        headers={"anthropic-beta": "oauth-2025-04-20", "Accept": "application/json"},
    ) as resp:
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
    """Format token count: 200000 -> '200k', 1000000 -> '1M', 1B -> '1B'."""
    if n >= 1_000_000_000:
        return f"{n / 1_000_000_000:.0f}B" if n % 1_000_000_000 == 0 else f"{n / 1_000_000_000:.1f}B"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.0f}M" if n % 1_000_000 == 0 else f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.0f}k" if n % 1_000 == 0 else f"{n / 1_000:.1f}k"
    return str(n)


def make_bar(pct, theme=None, plain=False, width=None, bar_style=None,
             anim_mode="off", flash_color=None, config=None):
    """Build a coloured bar. plain=True returns characters only (no ANSI).

    anim_mode   — animation mode: off/pulse/glow/shift (per-character effects).
    flash_color — override the entire bar with this ANSI colour.
    """
    if theme is None:
        theme = THEMES["default"]
    if width is None:
        width = BAR_SIZES[DEFAULT_BAR_SIZE]
    style = bar_style or DEFAULT_BAR_STYLE
    pct = pct or 0

    if flash_color:
        colour = flash_color
    elif plain:
        colour = None
    else:
        colour = bar_colour(pct, theme)

    # Gradient styles
    gradient_data = BAR_GRADIENT_STYLES.get(style)
    if gradient_data is not None:
        gradient, empty_char = gradient_data
        levels = len(gradient) - 1
        total_steps = width * levels
        filled_steps = round(pct / 100 * total_steps)
        filled_steps = max(0, min(total_steps, filled_steps))
        full = filled_steps // levels
        partial = filled_steps % levels
        empty = width - full - (1 if partial else 0)
        bar_fill = gradient[-1] * full
        bar_partial = gradient[partial] if partial else ""
        bar_empty = empty_char * empty
        if plain:
            return f"{bar_fill}{bar_partial}{DIM}{bar_empty}{RESET}"
        return f"{colour}{bar_fill}{bar_partial}{DIM}{bar_empty}{RESET}"

    # Standard binary fill
    fill_char, empty_char = BAR_STYLES.get(style, BAR_STYLES[DEFAULT_BAR_STYLE])
    filled = round(pct / 100 * width)
    filled = max(0, min(width, filled))
    if plain:
        return f"{fill_char * filled}{DIM}{empty_char * (width - filled)}{RESET}"

    # Pulse mode: bars cycle through vivid truecolor hues
    if anim_mode == "pulse" and not plain:
        speed = _get_animation_speed(config) if config else 1.0
        phase = (time.time() * 0.8 * speed) % 1.0
        # 6 vivid colours that are obviously different on any terminal
        pulse_palette = [
            (0, 200, 200),    # cyan
            (80, 120, 255),   # blue
            (180, 80, 220),   # purple
            (220, 80, 120),   # pink
            (200, 160, 40),   # gold
            (40, 200, 120),   # green
        ]
        n = len(pulse_palette)
        scaled = phase * n
        idx = int(scaled) % n
        frac = scaled - int(scaled)
        nxt = (idx + 1) % n
        r = int(pulse_palette[idx][0] + (pulse_palette[nxt][0] - pulse_palette[idx][0]) * frac)
        g = int(pulse_palette[idx][1] + (pulse_palette[nxt][1] - pulse_palette[idx][1]) * frac)
        b = int(pulse_palette[idx][2] + (pulse_palette[nxt][2] - pulse_palette[idx][2]) * frac)
        pulse_col = f"\033[38;2;{r};{g};{b}m"
        return f"{pulse_col}{fill_char * filled}{DIM}{empty_char * (width - filled)}{RESET}"

    # Per-character animation (glow/shift)
    if anim_mode not in ("off", "rainbow", "pulse") and colour and not plain:
        chars = []
        for i in range(filled):
            anim_col = _apply_bar_animation(colour, i, width, anim_mode, config)
            c = anim_col or colour
            chars.append(f"{c}{fill_char}{RESET}")
        for i in range(width - filled):
            chars.append(f"{DIM}{empty_char}{RESET}")
        return "".join(chars)

    return f"{colour}{fill_char * filled}{DIM}{empty_char * (width - filled)}{RESET}"


# ---------------------------------------------------------------------------
# Animation state — threshold flash + celebration effects
# ---------------------------------------------------------------------------

def _get_anim_state_path():
    return get_state_dir() / "anim_state.json"


def _load_anim_state():
    try:
        with open(_get_anim_state_path(), "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_anim_state(state):
    try:
        with _secure_open_write(_get_anim_state_path()) as f:
            json.dump(state, f)
    except OSError:
        pass


def _check_threshold_flash(section, pct, anim_state):
    prev_key = f"prev_pct_{section}"
    flash_key = f"flash_renders_{section}"
    prev_pct = anim_state.get(prev_key, 0)
    crossed = any(prev_pct < t <= pct for t in FLASH_THRESHOLDS)
    anim_state[prev_key] = pct
    if crossed:
        anim_state[flash_key] = FLASH_DURATION
        anim_state[f"flash_time_{section}"] = time.time()
    renders_left = anim_state.get(flash_key, 0)
    if renders_left > 0:
        flash_time = anim_state.get(f"flash_time_{section}", 0)
        if time.time() - flash_time > FLASH_RENDER_TTL:
            anim_state[flash_key] = 0


def _get_flash_color(section, theme, anim_state):
    flash_key = f"flash_renders_{section}"
    renders_left = anim_state.get(flash_key, 0)
    if renders_left > 0:
        flash_time = anim_state.get(f"flash_time_{section}", 0)
        if time.time() - flash_time > FLASH_RENDER_TTL:
            return None
        anim_state[flash_key] = renders_left - 1
        return theme["high"]
    return None


def _check_celebration(weekly_pct, anim_state):
    prev_weekly = anim_state.get("prev_weekly_pct", 0)
    celeb_key = "celebration_renders"
    drop = prev_weekly - weekly_pct
    if drop >= CELEBRATION_DROP_THRESHOLD and prev_weekly >= 30:
        anim_state[celeb_key] = CELEBRATION_DURATION
        anim_state["celebration_time"] = time.time()
    anim_state["prev_weekly_pct"] = weekly_pct
    renders_left = anim_state.get(celeb_key, 0)
    if renders_left > 0:
        celeb_time = anim_state.get("celebration_time", 0)
        if time.time() - celeb_time > FLASH_RENDER_TTL:
            anim_state[celeb_key] = 0
            return False
        anim_state[celeb_key] = renders_left - 1
        return True
    return False


def _render_celebration_label(config=None):
    chars = CELEBRATION_CHAR * 3
    return rainbow_colorize(f" {chars} Reset! {chars} ", color_all=True, shimmer=True, config=config)


def _calc_pace_pct(resets_at_str, window_seconds):
    """Return expected usage % based on elapsed time in the window, or None."""
    if not resets_at_str:
        return None
    try:
        resets_at = datetime.fromisoformat(resets_at_str)
        now = datetime.now(timezone.utc)
        remaining = (resets_at - now).total_seconds()
        elapsed = window_seconds - remaining
        if elapsed <= 0 or window_seconds <= 0:
            return None
        return min(100.0, max(0.0, (elapsed / window_seconds) * 100))
    except Exception:
        return None


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


WEEKLY_TIMER_FORMATS = ("auto", "countdown", "date", "full")
DEFAULT_WEEKLY_TIMER_FORMAT = "auto"
CLOCK_FORMATS = ("12h", "24h")
DEFAULT_CLOCK_FORMAT = "12h"
DEFAULT_WEEKLY_TIMER_PREFIX = "R:"


def _weekly_countdown(total_seconds):
    """Format seconds as compact countdown: '2d 5h', '14h 22m', or '45m'."""
    if total_seconds >= 86400:
        days = total_seconds // 86400
        hours = (total_seconds % 86400) // 3600
        return f"{days}d {hours}h"
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    if hours > 0:
        return f"{hours}h {minutes:02d}m"
    return f"{minutes}m"


def _weekly_date(resets_at, clock="12h"):
    """Format reset time as local day+hour: 'Sat 5pm' or 'Sat 17:00'."""
    local_dt = resets_at.astimezone()
    hour = local_dt.hour
    if clock == "24h":
        time_str = f"{hour:02d}:{local_dt.minute:02d}"
    elif hour == 0:
        time_str = "12am"
    elif hour < 12:
        time_str = f"{hour}am"
    elif hour == 12:
        time_str = "12pm"
    else:
        time_str = f"{hour - 12}pm"
    return f"{local_dt.strftime('%a')} {time_str}"


def format_weekly_reset(resets_at_str, fmt="auto", clock="12h"):
    """Format weekly reset time.

    Formats:
      auto      — date when >24h, countdown when <24h (default)
      countdown — always show countdown: '2d 5h' / '14h 22m' / '45m'
      date      — always show date: 'Sat 5pm' (or 'Sat 17:00' with clock='24h')
      full      — both: 'Sat 5pm · 2d 5h'

    clock: '12h' for am/pm display, '24h' for 24-hour display.
    """
    if not resets_at_str:
        return None
    try:
        safe = _sanitize(str(resets_at_str))
        resets_at = datetime.fromisoformat(safe)
        now = datetime.now(timezone.utc)
        total_seconds = int((resets_at - now).total_seconds())
        if total_seconds <= 0:
            return "now"
        if fmt == "countdown":
            return _weekly_countdown(total_seconds)
        if fmt == "date":
            return _weekly_date(resets_at, clock=clock)
        if fmt == "full":
            return f"{_weekly_date(resets_at, clock=clock)} \u00b7 {_weekly_countdown(total_seconds)}"
        # auto: date when >24h, countdown when <24h
        if total_seconds < 86400:
            return _weekly_countdown(total_seconds)
        return _weekly_date(resets_at, clock=clock)
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

    # Prune entries older than 24 hours and cap entry count
    cutoff = now - HISTORY_MAX_AGE
    samples = [s for s in samples if s.get("t", 0) > cutoff]
    samples = samples[-2000:]  # prevent unbounded growth

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
        # Map 0-100 to index 0-6 (avoid █ at index 7 — it's in ALL_BAR_CHARS)
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


def _format_burn_rate(samples, current_pct, show_runway=False):
    """Format burn rate as an arrow indicator with optional runway."""
    velocity = _compute_velocity(samples)
    if velocity is None or velocity <= 0.5:
        return ""  # Only show when actively burning
    else:
        pct_per_hr = velocity * 60
        indicator = f"{VELOCITY_ARROW_UP}{pct_per_hr:.0f}%/hr" if pct_per_hr >= 10 else f"{VELOCITY_ARROW_UP}{pct_per_hr:.1f}%/hr"
    result = indicator
    if show_runway and velocity is not None and velocity > 0 and current_pct < 100:
        runway = _estimate_runway(samples, current_pct)
        if runway:
            result += f" {runway} left"
    return result


def _format_staleness(cache_age):
    """Format cache staleness as a colored age indicator."""
    if cache_age is None or cache_age <= STALENESS_WARN:
        return ""
    if cache_age >= STALENESS_RED:
        return f" {RED}(10m+ ago){RESET}"
    minutes = int(cache_age // 60)
    if cache_age >= STALENESS_YELLOW:
        return f" {YELLOW}({minutes}m ago){RESET}"
    return f" {DIM}({minutes}m ago){RESET}"


_EXCHANGE_RATE_TTL = 86400  # 24 hours
_FALLBACK_RATES = {
    "GBP": 0.79, "EUR": 0.92, "JPY": 149.0, "CAD": 1.36, "AUD": 1.53,
    "CHF": 0.88, "CNY": 7.24, "INR": 83.5, "BRL": 4.97, "KRW": 1330.0,
    "SEK": 10.4, "NOK": 10.6, "DKK": 6.85, "PLN": 3.98, "CZK": 23.2,
    "NZD": 1.63, "SGD": 1.34, "HKD": 7.82, "MXN": 17.1, "ZAR": 18.5,
    "TRY": 32.0, "THB": 34.8, "TWD": 31.5, "ILS": 3.62, "AED": 3.67,
}
_CURRENCY_TO_CODE = {
    "$": "USD", "\u00a3": "GBP", "\u20ac": "EUR", "\u00a5": "JPY",
    "C$": "CAD", "A$": "AUD", "NZ$": "NZD", "S$": "SGD", "HK$": "HKD",
    "R$": "BRL", "kr": "SEK", "Fr": "CHF", "\u20b9": "INR", "\u20a9": "KRW",
    "R": "ZAR", "z\u0142": "PLN", "K\u010d": "CZK", "\u20ba": "TRY",
    "\u20b4": "UAH", "\u20b1": "PHP", "RM": "MYR", "\u20aa": "ILS",
}


_exchange_rate_mem = {}  # in-memory cache: {code: (rate, timestamp)}


def _get_exchange_rate(currency_symbol):
    """Get USD→target exchange rate. Cached for 24h. Returns (rate, code) or (1.0, 'USD')."""
    code = _CURRENCY_TO_CODE.get(currency_symbol, "")
    if not code or code == "USD":
        return 1.0, "USD"

    # In-memory cache (avoids disk I/O on hot path)
    now = time.time()
    mem = _exchange_rate_mem.get(code)
    if mem and now - mem[1] < _EXCHANGE_RATE_TTL:
        return mem[0], code

    # Check disk cache
    cache_path = get_state_dir() / "exchange_rate.json"
    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            cached = json.load(f)
        if (now - cached.get("timestamp", 0) < _EXCHANGE_RATE_TTL
                and code in cached.get("rates", {})):
            rate = cached["rates"][code]
            _exchange_rate_mem[code] = (rate, now)
            return rate, code
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass

    # Fetch from frankfurter.app (free, no API key)
    try:
        url = f"https://api.frankfurter.dev/v1/latest?from=USD&to={code}"
        req = urllib.request.Request(url, headers={"User-Agent": "claude-pulse"})
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read(10000))
        rate = data.get("rates", {}).get(code)
        if rate:
            # Cache all fetched rates
            try:
                _atomic_json_write(cache_path, {
                    "timestamp": time.time(),
                    "rates": data["rates"],
                }, indent=None)
            except OSError:
                pass
            _exchange_rate_mem[code] = (float(rate), now)
            return float(rate), code
    except Exception:
        pass

    # Fallback to hardcoded rate
    fallback = _FALLBACK_RATES.get(code, 1.0)
    _exchange_rate_mem[code] = (fallback, now)
    return fallback, code


def _format_cost(stdin_ctx, config):
    """Format session cost from stdin context, converted to user's currency."""
    cost_usd = stdin_ctx.get("cost_usd")
    if cost_usd is None:
        return ""
    try:
        cost_val = float(cost_usd)
    except (ValueError, TypeError):
        return ""
    currency = _sanitize(config.get("currency", "$"))[:5]
    rate, code = _get_exchange_rate(currency)
    converted = cost_val * rate
    if code == "USD":
        return f"${converted:.2f}"
    return f"{currency}{converted:.2f}"


def _get_context_history_path():
    return get_state_dir() / "context_history.json"


def _read_context_history():
    try:
        with open(_get_context_history_path(), "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _append_context_history(context_pct):
    if context_pct is None:
        return
    samples = _read_context_history()
    now = time.time()
    samples.append({"t": now, "c": float(context_pct)})
    cutoff = now - 3600
    samples = [s for s in samples if s.get("t", 0) > cutoff][-500:]
    try:
        with _secure_open_write(_get_context_history_path()) as f:
            json.dump(samples, f)
    except OSError:
        pass


def _compute_context_velocity():
    samples = _read_context_history()
    if len(samples) < 2:
        return None
    now = time.time()
    recent = [s for s in samples if s.get("t", 0) > now - 300]
    if len(recent) < 2:
        return None
    dt = recent[-1]["t"] - recent[0]["t"]
    if dt < 10:
        return None
    dp = recent[-1].get("c", 0) - recent[0].get("c", 0)
    return (dp / dt) * 60


def _format_context_warning(ctx_pct, theme):
    """Return (label, suffix) for context pressure warning, or (None, None)."""
    if ctx_pct is None:
        return None, None
    ctx_velocity = _compute_context_velocity()
    if ctx_pct >= CONTEXT_PRESSURE_CRITICAL:
        suffix = ""
        if ctx_velocity is not None and ctx_velocity > CONTEXT_PRESSURE_VELOCITY:
            suffix = f" {VELOCITY_ARROW_UP}fast"
        elif ctx_velocity is not None and ctx_velocity > 0.5:
            suffix = f" {VELOCITY_ARROW_UP}"
        return f"{theme['high']}\u26a0 Context{RESET}", suffix
    if ctx_pct >= CONTEXT_PRESSURE_PCT:
        if ctx_velocity is not None and ctx_velocity > CONTEXT_PRESSURE_VELOCITY:
            return f"{theme['high']}\u26a0 Context{RESET}", f" {VELOCITY_ARROW_UP}fast"
    return None, None


PEAK_DISPLAYS = ("full", "minimal")
DEFAULT_PEAK_DISPLAY = "full"


def _fmt_peak_time(hhmm_str, clock="12h"):
    """Format a HH:MM string as 12h (1pm) or 24h (13:00)."""
    try:
        h, m = int(hhmm_str.split(":")[0]), int(hhmm_str.split(":")[1])
        if clock == "12h":
            if h == 0:
                return "12am"
            elif h < 12:
                return f"{h}am"
            elif h == 12:
                return "12pm"
            else:
                return f"{h - 12}pm"
        return hhmm_str
    except (ValueError, IndexError):
        return hhmm_str


def _check_peak_hours(config):
    """Check peak hours status. Returns (is_peak, display_str).

    Full mode:
      In peak:      'In Peak ⚡ 2h left (1pm-7pm)'   RED — burning limits faster
      Approaching:  'Peak ⚡ in 45m'                  YELLOW — heads up
      Off-peak:     'Off-Peak ✓'                      GREEN — limits stretch further

    Minimal mode:
      In peak:      '⚡ Peak 2h'
      Approaching:  '⚡ 45m'
      Off-peak:     '✓ Off-Peak'
    """
    peak = config.get("peak_hours", {})
    if not peak.get("enabled", True):
        return False, ""
    try:
        start_str = peak.get("start", "13:00")
        end_str = peak.get("end", "19:00")
        clock = config.get("clock_format", "12h")
        display_mode = peak.get("display", DEFAULT_PEAK_DISPLAY)
        minimal = display_mode == "minimal"
        sh, sm = int(start_str.split(":")[0]), int(start_str.split(":")[1])
        eh, em = int(end_str.split(":")[0]), int(end_str.split(":")[1])
        now = datetime.now()
        now_mins = now.hour * 60 + now.minute
        start_mins = sh * 60 + sm
        end_mins = eh * 60 + em
        start_display = _fmt_peak_time(start_str, clock)
        end_display = _fmt_peak_time(end_str, clock)

        if start_mins <= now_mins < end_mins:
            left = end_mins - now_mins
            left_str = f"{left // 60}h {left % 60}m" if left >= 60 else f"{left}m"
            if minimal:
                return True, f"\u26a1 Peak {left_str}"
            return True, f"In Peak \u26a1 {left_str} left ({start_display}-{end_display})"

        if now_mins < start_mins:
            until = start_mins - now_mins
            if until <= 120:
                until_str = f"{until // 60}h {until % 60}m" if until >= 60 else f"{until}m"
                if minimal:
                    return False, f"\u26a1 {until_str}"
                return False, f"Peak \u26a1 in {until_str}"

        if minimal:
            return False, "\u2713 Off-Peak"
        return False, "Off-Peak \u2713"
    except (ValueError, AttributeError):
        return False, ""


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


_CUMULATIVE_COST_CACHE_TTL = 300  # 5 minutes
_cumulative_cost_mem = {"ts": 0, "data": {}}


def _get_cached_cumulative_cost():
    """Return cumulative cost data with in-memory + 5-minute disk cache."""
    now = time.time()

    # In-memory cache (avoids disk I/O on hot path)
    if now - _cumulative_cost_mem["ts"] < _CUMULATIVE_COST_CACHE_TTL:
        return _cumulative_cost_mem["data"]

    # Disk cache
    cache_path = get_state_dir() / "cumulative_cost_cache.json"
    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            cached = json.load(f)
        if now - cached.get("timestamp", 0) < _CUMULATIVE_COST_CACHE_TTL:
            _cumulative_cost_mem["ts"] = now
            _cumulative_cost_mem["data"] = cached.get("data", {})
            return _cumulative_cost_mem["data"]
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass

    data = _scan_session_costs()
    _cumulative_cost_mem["ts"] = now
    _cumulative_cost_mem["data"] = data
    try:
        _atomic_json_write(cache_path, {"timestamp": now, "data": data}, indent=None)
    except OSError:
        pass
    return data


def _scan_session_costs():
    """Scan all Claude Code session JSONL transcripts and calculate API-equivalent costs.

    Returns a dict with per-model cost/token breakdown, totals, session count,
    and the earliest file mtime seen.
    """
    home = Path.home()
    projects_dir = home / ".claude" / "projects"

    models: dict = {}
    total_cost_usd = 0.0
    total_tokens = 0
    session_count = 0
    first_seen_ts = None

    if not projects_dir.exists():
        return {
            "models": {},
            "total_cost_usd": 0.0,
            "total_tokens": 0,
            "session_count": 0,
            "first_seen": None,
        }

    try:
        jsonl_files = projects_dir.rglob("*.jsonl")
    except (OSError, PermissionError):
        jsonl_files = []

    for jsonl_path in jsonl_files:
        # Count sessions: top-level JSONL files only (not inside subagents/ dirs)
        path_parts = jsonl_path.parts
        is_subagent = any(p == "subagents" for p in path_parts)
        if not is_subagent:
            session_count += 1

        # Track earliest file mtime
        try:
            mtime = jsonl_path.stat().st_mtime
            if first_seen_ts is None or mtime < first_seen_ts:
                first_seen_ts = mtime
        except OSError:
            pass

        # Parse each line
        try:
            with open(jsonl_path, "r", encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                    except (json.JSONDecodeError, ValueError):
                        continue
                    try:
                        if entry.get("type") != "assistant":
                            continue
                        msg = entry.get("message", {})
                        usage = msg.get("usage", {})
                        if not usage or "input_tokens" not in usage:
                            continue
                        model_id = msg.get("model", "")
                        # Normalise: strip version suffix variants for matching
                        # e.g. "claude-sonnet-4-5-20251022" → "claude-sonnet-4-5"
                        pricing = API_PRICING.get(model_id)
                        if pricing is None:
                            # Try prefix match (handles dated variants)
                            for key in API_PRICING:
                                if model_id.startswith(key):
                                    pricing = API_PRICING[key]
                                    model_id = key
                                    break
                        if pricing is None:
                            continue

                        inp = int(usage.get("input_tokens") or 0)
                        out = int(usage.get("output_tokens") or 0)
                        cr = int(usage.get("cache_read_input_tokens") or 0)
                        cw = int(usage.get("cache_creation_input_tokens") or 0)

                        cost = (
                            inp * pricing["input"]
                            + out * pricing["output"]
                            + cr * pricing["cache_read"]
                            + cw * pricing["cache_write"]
                        ) / 1_000_000

                        if model_id not in models:
                            models[model_id] = {
                                "cost_usd": 0.0,
                                "total_tokens": 0,
                                "input": 0,
                                "output": 0,
                                "cache_read": 0,
                                "cache_write": 0,
                            }
                        m = models[model_id]
                        m["cost_usd"] += cost
                        m["input"] += inp
                        m["output"] += out
                        m["cache_read"] += cr
                        m["cache_write"] += cw
                        m["total_tokens"] += inp + out + cr + cw
                        total_cost_usd += cost
                        total_tokens += inp + out + cr + cw
                    except (AttributeError, KeyError, TypeError, ValueError):
                        continue
        except (OSError, PermissionError):
            continue

    first_seen_str = None
    if first_seen_ts is not None:
        try:
            first_seen_str = date.fromtimestamp(first_seen_ts).isoformat()
        except (OSError, ValueError, OverflowError):
            pass

    return {
        "models": models,
        "total_cost_usd": total_cost_usd,
        "total_tokens": total_tokens,
        "session_count": session_count,
        "first_seen": first_seen_str,
    }


def cmd_stats():
    """Show full session stats summary."""
    stats = _load_stats()
    today = _today_local()
    current, longest = _calculate_streak(stats.get("daily_dates", []), today)

    utf8_print(f"\n{BOLD}claude-pulse stats{RESET}\n")
    utf8_print(f"  First seen:     {_sanitize(str(stats.get('first_seen', 'unknown')))}")
    utf8_print(f"  Total sessions: {stats.get('total_sessions', 0)}")
    utf8_print(f"  Days active:    {len(set(stats.get('daily_dates', [])))}")
    utf8_print(f"  Current streak: {current}d")
    utf8_print(f"  Longest streak: {max(stats.get('longest_streak', 0), longest)}d")

    milestone = _check_milestone(stats.get("total_sessions", 0))
    if milestone:
        utf8_print(f"  Milestone:      {BRIGHT_YELLOW}{milestone}{RESET}")
    utf8_print("")

    # --- API-equivalent cost section ---
    sys.stdout.buffer.write(f"{DIM}  Scanning sessions...{RESET}\r".encode("utf-8"))
    sys.stdout.buffer.flush()
    cost_data = _scan_session_costs()
    sys.stdout.buffer.write(b"                        \r")
    sys.stdout.buffer.flush()

    config = load_config()
    currency_sym = _sanitize(config.get("currency", "$"))[:5]
    rate, _code = _get_exchange_rate(currency_sym)

    model_rows = sorted(
        [(mid, mdata) for mid, mdata in cost_data["models"].items() if mdata["cost_usd"] > 0],
        key=lambda x: x[1]["cost_usd"],
        reverse=True,
    )

    if model_rows:
        utf8_print(f"  {BOLD}API-equivalent cost:{RESET}")
        # Find longest display name for alignment
        display_names = [API_PRICING_DISPLAY.get(mid, mid) for mid, _ in model_rows]
        max_name_len = max(len(n) for n in display_names)

        for (mid, mdata), dname in zip(model_rows, display_names):
            local_cost = mdata["cost_usd"] * rate
            cost_str = f"{currency_sym}{local_cost:,.2f}"
            tok_str = (
                f"{_fmt_tokens(mdata['input'])} in"
                f" \u00b7 {_fmt_tokens(mdata['output'])} out"
                f" \u00b7 {_fmt_tokens(mdata['cache_read'] + mdata['cache_write'])} cached"
            )
            pad = max_name_len - len(dname)
            utf8_print(
                f"    {BRIGHT_WHITE}{dname}:{RESET}{' ' * pad}  "
                f"{BRIGHT_YELLOW}{cost_str:<12}{RESET}{DIM}({tok_str}){RESET}"
            )

        utf8_print(f"    {DIM}{'\u2500' * 33}{RESET}")
        total_local = cost_data["total_cost_usd"] * rate
        utf8_print(f"    {'Total:':<{max_name_len + 2}}  {BOLD}{BRIGHT_YELLOW}{currency_sym}{total_local:,.2f}{RESET}")
        utf8_print("")

        # Subscription value vs $200/month Max plan
        first_seen = cost_data.get("first_seen")
        months_active = 1.0
        if first_seen:
            try:
                fs = date.fromisoformat(first_seen)
                delta_days = (date.today() - fs).days
                months_active = max(delta_days / 30.44, 1.0)
            except (ValueError, TypeError):
                pass

        subscription_ref_usd = 200.0 * months_active
        ratio = cost_data["total_cost_usd"] / subscription_ref_usd
        utf8_print(
            f"  {DIM}Subscription value: ~{RESET}{BRIGHT_GREEN}{ratio:.1f}x{RESET}"
            f"{DIM} vs API pricing ({months_active:.1f} months \u00d7 $200/mo Max){RESET}"
        )
        utf8_print("")
    else:
        utf8_print(f"  {DIM}No session transcript data found for cost analysis.{RESET}\n")


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

    # Cost and lines changed
    try:
        cost = data.get("data", data).get("cost", {})
        total = cost.get("total_cost_usd")
        if total is not None:
            result["cost_usd"] = float(total)
        lines_added = cost.get("total_lines_added")
        lines_removed = cost.get("total_lines_removed")
        if lines_added is not None or lines_removed is not None:
            result["lines_added"] = int(lines_added or 0)
            result["lines_removed"] = int(lines_removed or 0)
    except (AttributeError, KeyError, ValueError, TypeError):
        pass

    # Worktree (v2.1.69+)
    try:
        wt = data.get("data", data).get("worktree", {})
        if wt:
            branch = _sanitize(wt.get("branch", ""))
            name = _sanitize(wt.get("name", ""))
            if branch:
                result["worktree_branch"] = branch
            elif name:
                result["worktree_branch"] = name
    except (AttributeError, KeyError):
        pass

    # Rate limits from stdin (v2.1.80+) — eliminates need for OAuth API call
    try:
        rl = data.get("data", data).get("rate_limits", {})
        if rl:
            result["_rate_limits"] = {}
            for window in ("five_hour", "seven_day", "seven_day_opus", "seven_day_sonnet"):
                w = rl.get(window)
                if w and w.get("used_percentage") is not None:
                    # Convert Unix epoch seconds to ISO string for compatibility
                    # with existing format_reset_time / format_weekly_reset
                    resets_at = w.get("resets_at")
                    resets_iso = None
                    if resets_at is not None:
                        try:
                            resets_iso = datetime.fromtimestamp(
                                float(resets_at), tz=timezone.utc
                            ).isoformat()
                        except (ValueError, OSError):
                            pass
                    result["_rate_limits"][window] = {
                        "utilization": float(w["used_percentage"]),
                        "resets_at": resets_iso,
                    }
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


# ---------------------------------------------------------------------------
# Multi-session awareness
# ---------------------------------------------------------------------------

def _get_sessions_dir():
    sessions_dir = get_state_dir() / SESSION_DIR_NAME
    _secure_mkdir(sessions_dir)
    return sessions_dir


def _get_session_id():
    return os.getppid()


def _update_session_state(usage, stdin_ctx):
    try:
        session_id = _get_session_id()
        sessions_dir = _get_sessions_dir()
        five = usage.get("five_hour", {}) if usage else {}
        seven = usage.get("seven_day", {}) if usage else {}
        state = {
            "pid": session_id,
            "session_pct": five.get("utilization") or 0,
            "weekly_pct": seven.get("utilization") or 0,
            "timestamp": time.time(),
            "model": (stdin_ctx or {}).get("model_name", ""),
        }
        _atomic_json_write(sessions_dir / f"{session_id}.json", state, indent=None)
    except Exception:
        pass


def _get_active_sessions():
    sessions_dir = _get_sessions_dir()
    my_pid = _get_session_id()
    now = time.time()
    active = []
    try:
        for entry in sessions_dir.iterdir():
            if not entry.name.endswith(".json"):
                continue
            try:
                with open(entry, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if now - data.get("timestamp", 0) > SESSION_STALE_SECONDS:
                    try:
                        entry.unlink(missing_ok=True)
                    except OSError:
                        pass
                    continue
                if data.get("pid") == my_pid:
                    continue
                active.append(data)
            except (json.JSONDecodeError, OSError):
                try:
                    entry.unlink(missing_ok=True)
                except OSError:
                    pass
    except OSError:
        pass
    return active


# ---------------------------------------------------------------------------
# Focus timer
# ---------------------------------------------------------------------------

def _get_pomodoro_path():
    return get_state_dir() / POMODORO_FILE


def _read_pomodoro():
    try:
        with open(_get_pomodoro_path(), "r", encoding="utf-8") as f:
            data = json.load(f)
        if data.get("active"):
            return data
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass
    return None


def _write_pomodoro(data):
    _atomic_json_write(_get_pomodoro_path(), data, indent=2)


def _pomodoro_remaining(pomo):
    if not pomo or not pomo.get("active"):
        return (0, False)
    start = pomo.get("start", 0)
    duration = pomo.get("duration_minutes", POMODORO_DEFAULT_MINUTES)
    elapsed = time.time() - start
    focus_seconds = duration * 60
    break_seconds = POMODORO_BREAK_MINUTES * 60
    if elapsed < focus_seconds:
        return (focus_seconds - elapsed, False)
    elif elapsed < focus_seconds + break_seconds:
        return (focus_seconds + break_seconds - elapsed, True)
    return (0, False)


def _render_pomodoro(pomo, theme, bar_width=8):
    if not pomo or not pomo.get("active"):
        return ""
    remaining, is_break = _pomodoro_remaining(pomo)
    if remaining <= 0:
        try:
            pomo["active"] = False
            _write_pomodoro(pomo)
        except Exception:
            pass
        return ""
    remaining_min = int(remaining / 60) + (1 if remaining % 60 > 0 else 0)
    if is_break:
        return f"\u2615 Break! {remaining_min}m"
    duration = pomo.get("duration_minutes", POMODORO_DEFAULT_MINUTES)
    elapsed = time.time() - pomo.get("start", 0)
    pct = min(100.0, max(0.0, (elapsed / (duration * 60)) * 100))
    filled = round(pct / 100 * bar_width)
    filled = max(0, min(bar_width, filled))
    colour = bar_colour(pct, theme)
    bar = f"{colour}{FILL * filled}{DIM}{EMPTY * (bar_width - filled)}{RESET}"
    return f"Focus {remaining_min}m {bar}"


def cmd_pomodoro(action, minutes=None):
    if action == "start":
        duration = POMODORO_DEFAULT_MINUTES
        if minutes is not None:
            try:
                duration = int(minutes)
                if duration < 1 or duration > 240:
                    utf8_print("Duration must be between 1 and 240 minutes.")
                    return
            except ValueError:
                utf8_print(f"Invalid duration: {_sanitize(str(minutes))}")
                return
        _write_pomodoro({"start": time.time(), "duration_minutes": duration, "active": True})
        utf8_print(f"{BRIGHT_GREEN}Focus started: {duration} minutes{RESET}")
        utf8_print(f"  Focus timer will appear in your status line.")
        utf8_print(f"  Stop with: --focus stop")
    elif action == "stop":
        pomo = _read_pomodoro()
        if pomo and pomo.get("active"):
            pomo["active"] = False
            _write_pomodoro(pomo)
            utf8_print("Focus stopped.")
        else:
            utf8_print("No active pomodoro timer.")
    elif action == "status":
        pomo = _read_pomodoro()
        if not pomo or not pomo.get("active"):
            utf8_print("No active pomodoro timer.")
            utf8_print("  Start with: --focus start [minutes]")
            return
        remaining, is_break = _pomodoro_remaining(pomo)
        if remaining <= 0:
            utf8_print("Focus timer has expired.")
            return
        remaining_min = int(remaining / 60) + (1 if remaining % 60 > 0 else 0)
        if is_break:
            utf8_print(f"\u2615 Break time! {remaining_min}m remaining")
        else:
            elapsed_min = int((time.time() - pomo.get("start", 0)) / 60)
            utf8_print(f"{BOLD}Focus:{RESET} {elapsed_min}m / {pomo.get('duration_minutes', 25)}m elapsed, {remaining_min}m remaining")
    else:
        utf8_print(f"Usage: --focus start [minutes] | stop | status")


# ---------------------------------------------------------------------------
# Git drift detector
# ---------------------------------------------------------------------------

def _check_git_drift():
    state_dir = get_state_dir()
    drift_cache = state_dir / GIT_DRIFT_FILE
    try:
        with open(drift_cache, "r", encoding="utf-8") as f:
            cached = json.load(f)
        if time.time() - cached.get("timestamp", 0) < GIT_DRIFT_CACHE_TTL:
            return (cached.get("behind", 0), cached.get("ahead", 0))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass
    behind = ahead = 0
    try:
        result = subprocess.run([_GIT_PATH, "rev-list", "--count", "HEAD..@{upstream}"], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            behind = int(result.stdout.strip())
    except (subprocess.TimeoutExpired, ValueError, OSError):
        pass
    try:
        result = subprocess.run([_GIT_PATH, "rev-list", "--count", "@{upstream}..HEAD"], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            ahead = int(result.stdout.strip())
    except (subprocess.TimeoutExpired, ValueError, OSError):
        pass
    try:
        _atomic_json_write(drift_cache, {"timestamp": time.time(), "behind": behind, "ahead": ahead}, indent=None)
    except OSError:
        pass
    return (behind, ahead)


def _render_git_drift():
    try:
        behind, ahead = _check_git_drift()
        if behind == 0 and ahead == 0:
            return ""
        parts = []
        if behind > 0:
            parts.append(f"\u2193{behind}")
        if ahead > 0:
            parts.append(f"\u2191{ahead}")
        return " ".join(parts)
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Files changed counter
# ---------------------------------------------------------------------------

def _count_changed_files():
    state_dir = get_state_dir()
    files_cache = state_dir / FILES_CHANGED_FILE
    try:
        with open(files_cache, "r", encoding="utf-8") as f:
            cached = json.load(f)
        if time.time() - cached.get("timestamp", 0) < FILES_CHANGED_CACHE_TTL:
            return cached.get("count", 0)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass
    count = 0
    try:
        result = subprocess.run([_GIT_PATH, "diff", "--name-only"], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            count = len([l for l in result.stdout.strip().split("\n") if l.strip()])
    except (subprocess.TimeoutExpired, OSError):
        pass
    try:
        _atomic_json_write(files_cache, {"timestamp": time.time(), "count": count}, indent=None)
    except OSError:
        pass
    return count


def _render_files_changed():
    try:
        count = _count_changed_files()
        if count > 0:
            return f"{count} file{'s' if count != 1 else ''}"
        return ""
    except Exception:
        return ""


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


def build_status_line(usage, plan, config=None, stdin_ctx=None, cache_age=None):
    if config is None:
        config = load_config()

    theme_name = config.get("theme", "default")
    is_rainbow_theme = theme_name == "rainbow"
    animate_raw = config.get("animate", "off")
    # Normalize: True→"rainbow", False→"off", string→itself
    if animate_raw is True:
        animate_raw = "rainbow"
    elif animate_raw is False:
        animate_raw = "off"
    animate = animate_raw != "off"

    use_rainbow = is_rainbow_theme or animate_raw == "rainbow"

    if use_rainbow:
        bar_plain = True
        theme = get_theme_colours(theme_name) if not is_rainbow_theme else THEMES["default"]
    else:
        bar_plain = False
        theme = get_theme_colours(theme_name)

    # Animation state for threshold flash and celebration
    anim_state = _load_anim_state() if animate else {}
    # Animation mode
    anim_mode = animate_raw if animate_raw in ANIMATE_MODES else "off"

    show = config.get("show", DEFAULT_SHOW)
    bar_size = config.get("bar_size", DEFAULT_BAR_SIZE)
    bw = BAR_SIZES.get(bar_size, BAR_SIZES[DEFAULT_BAR_SIZE])
    bstyle = config.get("bar_style", DEFAULT_BAR_STYLE)
    layout = config.get("layout", DEFAULT_LAYOUT)

    # Terminal width clamping — shrink bars proportionally when the viewport
    # is narrower than the full rendered line.  _detect_terminal_width tries
    # real TTY, stderr/stdin fds, /dev/tty, COLUMNS env, then /proc on Linux.
    # When all fail, fall back to shutil's conservative estimate so bars still
    # shrink to keep all sections visible rather than being truncated.
    try:
        term_width = _detect_terminal_width() or shutil.get_terminal_size((120, 24)).columns
        max_width_pct = config.get("max_width", DEFAULT_MAX_WIDTH_PCT)
        if not (isinstance(max_width_pct, int) and 20 <= max_width_pct <= 100):
            max_width_pct = DEFAULT_MAX_WIDTH_PCT
        effective_width = (term_width * max_width_pct) // 100
        # Count ALL bar sections that will be rendered (session, weekly,
        # extra, context) so the width budget is split correctly.
        num_bars = sum(1 for k in ("session", "weekly") if show.get(k, True))
        extra = usage.get("extra_usage")
        if extra and extra.get("is_enabled") and not config.get("extra_hidden", False):
            num_bars += 1
        if stdin_ctx and show.get("context", True):
            num_bars += 1
        # Per-bar overhead: label + space + space + pct + timer ≈ 18 chars
        # Separators between sections: " | " = 3 chars each
        # Trailing fixed items (model name, update/plan indicators) ≈ 15 chars
        overhead = num_bars * 18 + max(num_bars - 1, 0) * 3 + 15
        max_bar_width = max(2, (effective_width - overhead) // max(num_bars, 1))
        if bw > max_bar_width:
            bw = max_bar_width
    except Exception:
        pass  # if width detection/clamping fails, use configured bar size

    parts = []  # list of (priority, text) tuples — sorted before joining
    _wpri = dict(WIDGET_PRIORITY)
    _wpri.update(config.get("widget_priority", {}))
    def _pri(widget_id):
        return _wpri.get(widget_id, 999)

    # Current Session (5-hour block)
    if show.get("session", True):
        five = usage.get("five_hour")
        if five:
            pct = five.get("utilization") or 0
            session_flash = None
            if animate:
                _check_threshold_flash("session", pct, anim_state)
                session_flash = _get_flash_color("session", theme, anim_state)
            bar = make_bar(pct, theme, plain=bar_plain, width=bw, bar_style=bstyle,
                           anim_mode=anim_mode, flash_color=session_flash, config=config)
            reset = format_reset_time(five.get("resets_at")) if show.get("timer", True) else None
            reset_str = f" {reset}" if reset else ""
            pace_str = ""
            if show.get("pace"):
                pace = _calc_pace_pct(five.get("resets_at"), 18000)
                if pace is not None:
                    pace_str = f" ({pace:.0f}%)"
            _s = _pri("session")
            if layout == "compact":
                parts.append((_s, f"S {bar} {pct:.0f}%{pace_str}{reset_str}"))
            elif layout == "minimal":
                parts.append((_s, f"{bar} {pct:.0f}%{pace_str}{reset_str}"))
            elif layout == "percent-first":
                parts.append((_s, f"{pct:.0f}%{pace_str} {bar}{reset_str}"))
            else:  # standard
                history = _read_history() if show.get("sparkline", True) or show.get("runway", True) or show.get("status_message", True) or show.get("burn_rate", True) else []
                label = "Session"
                if show.get("status_message", True):
                    velocity = _compute_velocity(history)
                    msg, _ = _get_status_message(pct, velocity)
                    label = msg
                spark_str = ""
                if show.get("sparkline", True):
                    spark = _render_sparkline(history)
                    if spark:
                        spark_str = f" {spark}"
                runway_str = ""
                if show.get("runway", True):
                    runway = _estimate_runway(history, pct)
                    if runway:
                        runway_str = f" {runway}"
                burn_str = ""
                if show.get("burn_rate", True) and history:
                    br = _format_burn_rate(history, pct, show_runway=show.get("runway", False))
                    burn_str = f" {br}" if br else ""
                if reset_str and (runway_str or spark_str or burn_str):
                    reset_str = f" \u00b7{reset}"
                parts.append((_s, f"{label} {bar} {pct:.0f}%{burn_str}{pace_str}{spark_str}{runway_str}{reset_str}"))
        else:
            _s = _pri("session")
            bar = make_bar(0, theme, plain=bar_plain, width=bw, bar_style=bstyle)
            if layout == "compact":
                parts.append((_s, f"S {bar} 0%"))
            elif layout == "minimal":
                parts.append((_s, f"{bar} 0%"))
            elif layout == "percent-first":
                parts.append((_s, f"0% {bar}"))
            else:
                parts.append((_s, f"Session {bar} 0%"))

    # Weekly Limit (7-day all models)
    if show.get("weekly", True):
        seven = usage.get("seven_day")
        if seven:
            pct = seven.get("utilization") or 0
            weekly_flash = None
            celebrating = False
            if animate:
                _check_threshold_flash("weekly", pct, anim_state)
                weekly_flash = _get_flash_color("weekly", theme, anim_state)
                celebrating = _check_celebration(pct, anim_state)
            bar = make_bar(pct, theme, plain=bar_plain, width=bw, bar_style=bstyle,
                           anim_mode=anim_mode, flash_color=weekly_flash, config=config)
            weekly_reset_str = ""
            if show.get("weekly_timer", True):
                wt_fmt = config.get("weekly_timer_format", DEFAULT_WEEKLY_TIMER_FORMAT)
                if wt_fmt not in WEEKLY_TIMER_FORMATS:
                    wt_fmt = DEFAULT_WEEKLY_TIMER_FORMAT
                wt_prefix = _sanitize(str(config.get("weekly_timer_prefix", DEFAULT_WEEKLY_TIMER_PREFIX)))[:10]
                wt_clock = config.get("clock_format", DEFAULT_CLOCK_FORMAT)
                if wt_clock not in CLOCK_FORMATS:
                    wt_clock = DEFAULT_CLOCK_FORMAT
                wr = format_weekly_reset(seven.get("resets_at"), fmt=wt_fmt, clock=wt_clock)
                if wr:
                    weekly_reset_str = f" {wt_prefix}{wr}"
            pace_str = ""
            if show.get("pace"):
                pace = _calc_pace_pct(seven.get("resets_at"), 604800)
                if pace is not None:
                    pace_str = f" ({pace:.0f}%)"
            _w = _pri("weekly")
            if celebrating:
                celeb_label = _render_celebration_label(config)
                parts.append((_w, f"{celeb_label} {bar} {pct:.0f}%{pace_str}{weekly_reset_str}"))
            elif layout == "compact":
                parts.append((_w, f"W {bar} {pct:.0f}%{pace_str}{weekly_reset_str}"))
            elif layout == "minimal":
                parts.append((_w, f"{bar} {pct:.0f}%{pace_str}{weekly_reset_str}"))
            elif layout == "percent-first":
                parts.append((_w, f"{pct:.0f}%{pace_str} {bar}{weekly_reset_str}"))
            else:
                parts.append((_w, f"Weekly {bar} {pct:.0f}%{pace_str}{weekly_reset_str}"))

    # Opus weekly limit
    if show.get("opus", True):
        opus = usage.get("seven_day_opus")
        if opus and opus.get("utilization") is not None:
            pct = opus.get("utilization") or 0
            bar = make_bar(pct, theme, plain=bar_plain, width=bw, bar_style=bstyle)
            _o = _pri("opus")
            if layout == "compact":
                parts.append((_o, f"O {bar} {pct:.0f}%"))
            elif layout == "minimal":
                parts.append((_o, f"{bar} {pct:.0f}%"))
            elif layout == "percent-first":
                parts.append((_o, f"{pct:.0f}% {bar}"))
            else:
                parts.append((_o, f"Opus {bar} {pct:.0f}%"))

    # Sonnet weekly limit
    if show.get("sonnet", True):
        sonnet = usage.get("seven_day_sonnet")
        if sonnet and sonnet.get("utilization") is not None:
            pct = sonnet.get("utilization") or 0
            bar = make_bar(pct, theme, plain=bar_plain, width=bw, bar_style=bstyle)
            pace_str = ""
            if show.get("pace"):
                pace = _calc_pace_pct(sonnet.get("resets_at"), 604800)
                if pace is not None:
                    pace_str = f" ({pace:.0f}%)"
            _sn = _pri("sonnet")
            if layout == "compact":
                parts.append((_sn, f"S {bar} {pct:.0f}%{pace_str}"))
            elif layout == "minimal":
                parts.append((_sn, f"{bar} {pct:.0f}%{pace_str}"))
            elif layout == "percent-first":
                parts.append((_sn, f"{pct:.0f}%{pace_str} {bar}"))
            else:
                parts.append((_sn, f"Sonnet {bar} {pct:.0f}%{pace_str}"))
        else:
            bar = make_bar(0, theme, plain=bar_plain, width=bw, bar_style=bstyle)
            _sn = _pri("sonnet")
            if layout == "compact":
                parts.append((_sn, f"S {bar} 0%"))
            elif layout == "minimal":
                parts.append((_sn, f"{bar} 0%"))
            elif layout == "percent-first":
                parts.append((_sn, f"0% {bar}"))
            else:
                parts.append((_sn, f"Sonnet {bar} 0%"))

    # Extra usage (bonus/gifted credits)
    extra = usage.get("extra_usage")
    extra_enabled_by_user = show.get("extra", False)
    extra_explicitly_hidden = config.get("extra_hidden", False)
    extra_has_credits = extra and extra.get("is_enabled") and (extra.get("monthly_limit") or 0) > 0
    if extra_enabled_by_user or (extra_has_credits and not extra_explicitly_hidden):
        _e = _pri("extra")
        currency = _sanitize(config.get("currency", "$"))[:5]
        if extra and extra.get("is_enabled"):
            pct = min(extra.get("utilization") or 0, 100)
            used = (extra.get("used_credits") or 0) / 100
            limit = (extra.get("monthly_limit") or 0) / 100
            extra_display = config.get("extra_display", "auto")
            if extra_display == "auto":
                extra_display = "amount" if limit == 0 else "full"
            if extra_display == "amount":
                if layout == "compact":
                    parts.append((_e, f"E {currency}{used:.2f}"))
                elif layout == "minimal":
                    parts.append((_e, f"{currency}{used:.2f}"))
                else:
                    parts.append((_e, f"Extra {currency}{used:.2f}"))
            else:
                bar = make_bar(pct, theme, plain=bar_plain, width=bw, bar_style=bstyle)
                if layout == "compact":
                    parts.append((_e, f"E {bar} {currency}{used:.2f}/{currency}{limit:.2f}"))
                elif layout == "minimal":
                    parts.append((_e, f"{bar} {currency}{used:.2f}"))
                elif layout == "percent-first":
                    parts.append((_e, f"{currency}{used:.2f} {bar}"))
                else:
                    parts.append((_e, f"Extra {bar} {currency}{used:.2f}/{currency}{limit:.2f}"))
        elif extra_enabled_by_user:
            if layout == "minimal":
                parts.append((_e, "n/a"))
            elif layout == "compact":
                parts.append((_e, "E: n/a"))
            else:
                parts.append((_e, "Extra: n/a"))

    # Context window usage from stdin context (with pressure warning)
    if stdin_ctx and show.get("context", True):
        ctx_pct = stdin_ctx.get("context_pct")
        if ctx_pct is not None:
            ctx_bar = make_bar(ctx_pct, theme, plain=bar_plain, width=bw, bar_style=bstyle,
                               anim_mode=anim_mode, config=config)
            ctx_fmt = config.get("context_format", "percent")
            ctx_used = stdin_ctx.get("context_used")
            ctx_limit = stdin_ctx.get("context_limit")
            if ctx_used is None or ctx_limit is None:
                model_name = stdin_ctx.get("model_name", "")
                window = MODEL_CONTEXT_WINDOWS.get(model_name, DEFAULT_CONTEXT_WINDOW)
                ctx_limit = window
                ctx_used = int(ctx_pct / 100 * window)
            if ctx_fmt == "tokens":
                pct_label = f"{_fmt_tokens(ctx_used)}/{_fmt_tokens(ctx_limit)}"
            else:
                pct_label = f"{ctx_pct:.0f}%"
            ctx_warning_label = None
            ctx_warning_suffix = ""
            if show.get("context_warning", True):
                ctx_warning_label, ctx_warning_suffix = _format_context_warning(ctx_pct, theme)
                if ctx_warning_suffix is None:
                    ctx_warning_suffix = ""
            _cx = _pri("context")
            if layout == "compact":
                prefix = f"\u26a0 C" if ctx_warning_label else "C"
                parts.append((_cx, f"{prefix} {ctx_bar} {pct_label}{ctx_warning_suffix}"))
            elif layout == "minimal":
                parts.append((_cx, f"{ctx_bar} {pct_label}{ctx_warning_suffix}"))
            elif layout == "percent-first":
                parts.append((_cx, f"{pct_label}{ctx_warning_suffix} {ctx_bar}"))
            else:
                if ctx_warning_label:
                    parts.append((_cx, f"{ctx_warning_label} {ctx_bar} {pct_label}{ctx_warning_suffix}"))
                else:
                    parts.append((_cx, f"Context {ctx_bar} {pct_label}"))

    # Cost ticker
    if stdin_ctx and show.get("cost", True):
        cost_str = _format_cost(stdin_ctx, config)
        if cost_str:
            parts.append((_pri("cost"), cost_str))

    # Cumulative API-equivalent cost (opt-in, off by default)
    if show.get("cumulative_cost", False):
        try:
            cost_data = _get_cached_cumulative_cost()
            total_usd = cost_data.get("total_cost_usd", 0.0)
            if total_usd > 0:
                currency = _sanitize(config.get("currency", "$"))[:5]
                rate, code = _get_exchange_rate(currency)
                total_local = total_usd * rate
                sym = "$" if code == "USD" else currency
                parts.append((_pri("cumulative_cost"), f"{DIM}All:{RESET} {sym}{total_local:,.2f}"))
        except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError):
            pass

    # Lines changed (from stdin cost data)
    if stdin_ctx and show.get("lines", True):
        la = stdin_ctx.get("lines_added")
        lr = stdin_ctx.get("lines_removed")
        if la is not None or lr is not None:
            a = int(la or 0)
            r = int(lr or 0)
            if a > 0 or r > 0:
                parts.append((_pri("lines"), f"{BRIGHT_GREEN}+{a}{RESET} {BRIGHT_RED}-{r}{RESET}"))

    # Peak hours indicator
    is_peak, peak_str = _check_peak_hours(config)
    if peak_str:
        _pk = _pri("peak")
        if is_peak:
            parts.append((_pk, f"{RED}{peak_str}{RESET}"))
        elif "in " in peak_str:
            parts.append((_pk, f"{YELLOW}{peak_str}{RESET}"))
        else:
            parts.append((_pk, f"{GREEN}{peak_str}{RESET}"))

    # Plan name (hidden in minimal layout)
    if layout != "minimal" and show.get("plan", True) and plan:
        parts.append((_pri("plan"), _sanitize(plan)))

    # Streak display
    if show.get("streak", True):
        try:
            stats = _load_stats()
            sd = _get_streak_display(config, stats)
            if sd:
                parts.append((_pri("streak"), sd))
        except Exception:
            pass

    # Model name from stdin context
    if stdin_ctx and show.get("model", True):
        model = stdin_ctx.get("model_name")
        if model:
            model = re.sub(r'\s*\([^)]*context[^)]*\)', '', model).strip()
            if model:
                parts.append((_pri("model"), model))

    # Effort level
    if show.get("effort", True):
        effort = os.environ.get("CLAUDE_CODE_EFFORT_LEVEL", "")
        if effort and effort != "unset":
            effort = _sanitize(effort)
            effort_short = {"medium": "med"}.get(effort, effort)
            parts.append((_pri("effort"), effort_short))

    # Worktree branch
    if stdin_ctx and show.get("worktree", True):
        wt_branch = stdin_ctx.get("worktree_branch")
        if wt_branch:
            parts.append((_pri("worktree"), wt_branch))

    # --- Hook-based live features ---
    hook_state = _read_hook_state()
    hook_fresh = _is_hook_state_fresh(hook_state)

    if show.get("heartbeat", True) and hook_fresh:
        tool_count = hook_state.get("tool_count", 0)
        session_start = hook_state.get("session_start", time.time())
        elapsed = time.time() - session_start
        frame_idx = int(time.time() * 4) % len(HEARTBEAT_SPINNER)
        spinner = HEARTBEAT_SPINNER[frame_idx]
        parts.append((_pri("heartbeat"), f"[{spinner}] {tool_count} tools {_format_elapsed(elapsed)}"))

    if show.get("activity", True) and hook_fresh:
        if hook_state.get("rapid_calls", 0) > 3:
            parts.append((_pri("activity"), f"\u26a1 Active"))

    if show.get("last_tool", False) and hook_fresh:
        last_tool = hook_state.get("last_tool", "")
        if last_tool:
            parts.append((_pri("last_tool"), f"Last: {last_tool[:12]}"))

    if show.get("branch", True):
        worktree_shown = stdin_ctx and show.get("worktree", True) and stdin_ctx.get("worktree_branch")
        if not worktree_shown:
            git_branch = _get_git_branch()
            if git_branch:
                parts.append((_pri("branch"), git_branch))

    if show.get("sessions", False):
        try:
            other_sessions = _get_active_sessions()
            if other_sessions:
                count = len(other_sessions)
                parts.append((_pri("sessions"), f"+{count} session{'s' if count != 1 else ''}"))
        except Exception:
            pass

    if show.get("pomodoro", True):
        try:
            pomo = _read_pomodoro()
            if pomo and pomo.get("active"):
                pomo_str = _render_pomodoro(pomo, theme, bar_width=min(bw, 8))
                if pomo_str:
                    parts.append((_pri("pomodoro"), pomo_str))
        except Exception:
            pass

    if show.get("git_drift", False):
        try:
            drift_str = _render_git_drift()
            if drift_str:
                parts.append((_pri("git_drift"), drift_str))
        except Exception:
            pass

    if show.get("files_changed", False):
        try:
            files_str = _render_files_changed()
            if files_str:
                parts.append((_pri("files_changed"), files_str))
        except Exception:
            pass

    # Sort widgets by priority, then join
    parts.sort(key=lambda x: x[0])
    line = " | ".join(p[1] for p in parts)

    # Staleness indicator
    if show.get("staleness", True) and cache_age is not None:
        staleness_str = _format_staleness(cache_age)
        if staleness_str:
            line += staleness_str

    # Animation: on = rainbow always moving, off = static theme colours
    if use_rainbow:
        line = rainbow_colorize(line, color_all=False, shimmer=animate, config=config)
    else:
        text_color_code = resolve_text_color(config)
        if text_color_code:
            line = apply_text_color(line, text_color_code)

    # Persist animation state
    if animate:
        _save_anim_state(anim_state)

    return line


def _visible_len(text):
    """Return the number of visible (non-ANSI-escape) characters in *text*."""
    count = 0
    i = 0
    while i < len(text):
        if text[i] == "\033":
            j = i + 1
            while j < len(text) and j < i + 25 and text[j] not in "ABCDEFGHJKSTfmnsulh":
                j += 1
            i = j + 1 if j < len(text) else j
            continue
        count += 1
        i += 1
    return count


def _truncate_line(line, config):
    """Clip visible characters to effective terminal width.

    Applied as the very last step before output so the line never spills
    into Claude Code's side notification area or wraps to the next line.
    """
    try:
        term_width = _detect_terminal_width() or shutil.get_terminal_size((120, 24)).columns
        max_width_pct = config.get("max_width", DEFAULT_MAX_WIDTH_PCT)
        if not (isinstance(max_width_pct, int) and 20 <= max_width_pct <= 100):
            max_width_pct = DEFAULT_MAX_WIDTH_PCT
        max_visible = (term_width * max_width_pct) // 100
        visible_count = 0
        cut = None
        i = 0
        while i < len(line):
            if line[i] == "\033":
                # Skip ANSI escape sequence
                j = i + 1
                while j < len(line) and j < i + 25 and line[j] not in "ABCDEFGHJKSTfmnsulh":
                    j += 1
                i = j + 1 if j < len(line) else j
                continue
            visible_count += 1
            if visible_count > max_visible:
                cut = i
                break
            i += 1
        if cut is not None:
            line = line[:cut] + RESET
    except Exception:
        pass
    return line


def _wrap_line(line, config):
    """Wrap at ' | ' separators when the line would overflow the terminal.

    Returns one or two lines joined by newline.  If the line fits, it is
    returned unchanged (no trailing newline added).  When wrapping is needed,
    segments are distributed across two lines so that each stays within the
    effective terminal width.
    """
    try:
        term_width = _detect_terminal_width() or shutil.get_terminal_size((120, 24)).columns
        max_width_pct = config.get("max_width", DEFAULT_MAX_WIDTH_PCT)
        if not (isinstance(max_width_pct, int) and 20 <= max_width_pct <= 100):
            max_width_pct = DEFAULT_MAX_WIDTH_PCT
        max_visible = (term_width * max_width_pct) // 100

        if _visible_len(line) <= max_visible:
            return line

        # Split on the rendered separator
        segments = line.split(" | ")
        if len(segments) < 2:
            return _truncate_line(line, config)

        # Greedily fill line 1, then put the rest on line 2
        line1_parts = [segments[0]]
        rest = segments[1:]
        for seg in rest:
            candidate = " | ".join(line1_parts + [seg])
            if _visible_len(candidate) <= max_visible:
                line1_parts.append(seg)
            else:
                break
        used = len(line1_parts)
        line2_parts = segments[used:]

        if not line2_parts:
            return _truncate_line(line, config)

        row1 = " | ".join(line1_parts)
        row2 = " | ".join(line2_parts)
        # Truncate each row individually as a safety net
        row1 = _truncate_line(row1, config)
        row2 = _truncate_line(row2, config)
        return row1 + RESET + "\n" + row2
    except Exception:
        return _truncate_line(line, config)


def _fit_line(line, config):
    """Apply wrap or truncate depending on the user's --wrap setting."""
    if config.get("wrap") == "auto":
        return _wrap_line(line, config)
    return _truncate_line(line, config)


# ---------------------------------------------------------------------------
# Install
# ---------------------------------------------------------------------------

def _win_portable_path(path_str):
    """Convert a Windows absolute path to use $HOME where possible.

    Claude Code v2.1.47+ invokes statusLine commands via a shell that
    does not expand backslash paths correctly on Windows.  Using forward
    slashes and ``$HOME`` instead of the literal home directory avoids
    the issue.  See: https://github.com/anthropics/claude-code/issues/27057
    """
    if sys.platform != "win32":
        return path_str
    path_str = str(path_str).replace("\\", "/")
    home = str(Path.home()).replace("\\", "/")
    if path_str.startswith(home + "/") or path_str == home:
        path_str = "$HOME" + path_str[len(home):]
    return path_str


def _get_python_cmd():
    """Return the Python command to use in hooks/settings.

    Uses sys.executable to ensure we match whatever Python is running this script.
    On Linux this is typically 'python3', on Windows 'python'.
    """
    exe = _win_portable_path(sys.executable)
    # If the executable path contains spaces, quote it
    if " " in exe:
        return f'"{exe}"'
    return exe


def install_status_line():
    settings_path = Path.home() / ".claude" / "settings.json"
    script_path = _win_portable_path(Path(__file__).resolve())
    python_cmd = _get_python_cmd()

    settings = {}
    if settings_path.exists():
        try:
            with open(settings_path, "r", encoding="utf-8") as f:
                settings = json.load(f)
        except (json.JSONDecodeError, OSError):
            pass

    # Status line command — use $HOME on Windows for Claude Code compat
    settings["statusLine"] = {
        "type": "command",
        "command": f'{python_cmd} "{script_path}"',
        "refresh": 150,
    }

    # No hooks installed here — static status bar by default.
    # Use --animate on for always-on animation (installs hooks automatically)
    # Use --install-hooks for animate-while-working mode

    _secure_mkdir(settings_path.parent)
    _atomic_json_write(settings_path, settings)

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
        "seven_day": {"utilization": 67, "resets_at": None},
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
        "seven_day": {"utilization": 67, "resets_at": None},
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
    """Set the active theme and save to config.

    Special case: ``--theme default`` applies the full factory-reset preset
    so that bar size, text colour, animation, etc. all return to defaults —
    not just the colour palette.
    """
    if name not in THEMES:
        utf8_print(f"Unknown theme: {_sanitize(name)}")
        utf8_print(f"Available: {', '.join(THEMES.keys())}")
        return
    # "default" means full factory reset, not just the colour palette
    if name == "default" and "default" in PRESETS:
        cmd_preset("default")
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
            utf8_print(f"Unknown part: {_sanitize(part)} (valid: {', '.join(sorted(valid))})")
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
            utf8_print(f"Unknown part: {_sanitize(part)} (valid: {', '.join(sorted(valid))})")
            return
    for part in parts:
        config["show"][part] = False
        # Mark extra as explicitly hidden so auto-show respects it
        if part == "extra":
            config["extra_hidden"] = True
    save_config(config)
    utf8_print(f"Disabled: {', '.join(parts)}")


def cmd_preset(name):
    """Apply a named preset configuration."""
    if name not in PRESETS:
        utf8_print(f"Unknown preset: {_sanitize(name)}")
        utf8_print(f"\nAvailable presets:")
        for pname, pdata in PRESETS.items():
            utf8_print(f"  {BOLD}{pname:<10}{RESET} {pdata['description']}")
        return
    preset = PRESETS[name]
    config = load_config()
    # Apply config overrides (bar_size, layout, max_width, etc.)
    for key, val in preset["config"].items():
        config[key] = val
    # Apply show/hide overrides — respect user preferences for update notifications
    for key, val in preset["show_overrides"].items():
        config["show"][key] = val
    # Full reset should also clear sticky flags
    if name == "default":
        config.pop("extra_hidden", None)
    save_config(config)
    try:
        os.remove(get_cache_path())
    except OSError:
        pass
    utf8_print(f"Preset {BOLD}{name}{RESET} applied!")
    utf8_print(f"  {preset['description']}")
    # Show a preview
    demo_usage = {
        "five_hour": {"utilization": 42, "resets_at": None},
        "seven_day": {"utilization": 67, "resets_at": None},
    }
    line = build_status_line(demo_usage, "Max 20x", config)
    utf8_print(f"  Preview: {line}")


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
    utf8_print(f"  Currency:  {_sanitize(config.get('currency', chr(163)))}")
    bs = config.get("bar_size", DEFAULT_BAR_SIZE)
    bw_display = BAR_SIZES.get(bs, BAR_SIZES[DEFAULT_BAR_SIZE])
    utf8_print(f"  Bar size:  {bs} ({bw_display} chars)")
    mw = config.get("max_width", DEFAULT_MAX_WIDTH_PCT)
    utf8_print(f"  Max width: {mw}% of terminal")
    bst = config.get("bar_style", DEFAULT_BAR_STYLE)
    bst_chars = BAR_STYLES.get(bst, BAR_STYLES[DEFAULT_BAR_STYLE])
    if bst in BAR_GRADIENT_STYLES:
        _g = BAR_GRADIENT_STYLES[bst][0]
        utf8_print(f"  Bar style: {bst} ({_g[0]}..{_g[-1]})")
    else:
        utf8_print(f"  Bar style: {bst} ({bst_chars[0]}{bst_chars[1]})")
    ly = config.get("layout", DEFAULT_LAYOUT)
    utf8_print(f"  Layout:    {ly}")
    cf = config.get("context_format", "percent")
    utf8_print(f"  Context:   {cf}")
    ed = config.get("extra_display", "auto")
    utf8_print(f"  Extra display: {ed}")
    show = config.get("show", DEFAULT_SHOW)
    wt_fmt = _sanitize(str(config.get("weekly_timer_format", DEFAULT_WEEKLY_TIMER_FORMAT)))
    if wt_fmt not in WEEKLY_TIMER_FORMATS:
        wt_fmt = DEFAULT_WEEKLY_TIMER_FORMAT
    wt_pfx = _sanitize(str(config.get("weekly_timer_prefix", DEFAULT_WEEKLY_TIMER_PREFIX)))[:10]
    wt_vis = show.get("weekly_timer", True)
    wt_state = f"{GREEN}on{RESET}" if wt_vis else f"{RED}off{RESET}"
    wt_clk = config.get("clock_format", DEFAULT_CLOCK_FORMAT)
    if wt_clk not in CLOCK_FORMATS:
        wt_clk = DEFAULT_CLOCK_FORMAT
    utf8_print(f"  Weekly timer:  {wt_state}  format={wt_fmt}  prefix=\"{wt_pfx}\"  clock={wt_clk}")
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
    # Claude Code update check
    if _CLAUDE_PATH:
        try:
            result = subprocess.run(
                [_CLAUDE_PATH, "--version"],
                capture_output=True, text=True, timeout=3,
            )
            if result.returncode == 0:
                local_ver = _sanitize(result.stdout.strip().split()[0])
                cc_update = check_claude_code_update()
                if cc_update:
                    # Read cached remote version
                    try:
                        cc_cache_path = get_state_dir() / "claude_code_update.json"
                        with open(cc_cache_path, "r", encoding="utf-8") as f:
                            cc_cached = json.load(f)
                        remote_ver = _sanitize(cc_cached.get("remote", "?"))
                    except Exception:
                        remote_ver = "newer"
                    utf8_print(f"  Claude Code:  {BRIGHT_YELLOW}{local_ver} \u2192 {remote_ver} available{RESET}  (run {BOLD}claude update{RESET} in a new terminal)")
                elif cc_update is False:
                    utf8_print(f"  Claude Code:  {GREEN}{local_ver} (up to date){RESET}")
                else:
                    utf8_print(f"  Claude Code:  {DIM}{local_ver} (check failed){RESET}")
        except Exception:
            utf8_print(f"  Claude Code:  {DIM}check failed{RESET}")

    # Extra credits status — check the API
    utf8_print(f"\n  {BOLD}Extra Credits:{RESET}")
    try:
        token, _ = get_credentials()
        if token:
            _usage = fetch_usage(token)
            _extra = _usage.get("extra_usage")
            if _extra and _extra.get("is_enabled"):
                currency = config.get("currency", "$")
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

    if "--preset" in args:
        idx = args.index("--preset")
        if idx + 1 < len(args):
            cmd_preset(args[idx + 1].lower())
        else:
            utf8_print("Usage: --preset <name>\n")
            for pname, pdata in PRESETS.items():
                utf8_print(f"  {BOLD}{pname:<10}{RESET} {pdata['description']}")
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

    if "--priority" in args:
        idx = args.index("--priority")
        if idx + 1 < len(args):
            raw = args[idx + 1]
            config = load_config()
            wp = config.get("widget_priority", {})
            valid = set(WIDGET_PRIORITY.keys())
            for pair in raw.split(","):
                if "=" not in pair:
                    utf8_print(f"Bad format: {_sanitize(pair)} (use widget=number)")
                    return
                wid, val = pair.split("=", 1)
                wid = wid.strip().lower()
                if wid not in valid:
                    utf8_print(f"Unknown widget: {_sanitize(wid)} (valid: {', '.join(sorted(valid))})")
                    return
                try:
                    wp[wid] = int(val)
                except ValueError:
                    utf8_print(f"Bad priority: {_sanitize(val)} (must be a number)")
                    return
            config["widget_priority"] = wp
            save_config(config)
            utf8_print(f"Widget priorities updated: {', '.join(f'{k}={v}' for k, v in wp.items())}")
        else:
            utf8_print("Usage: --priority widget=N,widget=N")
            utf8_print(f"\nDefaults:")
            for wid, pri in sorted(WIDGET_PRIORITY.items(), key=lambda x: x[1]):
                utf8_print(f"  {wid:20s} {pri}")
        return

    if "--text-color" in args:
        idx = args.index("--text-color")
        if idx + 1 < len(args):
            val = args[idx + 1].lower()
            if val not in TEXT_COLORS and val != "auto":
                utf8_print(f"Unknown colour: {_sanitize(val)}")
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
            # Legacy compat: on/off map to rainbow/off
            if val in ("on", "true", "yes", "1"):
                val = "rainbow"
            elif val in ("off", "false", "no", "0"):
                val = "off"
            if val not in ANIMATE_MODES:
                utf8_print(f"Unknown animation: {_sanitize(val)}")
                utf8_print(f"Available: {', '.join(ANIMATE_MODES)}")
                return
            config = load_config()
            config["animate"] = val
            save_config(config)
            try:
                os.remove(get_cache_path())
            except OSError:
                pass
            descriptions = {
                "off": "static, no animation",
                "rainbow": "flowing rainbow gradient (overwrites theme colours)",
                "pulse": "bars fade between theme colour and white",
                "glow": "bars brighten and dim dramatically",
                "shift": "bright highlight slides across the bar",
            }
            if val == "off":
                utf8_print(f"Animation: {RED}off{RESET}  (static)")
            else:
                utf8_print(f"Animation: {GREEN}{val}{RESET}  ({descriptions.get(val, '')})")
        else:
            utf8_print(f"Usage: --animate <mode>\n")
            utf8_print(f"  {'off':<10} Static, no animation")
            utf8_print(f"  {'rainbow':<10} Flowing rainbow gradient")
            utf8_print(f"  {'pulse':<10} Bars fade to white and back")
            utf8_print(f"  {'glow':<10} Bars brighten and dim")
            utf8_print(f"  {'shift':<10} Highlight slides across bars")
        return

    if "--bar-size" in args:
        idx = args.index("--bar-size")
        if idx + 1 < len(args):
            val = args[idx + 1].lower()
            if val not in BAR_SIZES:
                utf8_print(f"Unknown size: {_sanitize(val)}")
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
            utf8_print(f"Usage: --bar-size <{'|'.join(BAR_SIZES.keys())}>")
            for name, width in BAR_SIZES.items():
                demo = f"{GREEN}{FILL * width}{RESET}"
                utf8_print(f"  {name:<14} {demo}  ({width} chars)")
        return

    if "--max-width" in args:
        idx = args.index("--max-width")
        if idx + 1 < len(args):
            try:
                val = int(args[idx + 1])
                if not (20 <= val <= 100):
                    utf8_print("max-width must be between 20 and 100")
                    return
            except ValueError:
                utf8_print("max-width must be a number (percentage of terminal width)")
                return
            config = load_config()
            config["max_width"] = val
            save_config(config)
            try:
                os.remove(get_cache_path())
            except OSError:
                pass
            utf8_print(f"Max width: {BOLD}{val}%{RESET} of terminal width")
        else:
            utf8_print("Usage: --max-width <20-100>  (percentage, default 80)")
        return

    if "--wrap" in args:
        idx = args.index("--wrap")
        if idx + 1 < len(args):
            val = args[idx + 1].lower()
            if val not in ("off", "auto"):
                utf8_print(f"Unknown wrap mode: {_sanitize(val)}")
                utf8_print("Available: off, auto")
                return
            config = load_config()
            config["wrap"] = val
            save_config(config)
            try:
                os.remove(get_cache_path())
            except OSError:
                pass
            if val == "auto":
                utf8_print(f"Wrap: {GREEN}auto{RESET}  (splits at | when line overflows)")
            else:
                utf8_print(f"Wrap: {BOLD}off{RESET}  (truncate, default)")
        else:
            utf8_print("Usage: --wrap <off|auto>")
            utf8_print(f"  {'off':<10} Truncate long lines (default)")
            utf8_print(f"  {'auto':<10} Wrap to 2 lines at | separators when overflow")
        return

    if "--bar-style" in args:
        idx = args.index("--bar-style")
        if idx + 1 < len(args):
            val = args[idx + 1].lower()
            if val not in BAR_STYLES:
                utf8_print(f"Unknown style: {_sanitize(val)}")
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
            _grad_data = BAR_GRADIENT_STYLES.get(val)
            if _grad_data:
                _grad = _grad_data[0]
                n = len(_grad)
                colored = "".join(_grad[n - 1 - i * (n - 1) // 7] for i in range(4))
                dimmed = "".join(_grad[n - 1 - (i + 4) * (n - 1) // 7] for i in range(4))
                demo = f"{GREEN}{colored}{DIM}{dimmed}{RESET}"
            else:
                demo = f"{GREEN}{fill_ch * 4}{DIM}{empty_ch * 4}{RESET}"
            utf8_print(f"Bar style: {BOLD}{val}{RESET}  {demo}")
        else:
            utf8_print(f"Usage: --bar-style <name>\n")
            for name, (fc, ec) in BAR_STYLES.items():
                _grad_data = BAR_GRADIENT_STYLES.get(name)
                if _grad_data:
                    _grad = _grad_data[0]
                    n = len(_grad)
                    colored = "".join(_grad[n - 1 - i * (n - 1) // 7] for i in range(4))
                    dimmed = "".join(_grad[n - 1 - (i + 4) * (n - 1) // 7] for i in range(4))
                    demo = f"{GREEN}{colored}{DIM}{dimmed}{RESET}"
                else:
                    demo = f"{GREEN}{fc * 4}{DIM}{ec * 4}{RESET}"
                utf8_print(f"  {name:<10} {demo}")
        return

    if "--extra-display" in args:
        idx = args.index("--extra-display")
        if idx + 1 < len(args):
            val = args[idx + 1].lower()
            if val not in ("auto", "full", "amount"):
                utf8_print(f"Unknown value: {_sanitize(val)}  (use auto, full, or amount)")
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
                utf8_print(f"Unknown format: {_sanitize(val)}  (use percent or tokens)")
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
                utf8_print(f"Unknown layout: {_sanitize(val)}")
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

    if "--weekly-timer-format" in args:
        idx = args.index("--weekly-timer-format")
        if idx + 1 < len(args):
            val = args[idx + 1].lower()
            if val not in WEEKLY_TIMER_FORMATS:
                utf8_print(f"Unknown format: {_sanitize(val)}")
                utf8_print(f"Available: {', '.join(WEEKLY_TIMER_FORMATS)}")
                return
            config = load_config()
            config["weekly_timer_format"] = val
            save_config(config)
            try:
                os.remove(get_cache_path())
            except OSError:
                pass
            descriptions = {
                "auto": "date when >24h, countdown when <24h",
                "countdown": "always show countdown (2d 5h / 14h 22m)",
                "date": "always show date (Sat 5pm)",
                "full": "both date and countdown (Sat 5pm \u00b7 2d 5h)",
            }
            utf8_print(f"Weekly timer format: {BOLD}{val}{RESET}  ({descriptions[val]})")
        else:
            utf8_print(f"Usage: --weekly-timer-format <mode>\n")
            utf8_print(f"  auto       date when >24h, countdown when <24h (default)")
            utf8_print(f"  countdown  always show countdown: 2d 5h / 14h 22m / 45m")
            utf8_print(f"  date       always show date: Sat 5pm")
            utf8_print(f"  full       both: Sat 5pm \u00b7 2d 5h")
        return

    if "--weekly-timer-prefix" in args:
        idx = args.index("--weekly-timer-prefix")
        if idx + 1 < len(args):
            val = _sanitize(args[idx + 1])[:10]  # strip escapes, max 10 chars
            config = load_config()
            config["weekly_timer_prefix"] = val
            save_config(config)
            try:
                os.remove(get_cache_path())
            except OSError:
                pass
            if val:
                utf8_print(f"Weekly timer prefix: {BOLD}{val}{RESET}")
            else:
                utf8_print(f"Weekly timer prefix: {DIM}(none){RESET}")
        else:
            utf8_print('Usage: --weekly-timer-prefix <text>  (e.g. "R:", "Resets:", "")')
        return

    if "--clock-format" in args:
        idx = args.index("--clock-format")
        if idx + 1 < len(args):
            val = args[idx + 1].lower()
            if val not in CLOCK_FORMATS:
                utf8_print(f"Unknown clock format: {_sanitize(val)}")
                utf8_print(f"Available: {', '.join(CLOCK_FORMATS)}")
                return
            config = load_config()
            config["clock_format"] = val
            save_config(config)
            try:
                os.remove(get_cache_path())
            except OSError:
                pass
            descriptions = {
                "12h": "12-hour with am/pm (Fri 5pm)",
                "24h": "24-hour (Fri 17:00)",
            }
            utf8_print(f"Clock format: {BOLD}{val}{RESET}  ({descriptions[val]})")
        else:
            utf8_print("Usage: --clock-format <mode>\n")
            utf8_print("  12h  12-hour with am/pm: Fri 5pm (default)")
            utf8_print("  24h  24-hour: Fri 17:00")
        return

    if "--stats" in args:
        cmd_stats()
        return

    if "--streak-style" in args:
        idx = args.index("--streak-style")
        if idx + 1 < len(args):
            val = args[idx + 1].lower()
            if val not in ("fire", "text"):
                utf8_print(f"Unknown streak style: {_sanitize(val)}  (use fire or text)")
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

    if "--install-hooks" in args:
        install_hooks()
        return

    if "--hook-refresh" in args:
        idx = args.index("--hook-refresh")
        tool_name = args[idx + 1] if idx + 1 < len(args) else "unknown"
        hook_refresh(tool_name)
        return

    if "--focus" in args:
        idx = args.index("--focus")
        if idx + 1 < len(args):
            action = args[idx + 1].lower()
            minutes = args[idx + 2] if idx + 2 < len(args) and action == "start" else None
            cmd_pomodoro(action, minutes)
        else:
            utf8_print("Usage: --focus start [minutes] | stop | status")
        return

    if "--animation-speed" in args:
        idx = args.index("--animation-speed")
        if idx + 1 < len(args):
            val = args[idx + 1].lower()
            if val not in ANIMATION_SPEEDS:
                utf8_print(f"Unknown speed: {_sanitize(val)}")
                utf8_print(f"Available: {', '.join(ANIMATION_SPEEDS.keys())}")
                return
            config = load_config()
            config["animation_speed"] = val
            save_config(config)
            try:
                os.remove(get_cache_path())
            except OSError:
                pass
            utf8_print(f"Animation speed: {BOLD}{val}{RESET}  ({ANIMATION_SPEEDS[val]}x)")
        else:
            utf8_print("Usage: --animation-speed <slow|normal|fast>")
        return

    if "--peak-hours" in args:
        idx = args.index("--peak-hours")
        if idx + 1 < len(args):
            val = args[idx + 1].lower()
            config = load_config()
            if val in ("off", "false", "no", "0"):
                config["peak_hours"]["enabled"] = False
                save_config(config)
                utf8_print(f"Peak hours: {RED}off{RESET}")
            elif val in ("on", "true", "yes", "1"):
                config["peak_hours"]["enabled"] = True
                save_config(config)
                start = config["peak_hours"]["start"]
                end = config["peak_hours"]["end"]
                utf8_print(f"Peak hours: {GREEN}on{RESET}  ({start} - {end} local time)")
            elif ":" in val or "-" in val:
                # Parse "13:00-19:00" or "13:00" as start with optional end
                parts_str = val.replace(" ", "").split("-")
                start = parts_str[0]
                end = parts_str[1] if len(parts_str) > 1 else args[idx + 2] if idx + 2 < len(args) else None
                if not end:
                    utf8_print("Usage: --peak-hours 13:00-19:00")
                    return
                config["peak_hours"]["enabled"] = True
                config["peak_hours"]["start"] = start
                config["peak_hours"]["end"] = end
                save_config(config)
                utf8_print(f"Peak hours: {GREEN}{start} - {end}{RESET} (local time)")
            else:
                utf8_print("Usage: --peak-hours on|off|HH:MM-HH:MM")
                utf8_print(f"  on              Enable peak indicator")
                utf8_print(f"  off             Disable peak indicator")
                utf8_print(f"  13:00-19:00     Set custom peak window (local time)")
        else:
            config = load_config()
            peak = config.get("peak_hours", {})
            state = f"{GREEN}on{RESET}" if peak.get("enabled") else f"{RED}off{RESET}"
            utf8_print(f"Peak hours: {state}  ({peak.get('start', '13:00')} - {peak.get('end', '19:00')} local time)")
        return

    if "--config" in args:
        cmd_print_config()
        return

    # Normal status line mode
    config = load_config()
    cache_ttl = config.get("cache_ttl_seconds", DEFAULT_CACHE_TTL)
    animate = config.get("animate", "off")

    # Note: _detect_status_bar_conflict() removed — it suppressed all output
    # when leftover npm @anthropic-ai/claude-code files existed on disk,
    # even after migrating to the native installer.

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
    _STDIN_CTX_KEYS = {"model_name", "context_pct", "context_used", "context_limit", "cost_usd", "worktree_branch", "_rate_limits", "lines_added", "lines_removed"}
    stdin_ctx_path = get_state_dir() / "stdin_ctx.json"
    persisted = {}
    try:
        with open(str(stdin_ctx_path), "r", encoding="utf-8") as f:
            raw_persisted = json.load(f)
            persisted = {k: _sanitize(str(v)) if isinstance(v, str) else v for k, v in raw_persisted.items() if k in _STDIN_CTX_KEYS}
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass
    if stdin_ctx:
        persisted.update(stdin_ctx)
        try:
            _atomic_json_write(stdin_ctx_path, persisted, indent=None)
        except OSError:
            pass
    stdin_ctx = persisted

    cache_path = get_cache_path()
    cached = read_cache(cache_path, cache_ttl)

    # --- Stdin rate limits (v2.1.80+): use data from Claude Code directly ---
    # This avoids calling the OAuth API entirely for basic session/weekly bars.
    # The API is only needed for extra credits and per-model caps (opus/sonnet).
    stdin_rl = stdin_ctx.get("_rate_limits")
    if stdin_rl:
        # Build a synthetic usage dict from stdin rate limits
        usage_from_stdin = {}
        if "five_hour" in stdin_rl:
            usage_from_stdin["five_hour"] = stdin_rl["five_hour"]
        if "seven_day" in stdin_rl:
            usage_from_stdin["seven_day"] = stdin_rl["seven_day"]

        # Merge with cached API data for extra/opus/sonnet if available
        has_model_caps = False
        if cached and "usage" in cached:
            for key in ("extra_usage", "seven_day_opus", "seven_day_sonnet"):
                if key in cached["usage"]:
                    usage_from_stdin[key] = cached["usage"][key]
                    has_model_caps = True
            plan_from_cache = cached.get("plan", "")
        else:
            plan_from_cache = ""

        # If no per-model data cached, fetch from API once to populate it
        if not has_model_caps:
            try:
                token, api_plan = get_credentials()
                if token:
                    api_usage = fetch_usage(token)
                    for key in ("extra_usage", "seven_day_opus", "seven_day_sonnet"):
                        if key in api_usage:
                            usage_from_stdin[key] = api_usage[key]
                    if api_plan:
                        plan_from_cache = api_plan
                    write_cache(cache_path, "", usage=api_usage, plan=plan_from_cache)
            except Exception:
                pass

        # Get plan from credentials (lightweight, no API call)
        if not plan_from_cache:
            _, plan_from_cache = get_credentials()
            plan_from_cache = plan_from_cache or ""

        line = build_status_line(usage_from_stdin, plan_from_cache, config, stdin_ctx, cache_age=0)
        _update_session_state(usage_from_stdin, stdin_ctx)
        _append_history(usage_from_stdin)
        if stdin_ctx.get("context_pct") is not None:
            _append_context_history(stdin_ctx["context_pct"])

        # Write to cache so staleness tracking works
        write_cache(cache_path, line, usage_from_stdin, plan_from_cache)

        line = append_update_indicator(line, config)
        line = append_claude_update_indicator(line, config)
        line = _fit_line(line, config)
        sys.stdout.buffer.write((line + RESET + "\n").encode("utf-8"))
        return

    # --- Cached data (no stdin rate limits available) ---
    if cached is not None:
        cache_age = time.time() - cached.get("timestamp", time.time())
        if "usage" in cached:
            line = build_status_line(cached["usage"], cached.get("plan", ""), config, stdin_ctx, cache_age=cache_age)
            _update_session_state(cached["usage"], stdin_ctx)
        else:
            line = cached.get("line", "")
        line = append_update_indicator(line, config)
        line = append_claude_update_indicator(line, config)
        line = _fit_line(line, config)
        sys.stdout.buffer.write((line + RESET + "\n").encode("utf-8"))
        return

    # --- API fallback (first call or no stdin rate limits) ---
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
        line = build_status_line(usage, plan, config, stdin_ctx, cache_age=0)
    except urllib.error.HTTPError as e:
        usage = None
        if e.code == 401:
            new_token, plan = refresh_and_retry(plan)
            if new_token:
                try:
                    usage = fetch_usage(new_token)
                    line = build_status_line(usage, plan, config, stdin_ctx, cache_age=0)
                except Exception:
                    usage = None
                    line = "Token refresh failed \u2014 restart Claude to re-login"
            else:
                line = "Token expired \u2014 restart Claude to refresh"
        elif e.code == 403:
            line = "Access denied \u2014 check your subscription"
        elif e.code == 429:
            stale = _read_stale_cache(cache_path)
            stale_usage = stale.get("usage") if stale else None
            if stale_usage:
                usage = stale_usage
                stale_age = time.time() - stale.get("timestamp", time.time())
                line = build_status_line(usage, stale.get("plan", plan), config, stdin_ctx, cache_age=stale_age)
            else:
                line = "Rate limited \u2014 retrying in 2 min"
                # Write with rate_limited flag so cache uses longer backoff TTL
                write_cache(cache_path, line)
                try:
                    with open(cache_path, "r", encoding="utf-8") as f:
                        rl_data = json.load(f)
                    rl_data["rate_limited"] = True
                    with _secure_open_write(cache_path) as f:
                        json.dump(rl_data, f)
                except (OSError, json.JSONDecodeError):
                    pass
                sys.stdout.buffer.write((line + RESET + "\n").encode("utf-8"))
                return
        else:
            line = f"API error: {e.code}"
    except urllib.error.URLError as e:
        usage = None
        reason = getattr(e, "reason", None)
        is_ssl = False
        try:
            import ssl
            is_ssl = isinstance(reason, ssl.SSLCertVerificationError)
        except (ImportError, AttributeError):
            is_ssl = reason and "CERTIFICATE_VERIFY_FAILED" in str(reason)
        if is_ssl:
            if sys.platform == "darwin":
                line = "SSL cert error \u2014 run: /Applications/Python*/Install\\ Certificates.command"
            else:
                line = "SSL cert error \u2014 check Python SSL certificates"
        else:
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

    if usage is not None:
        write_cache(cache_path, line, usage, plan)
        _append_history(usage)
        _update_heatmap(usage)
        _update_session_state(usage, stdin_ctx)
        if stdin_ctx and stdin_ctx.get("context_pct") is not None:
            _append_context_history(stdin_ctx["context_pct"])
        try:
            stats, milestone = _update_stats()
            if milestone:
                line = line + f" {BRIGHT_YELLOW}{milestone}{RESET}"
        except Exception:
            pass
    else:
        # Cache error lines so we don't hammer the API on every refresh
        write_cache(cache_path, line)
    line = append_update_indicator(line, config)
    line = append_claude_update_indicator(line, config)
    line = _fit_line(line, config)
    sys.stdout.buffer.write((line + RESET + "\n").encode("utf-8"))


if __name__ == "__main__":
    main()
