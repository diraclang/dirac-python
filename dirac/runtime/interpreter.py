"""
Core interpreter - dispatches DiracElement nodes to tag handlers.
Mirrors dirac/src/runtime/interpreter.ts from the Node.js reference implementation.
"""

from ..types import DiracElement, DiracSession
from .session import emit, substitute_attribute
from ..tags.assign import execute_assign
from ..tags.break_tag import execute_break
from ..tags.call import execute_call
from ..tags.defvar import execute_defvar
from ..tags.eval_tag import execute_eval
from ..tags.foreach import execute_foreach
from ..tags.if_tag import execute_if
from ..tags.import_tag import execute_import
from ..tags.input_tag import execute_input
from ..tags.llm_tag import execute_llm
from ..tags.loop import execute_loop
from ..tags.output import execute_output
from ..tags.parameters_tag import execute_parameters
from ..tags.return_tag import execute_return
from ..tags.subroutine import execute_subroutine
from ..tags.system import execute_system
from ..tags.test_if import execute_test_if
from ..tags.variable import execute_variable

# Tags whose body is a direct-call to a registered subroutine (anything not
# in this set of built-in tag names).
_BUILTIN_TAGS = {
    "dirac-root",
    "dirac",
    "defvar",
    "variable",
    "assign",
    "output",
    "subroutine",
    "call",
    "parameters",
    "loop",
    "foreach",
    "break",
    "if",
    "test-if",
    "eval",
    "python",
    "system",
    "input",
    "return",
    "import",
    "llm",
}


def integrate(session: DiracSession, element: DiracElement) -> None:
    """Execute a single DiracElement node."""
    # Text nodes
    if element.text and not element.tag:
        emit(session, substitute_attribute(session, element.text))
        return

    # Control flow: stop execution if return or break has been signaled.
    if session.is_return or session.is_break:
        return

    tag = element.tag.lower()

    if tag in ("dirac-root", "dirac"):
        integrate_children(session, element)
        return
    if tag == "defvar":
        execute_defvar(session, element)
        return
    if tag == "variable":
        execute_variable(session, element)
        return
    if tag == "assign":
        execute_assign(session, element)
        return
    if tag == "output":
        execute_output(session, element)
        return
    if tag == "subroutine":
        execute_subroutine(session, element)
        return
    if tag == "call":
        execute_call(session, element)
        return
    if tag == "parameters":
        execute_parameters(session, element)
        return
    if tag == "loop":
        execute_loop(session, element)
        return
    if tag == "foreach":
        execute_foreach(session, element)
        return
    if tag == "break":
        execute_break(session, element)
        return
    if tag == "if":
        execute_if(session, element)
        return
    if tag == "test-if":
        execute_test_if(session, element)
        return
    if tag in ("eval", "python"):
        execute_eval(session, element)
        return
    if tag == "system":
        execute_system(session, element)
        return
    if tag == "input":
        execute_input(session, element)
        return
    if tag == "return":
        execute_return(session, element)
        return
    if tag == "import":
        execute_import(session, element)
        return
    if tag == "llm":
        execute_llm(session, element)
        return

    # Not a built-in tag - treat as a direct subroutine call, e.g. <greet name="Alice" />
    execute_call(session, element)


def integrate_children(session: DiracSession, element: DiracElement) -> None:
    """Execute all children of an element in order."""
    for child in element.children:
        integrate(session, child)
        if session.is_return or session.is_break:
            break
