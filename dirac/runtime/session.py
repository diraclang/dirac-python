"""
Session management for the DIRAC Python runtime.
Mirrors dirac/src/runtime/session.ts from the Node.js reference implementation.
"""

import re
from typing import Any, Optional

from ..types import DiracElement, DiracSession, Subroutine, Variable

# --- Session lifecycle -------------------------------------------------


def create_session(debug: bool = False) -> DiracSession:
    return DiracSession(debug=debug)


# --- Variable management (maps to var_info functions in MASK) ----------


def set_variable(session: DiracSession, name: str, value: Any, visible: bool = False) -> None:
    # First, check if the variable exists in the current scope (from
    # var_boundary onward) and update it. Search from the end to find the
    # most recent instance.
    for i in range(len(session.variables) - 1, session.var_boundary - 1, -1):
        existing = session.variables[i]
        if existing.name == name:
            existing.value = value
            existing.visible = visible
            return

    # Not in current scope - check parent scopes (might be a parameter).
    for i in range(session.var_boundary - 1, -1, -1):
        existing = session.variables[i]
        if existing.name == name:
            existing.value = value
            existing.visible = visible
            return

    # Variable doesn't exist anywhere - create a new one in the current scope.
    session.variables.append(
        Variable(
            name=name,
            value=value,
            visible=visible,
            boundary=1 if visible else 0,
        )
    )


def get_variable(session: DiracSession, name: str) -> Any:
    # Search from the end (most recent) to the beginning.
    for v in reversed(session.variables):
        if v.name == name:
            return v.value
    return None


def has_variable(session: DiracSession, name: str) -> bool:
    return any(v.name == name for v in session.variables)


def set_boundary(session: DiracSession) -> int:
    """Set boundary marker for local variables. Returns the previous boundary."""
    old_boundary = session.var_boundary
    session.var_boundary = len(session.variables)
    return old_boundary


def pop_to_boundary(session: DiracSession) -> None:
    """Pop variables back to boundary (discard local scope entirely)."""
    session.variables = session.variables[: session.var_boundary]


def clean_to_boundary(session: DiracSession, keep_visible: bool = False) -> None:
    """Clean private variables but keep visible ones (if keep_visible)."""
    kept = list(session.variables[: session.var_boundary])

    for v in session.variables[session.var_boundary :]:
        if keep_visible:
            # Keep the variable in the caller scope; it is removed when that
            # caller's own cleanup runs, unless that caller is also visible.
            v.boundary = 0
            kept.append(v)
        # Non-visible variables are discarded (not added to kept).

    session.variables = kept
    # var_boundary intentionally left unchanged - it stays at the current level.


# --- Subroutine management ---------------------------------------------


def register_subroutine(
    session: DiracSession,
    name: str,
    element: DiracElement,
    description: Optional[str] = None,
    parameters: Optional[list] = None,
    meta: Optional[dict] = None,
    visible: bool = False,
    source_path: Optional[str] = None,
) -> None:
    session.subroutines.append(
        Subroutine(
            name=name,
            element=element,
            boundary=1 if visible else 0,
            visible=visible,
            description=description,
            parameters=parameters or [],
            meta=meta or {},
            source_path=source_path,
        )
    )


def get_subroutine(session: DiracSession, name: str) -> Optional[Subroutine]:
    for sub in reversed(session.subroutines):
        if sub.name == name:
            return sub
    return None


def clean_subroutines_to_boundary(
    session: DiracSession,
    caller_subroutine: Optional[Subroutine] = None,
    call_element: Optional[DiracElement] = None,
) -> None:
    """
    Clean up subroutines registered during a call, honoring visible="subroutine"|"both"|"true".
    Call-time visible attribute (on the call element) takes precedence over
    the subroutine definition's own visible attribute.
    """
    visible_value = "false"
    if caller_subroutine is not None:
        visible_value = caller_subroutine.element.attributes.get("visible", "false")
    if call_element is not None and call_element.attributes.get("visible"):
        visible_value = call_element.attributes["visible"]

    keep_nested = visible_value in ("subroutine", "both", "true")

    if keep_nested:
        # Promote nested subroutines up one boundary level.
        kept = list(session.subroutines[: session.sub_boundary])
        for sub in session.subroutines[session.sub_boundary :]:
            if sub.boundary > 0:
                sub.boundary -= 1
            kept.append(sub)
        session.subroutines = kept
        # sub_boundary intentionally left unchanged.
    else:
        session.subroutines = session.subroutines[: session.sub_boundary]


# --- Parameter stack (for subroutine calls) -----------------------------


def push_parameters(session: DiracSession, params: list) -> None:
    session.parameter_stack.append(params)


def pop_parameters(session: DiracSession) -> Optional[list]:
    if session.parameter_stack:
        return session.parameter_stack.pop()
    return None


def get_current_parameters(session: DiracSession) -> Optional[list]:
    if session.parameter_stack:
        return session.parameter_stack[-1]
    return None


# --- Variable substitution (maps to var_replace functions in MASK) -----

_BRACE_VAR_RE = re.compile(r"\$\{(\w+)\}")
_DOLLAR_VAR_RE = re.compile(r"\$(\w+)")


def substitute_attribute(session: DiracSession, value: Any) -> Any:
    """Substitute both $var and ${var} in a string using session variables."""
    if not isinstance(value, str):
        return value

    def replace(match: "re.Match[str]") -> str:
        var_name = match.group(1)
        v = get_variable(session, var_name)
        return str(v) if v is not None else match.group(0)

    value = _BRACE_VAR_RE.sub(replace, value)
    value = _DOLLAR_VAR_RE.sub(replace, value)
    return value


def substitute_variables(session: DiracSession, text: str) -> str:
    """
    Decode XML/HTML entities only; do NOT substitute variables globally.
    This mirrors the (perhaps surprising) Node.js behavior where
    substitute_variables and substitute_attribute are NOT the same thing:
    only substitute_attribute performs $var/${var} replacement.
    """
    return (
        text.replace("&#10;", "\n")
        .replace("&#13;", "\r")
        .replace("&#9;", "\t")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&amp;", "&")
        .replace("&quot;", '"')
        .replace("&apos;", "'")
    )


# --- Output management ---------------------------------------------------


def emit(session: DiracSession, content: Any) -> None:
    session.output.append(str(content))


def get_output(session: DiracSession) -> str:
    return "".join(session.output)


def set_output_boundary(session: DiracSession) -> int:
    old_boundary = session.output_boundary
    session.output_boundary = len(session.output)
    return old_boundary


def capture_output_from_boundary(session: DiracSession) -> str:
    return "".join(session.output[session.output_boundary :])


def pop_output_to_boundary(session: DiracSession) -> None:
    session.output = session.output[: session.output_boundary]


def pop_and_capture_output(session: DiracSession) -> str:
    captured = capture_output_from_boundary(session)
    pop_output_to_boundary(session)
    return captured
