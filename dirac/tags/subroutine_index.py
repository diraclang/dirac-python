"""
<index-subroutines> and <search-subroutines> tags.
Mirrors the Node.js registry/search implementation in dirac/src/tags/subroutine-index.ts.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from ..runtime.parser import DiracParser
from ..runtime.session import emit, set_variable
from ..types import DiracElement, DiracSession


@dataclass
class SubroutineMetadata:
    name: str
    description: Optional[str] = None
    parameters: list[dict[str, Any]] = field(default_factory=list)
    file_path: str = ""
    source_code: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
            "filePath": self.file_path,
            "sourceCode": self.source_code,
        }


class SubroutineRegistry:
    _instance: Optional["SubroutineRegistry"] = None

    def __new__(cls, index_path: Optional[str] = None):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.index_path = index_path or str(Path.home() / ".dirac" / "subroutine-index.json")
            cls._instance.index = {"subroutines": [], "lastUpdated": 0}
            cls._instance._load_index()
        return cls._instance

    def _load_index(self) -> None:
        path = Path(self.index_path)
        if path.exists():
            try:
                with path.open("r", encoding="utf-8") as handle:
                    data = json.load(handle)
                self.index = data if isinstance(data, dict) else {"subroutines": [], "lastUpdated": 0}
            except Exception:
                self.index = {"subroutines": [], "lastUpdated": 0}
        else:
            self.index = {"subroutines": [], "lastUpdated": 0}

    def _save_index(self) -> None:
        path = Path(self.index_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.index["lastUpdated"] = __import__("time").time()
        with path.open("w", encoding="utf-8") as handle:
            json.dump(self.index, handle, indent=2)

    def index_directory(self, dir_path: str) -> int:
        resolved = Path(dir_path)
        if not resolved.is_absolute():
            resolved = (Path.cwd() / resolved).resolve()

        count = 0
        for file_path in sorted(resolved.rglob("*.di")):
            count += self.index_file(str(file_path))
        self._save_index()
        return count

    def index_file(self, file_path: str) -> int:
        try:
            with open(file_path, "r", encoding="utf-8") as handle:
                content = handle.read()
            parser = DiracParser()
            ast = parser.parse(content)
        except Exception:
            return 0

        self.index["subroutines"] = [
            sub for sub in self.index["subroutines"] if sub.get("filePath") != file_path
        ]

        subroutines = self._extract_subroutines(ast, file_path)
        self.index["subroutines"].extend(sub.to_dict() for sub in subroutines)
        self._save_index()
        return len(subroutines)

    def _extract_subroutines(self, element: DiracElement, file_path: str) -> list[SubroutineMetadata]:
        results: list[SubroutineMetadata] = []

        if element.tag == "subroutine":
            name = element.attributes.get("name")
            if name:
                metadata = SubroutineMetadata(
                    name=name,
                    description=element.attributes.get("description"),
                    parameters=[],
                    file_path=file_path,
                    source_code="",
                )

                for attr_name, attr_value in element.attributes.items():
                    if attr_name.startswith("param-"):
                        param_name = attr_name[len("param-") :]
                        parts = str(attr_value).split(":")
                        param_type = parts[0] if parts and parts[0] else "string"
                        is_required = any(part.strip().lower() == "required" for part in parts[1:])
                        description = parts[2] if len(parts) > 2 else None
                        meta = {"name": param_name, "type": param_type, "required": is_required}
                        if description:
                            meta["description"] = description
                        metadata.parameters.append(meta)

                results.append(metadata)

        for child in element.children:
            results.extend(self._extract_subroutines(child, file_path))

        return results

    def search(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        lower_query = query.lower()
        tokens = [token for token in re_split_tokens(lower_query) if token]

        results: list[tuple[dict[str, Any], int]] = []
        for sub in self.index.get("subroutines", []):
            name = str(sub.get("name", ""))
            description = str(sub.get("description") or "")
            lower_name = name.lower()
            lower_desc = description.lower()

            score = 0
            name_tokens = [token for token in re_split_tokens(lower_name) if token]
            desc_tokens = [token for token in re_split_tokens(lower_desc) if token]

            if lower_name == lower_query:
                score += 100
            elif lower_name.startswith(lower_query):
                score += 50
            elif lower_query in lower_name:
                score += 40
            elif lower_query in lower_desc:
                score += 30

            token_match_count = 0
            for token in tokens:
                if len(token) <= 2:
                    continue

                if token in name_tokens:
                    score += 40
                    token_match_count += 1
                elif any(part.startswith(token) for part in name_tokens):
                    score += 20
                    token_match_count += 1

                if token in desc_tokens or any(part.startswith(token) for part in desc_tokens):
                    score += 15
                    token_match_count += 1

                for param in sub.get("parameters", []):
                    param_name = str(param.get("name", "")).lower()
                    if param_name == token:
                        score += 10
                        token_match_count += 1
                    elif param_name.startswith(token):
                        score += 5

            if tokens and token_match_count >= max(1, len(tokens) // 2):
                score += 25

            if score > 0:
                results.append((sub, score))

        results.sort(key=lambda item: item[1], reverse=True)
        return [sub for sub, _ in results[:limit]]

    def get_all(self) -> list[dict[str, Any]]:
        return list(self.index.get("subroutines", []))

    def get_stats(self) -> dict[str, Any]:
        subroutines = self.index.get("subroutines", [])
        files = {sub.get("filePath") for sub in subroutines if sub.get("filePath")}
        return {
            "totalSubroutines": len(subroutines),
            "totalFiles": len(files),
            "lastUpdated": self.index.get("lastUpdated", 0),
        }


registry = SubroutineRegistry()


def re_split_tokens(text: str) -> list[str]:
    return [token for token in __import__("re").split(r"[\s\-_]+", text) if token]


def _build_sample_call_from_metadata(sub: dict[str, Any]) -> str:
    attrs: list[str] = []
    for param in sub.get("parameters", []) or []:
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


def execute_index_subroutines(session: DiracSession, element: DiracElement) -> None:
    path_attr = element.attributes.get("path")
    if not path_attr:
        raise ValueError("<index-subroutines> requires path attribute")
    count = registry.index_directory(str(path_attr))
    if session.debug:
        emit(session, f"Indexed {count} subroutines from {path_attr}\n")


def execute_search_subroutines(session: DiracSession, element: DiracElement) -> None:
    query = element.attributes.get("query")
    if not query:
        raise ValueError("<search-subroutines> requires query attribute")

    limit_attr = element.attributes.get("limit")
    limit = int(limit_attr) if limit_attr is not None else 10
    output_var = element.attributes.get("output")
    format_name = str(element.attributes.get("format") or "xml")

    results = registry.search(query, limit)

    if format_name == "json":
        output = json.dumps(results, indent=2)
    elif format_name == "xml":
        output = (
            '<!-- Dirac Subroutine Interface (source=disk, scope=all) -->\n'
            '<!-- Call convention: use direct tag call -->\n'
            '<!-- Generic form: <subroutineName required1="..." required2="..." optional1="..." /> -->\n'
            f'<subroutines source="disk" scope="all" query="{_escape_xml(query)}" total="{len(results)}">\n'
        )
        for sub in results:
            attrs = [f'name="{_escape_xml(str(sub.get("name", "")))}"']
            if sub.get("description"):
                attrs.append(f'description="{_escape_xml(str(sub["description"]))}"')
            for param in sub.get("parameters", []) or []:
                metadata = [param.get("type") or "any"]
                if param.get("required"):
                    metadata.append("required")
                if param.get("description"):
                    metadata.append(param["description"])
                attrs.append(f'param-{param["name"]}="{_escape_xml(":".join(str(part) for part in metadata))}"')
            attrs.append(f'file="{_escape_xml(str(sub.get("filePath", "")))}"')
            output += f"  <!-- Sample call: {_build_sample_call_from_metadata(sub)} -->\n"
            output += f"  <subroutine {' '.join(attrs)} />\n"
        output += "</subroutines>"
    else:
        if not results:
            output = "No subroutines found.\n"
        else:
            output = f"Found {len(results)} subroutine(s):\n\n"
            for sub in results:
                output += f"{sub.get('name')}({', '.join(str(param.get('name', '')) for param in (sub.get('parameters', []) or []))})\n"
                if sub.get("description"):
                    output += f"  {sub.get('description')}\n"
                output += f"  File: {sub.get('filePath')}\n\n"

    if output_var:
        set_variable(session, output_var, output, False)
    else:
        emit(session, output)
