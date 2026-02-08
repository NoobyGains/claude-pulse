Configure your Claude status bars — themes, colours, and animations. $ARGUMENTS

The claude-pulse script is at: [REPLACE_WITH_YOUR_PATH]/claude_status.py

---

## ROUTING — decide what to do based on $ARGUMENTS

### Direct commands (skip the menu, run immediately):

If $ARGUMENTS matches a **theme name** (`default`, `ocean`, `sunset`, `mono`, `neon`, `pride`, `frost`, `ember`, `candy`, `rainbow`):
-> Run `python "[REPLACE_WITH_YOUR_PATH]/claude_status.py" --theme <name>` directly, no menu.
-> Confirm: "Theme set to **<name>**. The status line will update on the next refresh."

If $ARGUMENTS is `config` or `settings`:
-> Run `python "[REPLACE_WITH_YOUR_PATH]/claude_status.py" --config` silently.
-> Summarise the settings in your response text (don't show raw ANSI output).

If $ARGUMENTS is exactly `show` (no parts after it), or `show all`, or `colors`, or `colours`, or `preview`:
-> Run TWO separate Bash commands (in parallel) so the output is NOT collapsed behind ctrl+o:
   1. `python "[REPLACE_WITH_YOUR_PATH]/claude_status.py" --show-themes`
   2. `python "[REPLACE_WITH_YOUR_PATH]/claude_status.py" --show-colors`
-> IMPORTANT: Show the raw command output DIRECTLY to the user. Do NOT summarise, reformat, or create tables. The commands output coloured ANSI text with live theme previews — the user needs to see the actual coloured bars, not a markdown description of them. Just run the commands and let the output speak for itself.
-> After both commands, say ONLY: "Press **Ctrl+O** to expand and see the colours."

If $ARGUMENTS contains `hide <parts>` or `show <parts>` (with specific parts like extra, timer, etc.):
-> Run the corresponding `--hide` or `--show` command directly.

If $ARGUMENTS is `animate on` or `animate off`:
-> Run `--animate on|off` directly.

If $ARGUMENTS matches `text-color <name>` or `text-colour <name>`:
-> Run `--text-color <name>` directly.
-> Available colours: auto, white, bright_white, cyan, blue, green, yellow, magenta, red, orange, violet, pink, dim, default, none

If $ARGUMENTS matches `currency <symbol>` (e.g. `currency £`, `currency €`, `currency $`):
-> Run `--currency <symbol>` directly.
-> Confirm: "Currency set to **<symbol>**. Extra usage will display as <symbol>amount."

If $ARGUMENTS matches `bar-size <size>` or `bars <size>` (where size is `small`, `medium`, or `large`):
-> Run `--bar-size <size>` directly.
-> Confirm: "Bar size set to **<size>**. The status line will update on the next refresh."

If $ARGUMENTS matches `bar-style <name>` or `style <name>` (where name is `classic`, `block`, `shade`, `pipe`, `dot`, `square`, or `star`):
-> Run `--bar-style <name>` directly.
-> Confirm: "Bar style set to **<name>**. The status line will update on the next refresh."

If $ARGUMENTS matches `layout <name>` (where name is `standard`, `compact`, `minimal`, or `percent-first`):
-> Run `--layout <name>` directly.
-> Confirm: "Layout set to **<name>**. The status line will update on the next refresh."

If $ARGUMENTS matches `extra-display <mode>` (where mode is `auto`, `full`, or `amount`):
-> Run `--extra-display <mode>` directly.
-> Confirm with description:
  - `auto`: "Extra display set to **auto**. Shows amount only if you have no spending limit, full bar otherwise."
  - `full`: "Extra display set to **full**. Shows progress bar with amount spent and limit."
  - `amount`: "Extra display set to **amount**. Shows just how much you've spent, no bar."

If $ARGUMENTS is `update`:
-> Run `python "[REPLACE_WITH_YOUR_PATH]/claude_status.py" --update` and show the output.
-> After a successful update, remind the user to restart Claude Code to use the new version.

### Interactive menu (when $ARGUMENTS is empty, `themes`, `theme`, or `menu`):

**Step 0 — Quick tips & update check:**

First, show the user available quick commands so they know what's possible:

> **Quick commands:** `/pulse show` preview all themes · `/pulse ocean` set a theme · `/pulse config` see settings · `/pulse update` check for updates

Then run `python "[REPLACE_WITH_YOUR_PATH]/claude_status.py" --config` silently to get the current settings. If the output contains "update available" or similar, also tell the user:

> **A new version of claude-pulse is available!** Run `/pulse update` to get the latest features and fixes.

Then continue with the wizard. If no update is available, skip the update message.

**Step 1:** Run `python "[REPLACE_WITH_YOUR_PATH]/claude_status.py" --themes-demo` and show the output to the user. This prints all 10 themes with their actual coloured bars so the user can see every option before picking.

**Step 2:** Show the first `AskUserQuestion` picker (page 1 of 3):

```
Question: "Pick a theme from the preview above"
Header: "Theme"
multiSelect: false
Options:
  - "rainbow" — "Full-spectrum rainbow colours across all bars"
  - "default" — "Classic green → yellow → red traffic-light"
  - "ocean" — "Cool cyan → blue → magenta"
  - "More themes..." — "See all 10 themes"
```

**Step 2b:** If "More themes...", show page 2:

```
Question: "Pick a theme"
Header: "Theme"
multiSelect: false
Options:
  - "frost" — "Icy light blue → steel blue → bright white"
  - "ember" — "Gold amber → hot orange → bright red"
  - "candy" — "Hot pink → purple → bright cyan"
  - "More themes..." — "See neon, sunset, pride, mono"
```

**Step 2c:** If "More themes..." again, show page 3:

```
Question: "Pick a theme"
Header: "Theme"
multiSelect: false
Options:
  - "neon" — "Vivid bright green → yellow → red"
  - "sunset" — "Warm yellow → orange → red"
  - "pride" — "Violet → green → pink"
  - "← Back" — "Return to the first set of themes"
```

If "← Back", go back to Step 2. Mono is available via "Other" on any page (it's visible in the preview above).

**Step 3:** After the user picks a theme, apply it with `--theme <name>`.

**Step 4:** If the chosen theme is NOT rainbow, ask about text colour. Use the theme-specific recommendation as the top option:

Theme-specific text colour recommendations:
- **ocean** → recommend **cyan** — "Cool cyan that complements the blue/magenta bars"
- **sunset** / **ember** → recommend **yellow** — "Warm tone that complements the orange/red bars"
- **frost** → recommend **cyan** — "Icy tone that complements the blue/white bars"
- **candy** → recommend **pink** — "Pink that complements the purple/cyan bars"
- **neon** → recommend **green** — "Bright green that matches the neon energy"
- **pride** → recommend **violet** — "Violet that complements the green/pink bars"
- **default** / **mono** / anything else → recommend **white** — "Neutral light grey that works with any bars"

```
Question: "What colour for the labels and percentages?"
Header: "Text colour"
multiSelect: false
Options:
  - "<theme recommendation> (Recommended)" — "<reason from above>"
  - "White" — "Neutral light grey — works with any theme"
  - "Default" — "Your terminal's default text colour"
  - "<a contrasting option>" — pick one that contrasts with the theme: cyan, magenta, green, yellow, etc.
```

If they pick the recommended option for a specific theme, use `--text-color <colour>` (e.g. `--text-color cyan` for ocean).
If they pick "White", use `--text-color white`.
If they pick "Default", use `--text-color default`.

**Step 5:** Ask about animation. The question depends on the chosen theme:

If the chosen theme IS **rainbow**:

```
Question: "Enable the flowing rainbow animation?"
Header: "Animation"
multiSelect: false
Options:
  - "On (Recommended)" — "Rainbow colours flow across the bar while Claude is active"
  - "Off" — "Rainbow colours without the flowing effect"
```

If the chosen theme is NOT rainbow:

```
Question: "Enable rainbow animation on your bars?"
Header: "Animation"
multiSelect: false
Options:
  - "Off (Recommended)" — "Keep your theme's own colours"
  - "On" — "Override bar colours with a flowing rainbow gradient"
```

If they pick "On", run `--animate on`. If "Off", run `--animate off`.

**Step 6:** Ask about bar size:

```
Question: "How wide should the progress bars be?"
Header: "Bar size"
multiSelect: false
Options:
  - "Medium (Recommended)" — "8 characters — balanced default"
  - "Small" — "4 characters — compact, more room for text"
  - "Large" — "12 characters — wide bars, more visual detail"
```

Apply with `--bar-size <small|medium|large>`.

**Step 7:** Check extra credits status by running `python "[REPLACE_WITH_YOUR_PATH]/claude_status.py" --config` silently and checking the "Extra Credits" section.

If credits are **active** (Status: active), ask:

```
Question: "You have bonus credits from Claude. How should extra usage appear?"
Header: "Extra credits"
multiSelect: false
Options:
  - "Dynamic (Recommended)" — "Auto-shows when credits are active, hides when not"
  - "Always show" — "Always display extra credits, even if none are gifted"
  - "Hide" — "Never show extra credits on the status line"
```

If they pick "Dynamic": this is the default behaviour — no command needed (leave defaults).
If they pick "Always show", run `--show extra`.
If they pick "Hide", run `--hide extra`.

If credits are **not active**, ask a simpler version:

```
Question: "If Claude gifts you bonus credits in the future, show them?"
Header: "Extra credits"
multiSelect: false
Options:
  - "Dynamic (Recommended)" — "Auto-shows when credits appear, stays hidden otherwise"
  - "Hide" — "Never show, even if credits are gifted later"
```

If "Dynamic", no command needed (default). If "Hide", run `--hide extra`.

**Step 7b:** If credits are **active** AND the user chose "Dynamic" or "Always show" in Step 7, ask about display mode:

```
Question: "How should extra credits be displayed?"
Header: "Display"
multiSelect: false
Options:
  - "Full bar (Recommended)" — "Progress bar with amount spent and limit"
  - "Amount only" — "Just show how much you've spent, no bar"
  - "Auto-detect" — "Shows amount only if you have no spending limit"
```

If they pick "Full bar", run `--extra-display full`.
If they pick "Amount only", run `--extra-display amount`.
If they pick "Auto-detect", run `--extra-display auto`.

If credits are **not active**, skip this question (they'll get the `auto` default).

**Step 8:** Ask about currency (only if they chose "Dynamic" or "Always show"):

```
Question: "What currency symbol for your extra credits?"
Header: "Currency"
multiSelect: false
Options:
  - "£ (GBP)" — "British Pound (default)"
  - "$ (USD)" — "US Dollar"
  - "€ (EUR)" — "Euro"
```

The user can also pick "Other" and type any symbol (e.g. ¥, ₹, kr, CHF, etc.).

Apply with `--currency <symbol>`.

**Step 9:** Confirm everything:
"All set! Your status line is now using **<theme>** with **<text colour>** text and animation **<on/off>**. It'll update on the next refresh (~30s) or restart Claude Code to see it immediately."

If credits were shown, also mention the display format:
- If display mode is "full": "Your bonus credits will appear as **Extra ━━━━ <currency>used/<currency>limit**."
- If display mode is "amount": "Your bonus credits will appear as **Extra <currency>amount**."
- If display mode is "auto": "Your bonus credits will auto-detect the best display format."

---

### Visibility settings (when $ARGUMENTS is `visibility` or `toggles`):

Use AskUserQuestion:

```
Question: "Which parts should be visible on your status line?"
Header: "Visibility"
multiSelect: true
Options:
  - "Session usage" — "5-hour usage block with progress bar and timer"
  - "Weekly usage" — "7-day rolling limit across all models"
  - "Plan name" — "Shows Pro / Max 5x / Max 20x"
  - "Timer" — "Countdown until session resets"
```

Then apply the appropriate `--show` and `--hide` commands based on what the user selected vs deselected.

Mention: "You can also enable **extra usage** tracking (bonus/overflow credits) with `/pulse show extra`."

---

## DISPLAY RULES

- After any theme/visibility change, tell the user the status line will update on the next refresh (~30 seconds) or they can restart Claude Code to see it immediately.
- When running `--config`, summarise in your own text — don't show raw terminal output (it has ANSI codes that collapse in the UI).
- Always be enthusiastic and brief. This is a fun cosmetic feature.
