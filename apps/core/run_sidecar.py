"""PyInstaller entrypoint for the core sidecar.

Importing the package (absolute import) keeps the package's internal relative imports
(`from . import ...`) working — running `contab_core/sidecar.py` directly as a top-level
script would break them. Mirrors `python -m contab_core.sidecar` used in dev.
"""
import sys

from contab_core.sidecar import main

if __name__ == "__main__":
    sys.exit(main())
