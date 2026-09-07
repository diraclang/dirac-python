"""
<llm> tag for the Python runtime.

This implements the core Node.js behavior needed for local LLM calls:
- prompt building
- provider selection
- safe output of plain-text responses
- execute="true" for generated XML execution
- feedback loop for iterative correction/iteration
"""

import json
import os
import re
from typing import Any
from urllib import request, error

from ..runtime.parser import DiracParser
from ..runtime.session import emit, get_subroutine, get_variable, set_variable, substitute_attribute
from ..types import DiracElement, DiracSession

_XML_TAG_RE = re.compile(r"<\s*/?\s*[a-zA-Z_][\w:.-]*(?:\s[^<>]*?)?/?>")


class _CustomLlmClient:
    def __init__(self, base_url: str = "http://localhost:5001"):
        self.base_url = base_url.rstrip("/")

    def complete(self, prompt: str, *, messages: Any = None, model: str = "", **_: Any) -> str:
        payload = {"messages": messages or [{"role": "user", "content": prompt}]}
        if model:
            payload["model"] = model
        data = json.dumps(payload).encode("utf-8")
        req = request.Request(
            f"{self.base_url}/chat",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=120) as response:
                body = response.read().decode("utf-8")
        except error.HTTPError as exc:
            details = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Custom LLM server error ({exc.code}): {details[:200]}") from exc
        except error.URLError as exc:
            raise RuntimeError(f"Custom LLM server unreachable: {exc}") from exc

        try:
            parsed = json.loads(body)
        except json.JSONDecodeError as exc:  # pragma: no cover - defensive
            raise RuntimeError(f"Custom LLM server returned invalid JSON: {body[:200]}") from exc

        if not isinstance(parsed, dict) or not isinstance(parsed.get("response"), str):
            raise RuntimeError(f"Custom LLM server returned invalid payload: {parsed!r}")

        return parsed["response"]


def _build_client(session: DiracSession, provider: str | None, model: str | None) -> Any:
    provider_name = (provider or session.llm_provider or "").lower()
    selected_model = model or session.llm_model or "default"

    if not provider_name:
        raise RuntimeError(
            "<llm> tag requires LLM configuration. Set LLM_PROVIDER (ollama/anthropic/openai/custom) or provider=..."
        )

    if provider_name == "custom":
        base_url = session.custom_llm_url or os.environ.get("CUSTOM_LLM_URL") or os.environ.get("CUSTM_LLM_URL") or "http://localhost:5001"
        return _CustomLlmClient(base_url)

    if provider_name == "ollama":
        from .ollama import OllamaProvider  # type: ignore

        return OllamaProvider(model=selected_model)

    if provider_name == "openai":
        raise RuntimeError("OpenAI provider is not yet implemented in the Python runtime")

    if provider_name == "anthropic":
        raise RuntimeError("Anthropic provider is not yet implemented in the Python runtime")

    raise RuntimeError(f"Unknown LLM provider: {provider_name!r}. Use 'custom', 'ollama', 'anthropic', or 'openai'.")


def _extract_prompt(session: DiracSession, element: DiracElement) -> str:
    if element.children:
        before = len(session.output)
        from ..runtime.interpreter import integrate

        for child in element.children:
            integrate(session, child)
        prompt = "".join(session.output[before:]).strip()
        del session.output[before:]
        return prompt

    if element.text:
        return substitute_attribute(session, element.text).strip()

    raise ValueError("<llm> requires prompt content")


def _strip_code_fence(response: str) -> str:
    text = response.strip()
    if not text.startswith("```"):
        return text

    lines = text.splitlines()
    if len(lines) >= 2 and lines[0].startswith("```"):
        if lines[0].startswith("```bash"):
            body = "\n".join(lines[1:-1]).strip()
            return f"<system>{body}</system>"
        body = "\n".join(lines[1:-1]).strip()
        return body
    return text


def _has_xml_tag(text: str) -> bool:
    return bool(_XML_TAG_RE.search(text))


def _execute_generated_dirac(session: DiracSession, code: str) -> None:
    parser = DiracParser()
    ast = parser.parse(code)
    from ..runtime.interpreter import integrate

    integrate(session, ast)


def execute_llm(session: DiracSession, element: DiracElement) -> None:
    provider = element.attributes.get("provider") or session.llm_provider
    model = element.attributes.get("model") or session.llm_model
    result_var = element.attributes.get("output") or element.attributes.get("result")
    context_var = element.attributes.get("context")
    save_dialog = element.attributes.get("save-dialog") == "true"
    dialog_var = context_var or ("__llm_dialog__" if save_dialog else None)
    append_this = save_dialog
    execute_mode = element.attributes.get("execute") == "true"
    feedback_mode = element.attributes.get("feedback") == "true"
    max_iterations = max(1, int(element.attributes.get("max-iterations", "3")))

    prompt = _extract_prompt(session, element)
    if not prompt:
        raise ValueError("<llm> requires prompt content")

    client = session.llm_client or _build_client(session, provider, model)
    session.llm_client = client
    session.llm_provider = provider or session.llm_provider
    session.llm_model = model or session.llm_model

    if dialog_var:
        existing = get_variable(session, dialog_var)
        if existing is not None:
            try:
                if isinstance(existing, str):
                    existing = json.loads(existing)
                if isinstance(existing, list):
                    history = existing
                else:
                    history = [{"role": "system", "content": str(existing)}]
            except Exception:
                history = [{"role": "system", "content": str(existing)}]
        else:
            history = []
    else:
        history = []

    router_name = element.attributes.get("router")
    router_prompt = ""
    if router_name:
        router_subroutine = get_subroutine(session, router_name)
        if router_subroutine:
            before_output = len(session.output)
            from ..tags.call import execute_call

            execute_call(session, DiracElement(tag=router_name, attributes={}, children=[]))
            router_output = "".join(session.output[before_output:]).strip()
            del session.output[before_output:]
            router_prompt = router_output

    request_messages = list(history)
    if router_prompt:
        request_messages.append({"role": "system", "content": router_prompt})
    request_messages.append({"role": "user", "content": prompt})

    messages = request_messages
    response = client.complete(prompt, model=model or "", messages=messages)
    result = _strip_code_fence(response)

    if dialog_var:
        set_variable(session, dialog_var, json.dumps(messages + [{"role": "assistant", "content": result}]), True)

    if execute_mode:
        iteration = 0
        while iteration < max_iterations:
            iteration += 1
            code = _strip_code_fence(result)
            trimmed = code.strip()
            if trimmed in ("<DONE />", "<DONE/>"):
                break
            if not _has_xml_tag(trimmed):
                if result_var:
                    set_variable(session, result_var, result, False)
                else:
                    emit(session, result)
                break

            try:
                before_output = len(session.output)
                _execute_generated_dirac(session, code)
                exec_output = "".join(session.output[before_output:])
                if exec_output:
                    emit(session, exec_output)
                if not feedback_mode:
                    break
                feedback_prompt = "The code executed successfully. Here is the output:\n```\n" + exec_output + "\n```"
                result = client.complete(feedback_prompt, model=model or "", messages=messages + [{"role": "assistant", "content": code}, {"role": "user", "content": feedback_prompt}])
                result = _strip_code_fence(result)
                if result.strip() in ("<DONE />", "<DONE/>"):
                    break
                if not _has_xml_tag(result.strip()):
                    if result_var:
                        set_variable(session, result_var, result, False)
                    else:
                        emit(session, result)
                    break
            except Exception as exc:  # pragma: no cover - simple retry path
                if not feedback_mode or iteration >= max_iterations:
                    raise
                error_prompt = f"System: Your code had an execution error:\n{exc}\nPlease fix the error and return valid Dirac XML."
                result = client.complete(error_prompt, model=model or "", messages=messages + [{"role": "assistant", "content": code}, {"role": "user", "content": error_prompt}])
                result = _strip_code_fence(result)
                if not _has_xml_tag(result.strip()):
                    if result_var:
                        set_variable(session, result_var, result, False)
                    else:
                        emit(session, result)
                    break
        return

    if result_var:
        set_variable(session, result_var, result, False)
    else:
        emit(session, result)
