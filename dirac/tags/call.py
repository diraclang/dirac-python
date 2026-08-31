"""
<call> tag - invoke a subroutine (also handles direct-tag call syntax,
e.g. <greet name="Alice" /> where "greet" is a registered subroutine name).
Mirrors dirac/src/tags/call.ts (extend/positional-args/Object-writeback
features are not yet ported - see README "Known Limitations").
"""

import json

from ..runtime.session import (
    clean_subroutines_to_boundary,
    clean_to_boundary,
    get_subroutine,
    pop_parameters,
    push_parameters,
    set_boundary,
    set_variable,
    substitute_attribute,
)
from ..types import DiracElement, DiracSession, Subroutine


def _convert_type(value: str, param_type: str):
    if value == "":
        return value
    if param_type == "number":
        try:
            return float(value) if "." in value else int(value)
        except ValueError as exc:
            raise ValueError(f"Cannot convert '{value}' to number") from exc
    if param_type == "boolean":
        if value in ("true", "1"):
            return True
        if value in ("false", "0"):
            return False
        raise ValueError(f"Cannot convert '{value}' to boolean")
    if param_type == "json":
        try:
            return json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Cannot parse '{value}' as JSON") from exc
    return value  # 'string' or unknown -> pass through


def execute_call(session: DiracSession, element: DiracElement) -> None:
    if element.tag == "call":
        name = element.attributes.get("subroutine") or element.attributes.get("name") or ""
    else:
        name = element.tag

    if not name:
        raise ValueError("<call> requires name or subroutine attribute")

    subroutine = get_subroutine(session, name)
    if subroutine is None:
        raise ValueError(f"Subroutine '{name}' not found")

    returned_value = _execute_call_internal(session, subroutine, element)

    result_attr = element.attributes.get("result")
    if result_attr:
        set_variable(session, result_attr, returned_value, False)


def _execute_call_internal(session: DiracSession, subroutine: Subroutine, call_element: DiracElement):
    from ..runtime.interpreter import integrate, integrate_children

    old_var_boundary = set_boundary(session)
    old_sub_boundary = session.sub_boundary
    current_sub_boundary = len(session.subroutines)
    session.sub_boundary = current_sub_boundary

    was_return = session.is_return
    was_return_value = session.return_value
    session.is_return = False
    session.return_value = None

    old_children_consumed = session.children_consumed
    old_subroutine_name = session.current_subroutine_name
    session.current_subroutine_name = call_element.tag

    # Substitute variables in call element attributes before use.
    substituted_attributes = {
        key: substitute_attribute(session, value) for key, value in call_element.attributes.items()
    }
    substituted_element = DiracElement(
        tag=call_element.tag, attributes=substituted_attributes, children=call_element.children
    )

    push_parameters(session, [substituted_element])

    visible_attr = call_element.attributes.get("visible")
    parameters_visible = visible_attr in ("true", "variable", "both")

    captured_return_value = None

    try:
        for attr_name, attr_value in subroutine.element.attributes.items():
            if not attr_name.startswith("param-"):
                continue
            param_name = attr_name[len("param-") :]

            if call_element.tag == "call" and param_name == "name" and "subroutine" not in call_element.attributes:
                continue
            if call_element.tag == "call" and param_name == "subroutine" and "subroutine" in call_element.attributes:
                continue

            already_set = any(v.name == param_name for v in session.variables[session.var_boundary :])
            if already_set:
                continue

            value = ""
            if param_name in substituted_element.attributes:
                value = substituted_element.attributes[param_name]
            else:
                parts = attr_value.split(":")
                if len(parts) > 3:
                    value = parts[-1]

            if value != "":
                parts = attr_value.split(":")
                param_type = parts[0] if parts and parts[0] else "string"
                try:
                    value = _convert_type(value, param_type)
                except ValueError as exc:
                    raise ValueError(f"Parameter '{param_name}': {exc}") from exc

            set_variable(session, param_name, value, parameters_visible)

        session.children_consumed = False
        integrate_children(session, subroutine.element)

        if not session.children_consumed and call_element.children:
            for child in call_element.children:
                integrate(session, child)

    finally:
        captured_return_value = session.return_value

        pop_parameters(session)

        visible_value = subroutine.element.attributes.get("visible", "false")
        if call_element.attributes.get("visible"):
            visible_value = call_element.attributes["visible"]
        keep_variables = visible_value in ("variable", "both", "true")
        keep_nested = visible_value in ("subroutine", "both", "true")

        clean_to_boundary(session, keep_variables)
        session.sub_boundary = current_sub_boundary
        clean_subroutines_to_boundary(session, subroutine, call_element)

        session.var_boundary = old_var_boundary
        if not keep_nested:
            session.sub_boundary = old_sub_boundary

        session.is_return = was_return
        session.return_value = was_return_value
        session.current_subroutine_name = old_subroutine_name
        session.children_consumed = old_children_consumed

    return captured_return_value
