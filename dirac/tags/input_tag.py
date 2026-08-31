"""
<input> tag - read from stdin or a file.
Mirrors a subset of dirac/src/tags/input.ts.

Usage:
    <input source="stdin" mode="all" />
    <input source="stdin" mode="line" />
    <input source="file" path="file.txt" mode="all" />
    <input source="file" path="file.txt" mode="line" />
"""

import sys

from ..runtime.session import emit, substitute_attribute
from ..types import DiracElement, DiracSession

_file_line_iterators: dict = {}


def execute_input(session: DiracSession, element: DiracElement) -> None:
    source = element.attributes.get("source")
    mode = element.attributes.get("mode", "all")
    path_attr = element.attributes.get("path")

    if not source:
        raise ValueError("<input> requires source attribute (stdin or file)")

    if source == "file" and not path_attr:
        raise ValueError('<input source="file"> requires path attribute')

    if source == "stdin":
        if mode == "all":
            value = sys.stdin.read()
        elif mode == "line":
            value = sys.stdin.readline().rstrip("\n")
        else:
            raise ValueError(f"<input> invalid mode: {mode}. Use 'all' or 'line'")
    elif source == "file":
        path = substitute_attribute(session, path_attr)
        if mode == "all":
            with open(path, "r", encoding="utf-8") as f:
                value = f.read()
        elif mode == "line":
            iterator = _file_line_iterators.get(path)
            if iterator is None:
                iterator = iter(open(path, "r", encoding="utf-8"))
                _file_line_iterators[path] = iterator
            try:
                value = next(iterator).rstrip("\n")
            except StopIteration:
                value = ""
        else:
            raise ValueError(f"<input> invalid mode: {mode}. Use 'all' or 'line'")
    else:
        raise ValueError(f"<input> invalid source: {source}. Use 'stdin' or 'file'")

    emit(session, value)
