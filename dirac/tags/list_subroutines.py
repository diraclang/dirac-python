"""
<list-subroutines> tag - list all registered subroutines.
Mirrors the Node.js implementation in dirac/src/tags/list-subroutines.ts.
"""

from __future__ import annotations

from typing import Any

from ..runtime.session import emit, get_output, set_variable
from ..types import DiracElement, DiracSession


def _format_xml(subroutines: list[dict[str, Any]]) -> str:
    lines = [
        "<!-- Dirac Subroutine Interface (source=memory, scope=all) -->",
        "<!-- Call convention: use direct tag call -->",
        "<!-- Generic form: <subroutineName required1=\"...\" required2=\"...\" optional1=\"...\" /> -->",
        f'<subroutines source="memory" scope="all" total="{len(subroutines)}">',
    ]

    for sub in subroutines:
        sample_call = _build_sample_call_from_metadata(sub)
        lines.append(f"  <!-- Sample call: {sample_call} -->")

        attrs: list[str] = [f'name="{_escape_xml(str(sub.get("name", "")))}"']
        if sub.get("description"):
            attrs.append(f'description="{_escape_xml(str(sub["description"]))}"')

        for param in sub.get("parameters") or []:
            metadata = [param.get("type") or "any"]
            if param.get("required"):
                metadata.append("required")
            if param.get("description"):
                metadata.append(param["description"])
            attrs.append(f'param-{param["name"]}="{_escape_xml(":".join(metadata))}"')

        lines.append(f"  <subroutine {' '.join(attrs)} />")

    lines.append("</subroutines>")
    return "\n".join(lines)


def _format_text(subroutines: list[dict[str, Any]]) -> str:
    lines = ["Available subroutines:\n"]
    for sub in subroutines:
        lines.append(f"{sub['name']}(")

        params = sub.get("parameters") or []
        if params:
            for param in params:
                required = " [required]" if param.get("required") else ""
                desc = f" - {param['description']}" if param.get("description") else ""
                lines.append(f"  {param['name']}: {param.get('type') or 'any'}{required}{desc}")

        lines.append(")")
        if sub.get("description"):
            lines.append(f" - {sub['description']}")
        lines.append("\n")

    return "\n".join(lines)


def _format_braket(subroutines: list[dict[str, Any]]) -> str:
    lines = ["Available subroutines:\n"]
    for sub in subroutines:
        params = sub.get("parameters") or []
        formatted_params = " ".join(
            f"{param['name']}={param.get('type') or 'any'}" for param in params
        )
        bra_line = f"<{sub['name']} {formatted_params}|" if formatted_params else f"<{sub['name']}|"
        lines.append(bra_line)
        if sub.get("description"):
            lines.append(f"  {sub['description']}")
        lines.append("")
    return "\n".join(lines)


def _build_sample_call_from_metadata(sub: dict[str, Any]) -> str:
    attrs: list[str] = []
    for param in sub.get("parameters") or []:
        if not param.get("required"):
            continue
        attrs.append(f'{param["name"]}="{_sample_value_for_type(param.get("type"))}"')
    return f'<{sub["name"]} {' '.join(attrs)} />' if attrs else f'<{sub["name"]} />'


def _sample_value_for_type(type_name: str | None) -> str:
    normalized = (type_name or "").lower()
    if normalized in {"number", "integer", "float"}:
        return "1"
    if normalized == "boolean":
        return "true"
    if normalized in {"json", "object"}:
        return "{}"
    return "value"


def _escape_xml(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def execute_list_subroutines(session: DiracSession, element: DiracElement) -> None:
    format_name = str(element.attributes.get("format") or "xml")
    output_var = element.attributes.get("output")

    subroutines = []
    for sub in session.subroutines:
        subroutines.append(
            {
                "name": sub.name,
                "description": sub.description,
                "parameters": sub.parameters,
                "meta": sub.meta,
                "boundary": sub.boundary,
            }
        )

    if format_name == "braket":
        result = _format_braket(subroutines)
    elif format_name == "xml":
        result = _format_xml(subroutines)
    elif format_name == "json":
        import json as json_module

        result = json_module.dumps(subroutines, indent=2)
    else:
        result = _format_text(subroutines)

    if output_var:
        set_variable(session, output_var, result, False)
    else:
        emit(session, result)
