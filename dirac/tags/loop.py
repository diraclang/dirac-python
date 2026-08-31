"""
<loop> tag - fixed-count iteration.
Mirrors dirac/src/tags/loop.ts.

Usage:
    <loop count="5">...</loop>                 loops 5 times, var 'i' = 0..4
    <loop count="${n}" var="idx">...</loop>    loops n times, var 'idx' = 0..n-1

Use <break /> inside <test-if>/<if> for conditional early exit.
"""

from ..runtime.session import set_variable, substitute_attribute
from ..types import DiracElement, DiracSession


def execute_loop(session: DiracSession, element: DiracElement) -> None:
    count_attr = element.attributes.get("count")
    var_name = element.attributes.get("var", "i")

    if not count_attr:
        raise ValueError(
            "<loop> requires count attribute. For conditional loops, use <test-if> with <break>."
        )

    substituted_count = substitute_attribute(session, count_attr)
    try:
        count = int(substituted_count)
    except ValueError as exc:
        raise ValueError(f"Invalid loop count: {count_attr} (evaluated to: {substituted_count})") from exc

    if count < 0:
        raise ValueError(f"Invalid loop count: {count_attr} (evaluated to: {substituted_count})")

    from ..runtime.interpreter import integrate_children

    was_break = session.is_break
    session.is_break = False

    for i in range(count):
        set_variable(session, var_name, i, False)

        integrate_children(session, element)

        if session.is_break:
            session.is_break = False
            break

        if session.is_return:
            break

    session.is_break = was_break
