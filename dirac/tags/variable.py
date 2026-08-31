"""
<variable> tag - retrieve variable value.
Mirrors dirac/src/tags/variable.ts.
"""

import json

from ..runtime.session import emit, get_variable
from ..types import DiracElement, DiracSession


def execute_variable(session: DiracSession, element: DiracElement) -> None:
    name = element.attributes.get("name")
    if not name:
        raise ValueError("<variable> requires name attribute")

    value = get_variable(session, name)
    if value is None:
        if session.debug:
            print(f"[Warning] Variable '{name}' is undefined")
        return

    if isinstance(value, (dict, list)):
        emit(session, json.dumps(value))
    else:
        emit(session, str(value))
