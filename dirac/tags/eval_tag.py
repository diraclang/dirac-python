"""
<eval> tag - execute Python code with access to session variables.
This replaces the Node.js implementation's JavaScript <eval> tag: DIRAC
Python uses Python itself for scripting blocks (no separate <python> tag
needed, unlike the Node.js runtime which shells out to a python3 subprocess).

Supports two modes, mirroring dirac/src/tags/python.ts:
  - Code containing a top-level `return` is wrapped in a function and
    called; the return value becomes the `result` variable.
  - Code without `return` is executed directly, and (if `result` is
    given) the value is read back from a variable of that name in the
    executed namespace.
"""

import json
import re
import textwrap

from ..runtime.session import get_variable, set_variable
from ..types import DiracElement, DiracSession

_HAS_RETURN_RE = re.compile(r"^\s*return\b", re.MULTILINE)


def _dedent(text: str) -> str:
    return textwrap.dedent(text).strip("\n")


def execute_eval(session: DiracSession, element: DiracElement) -> None:
    name = element.attributes.get("result") or element.attributes.get("name")
    expr_attr = element.attributes.get("expr")

    if expr_attr:
        code = expr_attr
    elif element.text:
        code = element.text
    else:
        raise ValueError("<eval> requires expr attribute or text content")

    code = _dedent(code)

    if session.debug:
        print(f"[EVAL] Code:\n{code}\n")

    # Build execution namespace from all session variables, auto-parsing
    # JSON-looking strings into dicts/lists (matches the Node.js behavior).
    namespace: dict = {}
    for v in session.variables:
        value = v.value
        if isinstance(value, str):
            trimmed = value.strip()
            if (trimmed.startswith("{") and trimmed.endswith("}")) or (
                trimmed.startswith("[") and trimmed.endswith("]")
            ):
                try:
                    value = json.loads(trimmed)
                except (json.JSONDecodeError, ValueError):
                    pass
        namespace[v.name] = value

    namespace["get_variable"] = lambda n: get_variable(session, n)
    namespace["set_variable"] = lambda n, val, visible=False: set_variable(session, n, val, visible)
    namespace["session"] = session

    has_return = bool(_HAS_RETURN_RE.search(code))

    try:
        if has_return and name:
            indented = "\n".join("    " + line for line in code.split("\n"))
            wrapper = f"def __dirac_function():\n{indented}\n"
            exec(wrapper, namespace)  # noqa: S102 - controlled DIRAC eval sandboxing
            result = namespace["__dirac_function"]()
            set_variable(session, name, result, False)
        else:
            exec(code, namespace)  # noqa: S102 - controlled DIRAC eval sandboxing
            if name:
                if name not in namespace:
                    raise NameError(f"Variable '{name}' not defined in eval code")
                set_variable(session, name, namespace[name], False)
    except Exception as exc:  # noqa: BLE001 - surface as a DIRAC runtime error
        raise RuntimeError(f"Eval error: {exc}") from exc
