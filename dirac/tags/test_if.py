"""
<test-if> tag - attribute-based conditional execution.
Mirrors dirac/src/tags/test-if.ts.

Usage: <test-if test="$var == value">...</test-if>
       <test-if test="$var" eq="value">...</test-if>
"""

from ..runtime.session import substitute_attribute
from ..types import DiracElement, DiracSession

_OPERATORS = ("==", "!=", "<=", ">=", "<", ">")


def execute_test_if(session: DiracSession, element: DiracElement) -> None:
    test = element.attributes.get("test")
    if not test:
        raise ValueError("<test-if> requires test attribute")

    value = substitute_attribute(session, test)

    eq = element.attributes.get("eq")
    ne = element.attributes.get("ne")
    lt = element.attributes.get("lt")
    gt = element.attributes.get("gt")
    le = element.attributes.get("le")
    ge = element.attributes.get("ge")

    condition = False

    if eq is not None:
        condition = value == substitute_attribute(session, eq)
    elif ne is not None:
        condition = value != substitute_attribute(session, ne)
    elif lt is not None:
        condition = _compare(value, substitute_attribute(session, lt), lambda a, b: a < b)
    elif gt is not None:
        condition = _compare(value, substitute_attribute(session, gt), lambda a, b: a > b)
    elif le is not None:
        condition = _compare(value, substitute_attribute(session, le), lambda a, b: a <= b)
    elif ge is not None:
        condition = _compare(value, substitute_attribute(session, ge), lambda a, b: a >= b)
    else:
        condition = _evaluate_condition(session, test)

    if condition:
        from ..runtime.interpreter import integrate_children

        integrate_children(session, element)


def _compare(value: str, compare_value: str, op) -> bool:
    try:
        return op(float(value), float(compare_value))
    except ValueError:
        return False


def _evaluate_condition(session: DiracSession, test: str) -> bool:
    substituted = substitute_attribute(session, test)

    for op in _OPERATORS:
        if op in substituted:
            left, _, right = substituted.partition(op)
            left, right = left.strip(), right.strip()
            try:
                left_num, right_num = float(left), float(right)
                both_numbers = True
            except ValueError:
                both_numbers = False

            if op == "==":
                return left_num == right_num if both_numbers else left == right
            if op == "!=":
                return left_num != right_num if both_numbers else left != right
            if op == "<=":
                return both_numbers and left_num <= right_num
            if op == ">=":
                return both_numbers and left_num >= right_num
            if op == "<":
                return both_numbers and left_num < right_num
            if op == ">":
                return both_numbers and left_num > right_num

    if substituted in ("", "0", "false"):
        return False
    return True
