"""
<available-subroutines> tag - list the subroutines currently visible in scope.
Mirrors dirac/src/tags/available-subroutines.ts.

This is not a global registry dump; it answers: "what subroutines are callable
from the current boundary?"
"""

from __future__ import annotations

from typing import Any

from ..runtime.session import emit
from ..types import DiracElement, DiracSession


def _escape_xml(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def _sample_value_for_type(type_name: str | None) -> str:
    normalized = (type_name or "").lower()
    if normalized in {"number", "integer", "float"}:
        return "1"
    if normalized == "boolean":
        return "true"
    if normalized in {"json", "object"}:
        return "{}"
    return "value"


def _build_sample_call_from_element(name: str, sub_element: DiracElement) -> str:
    required_args: list[str] = []

    for attr_name, attr_value in sub_element.attributes.items():
        if not attr_name.startswith("param-"):
            continue

        param_name = attr_name[len("param-") :]
        parts = str(attr_value).split(":")
        param_type = parts[0] if parts and parts[0] else "string"
        required = any(part.strip().lower() == "required" for part in parts)

        if required:
            required_args.append(f'{param_name}="{_sample_value_for_type(param_type)}"')

    return f"<{name} {' '.join(required_args)} />" if required_args else f"<{name} />"


def execute_available_subroutines(session: DiracSession, element: DiracElement) -> None:
    """Emit the subroutines visible in the current scope.

    This mirrors the Node.js implementation's boundary logic:
    - start from the stack top,
    - walk backwards to the current subBoundary,
    - skip the current subroutine itself,
    - keep only the most recent definition of each subroutine name.
    """
    available: dict[str, DiracElement] = {}

    current_subroutine_name = None
    if session.sub_boundary > 0 and session.sub_boundary <= len(session.subroutines):
        current_subroutine_name = session.subroutines[session.sub_boundary - 1].name

    for i in range(len(session.subroutines) - 1, session.sub_boundary - 1, -1):
        sub = session.subroutines[i]

        if sub.name == current_subroutine_name:
            continue

        if sub.name not in available:
            available[sub.name] = sub.element

    lines = [
        '<!-- Dirac Subroutine Interface (source=memory, scope=available) -->',
        '<!-- Call convention: use direct tag call -->',
        '<!-- Generic form: <subroutineName required1="..." required2="..." optional1="..." /> -->',
        f'<subroutines source="memory" scope="available" total="{len(available)}">',
    ]

    for name, sub_element in available.items():
        attrs: list[str] = [f'name="{_escape_xml(name)}"']

        lines.append(f"  <!-- Sample call: {_build_sample_call_from_element(name, sub_element)} -->")

        description = sub_element.attributes.get("description")
        if description:
            attrs.append(f'description="{_escape_xml(str(description))}"')

        for attr_name, attr_value in sub_element.attributes.items():
            if attr_name.startswith("param-"):
                attrs.append(f'{attr_name}="{_escape_xml(str(attr_value))}"')

        lines.append(f"  <subroutine {' '.join(attrs)} />")

    lines.append("</subroutines>")
    emit(session, "\n".join(lines))
