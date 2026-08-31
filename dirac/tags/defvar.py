"""
<defvar> tag - define a variable.
Mirrors dirac/src/tags/defvar.ts (literal/XML-serialization mode omitted).

Note: like the Node.js implementation, the `value` attribute and text
content use substitute_variables() (entity decoding only), NOT
substitute_attribute() ($var/${var} replacement). This looks asymmetric
compared to <assign>, but it faithfully mirrors the upstream behavior.
"""

from ..runtime.session import pop_and_capture_output, set_output_boundary, set_variable, substitute_variables
from ..types import DiracElement, DiracSession


def execute_defvar(session: DiracSession, element: DiracElement) -> None:
    name = element.attributes.get("name")
    if not name:
        raise ValueError("<defvar> requires name attribute")

    value_attr = element.attributes.get("value")
    visible_attr = element.attributes.get("visible", "false")
    trim_attr = element.attributes.get("trim")
    trim = trim_attr != "false"  # trim by default unless explicitly "false"

    visible = visible_attr in ("true", "variable", "both")

    if value_attr is not None:
        value = substitute_variables(session, value_attr)
    elif element.children:
        from ..runtime.interpreter import integrate

        old_boundary = set_output_boundary(session)
        for child in element.children:
            integrate(session, child)
        value = pop_and_capture_output(session)
        session.output_boundary = old_boundary
    elif element.text:
        value = substitute_variables(session, element.text)
    else:
        value = ""

    if trim and isinstance(value, str):
        value = value.strip()

    set_variable(session, name, value, visible)
