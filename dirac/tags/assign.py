"""
<assign> tag - assign a value to an existing variable (or create it).
Mirrors dirac/src/tags/assign.ts.
"""

from ..runtime.session import (
    get_variable,
    pop_and_capture_output,
    set_output_boundary,
    set_variable,
    substitute_attribute,
)
from ..types import DiracElement, DiracSession


def execute_assign(session: DiracSession, element: DiracElement) -> None:
    name = element.attributes.get("name")
    if not name:
        raise ValueError("<assign> requires name attribute")

    value_attr = element.attributes.get("value")
    trim_attr = element.attributes.get("trim")
    type_attr = element.attributes.get("type")  # type="cat" for concatenation

    if value_attr is not None:
        value = substitute_attribute(session, value_attr)
    elif element.children:
        from ..runtime.interpreter import integrate

        old_boundary = set_output_boundary(session)
        for child in element.children:
            integrate(session, child)
        value = pop_and_capture_output(session)
        session.output_boundary = old_boundary
    elif element.text:
        value = substitute_attribute(session, element.text)
    else:
        value = ""

    if trim_attr == "true" and isinstance(value, str):
        value = value.strip()

    if type_attr == "cat":
        existing_value = get_variable(session, name)
        if existing_value is not None:
            value = str(existing_value) + str(value)

    # Find existing variable (any scope) and update it directly.
    for v in reversed(session.variables):
        if v.name == name:
            v.value = value
            return

    # Variable not found - create it.
    set_variable(session, name, value, False)
