"""
<break> tag - exit the current loop or foreach iteration.
Mirrors dirac/src/tags/break.ts.
"""

from ..types import DiracElement, DiracSession


def execute_break(session: DiracSession, element: DiracElement) -> None:
    session.is_break = True
