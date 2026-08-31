"""
<return> tag - set the current subroutine's return value.
Mirrors dirac/src/tags/return.ts.

Sets session.is_return = True (short-circuiting remaining siblings in the
current subroutine body) and stores the evaluated value in
session.return_value, which the call site can capture via the `result`
attribute on <call>/direct-tag calls.

Usage:
    <return><variable name="sum" /></return>
    <return value="42" />
    <return>plain text</return>
"""

from ..runtime.session import get_variable, pop_and_capture_output, set_output_boundary, substitute_variables
from ..types import DiracElement, DiracSession


def execute_return(session: DiracSession, element: DiracElement) -> None:
    value_attr = element.attributes.get("value")

    if value_attr is not None:
        value = substitute_variables(session, value_attr)
    elif len(element.children) == 1 and element.children[0].tag == "variable":
        var_name = element.children[0].attributes.get("name")
        value = get_variable(session, var_name) if var_name else None
    elif element.children:
        from ..runtime.interpreter import integrate_children

        old_boundary = set_output_boundary(session)
        integrate_children(session, element)
        value = pop_and_capture_output(session)
        session.output_boundary = old_boundary
    elif element.text:
        value = substitute_variables(session, element.text)
    else:
        value = None

    session.return_value = value
    session.is_return = True
