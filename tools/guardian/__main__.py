"""Entrypoint for python -m tools.guardian."""

import sys

from tools.guardian.cli import main

if __name__ == "__main__":
    sys.exit(main())
