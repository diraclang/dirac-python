"""
DIRAC Python Runtime.

A Python-native port of the DIRAC language runtime (reference: dirac-lang on
npm / the Node.js implementation in the sibling `dirac` repo).

Usage:
    from dirac import execute
    output = execute('<dirac><output>Hello, DIRAC!</output></dirac>')

    # Bra-ket notation is also supported:
    output = execute('|output>Hello, DIRAC!', fmt="braket")
"""

from .runtime.braket_parser import BraKetParser
from .runtime.interpreter import integrate
from .runtime.parser import DiracParser
from .runtime.session import create_session, get_output
from .types import DiracElement, DiracSession

__all__ = [
    "execute",
    "DiracParser",
    "BraKetParser",
    "DiracSession",
    "DiracElement",
    "create_session",
]


def execute(source: str, debug: bool = False, fmt: str = "xml") -> str:
    """
    Parse and execute DIRAC source code, returning the captured output.

    fmt: "xml" (default, `.di` syntax) or "braket" (`.bk` syntax).
    """
    if fmt == "braket":
        source = BraKetParser().parse(source)
    elif fmt != "xml":
        raise ValueError(f"Unknown format: {fmt!r}. Use 'xml' or 'braket'.")

    parser = DiracParser()
    session = create_session(debug=debug)

    ast = parser.parse(source)
    integrate(session, ast)

    return get_output(session)
