"""``_atomic_json_write`` must be safe when two processes write one file.

Two status-line windows can write the same provider cache in the same
instant. Each writer uses its own temp sibling, so neither can truncate,
rename or delete the other's, and only its own sibling is cleaned up.

Run: ``python -m unittest tests.test_atomic_write``
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import claude_status as cs  # noqa: E402


class AtomicWriteTest(unittest.TestCase):
    def setUp(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        self.target = Path(td.name) / "cache.json"

    def test_writes_and_leaves_no_temp_file(self):
        cs._atomic_json_write(self.target, {"a": 1})
        self.assertEqual(json.loads(self.target.read_text(encoding="utf-8")), {"a": 1})
        self.assertEqual([p.name for p in self.target.parent.iterdir()], ["cache.json"])

    def test_each_writer_gets_its_own_temp_name(self):
        seen = []
        real = cs._secure_open_write

        def spy(path, *a, **k):
            seen.append(Path(path).name)
            return real(path, *a, **k)
        with mock.patch.object(cs, "_secure_open_write", spy):
            cs._atomic_json_write(self.target, {"a": 1})
            cs._atomic_json_write(self.target, {"a": 2})
        self.assertEqual(len(set(seen)), 2, seen)
        for name in seen:
            self.assertTrue(name.startswith("cache.json.") and name.endswith(".tmp"), name)

    def test_failure_cleans_only_its_own_temp_file(self):
        other = self.target.parent / "cache.json.other.tmp"
        other.write_text("someone else's", encoding="utf-8")
        with mock.patch.object(cs.os, "replace", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                cs._atomic_json_write(self.target, {"a": 1})
        self.assertTrue(other.exists(), "another writer's temp file is left alone")
        self.assertFalse(self.target.exists())
        self.assertEqual([p.name for p in self.target.parent.iterdir()], ["cache.json.other.tmp"])


if __name__ == "__main__":
    unittest.main()
