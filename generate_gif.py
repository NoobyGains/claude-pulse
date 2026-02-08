"""Generate an animated GIF showcasing claude-pulse inside Claude Code."""
import json
import sys
import tempfile
from pathlib import Path

THEME_CSS = {
    "default": {"low": "#22c55e", "mid": "#eab308", "high": "#ef4444"},
    "ocean":   {"low": "#06b6d4", "mid": "#3b82f6", "high": "#a855f7"},
    "sunset":  {"low": "#eab308", "mid": "#ff8800", "high": "#ef4444"},
    "neon":    {"low": "#4ade80", "mid": "#facc15", "high": "#f87171"},
    "frost":   {"low": "#afffff", "mid": "#5fafff", "high": "#ffffff"},
    "ember":   {"low": "#ffd700", "mid": "#ff5f00", "high": "#f87171"},
    "candy":   {"low": "#ff87ff", "mid": "#af87ff", "high": "#00ffff"},
    "pride":   {"low": "#af5fff", "mid": "#00ffaf", "high": "#ff00af"},
    "mono":    {"low": "#d1d5db", "mid": "#d1d5db", "high": "#ffffff"},
    "rainbow": {"low": "#ff0000", "mid": "#00ff00", "high": "#ff00ff"},
}

DIM_COLOR = "#3a3a3a"
RAINBOW_COLORS = ["#ff0000", "#ff8800", "#ffff00", "#00ff00", "#00ccff",
                   "#0066ff", "#8800ff", "#ff00ff", "#ff0066", "#ff4444"]

# Claude "Claw'd" pixel mascot as CSS pixel art (16x12 grid)
# R = coral body, D = dark eyes, . = transparent
# Square design: 12px wide body, 2px arm nubs on each side
MASCOT_PIXELS = [
    "..RRRRRRRRRRRR..",
    "..RRRRRRRRRRRR..",
    "..RDDRRRRRRDDR..",
    "..RDDRRRRRRDDR..",
    "..RRRRRRRRRRRR..",
    "RRRRRRRRRRRRRRRR",
    "RRRRRRRRRRRRRRRR",
    "..RRRRRRRRRRRR..",
    "..RRRRRRRRRRRR..",
    "..RRRRRRRRRRRR..",
    "..RR.RR..RR.RR..",
    "..RR.RR..RR.RR..",
]


def mascot_html():
    """Render the Claude pixel mascot as CSS grid pixel art."""
    rows = []
    for row in MASCOT_PIXELS:
        for ch in row:
            if ch == "R":
                rows.append('<span class="px pr"></span>')
            elif ch == "D":
                rows.append('<span class="px pd"></span>')
            elif ch == "N":
                rows.append('<span class="px pn"></span>')
            else:
                rows.append('<span class="px"></span>')
    return "\n            ".join(rows)


def bar_color(pct, theme):
    if pct >= 80:
        return theme["high"]
    if pct >= 50:
        return theme["mid"]
    return theme["low"]


def render_bar_html(pct, theme, width=10, rainbow=False, color_offset=0):
    filled = round(pct / 100 * width)
    filled = max(0, min(width, filled))
    empty = width - filled
    e_chars = "\u2500" * empty
    if rainbow and filled > 0:
        parts = ""
        for j in range(filled):
            c = RAINBOW_COLORS[(j + color_offset) % len(RAINBOW_COLORS)]
            parts += f'<span style="color:{c}">\u2501</span>'
        return f'{parts}<span style="color:{DIM_COLOR}">{e_chars}</span>'
    color = bar_color(pct, theme)
    f_chars = "\u2501" * filled
    return f'<span style="color:{color}">{f_chars}</span><span style="color:{DIM_COLOR}">{e_chars}</span>'


def generate_frame_html(theme_name, theme, session_pct, weekly_pct, ctx_pct,
                         reset_time, plan, model, frame_num, total_frames, desc,
                         is_rainbow=False, color_offset=0,
                         extra_used="", extra_limit="",
                         show_update=False):
    session_bar = render_bar_html(session_pct, theme, 10, rainbow=is_rainbow, color_offset=color_offset)
    weekly_bar = render_bar_html(weekly_pct, theme, 10, rainbow=is_rainbow, color_offset=color_offset + 3)
    ctx_bar = render_bar_html(ctx_pct, theme, 10, rainbow=is_rainbow, color_offset=color_offset + 6)

    text_color = "#d1d5db"
    sep = f'<span class="sep">|</span>'
    sp = f"{session_pct:3d}%"
    wp = f"{weekly_pct:3d}%"
    cp = f"{ctx_pct:3d}%"
    reset_str = f" {reset_time}" if reset_time else "       "

    extra_part = ""
    if extra_used and extra_limit:
        extra_pct = 100 * float(extra_used.replace("£", "")) / float(extra_limit.replace("£", ""))
        extra_bar = render_bar_html(extra_pct, theme, 10, rainbow=is_rainbow, color_offset=color_offset + 9)
        extra_part = (
            f'{sep}'
            f'<span class="sl">Extra </span>{extra_bar}'
            f'<span class="sl"> {extra_used}/{extra_limit}</span>'
        )

    update_part = ""
    if show_update:
        update_part = f'{sep}<span style="color:#eab308;font-weight:bold">&#x2191; Pulse Update</span>'

    status = (
        f'<span class="sl">Session </span>{session_bar}'
        f'<span class="sl"> {sp}{reset_str}</span>'
        f'{sep}'
        f'<span class="sl">Weekly </span>{weekly_bar}'
        f'<span class="sl"> {wp}</span>'
        f'{sep}'
        f'<span class="sl">Context </span>{ctx_bar}'
        f'<span class="sl"> {cp}</span>'
        f'{extra_part}'
        f'{update_part}'
        f'{sep}'
        f'<span class="sl">{plan}</span>'
        f'{sep}'
        f'<span class="sl">{model}</span>'
    )

    badge_color = theme["low"]
    mascot = mascot_html()

    return f'''<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;700&display=swap');
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    background: #ffffff;
    display: flex;
    align-items: center;
    justify-content: center;
    height: 100vh;
    font-family: 'JetBrains Mono', 'Cascadia Code', 'Consolas', monospace;
  }}
  .terminal {{
    background: #0c0c0c;
    border-radius: 8px;
    width: 920px;
    height: 430px;
    box-shadow: 0 8px 30px rgba(0,0,0,0.15), 0 0 0 1px rgba(0,0,0,0.08);
    overflow: hidden;
    display: flex;
    flex-direction: column;
    position: relative;
  }}
  .titlebar {{
    background: #202020;
    padding: 7px 12px;
    display: flex;
    align-items: center;
    border-bottom: 1px solid #2a2a2a;
    flex-shrink: 0;
  }}
  .tab {{
    background: #0c0c0c;
    color: #aaa;
    font-size: 11px;
    padding: 5px 14px;
    border-radius: 6px 6px 0 0;
    display: flex;
    align-items: center;
    gap: 6px;
    border: 1px solid #2a2a2a;
    border-bottom: none;
    margin-bottom: -1px;
  }}
  .tab-icon {{ color: #0078d4; font-size: 13px; }}
  .spacer {{ flex: 1; }}
  .win-controls {{ display: flex; gap: 0; }}
  .win-btn {{
    color: #888;
    font-size: 11px;
    padding: 4px 16px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
  }}

  .body {{ flex: 1; display: flex; flex-direction: column; overflow: hidden; }}

  .conversation {{
    flex: 1;
    padding: 14px 20px;
    overflow: hidden;
  }}

  /* ── Header ── */
  .cc-title {{
    color: #d4a574;
    font-size: 12px;
    margin-bottom: 10px;
    padding-bottom: 8px;
    border-bottom: 1px solid #d4a57433;
  }}

  /* ── Two-column welcome ── */
  .welcome-row {{
    display: flex;
    gap: 0;
    margin-bottom: 12px;
    border: 1px solid #d4a57455;
    border-radius: 6px;
    overflow: hidden;
  }}
  .welcome-left {{
    flex: 0 0 200px;
    display: flex;
    flex-direction: column;
    align-items: center;
    padding: 12px 10px;
    border-right: 1px solid #d4a57433;
  }}
  .welcome-greeting {{
    color: #e0e0e0;
    font-size: 12px;
    font-weight: 500;
    margin-bottom: 10px;
    text-align: center;
  }}
  .welcome-right {{
    flex: 1;
    padding: 12px 14px;
  }}

  /* Pixel mascot */
  .mascot {{
    display: grid;
    grid-template-columns: repeat(16, 6px);
    grid-template-rows: repeat(12, 6px);
    gap: 1px;
    margin-bottom: 8px;
  }}
  .px {{ width: 6px; height: 6px; background: transparent; }}
  .pr {{ background: #d4735c; }}
  .pd {{ background: #1a1a1a; }}
  .pn {{ background: #b85e48; }}

  .welcome-meta {{
    color: #888;
    font-size: 10px;
    text-align: center;
    line-height: 1.5;
  }}

  /* Right column */
  .section-title {{
    color: #d4a574;
    font-size: 11px;
    margin-bottom: 4px;
    font-weight: 500;
  }}
  .tip-text {{
    color: #888;
    font-size: 10.5px;
    line-height: 1.6;
    margin-bottom: 10px;
  }}
  .recent-text {{
    color: #666;
    font-size: 10.5px;
  }}

  /* ── User message + Claude reply ── */
  .user-msg {{
    margin-bottom: 8px;
    margin-top: 4px;
  }}
  .user-prompt {{
    display: flex;
    align-items: center;
    gap: 6px;
  }}
  .user-prompt .arrow {{ color: #b388ff; font-size: 12px; }}
  .user-text {{
    color: #e0e0e0;
    font-size: 12.5px;
    font-weight: 500;
  }}

  .claude-reply {{
    margin-bottom: 8px;
  }}
  .claude-reply .dot {{ color: #b388ff; font-size: 12px; }}
  .claude-reply-text {{
    color: #ccc;
    font-size: 12px;
    display: flex;
    align-items: center;
    gap: 5px;
  }}

  /* Prompt cursor */
  .prompt-line {{
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 13px;
  }}
  .prompt-arrow {{ color: #b388ff; }}
  .cursor {{
    display: inline-block;
    width: 8px;
    height: 15px;
    background: #b388ff;
    opacity: 0.7;
  }}

  /* ── Divider ── */
  .divider {{
    border-top: 1px solid #222;
    flex-shrink: 0;
  }}

  /* ── Status bar ── */
  .status-area {{
    padding: 8px 20px 6px 20px;
    flex-shrink: 0;
  }}
  .status-line {{
    font-size: 11.5px;
    line-height: 1.5;
    white-space: pre;
    letter-spacing: 0;
    font-variant-ligatures: none;
  }}
  .sl {{ color: {text_color}; }}
  .sep {{ color: #555; padding: 0 0.3em; }}

  /* ── Mode indicator ── */
  .mode-bar {{
    padding: 2px 20px 10px 20px;
    display: flex;
    align-items: center;
    gap: 8px;
    flex-shrink: 0;
  }}
  .mode-icon {{ color: #b388ff; font-size: 11px; }}
  .mode-text {{ color: #666; font-size: 11px; }}
  .mode-hint {{ color: #444; font-size: 10px; }}

  /* ── Theme badge ── */
  .theme-overlay {{
    position: absolute;
    bottom: 12px;
    right: 20px;
    display: flex;
    align-items: center;
    gap: 8px;
  }}
  .theme-badge {{
    display: inline-block;
    background: rgba(255,255,255,0.06);
    border: 1px solid {badge_color}44;
    color: {badge_color};
    padding: 3px 12px;
    border-radius: 4px;
    font-size: 10px;
    letter-spacing: 1.5px;
    text-transform: uppercase;
    font-weight: 500;
  }}
  .frame-counter {{
    color: #444;
    font-size: 10px;
    letter-spacing: 1px;
  }}
</style>
</head>
<body>
  <div class="terminal">
    <div class="titlebar">
      <div class="tab"><span class="tab-icon">&#x276F;</span> Windows PowerShell</div>
      <div class="spacer"></div>
      <div class="win-controls">
        <span class="win-btn">&#x2500;</span>
        <span class="win-btn">&#x25A1;</span>
        <span class="win-btn close">&#x2715;</span>
      </div>
    </div>

    <div class="body">
      <div class="conversation">
        <div class="cc-title">Claude Code v2.1.36</div>

        <div class="welcome-row">
          <div class="welcome-left">
            <div class="welcome-greeting">Welcome back NoobyGains!</div>
            <div class="mascot">
              {mascot}
            </div>
            <div class="welcome-meta">
              {model} &middot; Claude Max<br>
              C:\\Users\\David
            </div>
          </div>
          <div class="welcome-right">
            <div class="section-title">Tips for getting started</div>
            <div class="tip-text">
              Run <span style="color:#b388ff">/init</span> to create a CLAUDE.md file with instructions for Claude<br>
              Note: You have launched claude in your home directory. For the best<br>
              experience, navigate to a project folder first.
            </div>
            <div class="section-title">Recent activity</div>
            <div class="recent-text">No recent activity</div>
          </div>
        </div>

        <div class="user-msg">
          <div class="user-prompt">
            <span class="arrow">&#x276F;</span>
            <span class="user-text">hello</span>
          </div>
        </div>

        <div class="claude-reply">
          <div class="claude-reply-text">
            <span class="dot">&#x25CF;</span>
            Hello! How can I help you today?
          </div>
        </div>

        <div class="prompt-line">
          <span class="prompt-arrow">&#x276F;</span>
          <span class="cursor"></span>
        </div>
      </div>

      <div class="divider"></div>
      <div class="status-area">
        <div class="status-line">{status}</div>
      </div>
      <div class="mode-bar">
        <span class="mode-icon">&#x23F5;&#x23F5;</span>
        <span class="mode-text">auto-accept edits</span>
        <span class="mode-hint">(shift+tab to cycle)</span>
      </div>
    </div>

    <div class="theme-overlay">
      <span class="theme-badge">{theme_name}</span>
      <span class="frame-counter">{frame_num}/{total_frames}</span>
    </div>
  </div>
</body>
</html>'''


def generate_statusline_html(theme_name, theme, session_pct, weekly_pct, ctx_pct,
                              reset_time, plan, model, frame_num, total_frames,
                              is_rainbow=False, color_offset=0,
                              show_update=False, show_claude_update=False):
    """Render just the status line bar — no terminal chrome."""
    session_bar = render_bar_html(session_pct, theme, 10, rainbow=is_rainbow, color_offset=color_offset)
    weekly_bar = render_bar_html(weekly_pct, theme, 10, rainbow=is_rainbow, color_offset=color_offset + 3)
    ctx_bar = render_bar_html(ctx_pct, theme, 10, rainbow=is_rainbow, color_offset=color_offset + 6)

    text_color = "#d1d5db"
    sep = '<span class="sep">|</span>'
    sp = f"{session_pct:3d}%"
    wp = f"{weekly_pct:3d}%"
    cp = f"{ctx_pct:3d}%"
    reset_str = f" {reset_time}" if reset_time else "       "

    update_part = ""
    if show_update:
        update_part = f'{sep}<span style="color:#eab308;font-weight:bold">&#x2191; Pulse Update</span>'
    if show_claude_update:
        update_part += f'{sep}<span style="color:#eab308;font-weight:bold">&#x2191; Claude Update</span>'

    status = (
        f'<span class="sl">Session </span>{session_bar}'
        f'<span class="sl"> {sp}{reset_str}</span>'
        f'{sep}'
        f'<span class="sl">Weekly </span>{weekly_bar}'
        f'<span class="sl"> {wp}</span>'
        f'{sep}'
        f'<span class="sl">Context </span>{ctx_bar}'
        f'<span class="sl"> {cp}</span>'
        f'{update_part}'
        f'{sep}'
        f'<span class="sl">{plan}</span>'
        f'{sep}'
        f'<span class="sl">{model}</span>'
    )

    return f'''<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;700&display=swap');
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    background: #ffffff;
    display: flex;
    align-items: center;
    justify-content: center;
    height: 60px;
    font-family: 'JetBrains Mono', 'Cascadia Code', 'Consolas', monospace;
  }}
  .bar {{
    background: #0c0c0c;
    padding: 10px 20px;
    width: 920px;
    border-radius: 6px;
    border: 1px solid #333;
  }}
  .status-line {{
    font-size: 13px;
    line-height: 1.5;
    white-space: pre;
    letter-spacing: 0;
    font-variant-ligatures: none;
  }}
  .sl {{ color: {text_color}; }}
  .sep {{ color: #555; padding: 0 0.3em; }}
</style>
</head>
<body>
  <div class="bar">
    <div class="status-line">{status}</div>
  </div>
</body>
</html>'''


def main():
    themes_to_show = ["default", "ocean", "sunset", "neon", "frost", "ember", "candy", "pride", "mono"]
    frames_data = []

    # (session%, weekly%, ctx%, reset_time, desc, extra_used, extra_limit)
    scenarios = [
        (12, 6, 8, "4h 52m", "low usage", "£3.10", "£37.00"),
        (38, 22, 30, "3h 14m", "warming up", "£8.20", "£37.00"),
        (62, 45, 55, "1h 48m", "active session", "£22.50", "£37.00"),
        (88, 68, 82, "0h 22m", "near limit", "£34.80", "£37.00"),
    ]

    for theme_name in themes_to_show:
        theme = THEME_CSS[theme_name]
        for session_pct, weekly_pct, ctx_pct, reset, desc, eu, el in scenarios:
            frames_data.append((
                theme_name, theme, session_pct, weekly_pct, ctx_pct,
                reset, "Max 20x", "Opus 4.6", desc, False, 0, eu, el
            ))

    rainbow_theme = THEME_CSS["rainbow"]
    for offset in range(10):
        frames_data.append((
            "rainbow", rainbow_theme, 55, 38, 45,
            "2h 10m", "Max 20x", "Opus 4.6", "animated shimmer", True, offset,
            "£18.50", "£37.00"
        ))

    tmp_dir = Path(tempfile.mkdtemp())
    html_paths = []
    total = len(frames_data)

    for i, (tname, theme, sp, wp, cp, reset, plan, model, desc, is_rb, c_off, eu, el) in enumerate(frames_data):
        html = generate_frame_html(
            tname, theme, sp, wp, cp, reset, plan, model,
            i + 1, total, desc, is_rainbow=is_rb, color_offset=c_off,
            extra_used=eu, extra_limit=el
        )
        html_path = tmp_dir / f"frame_{i:03d}.html"
        html_path.write_text(html, encoding="utf-8")
        html_paths.append(str(html_path))

    manifest = tmp_dir / "manifest.json"
    manifest.write_text(json.dumps(html_paths), encoding="utf-8")

    output_gif = Path(__file__).parent / "assets" / "demo.gif"
    output_gif.parent.mkdir(exist_ok=True)

    print(f"Generated {len(html_paths)} HTML frames in {tmp_dir}")
    print(json.dumps({
        "tmp_dir": str(tmp_dir),
        "output_gif": str(output_gif),
        "frame_count": len(html_paths),
    }))

    # ── Second GIF: update notification (status line only, no Extra) ──
    update_frames = []
    update_scenarios = [
        (42, 28, 35, "2h 40m", "with update"),
        (65, 50, 60, "1h 15m", "with update"),
        (85, 72, 78, "0h 30m", "with update"),
    ]
    for tname in themes_to_show:
        theme = THEME_CSS[tname]
        for sp, wp, cp, reset, desc in update_scenarios:
            update_frames.append((tname, theme, sp, wp, cp, reset,
                                  "Max 20x", "Opus 4.6", desc, False, 0))

    # Rainbow shimmer for update GIF too
    for offset in range(10):
        update_frames.append((
            "rainbow", THEME_CSS["rainbow"], 55, 38, 45,
            "2h 10m", "Max 20x", "Opus 4.6", "shimmer", True, offset
        ))

    tmp_dir2 = Path(tempfile.mkdtemp())
    html_paths2 = []
    total2 = len(update_frames)

    for i, (tname, theme, sp, wp, cp, reset, plan, model, desc, is_rb, c_off) in enumerate(update_frames):
        html = generate_statusline_html(
            tname, theme, sp, wp, cp, reset, plan, model,
            i + 1, total2, is_rainbow=is_rb, color_offset=c_off,
            show_update=True
        )
        html_path = tmp_dir2 / f"update_{i:03d}.html"
        html_path.write_text(html, encoding="utf-8")
        html_paths2.append(str(html_path))

    manifest2 = tmp_dir2 / "manifest.json"
    manifest2.write_text(json.dumps(html_paths2), encoding="utf-8")

    output_gif2 = Path(__file__).parent / "assets" / "update.gif"
    print(f"Generated {len(html_paths2)} update frames in {tmp_dir2}")
    print(json.dumps({
        "tmp_dir2": str(tmp_dir2),
        "output_gif2": str(output_gif2),
        "frame_count2": len(html_paths2),
    }))

    # ── Third GIF: Claude Code update notification (status line only) ──
    cc_update_frames = []
    cc_update_scenarios = [
        (42, 28, 35, "2h 40m", "with claude update"),
        (65, 50, 60, "1h 15m", "with claude update"),
        (85, 72, 78, "0h 30m", "with claude update"),
    ]
    for tname in themes_to_show:
        theme = THEME_CSS[tname]
        for sp, wp, cp, reset, desc in cc_update_scenarios:
            cc_update_frames.append((tname, theme, sp, wp, cp, reset,
                                     "Max 20x", "Opus 4.6", desc, False, 0))

    # Rainbow shimmer for claude update GIF too
    for offset in range(10):
        cc_update_frames.append((
            "rainbow", THEME_CSS["rainbow"], 55, 38, 45,
            "2h 10m", "Max 20x", "Opus 4.6", "shimmer", True, offset
        ))

    tmp_dir3 = Path(tempfile.mkdtemp())
    html_paths3 = []
    total3 = len(cc_update_frames)

    for i, (tname, theme, sp, wp, cp, reset, plan, model, desc, is_rb, c_off) in enumerate(cc_update_frames):
        html = generate_statusline_html(
            tname, theme, sp, wp, cp, reset, plan, model,
            i + 1, total3, is_rainbow=is_rb, color_offset=c_off,
            show_claude_update=True
        )
        html_path = tmp_dir3 / f"claude_update_{i:03d}.html"
        html_path.write_text(html, encoding="utf-8")
        html_paths3.append(str(html_path))

    manifest3 = tmp_dir3 / "manifest.json"
    manifest3.write_text(json.dumps(html_paths3), encoding="utf-8")

    output_gif3 = Path(__file__).parent / "assets" / "claude-update.gif"
    print(f"Generated {len(html_paths3)} claude update frames in {tmp_dir3}")
    print(json.dumps({
        "tmp_dir3": str(tmp_dir3),
        "output_gif3": str(output_gif3),
        "frame_count3": len(html_paths3),
    }))


if __name__ == "__main__":
    main()
