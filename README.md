<p align="center">
  <h1 align="center">claude-pulse</h1>
  <p align="center">A real-time usage monitor for Claude Code — see your limits at a glance.</p>
</p>

<p align="center">
  <img src="screenshot.png" alt="claude-pulse in action" width="700">
</p>

<p align="center">
  <img src="rainbow.png" alt="Rainbow theme" width="500">
  <br>
  <sub>Rainbow theme — animated colours that shift while Claude is writing, with a white shimmer sweep</sub>
</p>

---

## What is this?

**claude-pulse** adds a live status bar to the bottom of your Claude Code CLI window showing:

- **Session usage** — how much of your current 5-hour block you've used
- **Time remaining** — countdown until your session resets
- **Weekly usage** — your 7-day rolling usage across all models
- **Plan tier** — auto-detected (Pro, Max 5x, Max 20x)
- **Extra usage** — optional bonus/overflow credit tracking

No guesswork. No scanning log files. It pulls the **exact same numbers** shown on [claude.ai/settings/usage](https://claude.ai/settings/usage) via Anthropic's OAuth API.

## Quick Start — `/pulse`

Once installed, just type **`/pulse`** in Claude Code. That's it. A guided wizard walks you through picking a theme, text colour, and animation settings — no commands to remember.

```
/pulse          — opens the interactive setup wizard
/pulse ocean    — jump straight to a theme by name
/pulse config   — see your current settings
```

Everything below can also be configured via `/pulse` — the CLI flags are there if you prefer them.

---

## Features

### Colour-coded progress bars

The bars change colour based on your usage level so you can tell at a glance how close you are to your limits:

| Usage | Colour | Meaning |
|-------|--------|---------|
| 0–49% | Green | Plenty of headroom |
| 50–79% | Yellow | Getting warm |
| 80%+ | Red | Close to the limit |

### 7 Built-in Themes

| Theme | Preview | Style |
|-------|---------|-------|
| `default` | ![](https://img.shields.io/badge/%E2%94%81%E2%94%81%E2%94%81%E2%94%81-2ea043?style=flat-square) ![](https://img.shields.io/badge/%E2%94%81%E2%94%81%E2%94%81%E2%94%81-d29922?style=flat-square) ![](https://img.shields.io/badge/%E2%94%81%E2%94%81%E2%94%81-cf222e?style=flat-square) | Classic traffic-light |
| `ocean` | ![](https://img.shields.io/badge/%E2%94%81%E2%94%81%E2%94%81%E2%94%81-0891b2?style=flat-square) ![](https://img.shields.io/badge/%E2%94%81%E2%94%81%E2%94%81%E2%94%81-2563eb?style=flat-square) ![](https://img.shields.io/badge/%E2%94%81%E2%94%81%E2%94%81-a855f7?style=flat-square) | Cool tones |
| `sunset` | ![](https://img.shields.io/badge/%E2%94%81%E2%94%81%E2%94%81%E2%94%81-d29922?style=flat-square) ![](https://img.shields.io/badge/%E2%94%81%E2%94%81%E2%94%81%E2%94%81-ea580c?style=flat-square) ![](https://img.shields.io/badge/%E2%94%81%E2%94%81%E2%94%81-cf222e?style=flat-square) | Warm tones |
| `mono` | ![](https://img.shields.io/badge/%E2%94%81%E2%94%81%E2%94%81%E2%94%81-6e7681?style=flat-square) ![](https://img.shields.io/badge/%E2%94%81%E2%94%81%E2%94%81%E2%94%81-8b949e?style=flat-square) ![](https://img.shields.io/badge/%E2%94%81%E2%94%81%E2%94%81-c9d1d9?style=flat-square) | Brightness only |
| `neon` | ![](https://img.shields.io/badge/%E2%94%81%E2%94%81%E2%94%81%E2%94%81-3fb950?style=flat-square) ![](https://img.shields.io/badge/%E2%94%81%E2%94%81%E2%94%81%E2%94%81-f0e040?style=flat-square) ![](https://img.shields.io/badge/%E2%94%81%E2%94%81%E2%94%81-f85149?style=flat-square) | Vivid/bold |
| `pride` | ![](https://img.shields.io/badge/%E2%94%81%E2%94%81%E2%94%81%E2%94%81-af5fff?style=flat-square) ![](https://img.shields.io/badge/%E2%94%81%E2%94%81%E2%94%81%E2%94%81-00ffaf?style=flat-square) ![](https://img.shields.io/badge/%E2%94%81%E2%94%81%E2%94%81-ff00af?style=flat-square) | Violet, green & pink |
| `frost` | ![](https://img.shields.io/badge/%E2%94%81%E2%94%81%E2%94%81%E2%94%81-87ceeb?style=flat-square) ![](https://img.shields.io/badge/%E2%94%81%E2%94%81%E2%94%81%E2%94%81-5fafff?style=flat-square) ![](https://img.shields.io/badge/%E2%94%81%E2%94%81%E2%94%81-ffffff?style=flat-square) | Icy blue to white |
| `ember` | ![](https://img.shields.io/badge/%E2%94%81%E2%94%81%E2%94%81%E2%94%81-ffd700?style=flat-square) ![](https://img.shields.io/badge/%E2%94%81%E2%94%81%E2%94%81%E2%94%81-ff5f00?style=flat-square) ![](https://img.shields.io/badge/%E2%94%81%E2%94%81%E2%94%81-ff3333?style=flat-square) | Gold to hot red |
| `candy` | ![](https://img.shields.io/badge/%E2%94%81%E2%94%81%E2%94%81%E2%94%81-ff87d7?style=flat-square) ![](https://img.shields.io/badge/%E2%94%81%E2%94%81%E2%94%81%E2%94%81-af87ff?style=flat-square) ![](https://img.shields.io/badge/%E2%94%81%E2%94%81%E2%94%81-00ffff?style=flat-square) | Pink, purple & cyan |
| `rainbow` | ![](https://img.shields.io/badge/%E2%94%81-ff0000?style=flat-square) ![](https://img.shields.io/badge/%E2%94%81-ff8800?style=flat-square) ![](https://img.shields.io/badge/%E2%94%81-ffff00?style=flat-square) ![](https://img.shields.io/badge/%E2%94%81-00cc00?style=flat-square) ![](https://img.shields.io/badge/%E2%94%81-0088ff?style=flat-square) ![](https://img.shields.io/badge/%E2%94%81-8800ff?style=flat-square) | Animated rainbow shimmer |

Each preview shows **low** → **mid** → **high** usage colours as they appear on your status bar. The `rainbow` theme is animated — every character cycles through the full spectrum with a white shimmer highlight that sweeps across, like the Claude loading animation.

### White Shimmer Animation

All themes support a white shimmer effect — a bright highlight that sweeps across the text while Claude is writing. The shimmer:

- **Only affects text** — labels, percentages and separators shimmer; progress bars keep their colour-coded meaning
- **Hooks into Claude's lifecycle** — animates when Claude is writing, cleanly reverts to static when idle (no frozen shimmer artifacts)
- **Fast and clean** — wide 20-character highlight band sweeps every 2.5 seconds, bright white (RGB 210-255) that's always visible against the text

The shimmer is **on by default**. Toggle it:
```bash
# Disable shimmer animation
python claude_status.py --animate off

# Re-enable shimmer animation
python claude_status.py --animate on
```

### Animation Lifecycle Hooks

The `--install` command automatically sets up Claude Code hooks so the animation knows when to start and stop:

- **`UserPromptSubmit`** hook — flags that Claude is processing (animation starts)
- **`Stop`** hook — clears the flag (animation stops, clean static display)

This means:
- While Claude is **writing** → rainbow shifts, shimmer sweeps
- While Claude is **idle** → clean static colours, no frozen animation artifacts
- **Backwards compatible** — without hooks, animation runs on every render (old behaviour)

The hooks are installed automatically with `--install`. To add them separately:
```bash
python claude_status.py --install-hooks
```

### Text Colour

The labels and percentages outside the progress bars (e.g. "Session", "35%", "|") use a contrasting colour so the shimmer is clearly visible against the bars:

```bash
# Use the theme's recommended colour (default)
python claude_status.py --text-color auto

# Pick a specific colour
python claude_status.py --text-color cyan
python claude_status.py --text-color magenta
```

**Available colours:** `auto`, `white`, `bright_white`, `cyan`, `blue`, `green`, `yellow`, `magenta`, `red`, `orange`, `violet`, `pink`, `dim`, `default`, `none`

| Theme | Default text colour | Why |
|-------|-------------------|-----|
| `default` | white | Contrasts with green/yellow/red bars |
| `ocean` | white | Contrasts with cyan/blue/magenta bars |
| `sunset` | white | Contrasts with yellow/orange/red bars |
| `neon` | white | Contrasts with bright green/yellow/red bars |
| `pride` | white | Contrasts with violet/green/pink bars |
| `frost` | white | Contrasts with icy blue/steel bars |
| `ember` | white | Contrasts with gold/orange/red bars |
| `candy` | white | Contrasts with pink/purple/cyan bars |
| `mono` | dim | Subtle contrast with white/bright bars |
| `rainbow` | none | Rainbow handles its own colouring |

Preview all themes in your terminal:
```bash
python claude_status.py --themes
```

Set a theme:
```bash
python claude_status.py --theme ocean
```

When using `rainbow`, you can choose whether the bars also get rainbow colours or keep their normal usage-based colours (green/yellow/red):
```bash
# Rainbow text only — bars stay green/yellow/red
python claude_status.py --rainbow-bars off

# Rainbow everything including bars (default)
python claude_status.py --rainbow-bars on
```

### Visibility Toggles

Show or hide individual parts of the status line:

```bash
# Hide the timer and plan name
python claude_status.py --hide timer,plan

# Show them again
python claude_status.py --show timer,plan

# Enable extra usage tracking (off by default)
python claude_status.py --show extra

# See current config
python claude_status.py --config
```

**Available parts:** `session`, `weekly`, `plan`, `timer`, `extra`

### `/pulse` Slash Command

All the CLI flags below also work as `/pulse` subcommands inside Claude Code:

```
/pulse visibility      — toggle which parts are visible
/pulse hide timer      — hide the reset timer
/pulse show extra      — enable extra usage display
/pulse animate off     — disable shimmer animation
/pulse text-color cyan — set text colour to cyan
```

### Automatic Update Notifications

claude-pulse checks GitHub for new releases once per hour (cached, 3-second timeout). If a newer version is available, a subtle `↑ update` indicator appears on your status line. Run `git pull` to update.

The update check is:
- **Automatic** — no setup needed for git clone installs
- **Silent** — never blocks the status line; skips quietly on network errors
- **Lightweight** — one small GitHub API call per hour, result cached locally

### Lightweight and fast

- **Single Python file** — no dependencies, no pip install, just Python 3.6+
- **30-second cache** — API is only called once every 30 seconds, cached responses return instantly
- **Zero config needed** — auto-detects your plan and credentials from Claude Code

### Auto-detected plan

Reads your subscription tier directly from Claude Code's credentials file. Supports:
- **Pro** — standard plan
- **Max 5x** — 5x Pro usage
- **Max 20x** — 20x Pro usage

If you upgrade your plan, just restart Claude Code and it picks up the new tier automatically.

## Installation

### 1. Clone the repo

```bash
git clone https://github.com/NoobyGains/claude-pulse.git
cd claude-pulse
```

### 2. Install the status line

```bash
python claude_status.py --install
```

This adds the status line **and** animation lifecycle hooks to your `~/.claude/settings.json` automatically.

### 3. Restart Claude Code

Close and reopen Claude Code. The status bar appears at the bottom of your terminal.

That's it. No virtual environments, no dependencies, no build steps.

### 4. (Optional) Install the slash command

Copy the pulse command file to your Claude Code commands directory:

```bash
# Linux/Mac
cp pulse.md ~/.claude/commands/pulse.md

# Windows
copy pulse.md %USERPROFILE%\.claude\commands\pulse.md
```

Now you can use `/pulse` inside Claude Code to configure themes and visibility.

## How it works

```
Claude Code starts
    ↓
Calls claude_status.py (passes session JSON via stdin)
    ↓
Check cache (~30s TTL)
    ├── Fresh? → Re-render with current animation state
    └── Stale? → Read OAuth token from ~/.claude/.credentials.json
                     ↓
                 GET https://api.anthropic.com/api/oauth/usage
                     ↓
                 Format status line with coloured bars
                     ↓
                 Cache result, print to stdout

Animation hooks (automatic):
    UserPromptSubmit → set "processing" flag  → animation ON
    Stop             → clear flag             → animation OFF (clean static)
```

The status line updates whenever Claude Code's conversation updates (roughly every 300ms), but the API is only hit once every 30 seconds to keep things fast and respectful.

## Configuration

Edit `config.json` directly or use the CLI flags:

```json
{
  "cache_ttl_seconds": 30,
  "theme": "default",
  "rainbow_bars": true,
  "animate": true,
  "text_color": "auto",
  "show": {
    "session": true,
    "weekly": true,
    "plan": true,
    "timer": true,
    "extra": false
  }
}
```

### CLI Flags

| Flag | Description |
|------|-------------|
| `--install` | Install status line + animation hooks into Claude Code settings |
| `--install-hooks` | Install only the animation hooks (if already have status line) |
| `--themes` | List all available themes with colour previews |
| `--themes-demo` | Preview all themes with simulated status lines |
| `--theme <name>` | Set the active theme |
| `--show <parts>` | Enable comma-separated parts |
| `--hide <parts>` | Disable comma-separated parts |
| `--rainbow-bars on\|off` | Toggle whether rainbow colours the bars or just the text |
| `--animate on\|off` | Toggle the white shimmer animation (default: on) |
| `--text-color <name>` | Set the text colour for labels/percentages (default: auto) |
| `--config` | Print current configuration summary (includes hook/update status) |

Lower cache TTL values = more frequent API calls. Higher values = faster response but slightly staler data. Default of 30 seconds is a good balance.

## Requirements

- **Python 3.6+** (no external packages)
- **Claude Code** with an active Pro or Max subscription
- **Windows, macOS, or Linux**

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Status line doesn't appear | Run `python claude_status.py --install` and restart Claude Code |
| Shows "No credentials found" | Make sure you're logged in to Claude Code (`claude /login`) |
| Shows wrong plan tier after upgrading | Log out (`claude /logout`) then log back in (`claude /login`) — your OAuth token needs to refresh to pick up the new subscription tier |
| Stale percentages | Delete the cache: `~/.cache/claude-status/cache.json` (Linux/Mac) or `%LOCALAPPDATA%\claude-status\cache.json` (Windows) |
| Theme not applying | Clear the cache file after changing themes so the next render uses the new colours |
| Animation doesn't stop when idle | Run `python claude_status.py --install` to install the lifecycle hooks, then restart Claude Code |
| `↑ update` showing | Run `git pull` in the claude-pulse directory to get the latest version |

## License

MIT License. See [LICENSE](LICENSE) for details.

---

<p align="center">
  Made by <a href="https://www.reddit.com/user/PigeonDroid/">PigeonDroid</a>
</p>
