"""
<load-context> tag - load relevant subroutines from the registry into session.
Mirrors dirac/src/tags/load-context.ts.
"""

from __future__ import annotations

from typing import Any

from ..runtime.session import emit, set_variable
from ..tags.import_tag import execute_import
from ..tags.subroutine_index import registry
from ..types import DiracElement, DiracSession


def execute_load_context(session: DiracSession, element: DiracElement) -> None:
    query = element.attributes.get("query")

    if not query and element.text:
        query = element.text.strip()

    if not query and element.children:
        before = len(session.output)
        for child in element.children:
            from ..runtime.interpreter import integrate

            integrate(session, child)
        child_output = "".join(session.output[before:]).strip()
        session.output = session.output[:before]
        query = child_output

    if not query:
        raise ValueError("<load-context> requires query attribute or text content")

    limit_attr = element.attributes.get("limit")
    should_import = element.attributes.get("import", "true") != "false"
    output_var = element.attributes.get("output")

    stats = registry.get_stats()
    if stats.get("totalSubroutines", 0) == 0:
        emit(session, '[load-context] Registry is empty. Use :index <path> or <index-subroutines path="..."> first.\n')
        return

    limit = int(limit_attr) if limit_attr is not None else 5
    results = registry.search(str(query), limit)

    if not results:
        emit(session, f'[load-context] No subroutines found for query: "{query}". Try indexing more libraries.\n')
        return

    emit(session, f"[load-context] Found {len(results)} subroutine(s): {', '.join(sub.get('name', '') for sub in results)}\n")

    file_map: dict[str, list[dict[str, Any]]] = {}
    for sub in results:
        file_path = str(sub.get("filePath") or "")
        if not file_path:
            continue
        if not file_map.get(file_path):
            file_map[file_path] = []
        file_map[file_path].append(sub)

    emit(session, f"[load-context] Importing {len(file_map)} file(s)...\n")

    if should_import:
        for file_path in list(file_map.keys()):
            try:
                import_path = file_path
                if not import_path.startswith("/"):
                    import_path = str((session.current_file and __import__('os').path.dirname(session.current_file)) or __import__('os').getcwd()) + "/" + import_path
                import_element = DiracElement(tag="import", attributes={"src": import_path}, children=[], text="")
                execute_import(session, import_element)
                emit(session, f"[load-context] ✓ Imported: {file_path}\n")
            except Exception as exc:
                emit(session, f"[load-context] ✗ Failed to import {file_path}: {exc}\n")
    else:
        emit(session, "[load-context] (import=false, not loading files)\n")

    if output_var:
        summary = [
            {
                "name": sub.get("name"),
                "description": sub.get("description"),
                "parameters": [param.get("name") for param in (sub.get("parameters") or [])],
                "filePath": sub.get("filePath"),
            }
            for sub in results
        ]
        set_variable(session, output_var, __import__("json").dumps(summary, indent=2), False)
