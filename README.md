<p align="center">
  <img src="assets/logo.svg" alt="usage-pulse" width="600" />
</p>

<p align="center">
  <strong>Your Claude Code limits, costs, agents and every other AI subscription you pay for. Live, under your prompt, in one line.</strong>
</p>

<p align="center">
  <a href="https://github.com/NoobyGains/usage-pulse/stargazers"><img src="https://img.shields.io/github/stars/NoobyGains/usage-pulse?style=social" alt="GitHub Stars" /></a>
  <img src="https://img.shields.io/github/v/tag/NoobyGains/usage-pulse?label=version&color=blue" alt="Version" />
  <img src="https://img.shields.io/badge/python-3.8+-3776AB?logo=python&logoColor=white" alt="Python 3.8+" />
  <img src="https://img.shields.io/badge/dependencies-zero-brightgreen" alt="Zero Dependencies" />
  <img src="https://img.shields.io/badge/Claude%20Code-v2.1.80+-7C3AED?logo=anthropic&logoColor=white" alt="Claude Code v2.1.80+" />
  <img src="https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey" alt="Platform" />
  <a href="https://github.com/NoobyGains/usage-pulse/blob/main/LICENSE"><img src="https://img.shields.io/github/license/NoobyGains/usage-pulse?color=green" alt="License" /></a>
  <a href="https://buymeacoffee.com/noobygains"><img src="https://img.shields.io/badge/buy%20me%20a%20coffee-donate-FFDD00?logo=buymeacoffee&logoColor=black" alt="Buy Me A Coffee" /></a>
</p>

<p align="center">
  <img src="assets/hero.gif" alt="usage-pulse: this account on the main line, one row each for a second Claude login, Gemini and Codex, all moving as a session runs" width="900" />
</p>

<p align="center">
  <a href="#install">Install</a> ·
  <a href="#every-subscription-one-screen">Providers</a> ·
  <a href="#make-it-yours">Themes</a> ·
  <a href="#48-widgets-pick-your-own">Widgets</a> ·
  <a href="#watch-your-agents-work">Agents</a> ·
  <a href="#full-flag-list">Flags</a> ·
  <a href="#renamed-from-claude-pulse">Renamed from claude-pulse</a>
</p>

---

## Why people install it

**You never hit the wall by surprise.** The 5-hour and weekly bars sit under every prompt with a countdown to the reset, read straight from what Claude Code pipes in. No API key, no polling, no rate limits of its own.

**Every subscription on one screen.** A second Claude account, Codex, Gemini / Antigravity, MiniMax, or anything that can write a JSON file: each gets its own row, in the same theme, and the rows are found for you.

**Costs you can actually compare.** API-equivalent spend per session in your own currency, priced per model for Fable 5.1, Opus 5.5, Sonnet 5.5 and Haiku 5.5, plus budget, rolling 7-day and all-time figures when you want them.

**See your agents work.** How many subagents are live, how many you have spawned against the cap, agent-team task progress, and a row per subagent in Claude Code's agent panel with model, effort, context and elapsed time.

**Looks the way you want.** **10 themes**, **5 animation modes**, **8 bar styles**, five sizes, four layouts, 48 widgets you switch on and off, and a full-screen setup wizard with live previews so you never edit JSON.

**One file. Zero dependencies.** A single Python script, Python 3.8+, Windows, macOS and Linux. Install in a minute, keep it with `--update`.

## Install

Pick one. All three end in the setup wizard, and all three are safe to run again.

**Claude Code plugin**

```
/plugin install usage-pulse --marketplace NoobyGains/usage-pulse
/usage-pulse:setup
```

On Claude Code older than 2.1.275, add the marketplace first: `/plugin marketplace add NoobyGains/usage-pulse`, then `/plugin install usage-pulse`.

A plugin cannot register a status line by itself, so `/usage-pulse:setup` writes it into `settings.json` with safe defaults. Run `/usage-pulse:pulse setup` afterwards to choose hooks, providers, theme and widgets. The plugin ships one `SessionStart` hook that keeps the status line pointing at the current plugin folder across plugin updates; it touches nothing else.

**One line, macOS / Linux / Git Bash**

```bash
curl -fsSL https://raw.githubusercontent.com/NoobyGains/usage-pulse/main/install.sh | bash
```

**One line, Windows PowerShell**

```powershell
irm https://raw.githubusercontent.com/NoobyGains/usage-pulse/main/install.ps1 | iex
```

The installers clone the repo to `~/.usage-pulse` (an install from before the rename stays in `~/.claude-pulse`) and run `--setup`. In a terminal that is the wizard below; piped or in CI (`USAGE_PULSE_NONINTERACTIVE=1`) it takes the defaults. `USAGE_PULSE_DIR` picks another folder.

**By hand**

```bash
git clone https://github.com/NoobyGains/usage-pulse.git ~/.usage-pulse
python3 ~/.usage-pulse/claude_status.py --setup
```

Then restart Claude Code. From then on `/pulse` inside Claude Code changes anything, and `python3 ~/.usage-pulse/claude_status.py --update` brings the next release.

## Two minutes of setup, nothing to edit

<p align="center">
  <img src="assets/wizard.gif" alt="The setup wizard: environment report, hooks, the providers found on this machine, model caps, theme picker, bar style with live preview, widgets, summary" width="900" />
</p>

`python3 claude_status.py --setup` is a full-screen guided setup with 14 screens. Every choice that changes the look has a live preview, nothing is written until you confirm the summary, and Esc anywhere changes nothing. It reports what it found (Python, Claude Code, your config folder, an existing status line it can replace), then walks through hooks, the providers on this machine, per-model caps, theme, bar size, bar style, layout, currency, clock, effort format and widgets. Before it first writes `settings.json` it keeps a copy in `settings-backups/`, five deep.

Inside Claude Code, `/pulse` opens the same choices as a menu: Setup, Look, Widgets, Providers, Hooks and Info. Jump straight to a part with `/pulse setup`, `/pulse providers`, `/pulse hooks`, `/pulse show` to preview every theme, or `/pulse ocean` to set one.

## What's on the bar

```
Session ━━━───────── 27% 2h 53m | Weekly ━━━━━━━━━─── 73% R:Fri 3pm | Context ━━━━──────── 35% | $38.75 | +142 -37 | Opus 5.5 | Effort: XHigh | ⚡fast | main
```

1. **Session**: the 5-hour window, with the time until it resets.
2. **Weekly**: the 7-day window, with the day and time it resets.
3. **Context**: how full the context window is. A `⚠ Context` label appears above 90%, or above 70% while it fills quickly.
4. **Cost**: what this session would cost at API prices, in your currency.
5. **Lines changed**: lines added and removed this session.
6. **Model**, **Effort**, **Fast mode** and **Branch**.

That is the default. Everything on it can be hidden, reordered or swapped for one of the other widgets below.

## Every subscription, one screen

Providers add one status row per *other* subscription under the main line. `--detect-providers` lists what this machine has, and the wizard or `/pulse providers` switches rows on.

| What | Id | Where it is read from |
|---|---|---|
| Other Claude Code accounts | `claude:default`, `claude:<suffix>` (for example `claude:b` for `~/.claude-b`) | Every `~/.claude*` folder that holds a `.credentials.json` |
| Codex CLI | `codex` | Session files under `~/.codex` |
| Google Antigravity (Gemini) | `gemini`, `gemini:<suffix>` | `statusline_last_live.json` under `~/.gemini/antigravity-cli*` |
| MiniMax | `minimax` | The `mmx` CLI on your PATH. Never switched on automatically |
| Anything else | `file:<name>` | A JSON file that any tool can write |

```bash
python3 ~/.usage-pulse/claude_status.py --detect-providers          # what is here
python3 ~/.usage-pulse/claude_status.py --providers enable claude:b,codex
python3 ~/.usage-pulse/claude_status.py --providers label claude:b Work
python3 ~/.usage-pulse/claude_status.py --providers list
```

The sub-commands are `list`, `detect`, `enable`, `disable`, `label`, `remove` and `add-file`. `--detect-providers --json` gives machine-readable output. Labels are 24 characters at most, up to 8 providers can be configured and at most 6 rows are shown.

**How the rows behave**

- Rows use the main line's theme, bar style and size. With `providers_label_main` on (the default) the main line's `Session` label becomes `Claude (<label>) 5h` so everything lines up.
- **Another Claude account** uses that account's own token, read from its `.credentials.json`. It is never refreshed, stored or logged. At most one usage-API call per account every `providers_refresh_seconds` (300 by default, 60 at the lowest), never more than one a minute, with back-off on 429 and a 15-minute pause on 401 or 403. Each window also saves its own account's numbers from stdin, so with both windows open no API call is made at all.
- **Codex and Gemini** rows are read from local files only: the last values seen, never a network call.
- **MiniMax** runs `mmx` to read its quota, which is why it is never on by default, and it is hidden while the window itself runs on MiniMax.
- A row whose data is more than 30 minutes old is drawn dim with a `~` in front of the number, such as `~29%`.

**Your own provider: a JSON file.** `--providers add-file <id> <path> [label]` adds a row read from a file. A ten-line script that polls any other service can feed it. The id is stored as `file:<id>`.

```json
{"label": "Kimi",
 "five_hour": {"used_percentage": 42, "resets_at": 1792386351},
 "seven_day": {"used_percentage": 7,  "resets_at": "2026-10-26T10:00:00Z"}}
```

The two windows may sit at the top level or inside a `rate_limits` object (Claude Code's own shape), `utilization` is accepted for `used_percentage`, `resets_at` may be epoch seconds, epoch milliseconds or ISO 8601, either window may be missing, and the file may be 1 MB at most.

**Multiple Claude accounts.** Claude Code's pattern is one config folder per account, `CLAUDE_CONFIG_DIR=~/.claude-work claude`. Run `--setup` once per account with that variable set:

```bash
CLAUDE_CONFIG_DIR=~/.claude-work python3 ~/.usage-pulse/claude_status.py --setup
```

State that belongs to one account (usage cache, stdin context, history, sessions, heatmap, cost caches) lives in `<state folder>/accounts/<name>-<hash>/`, so two windows on two accounts never overwrite each other. `config.json` stays shared.

## Make it yours

<p align="center">
  <img src="assets/themes.gif" alt="The ten themes: default, ocean, sunset, mono, neon, pride, frost, ember, candy, rainbow" width="900" />
</p>

**10 themes**: default, ocean, sunset, mono, neon, pride, frost, ember, candy and rainbow. `--theme ocean`, `/pulse ocean`, or `--pick-theme` for an arrow-key picker with a live preview. Bars shift from the theme's low colour through mid to high as a window fills.

<p align="center">
  <img src="assets/rainbow.gif" alt="The rainbow animation flowing across the bar" width="900" />
</p>

**5 animation modes** with `--animate <mode>`:

| Mode | Effect |
|---|---|
| `off` | Static, no animation |
| `rainbow` | A flowing rainbow gradient across the whole bar |
| `pulse` | Bars cycle through vivid colours (cyan, blue, purple, pink, gold, green) |
| `glow` | A per-character gradient that shifts across the bar each frame |
| `shift` | A bright highlight that slides across the bar |

`--animation-speed` takes `slow`, `normal` or `fast`. Animation advances on every repaint, including the 2-second `refreshInterval` setup configures while animation is on, so the bar keeps moving while you think.

**8 bar styles** with `--bar-style <name>`: classic, block, shade, pipe, dot, square, star, braille. If Unicode looks wrong in your terminal, `block` is the safe one. **Bar sizes**: small, small-medium, medium, medium-large, large (`--bar-size`).

<p align="center">
  <img src="assets/layouts.gif" alt="The same bar in the standard, compact, minimal and percent-first layouts" width="900" />
</p>

**Layouts** (`--layout`): `standard` has full labels, `compact` one-letter labels, `minimal` no labels, and `percent-first` puts the number before the bar. `--max-width` sets the share of the terminal the bar may use and `--wrap auto` wraps onto a second row instead of cutting the line. For a deliberate two-row split, set `line2_widgets` (these go to row 2) or `line1_widgets` (an allowlist for row 1, the rest flows to row 2) in `config.json`.

## 48 widgets, pick your own

<p align="center">
  <img src="assets/widgets.gif" alt="The bar gaining widgets: repo and session name and cache warmth, then pace and plan and fast mode and thinking, then pull request and files changed and budget" width="900" />
</p>

Switch any of them with `--show` and `--hide`, or tick them in the wizard. Most read fields Claude Code already pipes in, so they cost nothing.

| Id | Default | What it shows |
|---|---|---|
| `session` | on | The 5-hour window as a bar, with percentage |
| `timer` | on | Time until the session window resets |
| `weekly` | on | The 7-day window as a bar |
| `weekly_timer` | on | When the weekly window resets (`--weekly-timer-format`, `--weekly-timer-prefix`) |
| `context` | on | Context window usage, as a percentage or in tokens (`--context-format`) |
| `context_warning` | on | The `⚠ Context` label and a fast-rising arrow as the window fills |
| `cost` | on | Session cost at API prices, in your currency |
| `model` | on | The active model |
| `branch` | on | The current git branch |
| `effort` | on | Reasoning effort, such as `Effort: XHigh` (`--effort-format`) |
| `fast_mode` | on | `⚡fast` while Opus fast mode is on |
| `agent` | on | `▸name` of the active subagent |
| `worktree` | on | The worktree branch, when you work in one |
| `lines` | on | `+142 -37`, lines added and removed this session |
| `subagents` | on | `agents 3 live · 47/200`, needs the [agents hook](#watch-your-agents-work) |
| `team` | on | `team 3 · tasks 4/7`, needs the [team hooks](#watch-your-agents-work) |
| `budget` | on | A spend bar against the amount from `--budget`. Appears once a budget is set |
| `spend_limit` | on | `spend $12.40/$50 wk`, only when a Claude apps gateway reports a spend limit |
| `providers` | on | The extra rows for [other subscriptions](#every-subscription-one-screen) |
| `pomodoro` | on | The focus timer, while one is running (`--focus start 25`) |
| `staleness` | on | `(5m ago)` when the data on screen is old |
| `update` | on | `↑ Pulse Update` when a new usage-pulse release exists |
| `claude_update` | on | `↑ Claude Update` when a new Claude Code release exists |
| `opus`, `sonnet`, `fable` | off | Per-model weekly cap bars. These call the usage API, see [below](#per-model-weekly-caps) |
| `plan` | off | Your plan name |
| `extra` | off | Extra-usage (bonus) credits. Appears by itself if you have any (`--extra-display`) |
| `thinking` | off | `think` or `no-think` |
| `cache` | off | Share of input served from the prompt cache |
| `cache_warm` | off | Prompt-cache warmth, such as `♨ 92% · 3m` |
| `pr` | off | Clickable `#123` pull request badge with review state. GitLab merge requests show as `!123` |
| `repo` | off | `owner/name` of the current repository |
| `session_name` | off | The name you gave the session with `/rename` |
| `weekly_cost` | off | Rolling 7-day API-equivalent cost |
| `cumulative_cost` | off | API-equivalent cost across all sessions |
| `burn_rate` | off | How fast the window is filling, such as `↑3%/hr` |
| `runway` | off | Estimated time until the window is full |
| `sparkline` | off | A small chart of recent session usage |
| `status_message` | off | Replaces the `Session` label with a short message such as `Cruising` |
| `pace` | off | How much of the window's time has passed, next to the bar |
| `streak` | off | Days in a row you have used Claude Code (`--streak-style`) |
| `sessions` | off | `+2 sessions` when other windows are open |
| `git_drift` | off | Commits behind and ahead of upstream |
| `files_changed` | off | Count of uncommitted files |
| `heartbeat` | off | Spinner, tool count and elapsed time. Needs the [heartbeat hook](#watch-your-agents-work) |
| `activity` | off | `⚡ Active` during a burst of tool calls. Needs the heartbeat hook |
| `last_tool` | off | The last tool Claude used. Needs the heartbeat hook |

Order is set by priority numbers: `--priority` lists them, and `--priority model=5,cost=15` moves the model first and the cost after the session. Lower is further left. When a terminal is too narrow, the lowest-priority widgets drop off first.

### Per-model weekly caps

The `opus`, `sonnet` and `fable` bars show your weekly cap for each model, when your plan reports one. Claude Code's own input carries only the 5-hour and 7-day windows, so these three come from the usage API with your Claude Code login, which is why they are opt-in: `--show fable`, or the wizard's model caps screen. Each refresh is one API call, at most every `model_caps_refresh_seconds` (300 by default, 60 at the lowest), and a failed attempt waits 60 seconds. Claude Pro reports no model-scoped windows, so no bar appears there. Contributed by @thedanielmay in PR #53.

### Models and cost

The cost widgets price each turn with the rate that applies to its model:

| Model | Per million tokens (in / out) |
|---|---|
| Fable 5.1 | $10 / $50 |
| Opus 5.5 | $4 / $20 |
| Sonnet 5.5 | $2 / $10 |
| Haiku 5.5 | $0.10 / $0.50 up to 100K prompt tokens, $0.50 / $2.50 above |

All four have a 1M-token context window. Costs are API-equivalent: a figure to compare sessions by, not your bill. `--currency £` converts from USD at a daily exchange rate, and `--budget 25` draws a spend bar against the number you give Claude Code's `--max-budget-usd`, which the status line cannot read by itself.

## Watch your agents work

<p align="center">
  <img src="assets/agents.gif" alt="The live agent counter and the team segment on the bar, and the agent panel rows for three subagents as they run and finish" width="900" />
</p>

Three optional hook groups feed the bar. Install the ones you want with `--install-hooks`, or tick them in the wizard, and restart Claude Code:

```bash
python3 ~/.usage-pulse/claude_status.py --install-hooks                       # all three
python3 ~/.usage-pulse/claude_status.py --install-hooks --only agents,team    # just these
```

| Group | Claude Code events | What it drives | What it costs |
|---|---|---|---|
| `agents` | SubagentStart, SubagentStop | The live agent counter, `agents 3 live · 47/200` | A short Python run when a subagent starts or stops |
| `team` | TeammateIdle, TaskCreated, TaskCompleted | The agent-team segment, `team 3 · tasks 4/7` | A short Python run on each of those events |
| `heartbeat` | PostToolUse | The spinner and tool count, plus `activity` and `last_tool` | A Python run after **every** tool call, and it keeps the repaint timer alive, which is why it is off by default |

The agent panel rows need no hook at all: `--setup` registers `subagentStatusLine`, and Claude Code then asks usage-pulse to draw each subagent's row with its status, model, effort, a context bar and elapsed time. `--limits subagent_spawns=200,subagent_concurrent=20,web_searches=200` sets the denominators, since Claude Code enforces those caps but does not report them.

**Hooks never block Claude.** For the events where exit code 2 would steer Claude Code (SubagentStop, TeammateIdle, TaskCreated, TaskCompleted) the installed command ends in `; exit 0`, so even a moved or deleted script cannot keep a subagent running or refuse a task. `--install-hooks` refuses to touch a `settings.json` that is not valid JSON, and your other hooks are left alone.

**Agent teams** need `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`, and task counts need Claude Code's Task tools, which newer models only get with `CLAUDE_CODE_ENABLE_TODO_TOOLS=1`. The team segment only knows what the three hooks tell it, so it shows how many teammates have appeared rather than how many are busy, a task deleted with `TaskUpdate` stays open, split-pane teammates (tmux, iTerm2) run as separate sessions and do not appear in the lead's segment, and a session's team state is swept after six hours of silence.

## It tells you when there is something new

<p align="center">
  <img src="assets/update.gif" alt="The update indicators: a new usage-pulse release, and a new Claude Code release" width="900" />
</p>

Once an hour the bar checks for a new usage-pulse release and a new Claude Code release and shows `↑ Pulse Update` or `↑ Claude Update` on the right. `--update` pulls the new version into a git install, verifies the commit it got against GitHub, rolls back if they differ, and prints what changed. The hourly check is budgeted to a few seconds and never delays a repaint.

## Configuration

`/pulse` and `--setup` cover everything below. The flags do the same from a shell; the full list is at the end.

```bash
--theme ocean              # default, ocean, sunset, mono, neon, pride, frost, ember, candy, rainbow
--animate rainbow          # off, rainbow, pulse, glow, shift
--bar-size large           # small, small-medium, medium, medium-large, large
--bar-style block          # classic, block, shade, pipe, dot, square, star, braille
--layout compact           # standard, compact, minimal, percent-first
--currency £               # $, £, €, ¥, C$, A$, ₹, kr, and 20+ more
--clock-format 12h         # 12h or 24h
--effort-format labeled    # labeled 'Effort: Medium', full 'Medium', short 'med'
--budget 25                # spend bar; use the number you pass to Claude Code's --max-budget-usd
--show cache,pr            # turn widgets on
--hide cost                # turn a widget off
--preset minimal           # a compact bundle; --preset default is a factory reset
--focus start 25           # focus timer; --focus stop, --focus status
--config                   # print the current configuration
--stats                    # usage statistics and streaks
--heatmap                  # activity heatmap
--update                   # update a git install
```

**Where things live**

| What | Windows | macOS / Linux |
|---|---|---|
| `config.json` | `%LOCALAPPDATA%\claude-status\` | `~/.config/claude-status/` (or `$XDG_CONFIG_HOME`) |
| State and caches | `%LOCALAPPDATA%\claude-status\` | `~/.cache/claude-status/` (or `$XDG_CACHE_HOME`) |
| Settings backups | `<state folder>/settings-backups/` | `<state folder>/settings-backups/` |
| Claude Code's `settings.json` | `$CLAUDE_CONFIG_DIR` or `~/.claude` | `$CLAUDE_CONFIG_DIR` or `~/.claude` |

**`config.json` keys**

| Key | Meaning |
|---|---|
| `theme`, `animate`, `animation_speed`, `text_color` | Colours and animation |
| `bar_size`, `bar_style`, `layout`, `max_width`, `wrap` | Shape of the bars and line |
| `show` | Widget on/off map |
| `widget_priority` | Widget order, for example `{"model": 5}` |
| `line1_widgets`, `line2_widgets` | Two-row split |
| `currency`, `budget_usd`, `limits` | Cost display |
| `clock_format`, `effort_format`, `context_format`, `extra_display`, `streak_style` | Number and time formats |
| `weekly_timer_format`, `weekly_timer_prefix` | The weekly reset timer |
| `providers` | List of `{id, type, enabled, label?, dir or path, bucket?}`. Manage it with `--providers` |
| `providers_label_main` | `true` by default. Names the main line `Claude (<label>) 5h` on the standard layout |
| `providers_refresh_seconds` | Poll interval for other Claude accounts. Default 300, minimum 60 |
| `model_caps_refresh_seconds` | Poll interval for the per-model caps. Default 300, minimum 60 |

**The refresh timer.** Claude Code repaints the status line on its own events (a prompt, a tool call). Anything that moves with the clock, such as animation frames, the focus countdown or the heartbeat's elapsed time, needs a timer as well. Setup writes `statusLine.refreshInterval` into `settings.json` for this: 2 seconds while animating, 15 seconds for time-based widgets, and nothing at all for a static bar. It is kept in sync whenever you change a setting.

## Full flag list

This is the output of `python claude_status.py --help`:

```
usage-pulse 3.5.0 — usage status line for Claude Code

Usage: python claude_status.py [flag [args]]
With no flag and JSON on stdin (how Claude Code runs it) it prints the status line.

Setup
  --setup [--non-interactive]         Guided setup: status line, hooks, providers, theme, widgets
  --install                           Install the status line, agent-panel rows and /pulse (no questions)
  --update                            Update a git install to the latest release
  --help                              Show this list (also -h)

Look
  --theme <name>                      Set the colour theme (see --themes)
  --pick-theme                        Arrow-key theme picker with a live preview
  --pick                              Same as --pick-theme
  --themes                            List themes
  --themes-demo                       Preview the status line in every theme
  --show-themes                       Theme previews in their accent colours
  --show-colors                       List text colours
  --show-all                          --show-themes and --show-colors together
  --text-color <name|auto>            Colour for labels and percentages
  --animate <off|rainbow|pulse|glow|shift>
                                      Bar animation
  --animation-speed <slow|normal|fast>
                                      Animation speed
  --bar-size <small|small-medium|medium|medium-large|large>
                                      Bar width
  --bar-style <name>                  Bar characters (classic, block, dot, braille, ...)
  --layout <standard|compact|minimal|percent-first>
                                      How labels, bars and numbers are arranged
  --max-width <20-100>                Percent of the terminal width to use
  --wrap <off|auto>                   Wrap onto a second row instead of truncating
  --preset <minimal|default>          Apply a bundle of settings (default = factory reset)

Widgets
  --show <parts>                      Turn widgets on (comma-separated)
  --hide <parts>                      Turn widgets off (comma-separated)
  --priority <widget=N,...>           Reorder widgets (lower = further left)
  --currency <symbol>                 Currency for cost widgets (converted from USD)
  --clock-format <12h|24h>            Clock for reset times
  --effort-format <labeled|full|short>
                                      How reasoning effort is written
  --context-format <percent|tokens>   Context window as a percentage or tokens
  --extra-display <auto|full|amount>  How extra-usage credits are shown
  --weekly-timer-format <auto|countdown|date|full>
                                      Weekly reset timer style
  --weekly-timer-prefix <text>        Text before the weekly reset time (e.g. R:)
  --streak-style <fire|text>          Usage streak style
  --budget <amount|off>               Spend budget to match --max-budget-usd
  --limits [key=N,...]                Subagent and web-search caps used as denominators
  --focus <start [min]|stop|status>   Focus (pomodoro) timer

Providers
  --detect-providers [--json]         Find other Claude accounts, Codex, Gemini and MiniMax on this machine
  --providers <list|detect|enable|disable|label|remove|add-file> [...]
                                      Manage the extra status rows: --providers help lists the sub-commands

Hooks
  --install-hooks [--only heartbeat,agents,team]
                                      Install hooks (all three groups unless --only)

Info
  --config                            Print the current configuration
  --stats                             Usage statistics and streaks
  --heatmap                           Usage heatmap
  --debug-stdin                       Save and parse the JSON Claude Code pipes in

Internal
  --subagent-status-line              Agent-panel rows (run by Claude Code)
  --hook-refresh [tool]               PostToolUse hook
  --hook-subagent-start               SubagentStart hook
  --hook-subagent-stop                SubagentStop hook
  --hook-teammate-idle                TeammateIdle hook
  --hook-task-created                 TaskCreated hook
  --hook-task-completed               TaskCompleted hook
  --sync-install-path                 Plugin SessionStart hook: re-point settings.json after a plugin update

Inside Claude Code: /pulse (or /pulse setup) does all of this by asking you.
```

## How it works

```
┌───────────────────────────────────────────────┐
│  Claude Code                                  │
│  Pipes JSON via stdin on every status refresh │
│  (model, context, cost, rate_limits, effort,  │
│   fast_mode, agent, pr, prompt_cache, repo)   │
├───────────────────────────────────────────────┤
│  claude_status.py                             │
│  Reads stdin → builds the ANSI status line    │
│  No API calls for the main bars (v2.1.80+)    │
├───────────────────────────────────────────────┤
│  Hooks (optional)                             │
│  Agents, team, heartbeat: write small state   │
│  files that the next repaint reads            │
├───────────────────────────────────────────────┤
│  Provider rows (optional)                     │
│  Local files for Codex, Gemini, JSON files;   │
│  one cached usage call per other Claude acct  │
├───────────────────────────────────────────────┤
│  Cache layer                                  │
│  Exchange rates (24h) · update checks (1h)    │
│  cumulative + weekly cost (5m) · 429 backoff  │
│  animation state · history                    │
└───────────────────────────────────────────────┘
```

Claude Code sends `rate_limits` on stdin, so the main bars need no OAuth call and cannot be rate limited. The usage API is used for three optional things: extra (bonus) credits, the per-model caps you opted into, and the rows for other Claude accounts when none of their windows is open. A 429 backs off exponentially instead of retrying on every repaint. A truncated or hand-edited cache or settings file degrades to a cache miss instead of blanking the bar.

## Security

- **No API calls for the main usage bars.** They come straight from Claude Code's stdin.
- **Tokens only go to Anthropic.** OAuth tokens are sent only to `api.anthropic.com` (usage) and `platform.claude.com` (renewing your own expired token, kept in memory and never written back). A hardcoded allowlist enforces this, and redirects to any other host are blocked.
- **Other accounts' tokens are read, never changed.** For a provider row the token is read from that account's `.credentials.json` and is never refreshed, stored or logged. Refreshing it would rotate the refresh token and sign that account out.
- **No e-mail addresses or account names are read.** Labels come from your config or from the folder name.
- **Settings are backed up** before usage-pulse first writes `settings.json`, and `--install-hooks` refuses to replace a file that is not valid JSON.
- All file writes are atomic with 0o600 permissions, every piece of external data (provider labels and files included) is stripped of ANSI escapes, hyperlink targets are limited to `http(s)` without control characters, no subprocess uses `shell=True`, and the exchange-rate API (frankfurter.dev) is read-only, unauthenticated and cached for 24 hours.

## Requirements

- **Python 3.8+**, nothing to pip install.
- **Claude Code** v2.1.80+ with a Pro or Max subscription (Fable reporting needs v2.1.170+).
- No API key: it uses Claude Code's existing login.

## Troubleshooting

| Issue | Fix |
|---|---|
| No status line visible | Run `--setup` (or `/usage-pulse:setup` for the plugin) and restart Claude Code |
| Status line vanished after a plugin update | Start a new session: the plugin's `SessionStart` hook re-points `settings.json` at the new version folder. Or run `/usage-pulse:setup` again |
| `--setup` says it used the defaults | It found no interactive terminal. Run it in Windows Terminal, PowerShell or a normal shell, not Git Bash's mintty |
| Setup says `settings.json` is invalid | Fix the JSON it names and run setup again. Nothing was changed |
| Replaced my old status line by mistake | Setup prints the old command. Earlier copies of `settings.json` are in `settings-backups/` in the state folder |
| A provider row is missing | `--providers list` shows what is configured and `--detect-providers` what exists. Check that the `providers` widget is on |
| A Claude or MiniMax row shows `~29%` with dim bars | The data is more than 30 minutes old. Use that account once, or wait for the next refresh |
| A provider row shows `--` | The source could not be read yet: no token, a missing file, or no rate-limit data in the newest Codex session |
| "Rate limited" message | The main bars read stdin, so they keep working. API-backed parts back off before retrying |
| `--update` says it cannot reach GitHub | Both the GitHub API and `git ls-remote` failed. Check the network; the unauthenticated API alone is not needed since 3.4.1 |
| Animation or timer frozen when idle | Run `--setup` again. The real setting is `statusLine.refreshInterval` |
| Opus/Sonnet/Fable bar missing | They are off by default (`--show fable`). They also render only when your plan reports that cap, and Claude Pro returns none |
| Heartbeat not showing | Run `--install-hooks --only heartbeat`, switch the widget on with `--show heartbeat`, and restart Claude Code. It shows after the first tool call |
| Settings error after hook install | Run `/doctor`. Hooks need the nested format `{matcher, hooks: [{type, command}]}` |
| Unicode characters broken | Try `--bar-style block` |

## Renamed from claude-pulse

In October 2026 (3.5.0) the project became **usage-pulse**: Anthropic's plugin directory reserves names that start with `claude-`, and a different "Claude Pulse" is already listed there. The old GitHub address redirects here.

- **Git and one-liner installs** keep working as they are. `--update` and the installers recognise the old origin, and an install in `~/.claude-pulse` stays there.
- **Marketplace installs** need one reinstall: `/plugin uninstall claude-pulse`, then `/plugin marketplace add NoobyGains/usage-pulse` and `/plugin install usage-pulse`. On the next session start the new plugin's hook moves the status line over by itself.
- The script is still `claude_status.py`, `/pulse` keeps its name, the state folder does not move, and the old `CLAUDE_PULSE_*` installer variables still work next to the new `USAGE_PULSE_*` ones.

## Changelog

What changed in each release is in [CHANGELOG.md](CHANGELOG.md).

## Support

If usage-pulse earns its place under your prompt, star the repo, tell someone who lives in Claude Code, or buy me a coffee.

<a href="https://buymeacoffee.com/noobygains"><img src="https://cdn.buymeacoffee.com/buttons/v2/default-yellow.png" alt="Buy Me A Coffee" width="200" /></a>

## Star History

<a href="https://github.com/NoobyGains/usage-pulse/stargazers">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="assets/star-history-dark.svg" />
    <img alt="Star History Chart" src="assets/star-history.svg" width="700" />
  </picture>
</a>

## License

Source Available. See [LICENSE](LICENSE).
