Configure the claude-pulse status line. The user's request is: $ARGUMENTS

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

If $ARGUMENTS contains `hide <parts>` or `show <parts>`:
-> Run the corresponding `--hide` or `--show` command directly.

If $ARGUMENTS is `rainbow-bars on` or `rainbow-bars off`:
-> Run `--rainbow-bars on|off` directly.

If $ARGUMENTS is `animate on` or `animate off`:
-> Run `--animate on|off` directly.

If $ARGUMENTS matches `text-color <name>` or `text-colour <name>`:
-> Run `--text-color <name>` directly.
-> Available colours: auto, white, bright_white, cyan, blue, green, yellow, magenta, red, orange, violet, pink, dim, default, none

If $ARGUMENTS is `update`:
-> Run `python "[REPLACE_WITH_YOUR_PATH]/claude_status.py" --update` and show the output.
-> After a successful update, remind the user to restart Claude Code to use the new version.

### Interactive menu (when $ARGUMENTS is empty, `themes`, `theme`, or `menu`):

**Step 0 — Update check:** Run `python "[REPLACE_WITH_YOUR_PATH]/claude_status.py" --config` silently to get the current settings. If the output contains "update available" or similar, tell the user FIRST:

> **A new version of claude-pulse is available!** Run `/pulse update` to get the latest features and fixes.

Then continue with the wizard. If no update is available, skip this message.

**Step 1:** Run `python "[REPLACE_WITH_YOUR_PATH]/claude_status.py" --themes-demo` and show the output to the user. This prints all 10 themes with their actual coloured bars so the user can see every option before picking.

**Step 2:** Show the first `AskUserQuestion` picker (page 1 of 3):

```
Question: "Pick a theme from the preview above"
Header: "Theme"
multiSelect: false
Options:
  - "rainbow" — "Animated full-spectrum colours with white shimmer"
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
  - "White" — "Neutral light grey — works with any theme and shows the shimmer"
  - "Default" — "Your terminal's default text colour"
  - "<a contrasting option>" — pick one that contrasts with the theme: cyan, magenta, green, yellow, etc.
```

If they pick the recommended option for a specific theme, use `--text-color <colour>` (e.g. `--text-color cyan` for ocean).
If they pick "White", use `--text-color white`.
If they pick "Default", use `--text-color default`.

**Step 5:** Ask about animation:

```
Question: "Enable the white shimmer animation?"
Header: "Shimmer"
multiSelect: false
Options:
  - "On (Recommended)" — "White highlight sweeps across while Claude is writing"
  - "Off" — "Static colours, no animation"
```

**Step 6:** Apply the animation setting with `--animate on|off`.

**Step 7:** Confirm everything:
"All set! Your status line is now using **<theme>** with **<text colour>** text and shimmer **<on/off>**. It'll update on the next refresh (~30s) or restart Claude Code to see it immediately."

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
