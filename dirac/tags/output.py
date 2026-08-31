"""
<output> tag - emit content.
Mirrors dirac/src/tags/output.ts (file-writing support omitted for now).
"""

from ..runtime.session import emit, pop_and_capture_output, set_output_boundary, substitute_attribute
from ..types import DiracElement, DiracSession


def execute_output(session: DiracSession, element: DiracElement) -> None:
    if element.children:
        from ..runtime.interpreter import integrate_children

        integrate_children(session, element)
        return

    if element.text:
        content = substitute_attribute(session, element.text)
        emit(session, content)
        return
