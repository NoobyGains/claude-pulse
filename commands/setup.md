---
description: Install the usage-pulse status bar with safe defaults (safe to run again)
---
Set up the usage-pulse status bar. Safe to run again: it only refreshes what is already there.

---

## Steps

1. **Find the script.** Use the Glob tool to search for `**/claude_status.py` inside `~/.claude/plugins/`. Use the result whose path contains `usage-pulse` (or `claude-pulse`, the name before 3.5.0). Save it as SCRIPT_PATH. (If nothing is found, also try `~/.usage-pulse/claude_status.py` and `~/.claude-pulse/claude_status.py`.)

2. **Run setup with defaults.** Execute: `python "SCRIPT_PATH" --setup --non-interactive` (use `python3` if `python` is not found).

   A plugin can't register a status line itself, so this writes `statusLine` and `subagentStatusLine` (one row per running agent) into Claude Code's `settings.json` (in `$CLAUDE_CONFIG_DIR` if set, else `~/.claude`), copies the `/pulse` command, and turns on rows for any other accounts or tools it detects. It installs no hooks.

3. **Report.** Show the short environment report it prints, in plain words. If it exited with an error (for example an invalid `settings.json`), show the message and stop.

4. **Tell the user:**
   - "usage-pulse is installed with defaults. Restart Claude Code to see your status bar."
   - "Run `/usage-pulse:pulse setup` to choose hooks (live agents, agent team), providers, theme and widgets."
   - "For the full-screen wizard with live previews, type `!python "SCRIPT_PATH" --setup` in your prompt."
