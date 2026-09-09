"""
Interactive DIRAC shell for the Python runtime.

A minimal REPL: maintains a persistent session across inputs so variables
and subroutines defined in one entry remain available in the next (unlike
the plain CLI, which creates a fresh session per file).

Usage:
    python3 -m dirac.shell
"""

import fnmatch
import os
import re
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


def _complete_path_token(prefix: str) -> list[str]:
    """Return possible file/directory matches for a shell path prefix."""
    if not prefix:
        return []

    expanded = os.path.expanduser(prefix)
    head, tail = os.path.split(expanded)
    if prefix.startswith("~"):
        home_dir = os.path.expanduser("~")
        if prefix.startswith("~/") or prefix == "~":
            search_dir = home_dir if prefix == "~" else head if os.path.isdir(head) else home_dir
            search_prefix = tail or ""
        else:
            search_dir = os.getcwd()
            search_prefix = os.path.basename(prefix)
    elif not head:
        search_dir = os.getcwd()
        search_prefix = tail or ""
    else:
        search_dir = head if os.path.isdir(head) else os.getcwd()
        search_prefix = tail or ""

    try:
        entries = sorted(os.listdir(search_dir))
    except OSError:
        return []

    home_dir = os.path.expanduser("~")
    matches: list[str] = []
    for name in entries:
        if not fnmatch.fnmatch(name, f"{search_prefix}*"):
            continue
        candidate = os.path.join(search_dir, name)

        if prefix.startswith("~/"):
            rel_path = os.path.relpath(candidate, home_dir)
            display = os.path.join("~", rel_path)
        elif prefix.startswith("~"):
            display = name
        elif prefix.startswith("/") or prefix.startswith("./") or prefix.startswith("../"):
            display = name
        else:
            display = name

        if os.path.isdir(candidate):
            display = display + os.sep
        matches.append(display)

    return matches


def _bra_ket_tag_completion(session: DiracSession, text: str) -> list[str]:
    """Suggest known bra-ket tag names and subroutine names when typing |tag."""
    if not text:
        return []

    tag_prefix = text.strip()
    if not tag_prefix.startswith("|"):
        return []

    partial = tag_prefix[1:]
    if not partial:
        return []

    candidate_names = []
    for sub in getattr(session, "subroutines", []):
        name = getattr(sub, "name", None)
        if name and str(name).lower().startswith(partial.lower()):
            candidate_names.append(name)

    builtin_names = [
        "defvar", "variable", "assign", "output", "subroutine", "call",
        "parameters", "loop", "foreach", "break", "if", "test-if", "eval",
        "python", "system", "input", "return", "import", "llm"
    ]
    for name in builtin_names:
        if name.lower().startswith(partial.lower()):
            candidate_names.append(name)

    unique_names = []
    seen = set()
    for name in candidate_names:
        key = name.lower()
        if key not in seen:
            seen.add(key)
            unique_names.append(name)

    completions: list[str] = []
    for name in sorted(unique_names):
        sub = next((s for s in getattr(session, "subroutines", []) if getattr(s, "name", None) == name), None)
        params = getattr(sub, "parameters", []) if sub else []
        if params:
            completions.append(f"|{name} ")
        else:
            completions.append(f"|{name}>")
    return completions


def _native_tag_metadata() -> dict[str, list[dict[str, str]]]:
    """Load the authoritative built-in tag interface from native-tags.di."""
    package_root = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.dirname(package_root)
    parent_root = os.path.dirname(repo_root)

    candidates = [
        os.path.expanduser("~/dirac/lib/native-tags.di"),
        os.path.join(os.path.expanduser("~"), ".dirac", "lib", "native-tags.di"),
        os.path.join(parent_root, "dirac", "lib", "native-tags.di"),
        os.path.join(repo_root, "lib", "native-tags.di"),
        os.path.join(package_root, "../lib/native-tags.di"),
    ]

    for candidate in candidates:
        resolved = os.path.abspath(os.path.expanduser(candidate))
        if not os.path.exists(resolved):
            continue
        try:
            with open(resolved, "r", encoding="utf-8") as handle:
                source = handle.read()
        except OSError:
            continue

        metadata: dict[str, list[dict[str, str]]] = {}
        for match in re.finditer(r'<subroutine\s+name="([^"]+)"([^>]*)>', source, flags=re.DOTALL):
            name = match.group(1).strip()
            attrs = match.group(2)
            params = []
            for key, value in re.findall(r'(param-[A-Za-z0-9_-]+)="([^"]*)"', attrs):
                param_name = key[5:]
                label = param_name.replace("-", "")
                params.append({"name": label, "description": value})
            if params:
                metadata[name] = params
        if metadata:
            return metadata
    return {}


def _tag_parameter_suggestions(session: DiracSession, tag_name: str, prefix: str = "") -> list[str]:
    """Return parameter names for a tag, mixing session subroutines and native tag metadata."""
    metadata = _native_tag_metadata()
    params_by_name: dict[str, list[dict[str, str]]] = {}

    for sub in getattr(session, "subroutines", []):
        name = getattr(sub, "name", None)
        if name:
            params_by_name[name] = list(getattr(sub, "parameters", []) or [])

    for name, params in metadata.items():
        params_by_name.setdefault(name, params)

    params = params_by_name.get(tag_name, [])
    if not params:
        return []

    items = [str(p.get("name", "")) for p in params if str(p.get("name", "")).strip()]
    if not prefix:
        return [f"{item}=" for item in items]
    return [f"{item}=" for item in items if item.lower().startswith(prefix.lower())]


def _tag_name_suggestions(session: DiracSession, partial: str) -> list[str]:
    """Return known tag names matching a partial bra-ket prefix."""
    if not partial:
        return []

    names = set()
    for sub in getattr(session, "subroutines", []):
        name = getattr(sub, "name", None)
        if name:
            names.add(str(name))

    metadata = _native_tag_metadata()
    names.update(metadata.keys())

    builtin_names = [
        "defvar", "variable", "assign", "output", "subroutine", "call",
        "parameters", "loop", "foreach", "break", "if", "test-if", "eval",
        "python", "system", "input", "return", "import", "llm"
    ]
    names.update(builtin_names)

    matches = sorted(name for name in names if name.lower().startswith(partial.lower()))
    completions: list[str] = []
    for name in matches:
        params = _tag_parameter_suggestions(session, name)
        completions.append(f"|{name} " if params else f"|{name}>")
    return completions


def _emit_tag_parameter_help(tag_name: str, session: DiracSession) -> None:
    """Print parameter names/descriptions like the TypeScript shell does."""
    metadata = _native_tag_metadata()
    params_by_name: dict[str, list[dict[str, str]]] = {}
    for sub in getattr(session, "subroutines", []):
        name = getattr(sub, "name", None)
        if name:
            params_by_name[name] = list(getattr(sub, "parameters", []) or [])
    params_by_name.update(metadata)

    params = params_by_name.get(tag_name, [])
    if not params:
        return

    print()
    for param in params:
        name = str(param.get("name", "")).strip()
        if not name:
            continue
        description = str(param.get("description", "")).strip()
        suffix = f" ({description})" if description else ""
        print(f"  {name}={suffix}")


def _bra_ket_attribute_completion(session: DiracSession, text: str) -> list[str]:
    """Suggest remaining parameter names for an existing bra-ket tag while typing attributes."""
    match = re.search(r"\|([A-Za-z0-9_-]+)\s+(.*)$", text)
    if not match:
        return []

    tag_name = match.group(1)
    rest = match.group(2).strip()
    if not rest:
        return _tag_parameter_suggestions(session, tag_name, "")

    tokens = [token for token in rest.split() if token]
    if not tokens:
        return []

    used_names = set()
    for token in tokens[:-1]:
        name = token.split("=", 1)[0].strip()
        if name:
            used_names.add(name.lower())

    last_token = tokens[-1].strip()
    partial = last_token.split("=", 1)[0].strip()

    metadata = _native_tag_metadata()
    params_by_name: dict[str, list[dict[str, str]]] = {}
    for sub in getattr(session, "subroutines", []):
        name = getattr(sub, "name", None)
        if name:
            params_by_name[name] = list(getattr(sub, "parameters", []) or [])
    params_by_name.update(metadata)

    params = params_by_name.get(tag_name, [])
    if not params:
        return []

    items = [str(p.get("name", "")) for p in params if str(p.get("name", "")).strip()]
    suggestions = []
    for item in items:
        lower = item.lower()
        if lower in used_names:
            continue
        if not partial or lower.startswith(partial.lower()):
            suggestions.append(f"{item}=")
    return suggestions


def _path_value_completion(text: str) -> list[str]:
    """Handle filesystem completion when a shell value, attribute value, or command arg is a path."""
    if not text:
        return []

    path_match = re.search(r'(?:(?<=^)|(?<=\s)|(?<=\=))((?:\.?\.?/|~/?|/)[^\s]*)$', text)
    if not path_match:
        return []

    partial = path_match.group(1)
    if partial.startswith("="):
        partial = partial[1:]
    if not partial:
        return []
    return _complete_path_token(partial)


def _readline_completer(text: str, state: int, session: DiracSession | None = None) -> str | None:
    """Provide shell-like path and bra-ket completion for readline in the interactive shell."""
    if text is None:
        return None

    if session is None:
        session = create_session()

    full_buffer = ""
    if hasattr(readline, "get_line_buffer"):
        try:
            full_buffer = readline.get_line_buffer()
        except Exception:
            full_buffer = ""

    active_text = text
    if full_buffer and full_buffer.strip():
        if full_buffer.strip().startswith("|") or "=" in full_buffer or full_buffer.strip().startswith(("cd ", "ls ", "cat ", "vim ", "nano ")):
            active_text = full_buffer.strip()

    exact_tag_name = re.search(r"\|([A-Za-z0-9_-]+)$", active_text)
    if exact_tag_name:
        partial = exact_tag_name.group(1)
        tag_matches = _tag_name_suggestions(session, partial)
        if tag_matches:
            if state < len(tag_matches):
                completion = tag_matches[state]
                if state == 0 and completion.startswith(f"|{partial} "):
                    tag_name = partial
                    if tag_name in _native_tag_metadata() or any(getattr(sub, "name", None) == tag_name for sub in getattr(session, "subroutines", [])):
                        _emit_tag_parameter_help(tag_name, session)
                return completion
            return None

    path_matches = _path_value_completion(active_text)
    if path_matches:
        if state < len(path_matches):
            return path_matches[state]
        return None

    bra_ket_matches = _bra_ket_attribute_completion(session, active_text)
    if bra_ket_matches:
        tag_name_match = re.search(r"\|([A-Za-z0-9_-]+)\s+", active_text)
        if state == 0 and tag_name_match:
            current_attr = active_text.rsplit(" ", 1)[-1].strip()
            if not current_attr:
                _emit_tag_parameter_help(tag_name_match.group(1), session)
        if state < len(bra_ket_matches):
            return bra_ket_matches[state]
        return None

    tag_name_match = re.search(r"\|([A-Za-z0-9_-]+)\s+", active_text)
    if state == 0 and tag_name_match:
        current_attr = active_text.rsplit(" ", 1)[-1].strip()
        if not current_attr:
            _emit_tag_parameter_help(tag_name_match.group(1), session)

    token = active_text.rsplit(None, 1)[-1] if " " in active_text else active_text
    matches = _complete_path_token(token)
    if not matches:
        return None
    if state < len(matches):
        return matches[state]
    return None


def _configure_readline_completion(session: DiracSession | None = None) -> None:
    """Enable tab completion for file and directory names in shell mode."""
    if readline is None:
        return
    try:
        current_session = session or create_session()
        readline.set_completer(lambda text, state, current_session=current_session: _readline_completer(text, state, current_session))
        readline.set_completer_delims(" \t\n=")
        readline.parse_and_bind("tab: complete")
        readline.parse_and_bind("bind ^I rl_complete")
    except Exception:
        pass


def _load_source(session: DiracSession, parser: DiracParser, braket_parser: BraKetParser, source: str) -> str:
    """Parse and execute a DIRAC source string, returning any emitted output."""
    before = len(session.output)
    try:
        ast = parser.parse(source)
    except Exception:
        ast = parser.parse(braket_parser.parse(source))
    integrate(session, ast)
    return "".join(session.output[before:]).strip()


def _find_shell_init_script() -> str | None:
    """Return the project-local init script first, then user and packaged fallbacks."""
    package_root = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.dirname(package_root)
    parent_root = os.path.dirname(repo_root)

    candidates: list[str] = []
    candidates.append(os.path.join(repo_root, "shell-init.di"))

    home_dir = os.path.expanduser("~")
    user_dir = os.path.join(home_dir, ".dirac")
    candidates.append(os.path.join(user_dir, "shell-init.di"))
    candidates.append(os.path.join(parent_root, "dirac", "lib", "shell-init.di"))
    candidates.append(os.path.join(repo_root, "lib", "shell-init.di"))
    candidates.append(os.path.join(package_root, "../lib/shell-init.di"))
    candidates.append(os.path.join(package_root, "lib/shell-init.di"))

    for candidate in candidates:
        resolved = os.path.abspath(os.path.expanduser(candidate))
        if os.path.exists(resolved):
            return resolved
    return None


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


def _normalize_question_mark_input(value: str, target: str | None = None) -> str:
    """Map ? shorthand to a configurable ket tag like |ai>prompt or |helper>prompt."""
    trimmed = value.strip()
    if not trimmed.startswith("?"):
        return value
    rest = trimmed[1:].strip()
    target_name = (target or "ai").strip() or "ai"
    return f"|{target_name}>{rest}" if rest else f"|{target_name}>"


def _is_likely_natural_language(line: str) -> bool:
    """Heuristic for natural-language prompts in braket mode."""
    stripped = line.strip()
    if not stripped or stripped.startswith(":") or stripped.startswith("|") or stripped.startswith("<"):
        return False
    if stripped.startswith("?"):
        return True
    lowered = stripped.lower()
    if lowered.endswith("?"):
        return True
    starters = (
        "what", "why", "how", "where", "when", "which", "who", "can", "could",
        "would", "should", "please", "may", "might", "do", "does", "did",
        "is", "are", "was", "were", "will", "shall", "tell", "explain",
        "summarize", "show", "list", "find", "generate", "write", "create",
        "debug", "help",
    )
    return bool(re.match(rf"^(?:{'|'.join(starters)})\b", lowered))


def _should_fallback_to_ai(session: DiracSession, line: str) -> bool:
    """Return True when a braket-shell prompt should turn into a configured AI tag."""
    stripped = line.strip()
    if not stripped or stripped.startswith(":") or stripped.startswith("|") or stripped.startswith("<"):
        return False
    if _is_bare_unix_command(stripped):
        return False
    target = getattr(session, "question_mark_target", "ai") or "ai"
    if stripped.startswith("?"):
        return True
    return _is_likely_natural_language(stripped) and not any(ch in stripped for ch in ("<", ">", "=", "&"))


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


def _expand_user_home_in_command(command: str) -> str:
    """Expand '~' in shell commands to the user home directory."""
    if "~" not in command:
        return command

    def replace_home(match: re.Match[str]) -> str:
        return os.path.expanduser(match.group(0))

    return re.sub(r"(?<![A-Za-z0-9_])~(?=/|$|\s)", lambda _: os.path.expanduser("~"), command)


def run_shell_command(command: str) -> int:
    """Run a shell command in the current working directory and keep `cd` state."""
    stripped = command.strip()
    if stripped.startswith("cd"):
        rest = stripped[2:].strip()
        target = rest or os.path.expanduser("~")
        target = os.path.expanduser(target)
        try:
            os.chdir(target)
            return 0
        except OSError as exc:
            print(f"cd: {exc}")
            return 1

    expanded_command = _expand_user_home_in_command(command)
    try:
        completed = subprocess.run(expanded_command, shell=True, capture_output=False, text=True)
        return completed.returncode
    except KeyboardInterrupt:
        return 130


def run() -> None:
    _configure_readline_history()
    session = create_session()
    _configure_readline_completion(session)
    parser = DiracParser()
    braket_parser = BraKetParser()
    braket_mode = True
    shell_mode = False

    init_script = _find_shell_init_script()
    if init_script:
        try:
            with open(init_script, "r", encoding="utf-8") as handle:
                init_source = handle.read()
            if init_source.strip():
                init_output = _load_source(session, parser, braket_parser, init_source)
                if init_output:
                    print(init_output)
        except Exception:
            pass

    for candidate in (
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", "dirac", "lib", "ai.di"),
        os.path.join(os.path.expanduser("~"), ".dirac", "lib", "user", "sys-router.di"),
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", "dirac", "lib", "sys-router.di"),
    ):
        resolved = os.path.abspath(os.path.expanduser(candidate))
        if not os.path.exists(resolved):
            continue
        try:
            with open(resolved, "r", encoding="utf-8") as handle:
                imported_source = handle.read()
            if imported_source.strip():
                import_output = _load_source(session, parser, braket_parser, imported_source)
                if import_output:
                    print(import_output)
        except Exception:
            pass

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
                if braket_mode and _should_fallback_to_ai(session, stripped):
                    lines.append(_normalize_question_mark_input(stripped, getattr(session, "question_mark_target", "ai")))
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
