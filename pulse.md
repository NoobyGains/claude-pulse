Configure your Claude status bars — themes, colours, animations, widgets, and more. $ARGUMENTS

---

**Finding the script:** Before running any command below, you need the full path to `claude_status.py`. Do this ONCE at the start:

1. Read `~/.claude/settings.json`. If `statusLine.command` contains `claude_status.py`, extract the full script path from that string.
2. If not found, use the Glob tool to search for `**/claude_status.py` inside `~/.claude/plugins/` — pick the result containing `claude-pulse`.
3. If neither works, tell the user: "Run `/claude-pulse:setup` first to install the status bar."

Save the found path as SCRIPT_PATH. Use `python "SCRIPT_PATH"` for all commands below.

---

## ROUTING — decide what to do based on $ARGUMENTS

### Direct commands (skip the menu, run immediately):

If $ARGUMENTS matches a **theme name** (`default`, `ocean`, `sunset`, `mono`, `neon`, `pride`, `frost`, `ember`, `candy`, `rainbow`):
-> Run `python "SCRIPT_PATH" --theme <name>` directly, no menu.
-> Confirm: "Theme set to **<name>**. The status line will update on the next refresh."

If $ARGUMENTS is `pick`, `picker`, or `pick-theme`:
-> This is the **live arrow-key theme picker**: one screen, scroll through all 10 themes, and the status-bar preview recolours live. It needs an interactive terminal, so the **user must launch it themselves** — you cannot drive the keypresses for them.
-> Tell the user to type this in their prompt to launch it:
   `!python "SCRIPT_PATH" --pick-theme`
-> Explain the controls in one line: "↑/↓ (or j/k) to move · Enter to keep · Esc to cancel — your bar recolours live as you move."
-> Add the fallback note: "If you see a static coloured list instead of a moving cursor, this terminal isn't interactive here — just note the name you like and run `/pulse <name>`."

If $ARGUMENTS is `config` or `settings`:
-> Run `python "SCRIPT_PATH" --config` silently.
-> Summarise the settings in your response text (don't show raw ANSI output).

If $ARGUMENTS is exactly `show` (no parts after it), or `show all`, or `colors`, or `colours`, or `preview`:
-> Run TWO separate Bash commands (in parallel):
   1. `python "SCRIPT_PATH" --show-themes`
   2. `python "SCRIPT_PATH" --show-colors`
-> Show the raw output to the user (coloured ANSI text with live previews).
-> After both commands, say ONLY: "Press **Ctrl+O** to expand and see the colours."

If $ARGUMENTS contains `hide <parts>` or `show <parts>` (with specific parts):
-> Run the corresponding `--hide` or `--show` command directly.
-> Valid parts: session, weekly, context, timer, weekly_timer, cost, model, branch, heartbeat, activity, update, claude_update, opus, sonnet, effort, worktree, pomodoro, context_warning, staleness, plan, extra, burn_rate, sessions, last_tool, sparkline, runway, status_message, streak, pace, git_drift, files_changed

If $ARGUMENTS matches `animate <mode>` (where mode is `off`, `rainbow`, `pulse`, `glow`, `shift`, `on`):
-> Run `--animate <mode>` directly.
-> Explain what the mode does:
  - **off** — Static, no animation
  - **rainbow** — Flowing rainbow gradient across the entire bar
  - **pulse** — Bars cycle through vivid colours each refresh
  - **glow** — Per-character gradient that shifts across the bar
  - **shift** — Bright highlight slides across the bar

If $ARGUMENTS matches `text-color <name>` or `text-colour <name>`:
-> Run `--text-color <name>` directly.

If $ARGUMENTS matches `currency <symbol>` (e.g. `currency £`, `currency €`, `currency $`):
-> Run `--currency <symbol>` directly.
-> Explain: cost is auto-converted from USD using a live exchange rate (cached 24h).

If $ARGUMENTS matches `bar-size <size>`:
-> Run `--bar-size <size>` directly.

If $ARGUMENTS matches `bar-style <name>` or `style <name>`:
-> Run `--bar-style <name>` directly.

If $ARGUMENTS matches `layout <name>`:
-> Run `--layout <name>` directly.

If $ARGUMENTS matches `animation-speed <speed>` or `speed <speed>`:
-> Run `--animation-speed <speed>` directly.

If $ARGUMENTS matches `focus start [minutes]` or `focus stop` or `focus status`:
-> Run `--focus <action> [minutes]` directly.
-> Default is 25 minutes if no duration given.

If $ARGUMENTS matches `budget <amount|off>`:
-> Run `--budget <value>` directly. Explain it mirrors Claude Code's `--max-budget-usd`,
   which is CLI-only and cannot be read automatically.

If $ARGUMENTS matches `limits` or `limits <k>=<v>,...`:
-> Run `--limits <value>` directly. Keys: subagent_spawns, subagent_concurrent, web_searches.

If $ARGUMENTS matches `effort-format <value>`:
-> Run `--effort-format <value>` directly.
-> Values: `labeled` (default, "Effort: Medium"), `full` ("Medium"), `short` ("med")

If $ARGUMENTS matches `clock <format>` (where format is `12h` or `24h`):
-> Run `--clock-format <format>` directly.

If $ARGUMENTS matches `preset <name>` or `minimal` or `default preset`:
-> Run the corresponding `--preset` command.

If $ARGUMENTS is `update`:
-> Run `python "SCRIPT_PATH" --update` and show the output.

If $ARGUMENTS is `hooks` or `install-hooks`:
-> Run `python "SCRIPT_PATH" --install-hooks` and show the output.
-> Remind user to restart Claude Code.

If $ARGUMENTS is `stats`:
-> Run `python "SCRIPT_PATH" --stats` and show the output.

If $ARGUMENTS is `heatmap`:
-> Run `python "SCRIPT_PATH" --heatmap` and show the output.

### Interactive menu (when $ARGUMENTS is empty, `themes`, `theme`, or `menu`):

**Step 0 — Quick tips:**

> **Quick commands:** `/pulse show` preview all themes · `/pulse ocean` set a theme · `/pulse config` see settings · `/pulse update` check for updates · `/pulse focus start` start a focus timer

Run `python "SCRIPT_PATH" --config` silently to check for updates.

**Step 1:** Run `python "SCRIPT_PATH" --themes-demo` and show the output.

**Step 2:** Theme — offer the **live picker** first.

Say: "For the best experience, launch the live picker — type  `!python "SCRIPT_PATH" --pick-theme`  in your prompt. Arrow keys move through all 10 themes, your bar recolours live, Enter keeps it, Esc cancels. (If it shows a static list instead of a moving cursor, this terminal isn't interactive — use the quick picker below.)"

If the user would rather pick from a list right here (or the live picker isn't available in their terminal), use the paginated picker below.

Theme picker (paginated as 3 pages):

Page 1:
```
Question: "Pick a theme from the preview above"
Options:
  - "rainbow" — "Full-spectrum flowing colours"
  - "default" — "Classic green → yellow → red"
  - "ocean" — "Cool cyan → blue → magenta"
  - "More themes..." — "See all 10 themes"
```

Page 2 (if "More themes..."):
```
Options:
  - "frost" — "Icy blue → steel → white"
  - "ember" — "Gold → hot orange → red"
  - "candy" — "Pink → purple → cyan"
  - "More themes..." — "See neon, sunset, pride, mono"
```

Page 3 (if "More themes..." again):
```
Options:
  - "neon" — "Vivid bright green → yellow → red"
  - "sunset" — "Warm yellow → orange → red"
  - "pride" — "Violet → green → pink"
  - "mono" — "White → white → bright white"
```

Apply with `--theme <name>`.

**Step 3:** Text colour (skip for rainbow):

Theme-specific recommendations: ocean→cyan, sunset/ember→yellow, frost→cyan, candy→pink, neon→green, pride→violet, default/mono→white.

```
Question: "What colour for labels and percentages?"
Options:
  - "<recommendation> (Recommended)" — "<reason>"
  - "White" — "Neutral, works with any theme"
  - "Auto" — "Best match for your theme"
```

Apply with `--text-color <colour>`.

**Step 4:** Animation:

```
Question: "Choose an animation style"
Options:
  - "Off (Recommended)" — "Static theme colours, clean and simple"
  - "Rainbow" — "Flowing rainbow gradient"
  - "Pulse" — "Bars cycle through vivid colours"
  - "Glow" — "Gradient shifts across the bar"
  - "Shift" — "Bright highlight slides across"
```

Apply with `--animate <mode>`.

**Step 5:** Bar size:

```
Question: "How wide should the progress bars be?"
Options:
  - "Large (Recommended)" — "12 characters — detailed bars"
  - "Medium" — "8 characters — balanced"
  - "Small" — "4 characters — compact"
```

Apply with `--bar-size <size>`.

**Step 6:** Currency:

```
Question: "What currency for the cost ticker?"
Options:
  - "$ (USD)" — "US Dollar (base currency)"
  - "£ (GBP)" — "British Pound (auto-converted)"
  - "€ (EUR)" — "Euro (auto-converted)"
  - "Other" — "Type any symbol (¥, ₹, C$, kr, etc.)"
```

Apply with `--currency <symbol>`. Explain: the cost shows what this session would cost at API rates, converted to their currency via live exchange rate.

**Step 7:** Clock format:

```
Question: "Clock format for timers?"
Options:
  - "12h" — "Fri 5pm"
  - "24h" — "Fri 17:00"
```

Apply with `--clock-format <12h|24h>`.

**Step 8:** Reasoning effort display:

```
Question: "How should the reasoning-effort level be written?"
Options:
  - "Effort: Medium (Recommended)" — "Unambiguous at a glance"
  - "Medium" — "Just the word"
  - "med" — "Shortest, saves width on a busy bar"
```

Apply with `--effort-format <labeled|full|short>`.

**Step 9:** Optional widgets — ask which extras they want, multi-select:

```
Question: "Any optional widgets? (all off by default)"
Options (multi-select):
  - "Live heartbeat" — "[/] 42 tools 5m spinner during active work. Needs the PostToolUse hook"
  - "Cache hit rate" — "Share of input served from cache — the clearest cost signal"
  - "PR badge" — "Clickable #123 with review state (needs a terminal with hyperlink support)"
  - "7-day cost" — "Rolling weekly API-equivalent spend"
  - "Thinking state" — "Whether extended thinking is on"
```

Apply each with `--show <name>`: `heartbeat` (also `activity`), `cache`, `pr`,
`weekly_cost`, `thinking`. If heartbeat was chosen, also run
`python "SCRIPT_PATH" --install-hooks`.

**Step 10:** Budget (optional):

```
Question: "Track spend against a budget?"
Options:
  - "No (Recommended)" — "Skip"
  - "Yes" — "Set an amount to match Claude Code's --max-budget-usd"
```

If "Yes", ask for the amount and apply `--budget <amount>`. Explain that
`--max-budget-usd` is CLI-only and cannot be read automatically, so this number
has to be kept in step with it by hand.

**Step 11:** Confirm everything:
"All set! Your status bar is configured with **<theme>**, **<animation>** animation,
and **<currency>** cost tracking. It updates on every interaction."

Mention anything switched on in Step 9/10. If hooks were installed, add:
"Restart Claude Code to activate the live heartbeat."

Also note that subagent rows in the agent panel are installed automatically —
each running subagent shows its model, effort, context bar and elapsed time.

---

## DISPLAY RULES

- After any change, tell the user it will update on the next refresh.
- When running `--config`, summarise — don't show raw ANSI.
- Be brief and enthusiastic.
