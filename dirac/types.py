"""
Core types for the DIRAC Python runtime.
Mirrors dirac/src/types/index.ts from the Node.js reference implementation.
"""

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class DiracElement:
    """A parsed DIRAC XML element (or a text node, when tag == '')."""

    tag: str
    attributes: dict = field(default_factory=dict)
    children: list = field(default_factory=list)  # list[DiracElement]
    text: Optional[str] = None


@dataclass
class Variable:
    """A variable on the session's variable stack."""

    name: str
    value: Any
    visible: bool = False
    boundary: int = 0  # 1 = visible (can be promoted once), 0 = not visible
    passby: str = "value"  # 'value' | 'ref'
    ref_name: Optional[str] = None


@dataclass
class Subroutine:
    """A registered subroutine on the session's subroutine stack."""

    name: str
    element: DiracElement
    boundary: int = 0
    visible: bool = False
    description: Optional[str] = None
    parameters: list = field(default_factory=list)
    meta: dict = field(default_factory=dict)
    source_path: Optional[str] = None


@dataclass
class DiracSession:
    """Execution context. Mirrors DiracSession from src/types/index.ts."""

    # Variable stack (all variables live on one flat stack)
    variables: list = field(default_factory=list)  # list[Variable]

    # Subroutine registry (also a flat stack)
    subroutines: list = field(default_factory=list)  # list[Subroutine]

    # Scope boundaries (for cleanup on subroutine return)
    var_boundary: int = 0
    sub_boundary: int = 0
    output_boundary: int = 0

    # Parameter stack (for subroutine calls / <parameters> tag)
    parameter_stack: list = field(default_factory=list)  # list[list[DiracElement]]

    # Output buffer
    output: list = field(default_factory=list)  # list[str]

    # Control flow
    is_return: bool = False
    is_break: bool = False
    return_value: Any = None

    # Track if a call's children were consumed (reserved for <parameters select="*"/>)
    children_consumed: bool = False

    # Track currently executing subroutine name (for diagnostics)
    current_subroutine_name: Optional[str] = None

    # Debugging
    debug: bool = False

    # Import tracking / file context
    current_file: Optional[str] = None
    imported_files: set = field(default_factory=set)
    library_paths: list = field(default_factory=list)
