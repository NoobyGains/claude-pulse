#!/usr/bin/env python3
"""Render the repository's star history as committed SVG charts.

GitHub restricted the stargazers API to a repo's own admins and
collaborators in June 2026, which broke every third-party live-chart
embed (star-history.com and friends). A workflow running *as this
repository* still has access, so this script fetches the star dates,
renders a light and a dark SVG into assets/, and the workflow commits
them — the README then depends on nothing outside the repo.

Environment: GITHUB_TOKEN (required), GITHUB_REPOSITORY ("owner/name",
set automatically inside GitHub Actions).

Run: python scripts/star_history.py
"""
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_LIGHT = REPO_ROOT / "assets" / "star-history.svg"
OUT_DARK = REPO_ROOT / "assets" / "star-history-dark.svg"

WIDTH, HEIGHT = 700, 360
MARGIN_L, MARGIN_R, MARGIN_T, MARGIN_B = 56, 24, 44, 44


def fetch_star_dates(repo, token):
    """Return the sorted list of starred_at datetimes for *repo*.

    The application/vnd.github.star+json media type adds starred_at to
    each stargazer record; without it the endpoint returns bare users.
    """
    dates = []
    page = 1
    while True:
        req = urllib.request.Request(
            f"https://api.github.com/repos/{repo}/stargazers"
            f"?per_page=100&page={page}",
            headers={
                "Accept": "application/vnd.github.star+json",
                "Authorization": f"Bearer {token}",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            batch = json.load(resp)
        if not isinstance(batch, list) or not batch:
            break
        for record in batch:
            raw = record.get("starred_at") if isinstance(record, dict) else None
            if raw:
                try:
                    dates.append(
                        datetime.fromisoformat(raw.replace("Z", "+00:00"))
                    )
                except ValueError:
                    pass
        if len(batch) < 100:
            break
        page += 1
    dates.sort()
    return dates


def _nice_ceiling(value):
    """Round *value* up to a tidy axis maximum (1/2/5 times a power of 10)."""
    if value <= 5:
        return 5
    magnitude = 10 ** (len(str(value)) - 1)
    for factor in (1, 2, 5, 10):
        if factor * magnitude >= value:
            return factor * magnitude
    return 10 * magnitude


def render_svg(dates, repo, dark):
    """Render the cumulative star count as a self-contained SVG string.

    Deliberately contains no generated-at timestamp: identical data must
    produce identical bytes, so the weekly workflow only commits when the
    chart actually changed.
    """
    fg = "#e6edf3" if dark else "#1f2328"
    grid = "#30363d" if dark else "#d1d9e0"
    accent = "#f0b72f"  # star yellow, readable on both backgrounds
    bg = "#0d1117" if dark else "#ffffff"

    total = len(dates)
    now = dates[-1] if dates else datetime.now(timezone.utc)
    start = dates[0] if dates else now
    span = max((now - start).total_seconds(), 1.0)
    y_max = _nice_ceiling(total)

    plot_w = WIDTH - MARGIN_L - MARGIN_R
    plot_h = HEIGHT - MARGIN_T - MARGIN_B

    def x_at(dt):
        return MARGIN_L + plot_w * ((dt - start).total_seconds() / span)

    def y_at(count):
        return MARGIN_T + plot_h * (1 - count / y_max)

    # Cumulative step line: one point per star.
    points = [(x_at(dt), y_at(i + 1)) for i, dt in enumerate(dates)]
    if points:
        path = f"M{MARGIN_L:.1f},{y_at(0):.1f} " + " ".join(
            f"L{x:.1f},{y:.1f}" for x, y in points
        )
    else:
        path = f"M{MARGIN_L:.1f},{y_at(0):.1f} L{MARGIN_L + plot_w:.1f},{y_at(0):.1f}"

    gridlines, labels = [], []
    for i in range(5):
        count = round(y_max * i / 4)
        y = y_at(count)
        gridlines.append(
            f'<line x1="{MARGIN_L}" y1="{y:.1f}" x2="{WIDTH - MARGIN_R}" '
            f'y2="{y:.1f}" stroke="{grid}" stroke-width="1"/>'
        )
        labels.append(
            f'<text x="{MARGIN_L - 8}" y="{y + 4:.1f}" text-anchor="end" '
            f'font-size="12" fill="{fg}">{count}</text>'
        )
    for dt, anchor, x in ((start, "start", MARGIN_L),
                          (now, "end", WIDTH - MARGIN_R)):
        labels.append(
            f'<text x="{x}" y="{HEIGHT - MARGIN_B + 20}" text-anchor="{anchor}" '
            f'font-size="12" fill="{fg}">{dt.strftime("%b %Y")}</text>'
        )

    font = "-apple-system, 'Segoe UI', Helvetica, Arial, sans-serif"
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}" role="img" aria-label="Star history of {repo}: {total} stars">
<rect width="{WIDTH}" height="{HEIGHT}" fill="{bg}"/>
<g font-family="{font}">
<text x="{MARGIN_L}" y="26" font-size="16" font-weight="bold" fill="{fg}">⭐ Star History — {repo}</text>
<text x="{WIDTH - MARGIN_R}" y="26" text-anchor="end" font-size="14" fill="{fg}">{total} stars</text>
{''.join(gridlines)}
<path d="{path}" fill="none" stroke="{accent}" stroke-width="2.5" stroke-linejoin="round"/>
{''.join(labels)}
</g>
</svg>
"""


def main():
    token = os.environ.get("GITHUB_TOKEN", "")
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if not token or "/" not in repo:
        print("GITHUB_TOKEN and GITHUB_REPOSITORY (owner/name) are required",
              file=sys.stderr)
        return 1
    dates = fetch_star_dates(repo, token)
    OUT_LIGHT.parent.mkdir(parents=True, exist_ok=True)
    OUT_LIGHT.write_text(render_svg(dates, repo, dark=False), encoding="utf-8")
    OUT_DARK.write_text(render_svg(dates, repo, dark=True), encoding="utf-8")
    print(f"Rendered {len(dates)} stars into {OUT_LIGHT.name} / {OUT_DARK.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
