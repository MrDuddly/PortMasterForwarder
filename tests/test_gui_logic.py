import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
try:
    from portmasterforwarder import padgui as g, core
except ImportError:          # pygame not installed (CI) -> skip
    g = None


@unittest.skipIf(g is None, "pygame not installed")
class NewCategoryFlow(unittest.TestCase):
    def test_x_opens_only_the_keyboard_and_creates_the_category(self):
        class App:
            def __init__(s):
                s.stack, s.toast, s.cfg = [], "", core.load_config("/nonexistent/c.json")
                s.games = []
            def push(s, x): s.stack.append(x)
            def save(s): pass
        a = App()
        ls = g.ListScreen.__new__(g.ListScreen)
        ls.app, ls.i = a, 0
        a.stack = [ls]
        ls.handle("x")
        self.assertEqual([type(x).__name__ for x in a.stack], ["ListScreen", "Keyboard"])
        a.stack[-1].t = "3DS"
        a.stack[-1].handle("start")
        nc = a.stack[-1]
        while core.FRIENDLY_THEMES[nc.i][1] != "3ds":
            nc.handle("down")
        nc.handle("accept")
        self.assertEqual(a.cfg["categories"][-1]["theme"], "3ds")
        self.assertEqual(len(a.stack), 1)


if __name__ == "__main__":
    unittest.main()
