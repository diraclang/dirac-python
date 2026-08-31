"""
<if> tag - conditional execution with <cond>, <then>, <else> children.
Mirrors dirac/src/tags/if.ts (the structured cond/then/else variant; see
test_if.py for the simpler attribute-based <test-if> tag).

Usage:
    <if>
      <cond>condition expression, or a <cond eval="eq"> block</cond>
      <then>executed if true</then>
      <else>executed if false</else>
    </if>
"""

from ..types import DiracElement, DiracSession

_CONDITION_TYPES = {
    "eq": lambda args: len(args) >= 2 and args[0] == args[1],
    "equal": lambda args: len(args) >= 2 and args[0] == args[1],
    "same": lambda args: len(args) >= 2 and args[0] == args[1],
    "ne": lambda args: len(args) >= 2 and args[0] != args[1],
    "notequal": lambda args: len(args) >= 2 and args[0] != args[1],
    "different": lambda args: len(args) >= 2 and args[0] != args[1],
}

_NUMERIC_CONDITION_TYPES = {
    "lt": lambda a, b: a < b,
    "less": lambda a, b: a < b,
    "le": lambda a, b: a <= b,
    "lessequal": lambda a, b: a <= b,
    "gt": lambda a, b: a > b,
    "greater": lambda a, b: a > b,
    "ge": lambda a, b: a >= b,
    "greaterequal": lambda a, b: a >= b,
}


def execute_if(session: DiracSession, element: DiracElement) -> None:
    condition_element = None
    then_element = None
    else_element = None

    for child in element.children:
        tag = child.tag.lower() if child.tag else ""
        if tag == "cond":
            condition_element = child
        elif tag in ("then", "do"):
            then_element = child
        elif tag == "else":
            else_element = child
        elif condition_element is None and child.tag:
            condition_element = child

    condition = _evaluate_predicate(session, condition_element)

    from ..runtime.interpreter import integrate_children

    if condition:
        if then_element is not None:
            integrate_children(session, then_element)
    else:
        if else_element is not None:
            integrate_children(session, else_element)


def _evaluate_predicate(session: DiracSession, predicate_element) -> bool:
    if predicate_element is None:
        return False

    if predicate_element.tag.lower() == "cond":
        return _evaluate_condition(session, predicate_element)

    from ..runtime.interpreter import integrate

    output_length_before = len(session.output)
    integrate(session, predicate_element)

    new_output = session.output[output_length_before:]
    result = "".join(new_output).strip()
    del session.output[output_length_before:]

    if result in ("", "0", "false"):
        return False
    if result in ("1", "true"):
        return True
    return len(result) > 0


def _evaluate_condition(session: DiracSession, cond_element) -> bool:
    eval_type = cond_element.attributes.get("eval")

    if not eval_type:
        return _evaluate_predicate(session, cond_element)

    from ..runtime.interpreter import integrate_children

    output_length_before = len(session.output)

    args = []
    for child in cond_element.children:
        if child.tag and child.tag.lower() == "arg":
            arg_output_start = len(session.output)
            integrate_children(session, child)
            args.append("".join(session.output[arg_output_start:]))

    del session.output[output_length_before:]

    return _evaluate_condition_type(eval_type.lower(), args)


def _evaluate_condition_type(eval_type: str, args: list) -> bool:
    if eval_type in _CONDITION_TYPES:
        return _CONDITION_TYPES[eval_type](args)

    if eval_type in _NUMERIC_CONDITION_TYPES:
        if len(args) < 2:
            return False
        try:
            a, b = float(args[0]), float(args[1])
        except ValueError:
            return False
        return _NUMERIC_CONDITION_TYPES[eval_type](a, b)

    return False
