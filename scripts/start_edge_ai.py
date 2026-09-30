from __future__ import annotations

import argparse
import sys
import webbrowser
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[1]
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from silenttalk.edge_ai import request_base  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Start the independent base E4B AI")
    parser.add_argument("--open", action="store_true", help="open the browser chat UI")
    args = parser.parse_args()
    status = request_base(PROJECT_DIR)
    if args.open:
        webbrowser.open(str(status["url"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
