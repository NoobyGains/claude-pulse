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
- **Extra credits** — auto-shows when Claude gifts you bonus credits (e.g. to try a new model)

No guesswork. No scanning log files. It pulls the **exact same numbers** shown on [claude.ai/settings/usage](https://claude.ai/settings/usage) via Anthropic's OAuth API.

## Quick Start — `/pulse`

Once installed, just type **`/pulse`** in Claude Code. That's it. A guided wizard walks you through picking a theme, text colour, and animation settings — no commands to remember.

```
/pulse          — opens the interactive setup wizard
/pulse show     — preview all themes and text colours
/pulse ocean    — jump straight to a theme by name
/pulse config   — see your current settings
/pulse update   — pull the latest version from GitHub
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

### 10 Built-in Themes

<p align="center">
  <img src="themes.png" alt="All 10 themes" width="700">
</p>

Each theme uses accent colours for text and colour-coded progress bars that shift from **low** → **mid** → **high** based on your usage. The `rainbow` theme is animated — every character cycles through the full spectrum with a white shimmer highlight that sweeps across.

Preview them live in Claude Code with `/pulse show`, or from the command line with `python claude_status.py --show-themes`.

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

Preview all themes and text colours live in Claude Code:
```
/pulse show
```
This renders every theme as a real status line with coloured bars so you can compare them side-by-side. Press **Ctrl+O** to expand the preview.

You can also preview from the command line:
```bash
python claude_status.py --show-themes
python claude_status.py --show-colors
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

### Rainbow Animation on Any Theme

Love the rainbow animation but prefer ocean's or ember's bar colours? **Rainbow mode** applies the flowing rainbow colour effect to any theme:

```bash
# Enable rainbow animation on your current theme
python claude_status.py --rainbow-mode on

# Turn it off (bars use the theme's own colours)
python claude_status.py --rainbow-mode off
```

This is independent of the `rainbow` theme — you can use `--theme ocean --rainbow-mode on` to get ocean bars with rainbow animation.

### Configurable Bar Size

Choose how wide the progress bars appear — small (4 chars), medium (8 chars, default), or large (12 chars):

```bash
python claude_status.py --bar-size small    # ━━━━
python claude_status.py --bar-size medium   # ━━━━━━━━
python claude_status.py --bar-size large    # ━━━━━━━━━━━━
```

The bars automatically clamp to your terminal width so they never wrap to the next line.

### Extra Credits (Auto-detected)

When Claude gifts you bonus credits (e.g. to try a new model), they **automatically appear** on your status line:

```
Session ━━━━━━━━ 5% 4h 07m | Weekly ━━━━━━━━ 6% | Extra ━━━━━━━━ £37.33/£37.00 | Max 20x
```

- **Automatic** — appears when credits are active in your account, no setup needed
- **Hideable** — `--hide extra` to suppress, `--show extra` to bring back
- **Currency** — defaults to `£`, change with `--currency $` or `--currency €`
- **Detailed in config** — `--config` shows credit status, used/limit amounts, and display state

```bash
# Set your currency symbol
python claude_status.py --currency £

# Hide extra credits (even when active)
python claude_status.py --hide extra

# Force show (even when no credits gifted)
python claude_status.py --show extra
```

### Visibility Toggles

Show or hide individual parts of the status line:

```bash
# Hide the timer and plan name
python claude_status.py --hide timer,plan

# Show them again
python claude_status.py --show timer,plan

# See current config
python claude_status.py --config
```

**Available parts:** `session`, `weekly`, `plan`, `timer`, `extra`, `update`

### `/pulse` Slash Command

All the CLI flags below also work as `/pulse` subcommands inside Claude Code:

```
/pulse visibility       — toggle which parts are visible
/pulse hide timer       — hide the reset timer
/pulse show extra       — show extra credits on the status line
/pulse hide extra       — hide extra credits
/pulse currency £       — set your currency symbol
/pulse animate off      — disable shimmer animation
/pulse rainbow-mode on  — enable rainbow animation on any theme
/pulse bar-size large   — set progress bar width
/pulse bar-style block  — set bar character style
/pulse layout compact   — set text layout
/pulse text-color cyan  — set text colour to cyan
/pulse update           — pull the latest version from GitHub
/pulse config           — see your current settings and credit status
```

### Automatic Update Notifications

claude-pulse checks GitHub for new releases once per hour (cached, 3-second timeout). If a newer version is available, a bright yellow `↑ Pulse Update` indicator appears on your status line.

Update right from Claude Code:
```
/pulse update    — pulls the latest version automatically
```

Or from the command line:
```bash
python claude_status.py --update
```

The update check is:
- **Automatic** — no setup needed for git clone installs
- **Silent** — never blocks the status line; skips quietly on network errors
- **Lightweight** — one small GitHub API call per hour, result cached locally
- **Optional** — hide the notification with `--hide update` if you want to stay on your current version

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
  "rainbow_mode": false,
  "animate": true,
  "text_color": "auto",
  "currency": "£",
  "bar_size": "medium",
  "bar_style": "classic",
  "layout": "standard",
  "show": {
    "session": true,
    "weekly": true,
    "plan": true,
    "timer": true,
    "extra": false,
    "update": true
  }
}
```

### CLI Flags

| Flag | Description |
|------|-------------|
| `--install` | Install status line + animation hooks into Claude Code settings |
| `--install-hooks` | Install only the animation hooks (if already have status line) |
| `--show-all` | Preview all themes and text colours with live samples |
| `--themes` | List all available themes with colour previews |
| `--themes-demo` | Preview all themes with simulated status lines |
| `--theme <name>` | Set the active theme |
| `--show <parts>` | Enable comma-separated parts |
| `--hide <parts>` | Disable comma-separated parts |
| `--rainbow-bars on\|off` | Toggle whether rainbow colours the bars or just the text |
| `--rainbow-mode on\|off` | Enable rainbow animation on any theme (default: off) |
| `--animate on\|off` | Toggle the white shimmer animation (default: on) |
| `--text-color <name>` | Set the text colour for labels/percentages (default: auto) |
| `--bar-size <small\|medium\|large>` | Set progress bar width: 4, 8, or 12 chars (default: medium) |
| `--bar-style <name>` | Set bar character style (default: classic) |
| `--layout <name>` | Set text layout (default: standard) |
| `--currency <symbol>` | Set currency symbol for extra credits (default: £) |
| `--update` | Pull the latest version from GitHub (shows changelog) |
| `--config` | Print current configuration summary (includes version, credits, hooks) |

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
| `↑ Pulse Update` showing | Run `/pulse update` in Claude Code, or `python claude_status.py --update` from the command line. To hide the notification: `--hide update` |

## Extra Features

### Bar Styles

Change the visual appearance of the progress bars. The default `classic` style uses thin horizontal lines, but you can switch to thicker or more decorative characters:

| Style | Filled | Empty | Look |
|-------|--------|-------|------|
| `classic` | ━ | ─ | Thin line (default) |
| `block` | █ | ░ | Thick/chunky |
| `shade` | ▓ | ░ | Medium shaded |
| `pipe` | ┃ | ┊ | Vertical segments |
| `dot` | ● | ○ | Round dots |
| `square` | ■ | □ | Filled/hollow squares |
| `star` | ★ | ☆ | Stars |

```bash
# Thin bars (default)
python claude_status.py --bar-style classic

# Thick, chunky bars
python claude_status.py --bar-style block

# Dot-style bars
python claude_status.py --bar-style dot
```

Bar styles work with all themes, sizes, and animations. The shimmer effect automatically skips bar characters regardless of style.

### Text Layouts

Change how labels, bars, and percentages are arranged on the status line:

| Layout | Example |
|--------|---------|
| `standard` | `Session ━━━━━━━━ 42% 3h 12m \| Weekly ━━━━━━━━ 67% \| Max 20x` |
| `compact` | `S ━━━━━━━━ 42% 3h 12m \| W ━━━━━━━━ 67% \| Max 20x` |
| `minimal` | `━━━━━━━━ 42% \| ━━━━━━━━ 67%` |
| `percent-first` | `42% ━━━━━━━━ 3h 12m \| 67% ━━━━━━━━ \| Max 20x` |

```bash
# Single-letter labels — saves space
python claude_status.py --layout compact

# Bars and percentages only — no labels, no plan name
python claude_status.py --layout minimal

# Numbers first, then bars
python claude_status.py --layout percent-first

# Back to default
python claude_status.py --layout standard
```

Layouts work with all themes, bar sizes, bar styles, and animations.

## License

MIT License. See [LICENSE](LICENSE) for details.

---

## Star History

<a href="https://star-history.com/#NoobyGains/claude-pulse&Date">
 <picture>
   <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/svg?repos=NoobyGains/claude-pulse&type=Date&theme=dark" />
   <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/svg?repos=NoobyGains/claude-pulse&type=Date" />
   <img alt="Star History Chart" src="https://api.star-history.com/svg?repos=NoobyGains/claude-pulse&type=Date" />
 </picture>
</a>

---

<p align="center">
  Made by <a href="https://www.reddit.com/user/PigeonDroid/">PigeonDroid</a>
</p>
