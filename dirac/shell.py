"""
Interactive DIRAC shell for the Python runtime.

A minimal REPL: maintains a persistent session across inputs so variables
and subroutines defined in one entry remain available in the next (unlike
the plain CLI, which creates a fresh session per file).

Usage:
    python3 -m dirac.shell
"""

import os
import shlex
import subprocess
import tempfile

try:
    import readline
except ImportError:  # pragma: no cover - platform-specific fallback
    readline = None

from .runtime.braket_parser import BraKetParser
from .runtime.interpreter import integrate
from .runtime.parser import DiracParser
from .runtime.session import create_session
from .types import DiracSession

BANNER = """DIRAC Python Shell
Type DIRAC XML, then press Enter on a blank line to execute it.
Commands: :vars  :subs  :debug  :braket  :shell  :help  :quit
"""

HISTORY_FILE = os.path.join(os.path.expanduser("~"), ".dirac_history")
MAX_HISTORY = 1000


def _configure_readline_history() -> None:
    """Enable readline history so up/down arrows recall prior shell commands."""
    if readline is None:
        return
    try:
        readline.set_history_length(MAX_HISTORY)
        if os.path.exists(HISTORY_FILE):
            readline.read_history_file(HISTORY_FILE)
    except Exception:
        pass


def _save_readline_history() -> None:
    """Persist command history for the next shell session."""
    if readline is None:
        return
    try:
        readline.write_history_file(HISTORY_FILE)
    except Exception:
        pass

COMMON_UNIX_COMMANDS = {
    "ls", "pwd", "cd", "echo", "cat", "head", "tail", "wc", "mkdir", "rmdir",
    "touch", "rm", "cp", "mv", "find", "grep", "ps", "whoami", "date", "uname",
    "which", "clear", "env", "printenv", "vi", "vim", "nvim", "python", "python3",
    "node", "npm", "yarn", "pnpm", "git", "curl", "wget", "ssh", "scp", "lsb_release",
}

HELP = """Commands:
  :vars    List current variables
  :subs    List registered subroutines
  :debug   Toggle debug logging
  :braket  Toggle bra-ket notation mode (default: XML)
  :shell   Toggle shell mode for running Unix commands directly
  :edit <name>   Open a subroutine in your editor ($EDITOR or vi)
  :save <name> [path]  Save a subroutine to disk
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


def _serialize_subroutine_to_braket(subroutine) -> str:
    """Serialize a registered subroutine in bra-ket notation for editor use."""
    element = subroutine.element
    lines: list[str] = []

    def render(node, indent=0):
        pad = "  " * indent

        if not node.tag:
            if not node.text:
                return
            text = node.text.strip()
            if text:
                lines.append(f"{pad}{text}")
            return

        if node.tag == "subroutine":
            name = node.attributes.get("name") or subroutine.name
            bra = f"{pad}<{name}"
            extras = []
            for key, value in node.attributes.items():
                if key == "name" or value is None:
                    continue
                value_str = str(value)
                if any(ch.isspace() for ch in value_str) or "=" in value_str:
                    extras.append(f"{key}=\"{value_str}\"")
                else:
                    extras.append(f"{key}={value_str}")
            if extras:
                bra += " " + " ".join(extras)
            bra += "|"
            lines.append(bra)
            for child in node.children:
                render(child, indent + 1)
            return

        ket = f"{pad}|{node.tag}"
        extras = []
        for key, value in node.attributes.items():
            if value is None:
                continue
            value_str = str(value)
            if any(ch.isspace() for ch in value_str) or "=" in value_str:
                extras.append(f"{key}=\"{value_str}\"")
            else:
                extras.append(f"{key}={value_str}")
        if extras:
            ket += " " + " ".join(extras)
        ket += ">"

        if node.children:
            lines.append(ket)
            for child in node.children:
                render(child, indent + 1)
            return

        lines.append(ket)

    render(element)
    return "\n".join(lines)


def _find_subroutine(session, name: str):
    for sub in reversed(session.subroutines):
        if sub.name == name:
            return sub
    return None


def _ensure_parent_dir(path: str) -> None:
    directory = os.path.dirname(path)
    if directory and not os.path.exists(directory):
        os.makedirs(directory, exist_ok=True)


def _edit_subroutine_in_editor(session, parser, name: str) -> None:
    subroutine = _find_subroutine(session, name)
    if subroutine is None:
        print(f"Subroutine '{name}' not found in session")
        return

    edited = _serialize_subroutine_to_braket(subroutine)
    editor = os.environ.get("EDITOR") or "vi"

    with tempfile.NamedTemporaryFile("w", suffix=".di", delete=False) as handle:
        handle.write(edited)
        temp_path = handle.name

    try:
        print(f"Opening '{name}' in {editor} ...")
        result = subprocess.run([editor, temp_path], check=False)
        if result.returncode != 0:
            print(f"Editor exited with code {result.returncode}")
            return

        with open(temp_path, "r", encoding="utf-8") as handle:
            new_source = handle.read()

        if not new_source.strip():
            print("No changes saved")
            return

        session.subroutines = [s for s in session.subroutines if s.name != name]
        try:
            ast = parser.parse(new_source)
        except Exception:
            xml_source = BraKetParser().parse(new_source)
            ast = parser.parse(xml_source)
        integrate(session, ast)
        print(f"Updated subroutine '{name}' in session")
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)


def _save_subroutine_to_disk(session, parser, name: str, path: str | None = None) -> None:
    subroutine = _find_subroutine(session, name)
    if subroutine is None:
        print(f"Subroutine '{name}' not found in session")
        return

    if not path:
        base = os.path.expanduser("~/.dirac/lib")
        path = os.path.join(base, f"{name}.di")

    _ensure_parent_dir(path)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(_serialize_subroutine_to_braket(subroutine))

    print(f"Saved subroutine '{name}' to {path}")


def _is_bare_unix_command(line: str) -> bool:
    """Detect a bare shell command in bra-ket mode using a safe allowlist."""
    stripped = line.strip()
    if not stripped or stripped.startswith(":") or stripped.startswith("|") or stripped.startswith("<"):
        return False
    if any(ch in stripped for ch in ("<", ">", "{", "}", "=", "&")):
        return False
    try:
        argv = shlex.split(stripped)
    except ValueError:
        return False
    if not argv:
        return False
    return argv[0] in COMMON_UNIX_COMMANDS


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
    _configure_readline_history()
    session = create_session()
    parser = DiracParser()
    braket_parser = BraKetParser()
    braket_mode = True
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
                if not lines and stripped.startswith(":edit"):
                    parts = stripped.split(maxsplit=1)
                    if len(parts) < 2:
                        print("Usage: :edit <subroutine-name>")
                    else:
                        _edit_subroutine_in_editor(session, parser, parts[1].strip())
                    break
                if not lines and stripped.startswith(":save"):
                    parts = stripped.split(maxsplit=2)
                    if len(parts) < 2:
                        print("Usage: :save <subroutine-name> [path]")
                    else:
                        target = parts[1].strip()
                        out_path = parts[2].strip() if len(parts) > 2 else None
                        _save_subroutine_to_disk(session, parser, target, out_path)
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
                if braket_mode and _is_bare_unix_command(stripped):
                    rc = run_shell_command(stripped)
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

        _save_readline_history()
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
