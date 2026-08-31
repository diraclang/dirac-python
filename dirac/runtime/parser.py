"""
XML Parser for DIRAC (.di files).
Mirrors dirac/src/runtime/parser.ts (which uses fast-xml-parser) using the
Python standard library's xml.etree.ElementTree.
"""

import re
import xml.etree.ElementTree as ET

from ..types import DiracElement

_SHEBANG_RE = re.compile(r"^#!.*\n")


class DiracParser:
    """Parses DIRAC XML source into a DiracElement tree."""

    def parse(self, source: str) -> DiracElement:
        # Strip shebang line if present
        if source.startswith("#!"):
            source = _SHEBANG_RE.sub("", source, count=1)

        # Always wrap in DIRAC-ROOT to ensure valid XML with a single root.
        # This allows files with comments, multiple top-level elements, or no
        # root element at all (matches the Node.js parser's behavior).
        wrapped = f"<DIRAC-ROOT>\n{source}\n</DIRAC-ROOT>"

        try:
            root = ET.fromstring(wrapped)
        except ET.ParseError as exc:
            raise ValueError(f"Failed to parse DIRAC XML: {exc}") from exc

        return self._convert(root)

    def _convert(self, node: ET.Element) -> DiracElement:
        element = DiracElement(tag=node.tag, attributes=dict(node.attrib), children=[])

        # Leading text (before the first child, if any)
        if node.text:
            element.children.append(DiracElement(tag="", text=node.text))
            element.text = node.text

        for child in node:
            element.children.append(self._convert(child))

            # Tail text (text following this child's closing tag)
            if child.tail:
                element.children.append(DiracElement(tag="", text=child.tail))
                element.text = (element.text or "") + child.tail

        return element
