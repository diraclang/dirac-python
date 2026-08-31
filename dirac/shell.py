"""
Interactive DIRAC shell for the Python runtime.

A minimal REPL: maintains a persistent session across inputs so variables
and subroutines defined in one entry remain available in the next (unlike
the plain CLI, which creates a fresh session per file).

Usage:
    python3 -m dirac.shell
"""

from .runtime.braket_parser import BraKetParser
from .runtime.interpreter import integrate
from .runtime.parser import DiracParser
from .runtime.session import create_session
from .types import DiracSession

BANNER = """DIRAC Python Shell
Type DIRAC XML, then press Enter on a blank line to execute it.
Commands: :vars  :subs  :debug  :braket  :help  :quit
"""

HELP = """Commands:
  :vars    List current variables
  :subs    List registered subroutines
  :debug   Toggle debug logging
  :braket  Toggle bra-ket notation mode (default: XML)
  :help    Show this help
  :quit    Exit the shell (also :exit)

Enter DIRAC XML (one or more lines), then press Enter on an empty line to
parse and execute it. Variables and subroutines persist across entries
within this session.

Example:
  dirac> <defvar name="x" value="5" />
  .....
  dirac> <output>x = <variable name="x" /></output>
  .....
  x = 5

In :braket mode, the same example is:
  braket> |defvar name=x value=5>
  ......
  braket> |output>x = |variable name=x>
  ......
  x = 5
"""


def _print_vars(session: DiracSession) -> None:
    if not session.variables:
        print("(no variables)")
        return
    for v in session.variables:
        flag = " [visible]" if v.visible else ""
        print(f"  {v.name} = {v.value!r}{flag}")


def _print_subs(session: DiracSession) -> None:
    if not session.subroutines:
        print("(no subroutines)")
        return
    for s in session.subroutines:
        flag = " [visible]" if s.visible else ""
        print(f"  {s.name}{flag}")


def run() -> None:
    session = create_session()
    parser = DiracParser()
    braket_parser = BraKetParser()
    braket_mode = False

    print(BANNER)

    while True:
        lines: list[str] = []
        prompt = "braket> " if braket_mode else "dirac> "

        try:
            while True:
                try:
                    line = input(prompt)
                except EOFError:
                    print()
                    return

                stripped = line.strip()

                if not lines and stripped in (":quit", ":exit"):
                    return
                if not lines and stripped == ":help":
                    print(HELP)
                    break
                if not lines and stripped == ":vars":
                    _print_vars(session)
                    break
                if not lines and stripped == ":subs":
                    _print_subs(session)
                    break
                if not lines and stripped == ":debug":
                    session.debug = not session.debug
                    print(f"debug = {session.debug}")
                    break
                if not lines and stripped == ":braket":
                    braket_mode = not braket_mode
                    print(f"braket mode = {braket_mode}")
                    break
                if stripped == "" and not lines:
                    break  # ignore a stray blank line at an empty prompt
                if stripped == "" and lines:
                    break  # blank line ends a multi-line entry

                lines.append(line)
                prompt = "......" if braket_mode else "..... "
        except KeyboardInterrupt:
            print()
            continue

        if not lines:
            continue

        source = "\n".join(lines)
        before = len(session.output)

        try:
            xml_source = braket_parser.parse(source) if braket_mode else source
            ast = parser.parse(xml_source)
            integrate(session, ast)
        except Exception as exc:  # noqa: BLE001 - surface errors to the shell user
            print(f"Error: {exc}")
            continue

        new_output = "".join(session.output[before:]).strip()
        if new_output:
            print(new_output)


if __name__ == "__main__":
    run()
