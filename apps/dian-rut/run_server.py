"""PyInstaller entrypoint for the DIAN sidecar.

Runs uvicorn programmatically (no `python -m uvicorn`, which doesn't exist inside a frozen bundle).
Host/port come from CLI flags (as the shell spawns it) or env, defaulting to 127.0.0.1:8756.
"""
import argparse
import os

import uvicorn

from main import app


def _main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default=os.environ.get("DIAN_HOST", "127.0.0.1"))
    ap.add_argument("--port", type=int, default=int(os.environ.get("DIAN_PORT", "8756")))
    args = ap.parse_args()
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    _main()
