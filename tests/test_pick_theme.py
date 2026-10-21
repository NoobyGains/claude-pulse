"""Tests for the interactive arrow-key theme picker (``--pick-theme``).

The picker needs a real terminal, so these tests drive it without one:

* the navigation loop is exercised by feeding a scripted key sequence into a
  patched ``_read_key`` and asserting which theme gets applied;
* the Windows arrow-key decoding (the ``\\xe0`` prefix + letter codes) is
  verified by patching ``msvcrt.getwch`` (Windows only);
* ``_render_picker`` is checked for the selection highlight and current marker;
* the no-TTY path is checked to fall back to the static gallery, not crash.

Run: ``python tests/test_pick_theme.py``
"""
import sys
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import claude_status as cs  # noqa: E402

# The picker's previews render through build_status_line, which reads and
# writes the state dir; keep that out of the real one.
_STATE = None
_STATE_PATCH = None


def setUpModule():
    global _STATE, _STATE_PATCH
    import tempfile
    _STATE = tempfile.TemporaryDirectory()
    state = Path(_STATE.name)
    _STATE_PATCH = mock.patch.object(cs, "get_state_dir", lambda: state)
    _STATE_PATCH.start()


def tearDownModule():
    _STATE_PATCH.stop()
    _STATE.cleanup()


class PickerLoopTest(unittest.TestCase):
    """The down/down/Enter dance should apply the third theme in the list."""

    def _run_with_keys(self, keys):
        """Drive cmd_pick_theme with a scripted key sequence; return the theme
        passed to cmd_set_theme (or None if it was never called)."""
        applied = {}
        key_iter = iter(keys)
        with mock.patch.object(cs, "_read_key", lambda: next(key_iter)), \
                mock.patch.object(cs, "_enable_windows_ansi", lambda: None), \
                mock.patch.object(cs, "load_config", lambda: {"theme": "default"}), \
                mock.patch.object(cs, "cmd_set_theme",
                                  side_effect=lambda name: applied.setdefault("name", name)), \
                mock.patch("sys.stdin") as fake_in, \
                mock.patch("sys.stdout") as fake_out:
            fake_in.isatty.return_value = True
            fake_out.isatty.return_value = True
            cs.cmd_pick_theme()
        return applied.get("name")

    def test_arrow_down_then_enter_applies_third_theme(self):
        names = list(cs.THEMES.keys())
        chosen = self._run_with_keys(["down", "down", "enter"])
        self.assertEqual(chosen, names[2],
                         "two downs from the top should land on the third theme")

    def test_vim_keys_navigate(self):
        names = list(cs.THEMES.keys())
        chosen = self._run_with_keys(["j", "enter"])  # j == down
        self.assertEqual(chosen, names[1])

    def test_up_wraps_to_last_theme(self):
        names = list(cs.THEMES.keys())
        chosen = self._run_with_keys(["up", "enter"])  # up from index 0 wraps
        self.assertEqual(chosen, names[-1])

    def test_esc_cancels_without_applying(self):
        self.assertIsNone(self._run_with_keys(["down", "esc"]),
                          "Esc must not apply any theme")

    def test_ctrl_c_cancels_without_applying(self):
        self.assertIsNone(self._run_with_keys(["down", "ctrl-c"]))


class RenderPickerTest(unittest.TestCase):
    def test_cursor_row_is_highlighted_and_current_is_marked(self):
        names = list(cs.THEMES.keys())
        out = cs._render_picker(names, cursor=1, current_theme=names[0],
                                bar_size="large", bar_style="classic")
        self.assertIn("Pick a theme", out)
        self.assertIn(cs.REVERSE, out, "selected row should use reverse video")
        self.assertIn("(current)", out, "the active theme should be marked current")
        # Every theme name appears exactly as a label.
        for name in names:
            self.assertIn(name, out)


class NoTtyFallbackTest(unittest.TestCase):
    def test_falls_back_to_gallery_without_a_terminal(self):
        with mock.patch.object(cs, "cmd_themes_demo") as demo, \
                mock.patch("sys.stdin") as fake_in, \
                mock.patch("sys.stdout") as fake_out:
            fake_in.isatty.return_value = False
            fake_out.isatty.return_value = True
            cs.cmd_pick_theme()
        demo.assert_called_once()


@unittest.skipUnless(sys.platform == "win32", "Windows-specific key decoding")
class WindowsKeyDecodeTest(unittest.TestCase):
    def _decode(self, chars):
        import msvcrt
        seq = iter(chars)
        with mock.patch.object(msvcrt, "getwch", lambda: next(seq)):
            return cs._read_key()

    def test_arrow_up(self):
        self.assertEqual(self._decode(["\xe0", "H"]), "up")

    def test_arrow_down(self):
        self.assertEqual(self._decode(["\x00", "P"]), "down")  # both prefixes occur

    def test_enter_esc_and_literal(self):
        self.assertEqual(self._decode(["\r"]), "enter")
        self.assertEqual(self._decode(["\x1b"]), "esc")
        self.assertEqual(self._decode(["\x03"]), "ctrl-c")
        self.assertEqual(self._decode(["q"]), "q")


if __name__ == "__main__":
    unittest.main(verbosity=2)
