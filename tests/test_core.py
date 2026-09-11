"""
Core regression tests for the DIRAC Python runtime.
These mirror a representative subset of the Node.js reference
implementation's .test.di suite (see dirac/tests/*.test.di), validating
behavioral parity for the ported subset of tags.

Run with:
    python -m unittest discover -s tests
"""

import io
import json
import os
import re
import sys
import tempfile
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

    def test_import_tag_loads_subroutine_from_disk(self):
        import tempfile

        from dirac.runtime.interpreter import integrate
        from dirac.runtime.session import create_session
        from dirac.types import DiracElement

        session = create_session()
        with tempfile.TemporaryDirectory() as tmpdir:
            lib_path = os.path.join(tmpdir, "demo.di")
            with open(lib_path, "w", encoding="utf-8") as handle:
                handle.write('<subroutine name="demo"><output>Hello from import</output></subroutine>')

            src = f'<dirac><import src="{lib_path}" /><demo /></dirac>'
            self.assertEqual(normalize(execute(src)), "Hello from import")

            session.current_file = os.path.join(tmpdir, "main.di")
            session.library_paths = [tmpdir]
            element = DiracElement(tag="import", attributes={"src": "demo.di"})
            integrate(session, element)
            self.assertEqual([s.name for s in session.subroutines if s.name == "demo"], ["demo"])

    def test_import_inside_subroutine_reloads_after_scope_cleanup(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            helper_path = os.path.join(tmpdir, "helper.di")
            wrapper_path = os.path.join(tmpdir, "wrapper.di")

            with open(helper_path, "w", encoding="utf-8") as handle:
                handle.write('<subroutine name="helper"><output>ok</output></subroutine>')

            with open(wrapper_path, "w", encoding="utf-8") as handle:
                handle.write(
                    f'<subroutine name="wrapper"><import src="{helper_path}" /><helper /></subroutine>'
                )

            src = f'<dirac><import src="{wrapper_path}" /><wrapper /><wrapper /></dirac>'
            self.assertEqual(normalize(execute(src)), "ok ok")

    def test_parameters_select_star_executes_call_children(self):
        src = '''
<dirac>
  <subroutine name="echo-children">
    <parameters select="*" />
  </subroutine>
  <echo-children>
    <output>Hello from child content</output>
  </echo-children>
</dirac>
'''
        self.assertEqual(normalize(execute(src)), "Hello from child content")

    def test_llm_tag_calls_custom_provider_and_emits_response(self):
        class FakeHTTPResponse:
            def __init__(self, payload):
                self.payload = payload

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return json.dumps(self.payload).encode("utf-8")

            def __iter__(self):
                return iter([json.dumps(self.payload).encode("utf-8")])

        with patch("dirac.tags.llm_tag.request.urlopen") as mock_urlopen:
            mock_urlopen.return_value = FakeHTTPResponse({"response": "Hello from custom LLM"})
            src = '<dirac><llm provider="custom" model="demo">Say hello</llm></dirac>'
            self.assertEqual(normalize(execute(src)), "Hello from custom LLM")

    def test_llm_tag_adds_router_subroutine_as_system_prompt(self):
        class FakeHTTPResponse:
            def __init__(self, payload):
                self.payload = payload

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return json.dumps(self.payload).encode("utf-8")

        with patch("dirac.tags.llm_tag.request.urlopen") as mock_urlopen:
            mock_urlopen.return_value = FakeHTTPResponse({"response": "Hello from routered LLM"})
            src = '''
<dirac>
  <subroutine name="simple-router" visible="subroutine">
    <output>You are a helpful router.</output>
  </subroutine>
  <llm provider="custom" model="demo" router="simple-router">Say hello</llm>
</dirac>
'''
            output = execute(src)
            self.assertEqual(normalize(output), "Hello from routered LLM")
            request_obj = mock_urlopen.call_args[0][0]
            payload = json.loads(request_obj.data.decode("utf-8"))
            self.assertEqual(payload["messages"][0]["role"], "system")
            self.assertEqual(payload["messages"][0]["content"], "You are a helpful router.")
            self.assertEqual(payload["messages"][1]["role"], "user")
            self.assertIn("Say hello", payload["messages"][1]["content"])

    def test_llm_tag_ollama_image_attribute_sends_image_payload(self):
        class FakeHTTPResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return json.dumps({"response": "A cat"}).encode("utf-8")

        with patch("dirac.tags.llm_tag.request.urlopen") as mock_urlopen:
            mock_urlopen.return_value = FakeHTTPResponse()
            png_data = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO7Z8xQAAAAASUVORK5CYII="
            with tempfile.TemporaryDirectory() as tmpdir:
                image_path = os.path.join(tmpdir, "sample.png")
                with open(image_path, "wb") as handle:
                    handle.write(__import__("base64").b64decode(png_data))

                src = f'<dirac><llm provider="ollama" model="llava" image="{image_path}">what is in this</llm></dirac>'
                output = execute(src)
                self.assertEqual(normalize(output), "A cat")

                request_obj = mock_urlopen.call_args[0][0]
                payload = json.loads(request_obj.data.decode("utf-8"))
                self.assertEqual(payload["model"], "llava")
                self.assertIn("images", payload)
                self.assertTrue(payload["images"][0].startswith("iVBORw0KGgo"))
                self.assertIn("what is in this", payload["prompt"])

    def test_llm_tag_switches_clients_when_provider_changes(self):
        class FakeHTTPResponse:
            def __init__(self, payload):
                self.payload = payload

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return json.dumps(self.payload).encode("utf-8")

        png_data = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO7Z8xQAAAAASUVORK5CYII="
        with tempfile.TemporaryDirectory() as tmpdir:
            image_path = os.path.join(tmpdir, "sample.png")
            with open(image_path, "wb") as handle:
                handle.write(__import__("base64").b64decode(png_data))

            calls: list[str] = []

            def fake_urlopen(request_obj, timeout=120):
                calls.append(request_obj.full_url)
                if request_obj.full_url.endswith("/chat"):
                    return FakeHTTPResponse({"response": "from custom"})
                return FakeHTTPResponse({"response": "from ollama"})

            with patch("dirac.tags.llm_tag.request.urlopen", side_effect=fake_urlopen):
                from dirac.runtime.session import create_session
                from dirac.tags.llm_tag import execute_llm
                from dirac.types import DiracElement

                session = create_session()
                execute_llm(
                    session,
                    DiracElement(tag="llm", attributes={"provider": "custom", "model": "demo"}, children=[], text="hello"),
                )
                execute_llm(
                    session,
                    DiracElement(
                        tag="llm",
                        attributes={"provider": "ollama", "model": "llava", "image": image_path},
                        children=[],
                        text="describe image",
                    ),
                )

            self.assertEqual(calls[0], "http://localhost:5001/chat")
            self.assertTrue(calls[1].endswith("/api/generate"))

    def test_llm_tag_ollama_router_system_prompt_is_inlined_into_prompt(self):
        class FakeHTTPResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return json.dumps({"response": "ok"}).encode("utf-8")

        with patch("dirac.tags.llm_tag.request.urlopen") as mock_urlopen:
            mock_urlopen.return_value = FakeHTTPResponse()

            src = """
<dirac>
  <subroutine name="image-router">
    <output>Always output XML only: &lt;human/&gt; or &lt;no-human/&gt;.</output>
  </subroutine>
  <llm provider="ollama" model="llava" router="image-router">please categorize</llm>
</dirac>
"""
            output = execute(src)
            self.assertEqual(normalize(output), "ok")

            request_obj = mock_urlopen.call_args[0][0]
            payload = json.loads(request_obj.data.decode("utf-8"))
            prompt = payload.get("prompt", "")
            self.assertIn("System: Always output XML only", prompt)
            self.assertIn("User: please categorize", prompt)

    def test_create_session_loads_custom_llm_config_from_config_yaml(self):
        from dirac.runtime.session import create_session

        prev_cwd = os.getcwd()
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                config_path = os.path.join(tmpdir, "config.yml")
                with open(config_path, "w", encoding="utf-8") as handle:
                    handle.write("llmProvider: custom\ncustomLLMUrl: http://localhost:5001\n")

                os.chdir(tmpdir)
                session = create_session()
                self.assertEqual(session.llm_provider, "custom")
                self.assertEqual(session.custom_llm_url, "http://localhost:5001")
        finally:
            os.chdir(prev_cwd)

    def test_llm_execute_with_feedback_stops_on_plain_text_response(self):
        class FakeHTTPResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return json.dumps({"response": "This is analysis text without XML."}).encode("utf-8")

        with patch("dirac.tags.llm_tag.request.urlopen") as mock_urlopen:
            mock_urlopen.return_value = FakeHTTPResponse()
            src = '<dirac><llm execute="true" feedback="true">Explain what this script should do</llm></dirac>'
            output = execute(src)
            self.assertIn("This is analysis text without XML.", output)
            self.assertEqual(mock_urlopen.call_count, 1)

    def test_system_basic(self):
        src = "<dirac><system>echo hello</system></dirac>"
        self.assertEqual(normalize(execute(src)), "hello")

    def test_run_shell_command_returns_zero_for_plain_echo(self):
        rc = run_shell_command("printf 'hello from shell\\n'")
        self.assertEqual(rc, 0)

    def test_run_shell_command_expands_home_tilde_in_arguments(self):
        with patch("dirac.shell.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            rc = run_shell_command("ls ~")
            self.assertEqual(rc, 0)
            self.assertEqual(mock_run.call_args[0][0], f"ls {os.path.expanduser('~')}")

    def test_shell_starts_in_braket_mode_by_default(self):
        from dirac import shell

        captured = []

        def fake_input(prompt):
            captured.append(prompt)
            return ":quit"

        with patch("builtins.input", side_effect=fake_input):
            shell.run()

        self.assertIn("braket> ", captured[0])

    def test_shell_enables_readline_history_for_arrow_key_recall(self):
        from dirac import shell

        with patch("dirac.shell.readline") as mock_readline:
            shell._configure_readline_history()

        mock_readline.set_history_length.assert_called_with(1000)
        mock_readline.read_history_file.assert_called_once_with(shell.HISTORY_FILE)

    def test_shell_enables_tab_completion_for_cd_paths(self):
        from dirac import shell

        with tempfile.TemporaryDirectory() as tmpdir:
            target_dir = os.path.join(tmpdir, "demo-dir")
            os.mkdir(target_dir)

            with patch("dirac.shell.readline") as mock_readline:
                shell._configure_readline_completion()
                completer = mock_readline.set_completer.call_args[0][0]

            result = completer(f"cd {tmpdir}/de", 0)
            self.assertTrue(result.startswith("demo-dir"))

    def test_shell_autocomplete_suggests_bra_ket_attributes_for_existing_tag(self):
        from dirac import shell

        session = shell.create_session()
        session.subroutines = [
            type("Sub", (), {"name": "greet", "parameters": [{"name": "name", "type": "string"}, {"name": "count", "type": "number"}]})()
        ]

        result = shell._readline_completer("|greet na", 0, session)
        self.assertEqual(result, "name=")

    def test_shell_autocomplete_suggests_bra_ket_tag_names_like_llm(self):
        from dirac import shell

        session = shell.create_session()

        self.assertIn("|llm", shell._readline_completer("|ll", 0, session))
        self.assertIn("|llm", shell._readline_completer("|llm", 0, session))

    def test_shell_autocomplete_suggests_subroutine_names_for_edit_command(self):
        from dirac import shell

        session = shell.create_session()
        session.subroutines = [
            type("Sub", (), {"name": "my-robot", "parameters": []})(),
            type("Sub", (), {"name": "image-router", "parameters": []})(),
        ]

        with patch("dirac.shell.readline.get_line_buffer", return_value=":edit my"):
            result = shell._readline_completer("my", 0, session)

        self.assertEqual(result, "my-robot")

    def test_shell_autocomplete_returns_none_for_unknown_edit_subroutine_prefix(self):
        from dirac import shell

        session = shell.create_session()
        session.subroutines = [
            type("Sub", (), {"name": "my-robot", "parameters": []})(),
        ]

        with patch("dirac.shell.readline.get_line_buffer", return_value=":edit zz"):
            result = shell._readline_completer("zz", 0, session)

        self.assertIsNone(result)

    def test_shell_autocomplete_suggests_bra_ket_attribute_prefix_from_readline_buffer(self):
        from dirac import shell

        session = shell.create_session()
        with patch("dirac.shell.readline.get_line_buffer", return_value="|llm p"):
            with redirect_stdout(io.StringIO()) as out:
                result = shell._readline_completer("p", 0, session)
                _ = shell._readline_completer("p", 1, session)
        self.assertEqual(result, "provider=")
        self.assertEqual(out.getvalue().count("provider="), 0)

    def test_shell_autocomplete_suggests_second_bra_ket_attribute_after_first_is_filled(self):
        from dirac import shell

        session = shell.create_session()
        with patch("dirac.shell.readline.get_line_buffer", return_value="|llm provider=ollama mo"):
            result = shell._readline_completer("mo", 0, session)
        self.assertEqual(result, "model=")

    def test_shell_autocomplete_suggests_file_paths_for_llm_image_attribute(self):
        from dirac import shell

        session = shell.create_session()
        with tempfile.TemporaryDirectory() as tmpdir:
            image_path = os.path.join(tmpdir, "demo-image.png")
            with open(image_path, "w", encoding="utf-8") as handle:
                handle.write("png")

            with patch("dirac.shell.readline.get_line_buffer", return_value=f"|llm image={tmpdir}/de"):
                result = shell._readline_completer(f"image={tmpdir}/de", 0, session)

        self.assertTrue(result.startswith("demo-image.png"))

    def test_shell_autocomplete_unmatched_path_keeps_input_unchanged(self):
        from dirac import shell

        session = shell.create_session()
        with patch("dirac.shell.readline.get_line_buffer", return_value="|llm image=/definitely-not-a-real-dir/nope"):
            result = shell._readline_completer("image=/definitely-not-a-real-dir/nope", 0, session)

        self.assertIsNone(result)

    def test_shell_autocomplete_keeps_tilde_prefix_for_home_paths(self):
        from dirac import shell

        home_matches = shell._path_value_completion("|llm image=~/")
        self.assertTrue(home_matches)
        self.assertTrue(any(match.startswith("~/") for match in home_matches))
        self.assertTrue(all(not match.startswith("~//") for match in home_matches))

        ls_matches = shell._path_value_completion("ls -tl ~/")
        self.assertTrue(ls_matches)
        self.assertTrue(any(match.startswith("~/") for match in ls_matches))
        self.assertTrue(all(not match.startswith("~//") for match in ls_matches))

        partial_matches = shell._path_value_completion("|llm image=~/Down")
        self.assertTrue(partial_matches)
        self.assertTrue(any(match.startswith("~/Downloads/") for match in partial_matches))
        self.assertTrue(all(not match.startswith("~/~/") for match in partial_matches))

        nested_matches = shell._path_value_completion("|llm image=~/Downloads/IMG_")
        self.assertTrue(nested_matches)
        self.assertTrue(any(match.startswith("~/Downloads/IMG_") for match in nested_matches))
        self.assertTrue(all(not match.startswith("~/Downloads/Downloads/") for match in nested_matches))

    def test_shell_runs_init_script_on_startup(self):
        from dirac import shell

        with tempfile.TemporaryDirectory() as tmpdir:
            init_path = os.path.join(tmpdir, "shell-init.di")
            with open(init_path, "w", encoding="utf-8") as handle:
                handle.write('<defvar name="boot" value="loaded" />\n<output>booted</output>\n')

            with patch.object(shell, "_find_shell_init_script", return_value=init_path), patch("builtins.input", side_effect=[":quit"]):
                out = io.StringIO()
                with redirect_stdout(out):
                    shell.run()

            self.assertIn("booted", out.getvalue())

    def test_shell_mode_runs_plain_unix_commands(self):
        from dirac import shell

        with patch("builtins.input", side_effect=[":shell", ":return", ":quit"]):
            out = io.StringIO()
            with redirect_stdout(out):
                shell.run()

        text = out.getvalue()
        self.assertIn("DIRAC Python Shell", text)
        self.assertIn("shell mode = True", text)
        self.assertIn("Returned to braket shell", text)

    def test_shell_vars_pretty_prints_json_values(self):
        from dirac import shell
        from dirac.types import Variable

        session = shell.create_session()
        session.variables = [
            Variable(name="payload", value={"a": 1, "b": [1, 2]}),
        ]

        out = io.StringIO()
        with redirect_stdout(out):
            shell._print_vars(session)

        text = out.getvalue()
        self.assertIn('  payload = {', text)
        self.assertIn('"a": 1', text)
        self.assertIn('"b": [', text)

    def test_shell_question_mark_and_natural_language_fallback_to_ai(self):
        from dirac import shell

        session = shell.create_session()
        self.assertEqual(shell._normalize_question_mark_input("? explain recursion", session.question_mark_target), "|ai>explain recursion")
        self.assertTrue(shell._is_likely_natural_language("what is the best way to sort a list?"))
        self.assertTrue(shell._is_likely_natural_language("? explain recursion"))
        self.assertFalse(shell._is_likely_natural_language("ls -la"))
        self.assertTrue(shell._should_fallback_to_ai(session, "what is the best way to sort a list?"))

    def test_shell_autoruns_common_unix_commands_in_braket_mode(self):
        from dirac import shell

        with patch("builtins.input", side_effect=["ls", ":quit"]), patch("dirac.shell.run_shell_command", return_value=0) as mock_run:
            out = io.StringIO()
            with redirect_stdout(out):
                shell.run()

        self.assertTrue(mock_run.called)
        self.assertEqual(mock_run.call_args[0][0], "ls")
        self.assertIn("DIRAC Python Shell", out.getvalue())

    def test_shell_autoruns_non_allowlisted_commands_in_braket_mode(self):
        from dirac import shell

        command = "awk 'BEGIN { print 1 }'"
        with patch("builtins.input", side_effect=[command, ":quit"]), patch("dirac.shell.run_shell_command", return_value=0) as mock_run:
            out = io.StringIO()
            with redirect_stdout(out):
                shell.run()

        self.assertTrue(mock_run.called)
        self.assertEqual(mock_run.call_args[0][0], command)
        self.assertIn("DIRAC Python Shell", out.getvalue())

    def test_shell_save_and_edit_subroutine(self):
        from dirac import shell

        session = shell.create_session()
        src = """
<dirac>
  <subroutine name="demo">
    <output>Hello</output>
  </subroutine>
</dirac>
"""
        parser = shell.DiracParser()
        ast = parser.parse(src)
        shell.integrate(session, ast)

        temp = os.path.join(os.getcwd(), "demo-shell-save.di")
        try:
            shell._save_subroutine_to_disk(session, None, "demo", temp)
            self.assertTrue(os.path.exists(temp))
            with open(temp, "r", encoding="utf-8") as handle:
                text = handle.read()
            self.assertIn("<demo|", text)
            self.assertNotIn("<demo|>", text)
        finally:
            if os.path.exists(temp):
                os.unlink(temp)

        edited_source = "<demo|\n  |output>Hello again"
        buf = io.StringIO()
        with patch("dirac.shell.subprocess.run") as mock_run, patch("builtins.open", create=True) as mock_open, redirect_stdout(buf):
            mock_run.return_value.returncode = 0
            mock_open.return_value.__enter__.return_value.read.return_value = edited_source
            shell._edit_subroutine_in_editor(session, parser, "demo")

        self.assertIn("Updated subroutine 'demo' in session", buf.getvalue())
        self.assertEqual([s.name for s in session.subroutines if s.name == "demo"], ["demo"])
        self.assertEqual(shell._find_subroutine(session, "demo").name, "demo")

    def test_shell_save_defaults_to_subroutine_source_path(self):
        from dirac import shell

        session = shell.create_session()
        src = """
<dirac>
  <subroutine name="my-robot">
    <output>hello</output>
  </subroutine>
</dirac>
"""
        parser = shell.DiracParser()
        ast = parser.parse(src)
        shell.integrate(session, ast)

        with tempfile.TemporaryDirectory() as tmpdir:
            target = os.path.join(tmpdir, "my-robot.di")
            sub = shell._find_subroutine(session, "my-robot")
            sub.source_path = target

            out = io.StringIO()
            with redirect_stdout(out):
                shell._save_subroutine_to_disk(session, parser, "my-robot")

            self.assertTrue(os.path.exists(target))
            with open(target, "r", encoding="utf-8") as handle:
                text = handle.read()
            self.assertIn("<my-robot|", text)
            self.assertIn(target, out.getvalue())

    def test_shell_save_without_source_path_defaults_to_user_lib(self):
        from dirac import shell

        session = shell.create_session()
        src = """
<dirac>
  <subroutine name="demo-save">
    <output>ok</output>
  </subroutine>
</dirac>
"""
        parser = shell.DiracParser()
        ast = parser.parse(src)
        shell.integrate(session, ast)

        with tempfile.TemporaryDirectory() as tmpdir:
            expected = os.path.join(tmpdir, "demo-save.di")
            out = io.StringIO()
            with patch("dirac.shell.os.path.expanduser", side_effect=lambda p: tmpdir if p == "~/.dirac/lib/user" else os.path.expanduser(p)), redirect_stdout(out):
                shell._save_subroutine_to_disk(session, parser, "demo-save")

            self.assertTrue(os.path.exists(expected))
            with open(expected, "r", encoding="utf-8") as handle:
                text = handle.read()
            self.assertIn("<demo-save|", text)

    def test_shell_edit_round_trip_keeps_valid_bra_ket(self):
        from dirac import shell

        session = shell.create_session()
        src = """
<dirac>
  <subroutine name="demo" visible="subroutine" param-name="string">
    <output>Hello</output>
  </subroutine>
</dirac>
"""
        parser = shell.DiracParser()
        ast = parser.parse(src)
        shell.integrate(session, ast)

        subroutine = shell._find_subroutine(session, "demo")
        serialized = shell._serialize_subroutine_to_braket(subroutine)

        self.assertIn('<demo', serialized.splitlines()[0])
        self.assertIn('visible=subroutine', serialized)
        self.assertIn('param-name=string', serialized)
        self.assertTrue(serialized.splitlines()[0].endswith('|'))

        xml = shell.BraKetParser().parse(serialized)
        reparsed = shell.DiracParser().parse(xml)
        self.assertIsNotNone(reparsed)
        self.assertNotIn('&lt;demo', xml)

    def test_shell_mode_persists_cd_state(self):
        start = os.getcwd()
        try:
            self.assertEqual(run_shell_command("cd .."), 0)
            self.assertNotEqual(os.getcwd(), start)
            self.assertEqual(run_shell_command("cd " + start), 0)
        finally:
            os.chdir(start)

    def test_shell_autosaves_user_subroutines_as_braket_on_braket_exit(self):
        from dirac import shell

        session = shell.create_session()
        src = """
<dirac>
  <subroutine name="my-robot">
    <output>hello</output>
  </subroutine>
</dirac>
"""
        parser = shell.DiracParser()
        ast = parser.parse(src)
        shell.integrate(session, ast)

        with tempfile.TemporaryDirectory() as tmpdir:
            user_lib = os.path.join(tmpdir, "lib", "user")
            target = os.path.join(user_lib, "my-robot.di")
            sub = shell._find_subroutine(session, "my-robot")
            sub.source_path = target

            shell._autosave_user_subroutines_on_exit(session, True, user_lib_dir=user_lib)

            self.assertTrue(os.path.exists(target))
            with open(target, "r", encoding="utf-8") as handle:
                text = handle.read()
            self.assertIn("<my-robot|", text)
            self.assertIn("|output>", text)

    def test_shell_autosave_skips_when_not_in_braket_mode(self):
        from dirac import shell

        session = shell.create_session()
        src = """
<dirac>
  <subroutine name="my-robot">
    <output>hello</output>
  </subroutine>
</dirac>
"""
        parser = shell.DiracParser()
        ast = parser.parse(src)
        shell.integrate(session, ast)

        with tempfile.TemporaryDirectory() as tmpdir:
            user_lib = os.path.join(tmpdir, "lib", "user")
            target = os.path.join(user_lib, "my-robot.di")
            sub = shell._find_subroutine(session, "my-robot")
            sub.source_path = target

            shell._autosave_user_subroutines_on_exit(session, False, user_lib_dir=user_lib)

            self.assertFalse(os.path.exists(target))


if __name__ == "__main__":
    unittest.main()
