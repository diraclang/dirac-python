"""
<foreach> tag - iterate over a literal/variable list of values.
Mirrors a simplified subset of dirac/src/tags/foreach.ts: iterating over
inline XML from an evaluated tag (xpath filtering) is not yet ported;
this supports the two common cases:

    <foreach from="$varname" as="item">...</foreach>   (variable holding a list)
    <foreach from="a,b,c" as="item">...</foreach>       (literal comma-separated values)
"""

from ..runtime.session import get_variable, set_variable, substitute_attribute
from ..types import DiracElement, DiracSession


def execute_foreach(session: DiracSession, element: DiracElement) -> None:
    from_attr = element.attributes.get("from")
    as_var = element.attributes.get("as", "item")

    if not from_attr:
        raise ValueError('<foreach> requires "from" attribute')

    if from_attr.startswith("$"):
        var_name = from_attr[1:]
        items = get_variable(session, var_name)
        if items is None:
            items = []
        elif isinstance(items, str):
            items = [part for part in items.split(",") if part != ""]
    else:
        literal = substitute_attribute(session, from_attr)
        items = [part for part in literal.split(",") if part != ""]

    from ..runtime.interpreter import integrate_children

    for item in items:
        set_variable(session, as_var, item, False)

        integrate_children(session, element)

        if session.is_break:
            session.is_break = False
            break

        if session.is_return:
            break
