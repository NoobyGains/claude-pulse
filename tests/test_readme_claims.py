"""Guard the README's factual claims against drift from the source.

The README is the project's shop window, and a claim that quietly drifted away
from the code is worse than no claim at all. Everything machine-checkable is
asserted here: theme/style/animation counts, that every documented --show/--hide
flag is a real widget, that the example status line has no removed segments,
that no removed feature is still advertised, and that every local asset exists.

Run: ``python tests/test_readme_claims.py``

The README is the project's shop window; a claim that drifted from the code is
worse than no claim. This checks the ones that are machine-verifiable.
"""
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
import claude_status as cs  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

readme = (REPO / "README.md").read_text(encoding="utf-8")
issues = []


def check(name, ok, detail=""):
    print(f"  {'ok  ' if ok else 'FAIL'}  {name}" + (f"  — {detail}" if detail else ""))
    if not ok:
        issues.append(f"{name}: {detail}")


print("== version / floor ==")
# Derived from the README's own heading rather than hardcoded here — a
# hardcoded version pin in this file is the same drift bug this suite
# exists to catch (the manifests are covered by test_version_lockstep.py).
_whats_new = re.search(r"## What's new in (\d+\.\d+\.\d+)", readme)
check(
    "README 'What's new' version matches VERSION",
    bool(_whats_new) and _whats_new.group(1) == cs.VERSION,
    f"README {_whats_new.group(1) if _whats_new else '(heading missing)'}"
    f" vs VERSION {cs.VERSION}",
)
# "3.6+" may legitimately appear in a historical note about 3.1.0; what must
# not appear is 3.6 stated as the *current* requirement.
stale_floor = re.search(r"(?:Python|python)[- ]3\.6\+(?!.*advertised)", readme)     and "advertised 3.6+" not in readme
check("README states Python 3.8+ as the requirement", "3.8+" in readme and not stale_floor)

print("\n== themes ==")
themes = set(cs.THEMES) if hasattr(cs, "THEMES") else set(cs.THEME_COLOURS)
claimed = re.search(r"\*\*(\d+) themes\*\*", readme)
check("theme count claim matches code",
      claimed and int(claimed.group(1)) == len(themes),
      f"README says {claimed.group(1) if claimed else '?'}, code has {len(themes)}: {sorted(themes)}")
for t in sorted(themes):
    check(f"theme '{t}' documented", t in readme)

print("\n== bar styles ==")
styles = set(cs.BAR_STYLES)
claimed_bs = re.search(r"\*\*(\d+) bar styles\*\*", readme)
check("bar style count matches",
      claimed_bs and int(claimed_bs.group(1)) == len(styles),
      f"README says {claimed_bs.group(1) if claimed_bs else '?'}, code has {len(styles)}: {sorted(styles)}")
for s in sorted(styles):
    check(f"bar style '{s}' documented", s in readme)

print("\n== animation modes ==")
modes = set(cs.ANIMATE_MODES)
if modes:
    claimed_am = re.search(r"\*\*(\d+) animation modes\*\*", readme)
    check("animation mode count matches",
          claimed_am and int(claimed_am.group(1)) == len(modes),
          f"README says {claimed_am.group(1) if claimed_am else '?'}, code has {len(modes)}: {sorted(modes)}")
    for m in sorted(modes):
        check(f"animation '{m}' documented", m in readme)

print("\n== show/hide flags ==")
flags = set(re.findall(r"--(?:show|hide) (\w+)", readme))
for f in sorted(flags):
    check(f"--show/--hide {f} is a real widget", f in cs.DEFAULT_SHOW)

print("\n== layouts / bar sizes ==")
for size in cs.BAR_SIZES:
    check(f"bar size '{size}' documented", size in readme)

print("\n== example status line reflects current reality ==")
example = next((l for l in readme.split("\n") if l.startswith("Session ")), "")
check("example exists", bool(example))
check("example has no peak segment", "Peak" not in example, example[:80])
check("example uses a current model",
      any(m in example for m in ("Opus 5", "Fable", "Sonnet 5")),
      example[:120])

print("\n== no removed features referenced ==")
for gone in ("--peak-hours", "peak_hours", "In Peak", "Off-Peak"):
    check(f"'{gone}' absent", gone not in readme)

print("\n== removed functions not referenced ==")
check("_check_peak_hours gone from code", not hasattr(cs, "_check_peak_hours"))
check("peak not in WIDGET_PRIORITY", "peak" not in cs.WIDGET_PRIORITY)

print("\n== settings key correctness ==")
check("README documents refreshInterval", "refreshInterval" in readme)
check("README does not promote the dead 'refresh' key",
      not re.search(r'"refresh"\s*:', readme))

print("\n== model claims ==")
for m in ("Fable", "Opus", "Sonnet", "Haiku"):
    check(f"model family '{m}' mentioned", m in readme)

print("\n== links / assets exist ==")
for src in re.findall(r'src="([^"]+)"', readme):
    if src.startswith("http"):
        continue
    check(f"asset {src} exists", (REPO / src).exists())

print("\n" + ("README AUDIT CLEAN" if not issues else f"{len(issues)} ISSUE(S):"))
for i in issues:
    print("  -", i)
sys.exit(1 if issues else 0)
