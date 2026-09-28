"""
<inspect-subroutines> tag - inspect the nested subroutines declared under a named subroutine.

This is a structural lookup, not execution. It walks the AST of the target subroutine
without invoking its children or body.
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


def _build_sample_call(name: str, sub_element: DiracElement) -> str:
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


def _collect_nested_subroutines(element: DiracElement) -> list[DiracElement]:
    matches: list[DiracElement] = []

    for child in element.children:
        if child.tag == "subroutine":
            matches.append(child)
        matches.extend(_collect_nested_subroutines(child))

    return matches


def _target_subroutine(session: DiracSession, name: str):
    for sub in reversed(session.subroutines):
        if sub.name == name:
            return sub
    return None


def execute_inspect_subroutines(session: DiracSession, element: DiracElement) -> None:
    """Emit nested subroutine definitions within the named parent subroutine."""
    target_name = element.attributes.get("name")
    if not target_name:
        raise ValueError("<inspect-subroutines> requires name attribute")

    target = _target_subroutine(session, str(target_name))
    if target is None:
        emit(session, f'[inspect-subroutines] Subroutine "{target_name}" not found in session.\n')
        return

    nested = _collect_nested_subroutines(target.element)
    unique: dict[str, DiracElement] = {}
    for sub_element in nested:
        name = sub_element.attributes.get("name")
        if not name:
            continue
        unique.setdefault(str(name), sub_element)

    lines = [
        '<!-- Dirac Subroutine Interface (source=memory, scope=nested) -->',
        '<!-- Call convention: use direct tag call -->',
        '<!-- Generic form: <subroutineName required1="..." required2="..." optional1="..." /> -->',
        f'<subroutines source="memory" scope="nested" total="{len(unique)}">',
    ]

    for name, sub_element in unique.items():
        attrs: list[str] = [f'name="{_escape_xml(name)}"']
        description = sub_element.attributes.get("description")
        if description:
            attrs.append(f'description="{_escape_xml(str(description))}"')
        for attr_name, attr_value in sub_element.attributes.items():
            if attr_name.startswith("param-"):
                attrs.append(f'{attr_name}="{_escape_xml(str(attr_value))}"')
        lines.append(f"  <!-- Sample call: {_build_sample_call(name, sub_element)} -->")
        lines.append(f"  <subroutine {' '.join(attrs)} />")

    lines.append("</subroutines>")
    emit(session, "\n".join(lines))
