"""Keep the plugin manifests' version in lockstep with the script.

The Claude Code plugin manager decides whether a marketplace install is
current by comparing manifest versions — never by looking at the code. When
``claude_status.py`` moved to 3.1.0 and then 3.2.0 while both manifests still
said 3.0.0, every marketplace install was told it was up to date forever
(issue #49). The script's ``VERSION``, ``.claude-plugin/plugin.json`` and
``.claude-plugin/marketplace.json`` must therefore always agree.

Run: ``python tests/test_version_lockstep.py``
"""
import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import claude_status as cs  # noqa: E402


class VersionLockstepTest(unittest.TestCase):
    def test_plugin_manifest_matches_script_version(self):
        manifest = json.loads(
            (REPO_ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            manifest.get("version"), cs.VERSION,
            "plugin.json version must match claude_status.py VERSION — a stale "
            "manifest pins marketplace installs to old code (issue #49)",
        )

    def test_marketplace_manifest_matches_script_version(self):
        manifest = json.loads(
            (REPO_ROOT / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8")
        )
        plugins = manifest.get("plugins") or []
        self.assertEqual(len(plugins), 1, "marketplace.json should declare exactly one plugin")
        self.assertEqual(
            plugins[0].get("version"), cs.VERSION,
            "marketplace.json plugin version must match claude_status.py VERSION — "
            "a stale manifest pins marketplace installs to old code (issue #49)",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
