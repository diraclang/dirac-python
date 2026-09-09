"""
<parameters> tag - access parameters passed to a subroutine.
Mirrors dirac/src/tags/parameters.ts.
"""

from ..runtime.session import capture_output_from_boundary, emit, get_current_parameters, pop_output_to_boundary, set_output_boundary


def execute_parameters(session, element):
    select = element.attributes.get("select")
    if not select:
        raise ValueError("<parameters> requires select attribute")

    params = get_current_parameters(session)
    if not params or len(params) == 0:
        return

    caller = params[0]

    if select == "*":
        session.children_consumed = True
        old_boundary = set_output_boundary(session)
        for child in caller.children:
            from ..runtime.interpreter import integrate

            integrate(session, child)
        captured = capture_output_from_boundary(session)
        session.output_boundary = old_boundary
        return captured

    if select.startswith("@"):
        attr_name = select[1:]

        if attr_name == "*":
            attrs = " ".join(f'{key}="{value}"' for key, value in caller.attributes.items())
            emit(session, attrs)
            return

        value = caller.attributes.get(attr_name)
        if value is not None:
            from ..runtime.session import get_variable, set_variable

            if not any(v.name == attr_name for v in session.variables[session.var_boundary :]):
                set_variable(session, attr_name, value, False)
        for child in element.children:
            from ..runtime.interpreter import integrate

            integrate(session, child)
        return

    raise ValueError(f"<parameters> invalid select: {select}")
