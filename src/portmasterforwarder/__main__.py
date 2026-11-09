"""`python -m portmasterforwarder [--gamepad | --desktop]`.

--gamepad  pygame UI for the handheld (used by the Knulli launcher in roms/tools)
--desktop  tkinter UI for Windows/Linux desktops (default; the .exe)
"""
import os
import sys


def run(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    pad = "--gamepad" in argv or os.environ.get("PORTMASTERFORWARDER_UI", "").lower() == "gamepad"
    if pad and "--desktop" not in argv:
        from .padgui import main as pad_main
        return pad_main()
    from .app import main
    return main([a for a in argv if a not in ("--gamepad", "--desktop")])


if __name__ == "__main__":
    sys.exit(run())
