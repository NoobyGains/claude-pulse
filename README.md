<p align="center">
  <img src="assets/logo.svg" alt="claude-pulse logo" width="600" />
</p>

<p align="center">
  Real-time usage monitor for Claude Code — session limits, weekly limits, per-model caps (Opus/Sonnet/Fable), cost tracking, and 10 themes with animations. All in your status bar.
</p>

<p align="center">
  <a href="https://github.com/NoobyGains/claude-pulse/stargazers"><img src="https://img.shields.io/github/stars/NoobyGains/claude-pulse?style=social" alt="GitHub Stars" /></a>
  <img src="https://img.shields.io/github/v/tag/NoobyGains/claude-pulse?label=version&color=blue" alt="Version" />
  <img src="https://img.shields.io/badge/python-3.8+-3776AB?logo=python&logoColor=white" alt="Python 3.8+" />
  <img src="https://img.shields.io/badge/dependencies-zero-brightgreen" alt="Zero Dependencies" />
  <img src="https://img.shields.io/badge/Claude%20Code-v2.1.80+-7C3AED?logo=anthropic&logoColor=white" alt="Claude Code v2.1.80+" />
  <img src="https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey" alt="Platform" />
  <a href="https://github.com/NoobyGains/claude-pulse/blob/main/LICENSE"><img src="https://img.shields.io/github/license/NoobyGains/claude-pulse?color=green" alt="License" /></a>
  <a href="https://buymeacoffee.com/noobygains"><img src="https://img.shields.io/badge/buy%20me%20a%20coffee-donate-FFDD00?logo=buymeacoffee&logoColor=black" alt="Buy Me A Coffee" /></a>
</p>

---

## What is this?

A single-file Python status bar for Claude Code that shows everything you need at a glance — no API key required, zero dependencies, works with your existing Claude Code subscription.

<p align="center">
  <img src="assets/demo.gif" alt="claude-pulse themes demo" width="700" />
  <br>
  <sub>10 built-in themes with colour-coded bars that shift green → yellow → red as usage increases</sub>
</p>

<p align="center">
  <img src="assets/rainbow.gif" alt="Rainbow animation demo" width="700" />
  <br>
  <sub>Rainbow animation — flowing gradient that shifts on every refresh</sub>
</p>

<p align="center">
  <img src="assets/update.gif" alt="Update notification demo" width="700" />
  <br>
  <sub>Automatic update notifications for both claude-pulse and Claude Code</sub>
</p>

```
Session ━━━───────── 27% 2h 53m | Weekly ━━━━━━━━━─── 73% R:Fri 3pm | Fable ━━───────── 18% | Context ━━━━──────── 35% | $38.75 | +142 -37 | Opus 5 | xh | ⚡fast | [\] 320 tools 51m | main
```

## Features

| Feature | Description |
|---|---|
| **Session & Weekly bars** | Colour-coded progress bars (green → yellow → red) for 5-hour session and 7-day weekly limits |
| **Context window** | Live context usage percentage with pressure warnings at 70%/90% |
| **Cost tracking** | Real-time session cost in your local currency (USD, GBP, EUR, + 25 more) with live exchange rates |
| **Per-model weekly caps** | Separate bars for Opus, Sonnet and **Fable** weekly budgets, read from the model-scoped limits the API reports. Shown only when your plan actually reports them |
| **Effort & fast mode** | Reasoning effort (`lo`/`med`/`hi`/`xh`/`max`, colour-escalating) and a **⚡fast** badge when Opus fast mode is active |
| **Subagent & PR** | Active subagent name, plus an opt-in clickable PR badge with review state (OSC 8 hyperlink) |
| **Cache efficiency** | Opt-in indicator for the share of input served from cache — the clearest cost signal on stdin |
| **Two-line layout** | Split widgets across two rows with `line1_widgets` / `line2_widgets` |
| **Live heartbeat** | Spinning indicator with tool count and elapsed time (via PostToolUse hook) |
| **Git branch** | Current branch name always visible |
| **Model display** | Shows which model is active (Fable, Opus, Sonnet, Haiku) |
| **10 themes** | default, ocean, sunset, mono, neon, pride, frost, ember, candy, rainbow |
| **5 animation modes** | off, rainbow, pulse, glow, shift — each visually distinct |
| **8 bar styles** | classic, block, shade, pipe, dot, square, star, braille |
| **Lines changed** | Shows `+42 -7` in green/red — lines added and removed this session, read from stdin |
| **Cumulative cost** | Opt-in widget showing total API-equivalent cost across all sessions (cached, 5-min refresh) |
| **Widget priorities** | Every widget has a priority number — reorder them with `--priority model=5,cost=15` |
| **Focus timer** | Built-in focus timer — `--focus start 25` shows countdown in the status bar |
| **Auto-updates** | Notifies when a new version of claude-pulse or Claude Code is available |
| **Staleness indicator** | Shows data age when cached data is old |
| **Zero API calls** | Reads rate limits directly from Claude Code's stdin (v2.1.80+) — no OAuth, no rate limiting |

## Quick Start

### Plugin marketplace (recommended)

```
/plugin marketplace add NoobyGains/claude-pulse
/plugin install claude-pulse
```

Then run `/pulse` to configure. Restart Claude Code.

### One-liner install

**macOS / Linux:**
```bash
curl -fsSL https://raw.githubusercontent.com/NoobyGains/claude-pulse/main/install.sh | bash
```

**Windows (PowerShell):**
```powershell
irm https://raw.githubusercontent.com/NoobyGains/claude-pulse/main/install.ps1 | iex
```

### Manual install

```bash
git clone https://github.com/NoobyGains/claude-pulse.git ~/.claude-pulse
python3 ~/.claude-pulse/claude_status.py --install
```

Restart Claude Code. That's it.

### Enable the live heartbeat (optional)

The heartbeat shows a tool counter and elapsed time, updated on every tool call:

```bash
python3 ~/.claude-pulse/claude_status.py --install-hooks
```

Restart Claude Code for hooks to take effect.

## Configuration

Use `/pulse` in Claude Code for an interactive setup wizard, or configure directly:

```bash
# Themes
--theme ocean              # ocean, sunset, mono, neon, pride, frost, ember, candy, rainbow

# Animation
--animate rainbow          # rainbow, pulse, glow, shift, off
--animation-speed fast     # slow, normal, fast

# Display
--bar-size large           # small, small-medium, medium, medium-large, large
--bar-style block          # classic, block, shade, pipe, dot, square, star, braille
--layout compact           # standard, compact, minimal, percent-first
--wrap auto                # off (default, truncate) or auto (wrap to 2 lines at | when narrow)

# Two-line layout (config.json) — deliberate split, unlike --wrap's overflow handling.
#   "line2_widgets": ["model", "effort", "branch"]   push these to row 2
#   "line1_widgets": ["session", "weekly"]           allowlist row 1, rest flows to row 2
# line1_widgets wins if both are set.

# Currency (auto-converts USD via live exchange rate)
--currency £               # $, £, €, ¥, C$, A$, ₹, kr, and 20+ more

# Clock
--clock-format 12h         # 12h or 24h

# Widget priority (lower = leftmost)
--priority                 # Show all widget priorities
--priority model=5,cost=15 # Move model first, cost after session

# Toggle features
--show lines               # Show +N/-N lines changed
--show burn_rate           # Show usage velocity (↑3%/hr)
--show git_drift           # Show commits ahead/behind
--show cumulative_cost     # Show total API-equivalent cost across all sessions
--show weekly_cost         # Show rolling 7-day API-equivalent cost
--show cache               # Show % of input served from cache (cost signal)
--show pr                  # Show clickable PR badge + review state
--show thinking            # Show whether extended thinking is on
--show files_changed       # Show modified file count
--show last_tool           # Show last tool Claude used
--hide cost                # Hide cost ticker
--hide heartbeat           # Hide tool counter
--hide fable               # Hide the Fable weekly cap bar
--hide fast_mode           # Hide the ⚡fast badge
--hide agent               # Hide the active subagent name

# Focus timer
--focus start 25        # Start a 25-minute focus timer
--focus stop            # Stop the timer
--focus status          # Check remaining time

# Info
--config                   # Show current configuration
--stats                    # Show session statistics
--heatmap                  # Show activity heatmap
--update                   # Update to latest version
```

## How It Works

```
┌───────────────────────────────────────────────┐
│  Claude Code                                  │
│  Pipes JSON via stdin on every status refresh │
│  (model, context, cost, rate_limits, effort,  │
│   fast_mode, agent, pr, version)              │
├───────────────────────────────────────────────┤
│  claude_status.py                             │
│  Reads stdin → builds ANSI status line        │
│  No API calls needed (v2.1.80+)               │
├───────────────────────────────────────────────┤
│  PostToolUse Hook (optional)                  │
│  Updates tool count, heartbeat, git branch    │
│  on every tool call                           │
├───────────────────────────────────────────────┤
│  Cache Layer                                  │
│  Exchange rates (24h) · update checks (1h)    │
│  cumulative + weekly cost (5m) · hook (5m)    │
│  429 backoff · animation state · history      │
└───────────────────────────────────────────────┘
```

**Data flow:** Claude Code sends session JSON via stdin → claude-pulse reads rate limits directly (no API) → renders colourised ANSI status line → Claude Code displays it.

**Rate limits from stdin (v2.1.80+):** Claude Code sends `rate_limits` on stdin — the 5-hour and 7-day windows plus the model-scoped weekly caps (`seven_day_opus`, `seven_day_sonnet`, `seven_day_fable`). claude-pulse reads all of them straight from stdin, so no OAuth call is needed for the bars. The API is only consulted for extra/bonus credits, which stdin doesn't carry, and a 429 there now backs off exponentially instead of retrying on every repaint.

**Refresh cadence:** Claude Code repaints on its own events (prompt, tool use), which covers anything derived from stdin. Content that moves with the clock — animation frames, the focus countdown, the heartbeat's elapsed time — also needs a timer, so `--install` sets `statusLine.refreshInterval` (2s when animating, 15s for time-based widgets, omitted entirely for a static bar). It is re-synced automatically whenever you change a setting.

**PostToolUse hook:** When installed, the hook fires on every tool call (Read, Edit, Bash, etc.), updating the heartbeat counter and git branch. The status line refreshes on each tool call, making the spinner animate during active work.

## Themes

<p align="center">
  <img src="themes.png" alt="All 10 themes" width="700" />
</p>

10 built-in themes with colour-coded bars that shift as usage increases. Set with `--theme <name>` or `/pulse <name>`.

## Animation Modes

| Mode | Effect |
|---|---|
| `off` | Static, no animation |
| `rainbow` | Flowing rainbow gradient across the entire bar |
| `pulse` | Bars cycle through vivid colours (cyan → blue → purple → pink → gold → green) |
| `glow` | Per-character gradient that shifts across the bar each frame |
| `shift` | Bright highlight slides across the bar |

Set with `--animate <mode>`. Animation advances on every repaint — Claude Code's own events plus the 2-second `refreshInterval` that `--install` configures while animation is on, so the bar keeps moving even while the session is idle.

## Requirements

- **Python 3.8+** (no pip installs needed)
- **Claude Code** v2.1.80+ with a Pro or Max subscription (Fable reporting needs v2.1.170+)
- No API key required — uses Claude Code's existing credentials

## Security

- **No API calls for usage data** — reads rate limits directly from Claude Code's stdin (v2.1.80+)
- OAuth tokens only used as fallback for extra credits/per-model caps, sent only to `api.anthropic.com` (hardcoded allowlist)
- All file writes use atomic operations with 0o600 permissions
- ANSI escape injection prevention on all external data
- Hyperlink targets (PR badge) restricted to `http(s)` and rejected if they contain control characters, so nothing can break out of the OSC 8 escape
- No `shell=True` in any subprocess call
- Exchange rate API (frankfurter.app) — no auth, read-only, cached 24h

## Troubleshooting

| Issue | Fix |
|---|---|
| No status line visible | Run `--install` then restart Claude Code |
| "Rate limited" message | v3.0.0+ reads limits from stdin, so the bars keep working. v3.2.0+ also backs off exponentially before retrying the API |
| Animation/timer frozen when idle | Re-run `--install` on v3.2.0+. Earlier versions wrote a `refresh` key that Claude Code ignores; the real setting is `refreshInterval` |
| Opus/Sonnet/Fable bar missing | Those bars render only when your plan reports that cap. Claude Pro returns `null` for the model-scoped windows |
| Heartbeat not showing | Run `--install-hooks` then restart Claude Code. Shows after first tool call |
| Heartbeat appears/disappears | Normal — shows when hook state is fresh (within 5 min of last tool call) |
| Settings error after hook install | Run `/doctor` — hooks need nested format: `{matcher, hooks: [{type, command}]}` |
| Stale data showing | Data refreshes on every interaction. If idle, it shows the last known state |
| Unicode characters broken | Try `--bar-style block` for better Windows terminal support |

## Support

If this project helped you, consider starring the repo, sharing it with others, or buying me a coffee.

<a href="https://buymeacoffee.com/noobygains"><img src="https://cdn.buymeacoffee.com/buttons/v2/default-yellow.png" alt="Buy Me A Coffee" width="200" /></a>

## Star History

<a href="https://star-history.com/#NoobyGains/claude-pulse&Date">
   <picture>
     <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/svg?repos=NoobyGains/claude-pulse&type=Date&theme=dark" />
     <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/svg?repos=NoobyGains/claude-pulse&type=Date" />
     <img alt="Star History Chart" src="https://api.star-history.com/svg?repos=NoobyGains/claude-pulse&type=Date" width="700" />
   </picture>
</a>

## License

MIT — see [LICENSE](LICENSE) for details.

---

<p align="center">
  Made by <a href="https://github.com/NoobyGains">NoobyGains</a> · <a href="https://www.reddit.com/user/PigeonDroid/">PigeonDroid</a>
</p>
