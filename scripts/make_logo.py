"""Build the README logo: assets/logo.svg (for dark pages) and assets/logo-light.svg.

The wordmark "Usage Pulse" and the tagline are font outlines, not <text>, so
the logo looks the same everywhere (an SVG shown as an image cannot load web
fonts). The outlines come from Cascadia Code (SIL Open Font License), the
font Windows Terminal ships; point CASCADIA at a copy of CascadiaCode.ttf.
The icon's bars animate with plain SMIL, which GitHub renders.

    pip install fonttools
    python scripts/make_logo.py
"""
import os
import sys
from pathlib import Path

from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont

REPO_ROOT = Path(__file__).resolve().parent.parent
CASCADIA = Path(os.environ.get("CASCADIA", r"C:\Windows\Fonts\CascadiaCode.ttf"))


class Face:
    def __init__(self, weight):
        font = TTFont(str(CASCADIA))
        if "fvar" in font:
            font = instantiateVariableFont(font, {"wght": weight})
        self.upem = font["head"].unitsPerEm
        self.glyphs = font.getGlyphSet()
        self.cmap = font.getBestCmap()
        self.hmtx = font["hmtx"]

    def path(self, text, size, x, baseline):
        """SVG path data for *text* at *size* px with its left edge at *x*."""
        scale = size / self.upem
        parts, advance = [], 0.0
        for ch in text:
            name = self.cmap[ord(ch)]
            pen = SVGPathPen(self.glyphs)
            self.glyphs[name].draw(TransformPen(pen, (scale, 0, 0, -scale, x + advance, baseline)))
            if pen.getCommands():
                parts.append(pen.getCommands())
            advance += self.hmtx[name][0] * scale
        return " ".join(parts), advance

    def cap_height(self, size):
        pen = BoundsPen(self.glyphs)
        self.glyphs[self.cmap[ord("U")]].draw(pen)
        return pen.bounds[3] * size / self.upem


def build(theme):
    fg = "#0f172a" if theme == "light" else "#f8fafc"
    muted = "#475569" if theme == "light" else "#94a3b8"
    bold, regular = Face(700), Face(400)

    size, tag_size = 74, 22
    icon_x, icon_y, icon = 24, 36, 128
    text_x = icon_x + icon + 34
    baseline = icon_y + 70
    usage, w1 = bold.path("Usage ", size, text_x, baseline)
    pulse_x = text_x + w1
    pulse, w2 = bold.path("Pulse", size, pulse_x, baseline)
    tagline, w3 = regular.path("The live usage status line for Claude Code", tag_size, text_x + 2, baseline + 44)
    width = int(max(pulse_x + w2, text_x + 2 + w3) + 28)

    # Three usage bars inside the icon; each fills and settles on its own loop.
    bars = []
    for i, (y, values, dur) in enumerate(((36, "24;74;60;82;24", "7s"),
                                          (58, "48;30;70;52;48", "9s"),
                                          (80, "16;60;40;68;16", "8s"))):
        bars.append(
            f'<rect x="{icon_x + 24}" y="{icon_y + y}" width="80" height="12" rx="6" fill="#ffffff" opacity=".22"/>'
            f'<rect x="{icon_x + 24}" y="{icon_y + y}" width="24" height="12" rx="6" fill="#ffffff">'
            f'<animate attributeName="width" values="{values}" dur="{dur}" repeatCount="indefinite" '
            f'calcMode="spline" keySplines="0.4 0 0.2 1;0.4 0 0.2 1;0.4 0 0.2 1;0.4 0 0.2 1"/></rect>')

    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} 200" width="{width}" height="200" role="img" aria-label="Usage Pulse: the live usage status line for Claude Code">
  <defs>
    <linearGradient id="icon" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#22d3ee"/>
      <stop offset=".55" stop-color="#818cf8"/>
      <stop offset="1" stop-color="#e879f9"/>
    </linearGradient>
    <linearGradient id="word" gradientUnits="userSpaceOnUse" x1="{pulse_x:.0f}" y1="0" x2="{pulse_x + w2:.0f}" y2="0">
      <stop offset="0" stop-color="#22d3ee"/>
      <stop offset=".5" stop-color="#818cf8"/>
      <stop offset="1" stop-color="#e879f9"/>
    </linearGradient>
    <filter id="glow" x="-40%" y="-40%" width="180%" height="180%">
      <feGaussianBlur stdDeviation="14"/>
    </filter>
  </defs>

  <!-- soft glow behind the icon, breathing slowly -->
  <rect x="{icon_x}" y="{icon_y}" width="{icon}" height="{icon}" rx="32" fill="url(#icon)" filter="url(#glow)" opacity=".45">
    <animate attributeName="opacity" values=".35;.6;.35" dur="6s" repeatCount="indefinite"/>
  </rect>
  <!-- the icon: a status bar's three windows -->
  <rect x="{icon_x}" y="{icon_y}" width="{icon}" height="{icon}" rx="30" fill="url(#icon)"/>
  {''.join(bars)}

  <!-- wordmark -->
  <path d="{usage}" fill="{fg}"/>
  <path d="{pulse}" fill="url(#word)"/>
  <path d="{tagline}" fill="{muted}"/>
</svg>
"""


def main():
    if not CASCADIA.exists():
        sys.exit(f"font not found: {CASCADIA} (set CASCADIA to a CascadiaCode.ttf)")
    for theme, name in (("dark", "logo.svg"), ("light", "logo-light.svg")):
        out = REPO_ROOT / "assets" / name
        out.write_text(build(theme), encoding="utf-8")
        print("wrote", out.relative_to(REPO_ROOT), out.stat().st_size // 1024, "KB")


if __name__ == "__main__":
    main()
