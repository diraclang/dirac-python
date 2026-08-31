"""
<system> tag - execute shell commands (synchronous; background/detached
mode is not yet ported - see README "Known Limitations").
Mirrors the foreground path of dirac/src/tags/system.ts.
"""

import subprocess

from ..runtime.session import emit, set_variable, substitute_attribute
from ..types import DiracElement, DiracSession


def execute_system(session: DiracSession, element: DiracElement) -> None:
    has_element_children = any(child.tag != "" for child in element.children)

    if has_element_children:
        from ..runtime.interpreter import integrate

        before_output = len(session.output)
        for child in element.children:
            integrate(session, child)
        command = "".join(session.output[before_output:])
        del session.output[before_output:]
    elif element.text:
        command = substitute_attribute(session, element.text)
    else:
        raise ValueError("<system> requires command content")

    if not command.strip():
        return

    result_var = element.attributes.get("result")
    silent = element.attributes.get("silent") == "true"

    if session.debug:
        print(f"[SYSTEM] Executing: {command}")

    completed = subprocess.run(
        command, shell=True, capture_output=True, text=True, check=False
    )

    stdout = completed.stdout or ""

    if result_var:
        set_variable(session, result_var, stdout, False)
        if not silent:
            emit(session, stdout)
    else:
        emit(session, stdout)

    if completed.returncode != 0:
        stderr = completed.stderr or ""
        raise RuntimeError(f"<system> command failed ({completed.returncode}): {stderr.strip()}")
