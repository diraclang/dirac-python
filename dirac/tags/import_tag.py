"""
<import> tag - Import subroutines from other Dirac files.
"""

import os

from ..runtime.braket_parser import BraKetParser
from ..runtime.parser import DiracParser
from ..runtime.session import substitute_attribute
from ..types import DiracElement, DiracSession


def _resolve_import_path(session: DiracSession, src: str) -> str:
    current_dir = os.path.dirname(session.current_file) if session.current_file else os.getcwd()
    candidate_paths = []

    if src.startswith("/"):
        candidate_paths.append(src)
    elif src.startswith("~/"):
        candidate_paths.append(os.path.expanduser(src))
    elif src.startswith("./") or src.startswith("../"):
        candidate_paths.append(os.path.normpath(os.path.join(current_dir, src)))
    else:
        for base in [current_dir] + list(getattr(session, "library_paths", []) or []):
            candidate_paths.append(os.path.normpath(os.path.join(base, src)))
        env_paths = os.environ.get("DIRAC_LIBS", "")
        for entry in env_paths.split(":"):
            if entry:
                candidate_paths.append(os.path.normpath(os.path.join(entry, src)))
        candidate_paths.append(os.path.normpath(os.path.join(os.getcwd(), src)))

    for candidate in candidate_paths:
        with_ext = candidate if candidate.endswith(".di") else candidate + ".di"
        if os.path.exists(with_ext):
            return with_ext

    raise FileNotFoundError(f"Module not found: {src}")


def execute_import(session: DiracSession, element: DiracElement) -> None:
    src_attr = element.attributes.get("src")
    if not src_attr:
        raise ValueError("<import> requires src attribute")

    src = substitute_attribute(session, src_attr)
    import_path = _resolve_import_path(session, src)

    if not getattr(session, "imported_files", None):
        session.imported_files = set()

    if import_path in session.imported_files:
        return

    session.imported_files.add(import_path)
    previous_file = session.current_file
    session.current_file = import_path

    try:
        from ..runtime.interpreter import integrate

        with open(import_path, "r", encoding="utf-8") as handle:
            source = handle.read()

        if any(
            line.strip().startswith("|")
            or (line.strip().startswith("<") and line.rstrip().endswith("|"))
            for line in source.splitlines()
            if line.strip() and not line.strip().startswith("<!--")
        ):
            source = BraKetParser().parse(source)

        ast = DiracParser().parse(source)
        integrate(session, ast)
    finally:
        session.current_file = previous_file
