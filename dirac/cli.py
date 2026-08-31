"""
Command-line interface for the DIRAC Python runtime.
Mirrors dirac/src/cli.ts (single-file execution mode only, for now).
"""

import argparse
import sys

from . import execute


def main() -> None:
    parser = argparse.ArgumentParser(prog="dirac-py", description="Run a DIRAC (.di) script.")
    parser.add_argument("file", help="Path to a .di file to execute")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    with open(args.file, "r", encoding="utf-8") as f:
        source = f.read()

    try:
        output = execute(source, debug=args.debug)
    except Exception as exc:  # noqa: BLE001 - surface runtime errors to the CLI user
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    print(output, end="")


if __name__ == "__main__":
    main()
