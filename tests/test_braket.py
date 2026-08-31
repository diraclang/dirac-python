"""
Tests for the bra-ket notation parser (dirac/runtime/braket_parser.py) and
its integration with execute(fmt="braket").

The key scenario this validates is the one that makes bra-ket notation a
natural fit for the Python port: a Python code block embedded inside a
ket's body (e.g. <eval>) keeps its own relative indentation intact, since
DIRAC's 2-space indentation unit and Python's own indentation are both
even-space, so the line-by-line "2 * (spaces // 2)" transform the parser
applies is an identity transform for realistic code.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dirac import execute  # noqa: E402
from dirac.runtime.braket_parser import BraKetParser  # noqa: E402


class TestBraKetParser(unittest.TestCase):
    def test_simple_output(self):
        src = "|output>Hello, DIRAC!"
        self.assertEqual(execute(src, fmt="braket").strip(), "Hello, DIRAC!")

    def test_defvar_and_variable(self):
        src = """|defvar name=x value=5>
|output>x = |variable name=x>"""
        self.assertEqual(execute(src, fmt="braket").strip(), "x = 5")

    def test_subroutine_bra_ket_with_indented_python_body(self):
        # This is the motivating case: a multi-line Python code block
        # embedded inside a ket (<eval>), with its own nested indentation
        # (the `if`/`return` lines) preserved relative to each other.
        src = """<classify n=number|
  |eval result=label>
    if n % 2 == 0:
        label = "even"
    else:
        label = "odd"
  |output>|variable name=label>

|classify n=4>
|classify n=7>"""

        output = execute(src, fmt="braket")
        self.assertEqual(output.strip().split(), ["even", "odd"])

    def test_braket_parser_produces_expected_xml_structure(self):
        src = """<square n=number|
  |eval result=r>
    return n * n
  |output>|variable name=r>"""

        xml = BraKetParser().parse(src)

        self.assertIn('<subroutine name="square" param-n="number">', xml)
        self.assertIn("return n * n", xml)
        self.assertIn('<variable name="r"/>', xml)

    def test_call_and_result(self):
        src = """<square n=number|
  |eval result=r>
    return n * n
  |output>|variable name=r>

|square n=9>"""
        self.assertEqual(execute(src, fmt="braket").strip(), "81")


if __name__ == "__main__":
    unittest.main()
