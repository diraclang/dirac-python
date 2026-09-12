"""
Command-line interface for the DIRAC Python runtime.
Mirrors dirac/src/cli.ts (single-file execution mode only, for now).
"""

import argparse
import sys

from . import execute


def main() -> None:
    parser = argparse.ArgumentParser(prog="paul", description="Run a DIRAC (.di or .bk) script.")
    parser.add_argument("file", help="Path to a .di (XML) or .bk (bra-ket) file to execute")
    parser.add_argument(
        "--format",
        choices=["xml", "braket"],
        default=None,
        help="Force the source format instead of auto-detecting from the file extension",
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    with open(args.file, "r", encoding="utf-8") as f:
        source = f.read()

    fmt = args.format or ("braket" if args.file.endswith(".bk") else "xml")

    try:
        output = execute(source, debug=args.debug, fmt=fmt)
    except Exception as exc:  # noqa: BLE001 - surface runtime errors to the CLI user
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    print(output, end="")


if __name__ == "__main__":
    main()
