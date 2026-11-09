"""Entry point used by PyInstaller (absolute import so it also works inside the frozen .exe)."""
import sys

from portmasterforwarder.app import main

if __name__ == "__main__":
    sys.exit(main())
