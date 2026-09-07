"""
Interactive DIRAC shell for the Python runtime.

A minimal REPL: maintains a persistent session across inputs so variables
and subroutines defined in one entry remain available in the next (unlike
the plain CLI, which creates a fresh session per file).

Usage:
    python3 -m dirac.shell
"""

import os
import subprocess

from .runtime.braket_parser import BraKetParser
from .runtime.interpreter import integrate
from .runtime.parser import DiracParser
from .runtime.session import create_session
from .types import DiracSession

BANNER = """DIRAC Python Shell
Type DIRAC XML, then press Enter on a blank line to execute it.
Commands: :vars  :subs  :debug  :braket  :shell  :help  :quit
"""

HELP = """Commands:
  :vars    List current variables
  :subs    List registered subroutines
  :debug   Toggle debug logging
  :braket  Toggle bra-ket notation mode (default: XML)
  :shell   Toggle shell mode for running Unix commands directly
  :help    Show this help
  :quit    Exit the shell (also :exit)

Enter DIRAC XML (one or more lines), then press Enter on an empty line to
parse and execute it. Variables and subroutines persist across entries
within this session.

In shell mode, you can type plain Unix commands like:
  shell> ls -la
  shell> pwd
  shell> vi foo.txt
  shell> exit

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


def run_shell_command(command: str) -> int:
    """Run a shell command in the current working directory and keep `cd` state."""
    stripped = command.strip()
    if stripped.startswith("cd"):
        rest = stripped[2:].strip()
        target = rest or os.path.expanduser("~")
        try:
            os.chdir(target)
            return 0
        except OSError as exc:
            print(f"cd: {exc}")
            return 1

    try:
        completed = subprocess.run(command, shell=True, capture_output=False, text=True)
        return completed.returncode
    except KeyboardInterrupt:
        return 130


def run() -> None:
    session = create_session()
    parser = DiracParser()
    braket_parser = BraKetParser()
    braket_mode = False
    shell_mode = False

    print(BANNER)

    while True:
        lines: list[str] = []
        prompt = "shell> " if shell_mode else ("braket> " if braket_mode else "dirac> ")

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
                    if hasattr(session, "variables"):
                        if not session.variables:
                            print("(no variables)")
                        else:
                            for v in session.variables:
                                print(f"  {v.name} = {v.value!r}")
                    break
                if not lines and stripped == ":subs":
                    if hasattr(session, "subroutines"):
                        if not session.subroutines:
                            print("(no subroutines)")
                        else:
                            for s in session.subroutines:
                                print(f"  {s.name}")
                    break
                if not lines and stripped == ":debug":
                    session.debug = not session.debug
                    print(f"debug = {session.debug}")
                    break
                if not lines and stripped == ":braket":
                    braket_mode = not braket_mode
                    shell_mode = False
                    print(f"braket mode = {braket_mode}")
                    break
                if not lines and stripped == ":shell":
                    shell_mode = not shell_mode
                    braket_mode = False
                    print(f"shell mode = {shell_mode}")
                    if not shell_mode:
                        print("Returned to DIRAC shell")
                    break
                if not lines and stripped in (":dirac", ":return"):
                    shell_mode = False
                    braket_mode = False
                    print("Returned to DIRAC shell")
                    break
                if not lines and stripped == ":braket":
                    shell_mode = False
                    braket_mode = True
                    print(f"braket mode = {braket_mode}")
                    break
                if shell_mode:
                    if stripped == "":
                        break
                    if stripped in (":dirac", ":return"):
                        shell_mode = False
                        braket_mode = False
                        print("Returned to DIRAC shell")
                        break
                    if stripped == ":braket":
                        shell_mode = False
                        braket_mode = True
                        print(f"braket mode = {braket_mode}")
                        break
                    rc = run_shell_command(line)
                    if rc != 0:
                        print(f"shell exit code: {rc}")
                    break
                if stripped == "" and not lines:
                    break
                if stripped == "" and lines:
                    break

                lines.append(line)
                prompt = "......" if braket_mode else "..... "
        except KeyboardInterrupt:
            print()
            continue

        if shell_mode:
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


if __name__ == "__main__":
    run()
