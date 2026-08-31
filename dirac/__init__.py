"""
DIRAC Python Runtime.

A Python-native port of the DIRAC language runtime (reference: dirac-lang on
npm / the Node.js implementation in the sibling `dirac` repo).

Usage:
    from dirac import execute
    output = execute('<dirac><output>Hello, DIRAC!</output></dirac>')
"""

from .runtime.interpreter import integrate
from .runtime.parser import DiracParser
from .runtime.session import create_session, get_output
from .types import DiracElement, DiracSession

__all__ = ["execute", "DiracParser", "DiracSession", "DiracElement", "create_session"]


def execute(source: str, debug: bool = False) -> str:
    """Parse and execute DIRAC source code, returning the captured output."""
    parser = DiracParser()
    session = create_session(debug=debug)

    ast = parser.parse(source)
    integrate(session, ast)

    return get_output(session)
