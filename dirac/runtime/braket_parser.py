"""
Bra-Ket Parser - converts bra-ket notation to XML.
Mirrors dirac/src/runtime/braket-parser.ts from the Node.js reference
implementation.

Syntax:
  - Bra (subroutine): <name|  ... defines a subroutine
  - Ket (everything else): |tag attrs>  ... can have children/content
  - Indentation defines scope (2 spaces per level), same convention as
    Python itself - which is the whole point of porting this to Python:
    a Python code block embedded in a ket's body (e.g. inside <eval>)
    keeps its own relative indentation intact, because each line's
    indentation is measured in absolute spaces and re-expressed as
    2 * (spaces // 2) - an identity transform for any evenly-indented
    code (2/4/8-space Python or JS, which is effectively all real code).

Examples:
    |output>Hello World          ->  <output>Hello World</output>
    |variable name=x>            ->  <variable name="x"/>
    <add|                        ->  <subroutine name="add">
      |output>test               ->    <output>test</output>
                                  ->  </subroutine>
"""

import re
from dataclasses import dataclass
from typing import Optional

_BRA_TAG_RE = re.compile(r"^<([a-zA-Z_][a-zA-Z0-9_-]*)\s*")
_KET_RE = re.compile(r"^\|([a-zA-Z_][a-zA-Z0-9_-]*)\s*([^>]*?)>\s*(.*)")
_INLINE_KET_RE = re.compile(r"\|([a-zA-Z_][a-zA-Z0-9_-]*)\s*([^>]*?)>")
_ATTR_RE = re.compile(r"^([a-zA-Z_][a-zA-Z0-9_-]*)=(.+)$")

_RESERVED_BRA_ATTRS = {"description", "extends", "visible", "lang"}


@dataclass
class _Line:
    indent: int
    type: str  # 'bra' | 'ket' | 'text' | 'empty'
    tag: Optional[str] = None
    attrs: Optional[str] = None
    text: Optional[str] = None
    raw: str = ""


class BraKetParser:
    """Parses bra-ket notation and compiles it to a DIRAC-ROOT-free XML string."""

    def __init__(self) -> None:
        self._lines: list = []
        self._current_line = 0

    def parse(self, source: str) -> str:
        self._lines = source.split("\n")
        self._current_line = 0

        xml = ["<dirac>"]
        self._parse_block(xml, -1)
        xml.append("</dirac>")

        return "\n".join(xml)

    # -- Block/line parsing ------------------------------------------------

    def _parse_block(self, output: list, parent_indent: int) -> None:
        while self._current_line < len(self._lines):
            line = self._parse_line(self._lines[self._current_line])

            if line.type == "empty":
                self._current_line += 1
                continue

            if line.indent <= parent_indent:
                break

            if line.type == "bra":
                attrs = f" {self._convert_bra_attributes(line.attrs)}" if line.attrs else ""
                output.append(f"{'  ' * line.indent}<subroutine name=\"{line.tag}\"{attrs}>")
                self._current_line += 1
                self._parse_block(output, line.indent)
                output.append(f"{'  ' * line.indent}</subroutine>")
                continue

            if line.type == "ket":
                indent_str = "  " * line.indent
                attrs = f" {self._convert_ket_attributes(line.attrs, line.tag or '')}" if line.attrs else ""

                next_line = (
                    self._parse_line(self._lines[self._current_line + 1])
                    if self._current_line + 1 < len(self._lines)
                    else None
                )

                if next_line is not None and next_line.indent > line.indent and next_line.type != "empty":
                    output.append(f"{indent_str}<{line.tag}{attrs}>")
                    self._current_line += 1
                    self._parse_block(output, line.indent)
                    output.append(f"{indent_str}</{line.tag}>")
                else:
                    if line.text:
                        content = self._convert_inline_kets(line.text)
                        output.append(f"{indent_str}<{line.tag}{attrs}>{content}</{line.tag}>")
                    else:
                        output.append(f"{indent_str}<{line.tag}{attrs}/>")
                    self._current_line += 1
                continue

            if line.type == "text":
                indent_str = "  " * line.indent
                content = self._convert_inline_kets(line.text or "")
                output.append(f"{indent_str}{content}")
                self._current_line += 1
                continue

    def _parse_line(self, raw: str) -> _Line:
        match = re.match(r"^(\s*)(.*)", raw)
        indent = len(match.group(1)) // 2 if match else 0
        content = match.group(2) if match else ""

        if not content.strip():
            return _Line(indent=indent, type="empty", raw=raw)

        if content.startswith("#"):
            return _Line(indent=indent, type="empty", raw=raw)

        # Bra: <name| or <name attrs|
        if content.startswith("<") and content.endswith("|"):
            tag_match = _BRA_TAG_RE.match(content)
            if tag_match:
                tag_name = tag_match.group(1)
                after_tag = content[tag_match.end() : -1]  # strip trailing |
                return _Line(
                    indent=indent,
                    type="bra",
                    tag=tag_name,
                    attrs=after_tag.strip() or None,
                    raw=raw,
                )

        # Ket: |tag> or |tag attrs> or |tag>text
        ket_match = _KET_RE.match(content)
        if ket_match:
            return _Line(
                indent=indent,
                type="ket",
                tag=ket_match.group(1),
                attrs=ket_match.group(2).strip() or None,
                text=ket_match.group(3) or None,
                raw=raw,
            )

        return _Line(indent=indent, type="text", text=content, raw=raw)

    # -- Attribute conversion ------------------------------------------------

    def _parse_attribute_parts(self, attrs: str) -> list:
        parts: list = []
        current = ""
        in_quotes = False
        quote_char = ""

        for i, char in enumerate(attrs):
            if char in ("\"", "'") and (i == 0 or attrs[i - 1] != "\\"):
                if not in_quotes:
                    in_quotes = True
                    quote_char = char
                    current += char
                elif char == quote_char:
                    in_quotes = False
                    current += char
                else:
                    current += char
            elif char == " " and not in_quotes:
                if current.strip():
                    parts.append(current.strip())
                    current = ""
            else:
                current += char

        if current.strip():
            parts.append(current.strip())

        return parts

    def _quote_value(self, value: str) -> str:
        if (value.startswith('"') and value.endswith('"')) or (
            value.startswith("'") and value.endswith("'")
        ):
            return value
        return f'"{value}"'

    def _convert_attributes(self, attrs: str) -> str:
        if not attrs:
            return ""

        parts = self._parse_attribute_parts(attrs)
        converted = []
        for part in parts:
            match = _ATTR_RE.match(part)
            if not match:
                converted.append(part)
                continue
            name, value = match.group(1), match.group(2)
            if (value.startswith('"') and value.endswith('"')) or (
                value.startswith("'") and value.endswith("'")
            ):
                converted.append(f"{name}={value}")
            else:
                converted.append(f'{name}="{value}"')
        return " ".join(converted)

    def _convert_bra_attributes(self, attrs: Optional[str]) -> str:
        if not attrs:
            return ""

        parts = self._parse_attribute_parts(attrs)
        converted = []
        for part in parts:
            match = _ATTR_RE.match(part)
            if not match:
                converted.append(part)
                continue
            name, value = match.group(1), match.group(2)
            is_reserved = name in _RESERVED_BRA_ATTRS
            attr_name = name if is_reserved else f"param-{name}"
            if (value.startswith('"') and value.endswith('"')) or (
                value.startswith("'") and value.endswith("'")
            ):
                converted.append(f"{attr_name}={value}")
            else:
                converted.append(f'{attr_name}="{value}"')
        return " ".join(converted)

    def _convert_ket_attributes(self, attrs: Optional[str], tag_name: str) -> str:
        if not attrs:
            return ""

        parts = self._parse_attribute_parts(attrs)
        has_positional = any("=" not in part for part in parts)

        if not has_positional:
            return self._convert_attributes(attrs)

        positional_index = 0
        converted = []
        for part in parts:
            match = _ATTR_RE.match(part)
            if match:
                name, value = match.group(1), match.group(2)
                converted.append(f"{name}={self._quote_value(value)}")
            else:
                converted.append(f"_positional-{positional_index}={self._quote_value(part)}")
                positional_index += 1
        return " ".join(converted)

    def _escape_xml(self, text: str) -> str:
        return (
            text.replace("&", "&amp;")  # must be first
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )

    def _convert_inline_kets(self, text: str) -> str:
        parts = []
        last_index = 0

        for match in _INLINE_KET_RE.finditer(text):
            if match.start() > last_index:
                parts.append(self._escape_xml(text[last_index : match.start()]))

            tag, attrs = match.group(1), match.group(2)
            attr_str = f" {self._convert_attributes(attrs.strip())}" if attrs.strip() else ""
            parts.append(f"<{tag}{attr_str}/>")

            last_index = match.end()

        if last_index < len(text):
            parts.append(self._escape_xml(text[last_index:]))

        return "".join(parts)
