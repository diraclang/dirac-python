"""
<subroutine> tag - define a reusable code block.
Mirrors dirac/src/tags/subroutine.ts (extend/lang=js features omitted;
see call.py for the corresponding invocation logic).
"""

import copy

from ..runtime.session import register_subroutine, substitute_attribute
from ..types import DiracElement, DiracSession


def execute_subroutine(session: DiracSession, element: DiracElement) -> None:
    name_attr = element.attributes.get("name")
    if not name_attr:
        raise ValueError("<subroutine> requires name attribute")

    # Substitute variables in the name attribute to support dynamic naming.
    name = substitute_attribute(session, name_attr)

    description = element.attributes.get("description")
    visible = element.attributes.get("visible") in ("subroutine", "both")

    parameters = []
    meta: dict = {}

    for attr_name, attr_value in element.attributes.items():
        if attr_name.startswith("param-"):
            param_name = attr_name[len("param-") :]
            parts = attr_value.split(":")
            param_meta = {
                "name": param_name,
                "type": parts[0] if parts and parts[0] else "string",
                "required": len(parts) > 1 and parts[1] == "required",
                "description": parts[2] if len(parts) > 2 and parts[2] else None,
            }
            if len(parts) > 3 and parts[3]:
                param_meta["enum"] = parts[3].split("|")
            if len(parts) > 4 and parts[4]:
                param_meta["example"] = parts[4]
            parameters.append(param_meta)
        elif attr_name.startswith("meta-"):
            meta_name = attr_name[len("meta-") :]
            meta[meta_name] = attr_value

    # Store subroutine with deep-copied children to prevent mutation across calls.
    subroutine_element = DiracElement(
        tag="subroutine",
        attributes={**element.attributes, "name": name},
        children=copy.deepcopy(element.children),
    )

    register_subroutine(
        session,
        name,
        subroutine_element,
        description=description,
        parameters=parameters or None,
        meta=meta or None,
        visible=visible,
        source_path=session.current_file,
    )
