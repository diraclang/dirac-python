"""
Core regression tests for the DIRAC Python runtime.
These mirror a representative subset of the Node.js reference
implementation's .test.di suite (see dirac/tests/*.test.di), validating
behavioral parity for the ported subset of tags.

Run with:
    python -m unittest discover -s tests
"""

import io
import os
import re
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dirac import execute  # noqa: E402
from dirac.shell import run_shell_command  # noqa: E402

_WHITESPACE_RE = re.compile(r"\s+")


def normalize(text: str) -> str:
    """
    Collapse whitespace runs to a single space and trim.
    Matches the normalization the Node.js test-runner applies before
    comparing actual vs. expected output (see src/test-runner.ts), since
    DIRAC XML text nodes preserve incidental whitespace/indentation
    between tags verbatim.
    """
    return _WHITESPACE_RE.sub(" ", text).strip()


class TestCoreRuntime(unittest.TestCase):
    def test_basic_output(self):
        src = "<dirac><output>Hello, World!</output></dirac>"
        self.assertEqual(normalize(execute(src)), "Hello, World!")

    def test_no_root_element(self):
        # DIRAC files don't require a single <dirac> root - multiple
        # top-level elements are allowed.
        src = "<output>one</output><output>two</output>"
        self.assertEqual(normalize(execute(src)), "onetwo")

    def test_defvar_and_variable_substitution(self):
        src = """
<dirac>
  <defvar name="a" value="1" />
  <defvar name="b" value="2" />
  <defvar name="c" value="3" />
  <output>a=<variable name="a" />, b=<variable name="b" />, c=<variable name="c" /></output>
</dirac>
"""
        self.assertEqual(normalize(execute(src)), "a=1, b=2, c=3")

    def test_assign_updates_variable(self):
        src = """
<dirac>
  <defvar name="myvar" value="initial" />
  <assign name="myvar" value="updated" />
  <output>New value: <variable name="myvar" /></output>
</dirac>
"""
        self.assertEqual(normalize(execute(src)), "New value: updated")

    def test_eval_with_result_and_subroutine_params(self):
        src = """
<dirac>
  <subroutine name="fullname" param-first="string" param-last="string">
    <eval result="result">return first + ' ' + last</eval>
    <output><variable name="result" /></output>
  </subroutine>
  <call name="fullname" first="John" last="Doe" />
</dirac>
"""
        self.assertEqual(normalize(execute(src)), "John Doe")

    def test_direct_tag_call_with_number_param(self):
        src = """
<dirac>
  <subroutine name="square" param-x="number">
    <eval result="result">return x * x</eval>
    <output><variable name="result" /></output>
  </subroutine>
  <square x="10" />
</dirac>
"""
        self.assertEqual(normalize(execute(src)), "100")

    def test_return_tag_and_result_capture(self):
        src = """
<dirac>
  <subroutine name="add-numbers" param-a="number" param-b="number">
    <eval result="sum">return a + b</eval>
    <return><variable name="sum" /></return>
  </subroutine>
  <add-numbers a="5" b="7" result="total" />
  <output><variable name="total" /></output>
</dirac>
"""
        self.assertEqual(normalize(execute(src)), "12")

    def test_loop_basic(self):
        src = """
<dirac>
  <defvar name="result" value="" />
  <loop count="3">
    <assign name="result" value="${result}x" />
  </loop>
  <output><variable name="result" /></output>
</dirac>
"""
        self.assertEqual(normalize(execute(src)), "xxx")

    def test_break_exits_loop(self):
        src = """
<loop count="5">
  <output>Before break</output>
  <break />
  <output>Should not print</output>
</loop>
<output>Done</output>
"""
        self.assertEqual(normalize(execute(src)), "Before break Done")

    def test_foreach_over_literal_list(self):
        src = """
<dirac>
  <defvar name="result" value="" />
  <foreach from="a,b,c" as="letter">
    <assign name="result" value="${result}${letter}-" />
  </foreach>
  <output><variable name="result" /></output>
</dirac>
"""
        self.assertEqual(normalize(execute(src)), "a-b-c-")

    def test_if_cond_then_else(self):
        src = """
<dirac>
  <defvar name="x" value="5" />
  <if>
    <cond eval="eq">
      <arg><variable name="x" /></arg>
      <arg>5</arg>
    </cond>
    <then><output>Match!</output></then>
    <else><output>No match!</output></else>
  </if>
</dirac>
"""
        self.assertEqual(normalize(execute(src)), "Match!")

    def test_test_if_attribute_based(self):
        src = """
<dirac>
  <defvar name="x" value="10" />
  <test-if test="$x" gt="5">
    <output>Greater!</output>
  </test-if>
</dirac>
"""
        self.assertEqual(normalize(execute(src)), "Greater!")

    def test_visible_subroutine_cleanup(self):
        src = """
<subroutine name="PARENT_WITHOUT_VISIBLE">
  <output>Parent without visible called</output>
  <subroutine name="SHOULD_BE_CLEANED">
    <output>This should not be called</output>
  </subroutine>
</subroutine>
<PARENT_WITHOUT_VISIBLE />
<output>After call: nested was cleaned up</output>
"""
        self.assertEqual(
            normalize(execute(src)),
            "Parent without visible called After call: nested was cleaned up",
        )

    def test_visible_subroutine_attribute_keeps_nested(self):
        src = """
<subroutine name="PARENT_WITH_VISIBLE" visible="subroutine">
  <output>Before call</output>
  <subroutine name="NESTED_HELPER">
    <output>Calling NESTED_HELPER: Success!</output>
  </subroutine>
  <output>Nested registered</output>
</subroutine>
<PARENT_WITH_VISIBLE />
<output>After call: NESTED_HELPER available</output>
<NESTED_HELPER />
"""
        self.assertEqual(
            normalize(execute(src)),
            "Before call Nested registered After call: NESTED_HELPER available "
            "Calling NESTED_HELPER: Success!",
        )

    def test_python_alias_executes_like_eval(self):
        src = """
<dirac>
  <python result="value">
    value = 21
    return value * 2
  </python>
  <output><variable name="value" /></output>
</dirac>
"""
        self.assertEqual(normalize(execute(src)), "42")

    def test_system_basic(self):
        src = "<dirac><system>echo hello</system></dirac>"
        self.assertEqual(normalize(execute(src)), "hello")

    def test_run_shell_command_returns_zero_for_plain_echo(self):
        rc = run_shell_command("printf 'hello from shell\\n'")
        self.assertEqual(rc, 0)

    def test_shell_mode_runs_plain_unix_commands(self):
        from dirac import shell

        with patch("builtins.input", side_effect=[":shell", ":return", ":quit"]):
            out = io.StringIO()
            with redirect_stdout(out):
                shell.run()

        text = out.getvalue()
        self.assertIn("DIRAC Python Shell", text)
        self.assertIn("shell mode = True", text)
        self.assertIn("Returned to DIRAC shell", text)

    def test_shell_mode_persists_cd_state(self):
        start = os.getcwd()
        try:
            self.assertEqual(run_shell_command("cd .."), 0)
            self.assertNotEqual(os.getcwd(), start)
            self.assertEqual(run_shell_command("cd " + start), 0)
        finally:
            os.chdir(start)


if __name__ == "__main__":
    unittest.main()
