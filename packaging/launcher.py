"""Entry point of the built program (PyInstaller needs a script, not a package entry)."""

import sys

from copticocr.app.main import main

if __name__ == "__main__":
    sys.exit(main())
