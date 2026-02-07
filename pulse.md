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

### Interactive menu (when $ARGUMENTS is empty, `themes`, `theme`, or `menu`):

**Step 1:** Run `python "[REPLACE_WITH_YOUR_PATH]/claude_status.py" --config` silently to get the current settings.

**Step 2:** Run `python "[REPLACE_WITH_YOUR_PATH]/claude_status.py" --themes-demo` and show the output to the user. This prints all 10 themes with their actual coloured bars so the user can see every option before picking.

**Step 3:** Show the first `AskUserQuestion` picker (page 1 of 3):

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

**Step 3b:** If "More themes...", show page 2:

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

**Step 3c:** If "More themes..." again, show page 3:

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

If "← Back", go back to Step 3. Mono is available via "Other" on any page (it's visible in the preview above).

**Step 4:** After the user picks a theme, apply it with `--theme <name>`.

**Step 5:** If the chosen theme is NOT rainbow, ask about text colour. The recommended option should be the theme's default (auto) which uses white for most themes — neutral and contrasts with all bar colours:

```
Question: "What colour for the labels and percentages?"
Header: "Text colour"
multiSelect: false
Options:
  - "White (Recommended)" — "Neutral light grey that contrasts with theme bars and shows the shimmer"
  - "Default" — "Your terminal's default text colour"
  - "cyan" — "Cool cyan text"
  - "magenta" — "Magenta/pink text"
```

If they pick "White", use `--text-color auto` (auto resolves to white for most themes).
If they pick "Default", use `--text-color default`.

Apply with `--text-color <name>`. If they pick Auto, use `--text-color auto`.

**Step 6:** Ask about animation:

```
Question: "Enable the white shimmer animation?"
Header: "Shimmer"
multiSelect: false
Options:
  - "On (Recommended)" — "White highlight sweeps across while Claude is writing"
  - "Off" — "Static colours, no animation"
```

**Step 7:** Apply the animation setting with `--animate on|off`.

**Step 8:** Confirm everything:
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
