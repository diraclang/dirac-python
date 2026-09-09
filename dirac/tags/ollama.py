"""Minimal Ollama provider used by the Python <llm> tag."""

import json
from urllib import request, error


class OllamaProvider:
    def __init__(self, model: str = "llama2", base_url: str = "http://localhost:11434"):
        self.model = model
        self.base_url = base_url.rstrip("/")

    @staticmethod
    def _normalize_image(image: str) -> str:
        if not image:
            return ""
        match = __import__("re").match(r"^data:(image/[a-zA-Z0-9.+-]+);base64,(.*)$", image)
        if match:
            return match.group(2)
        return image

    def complete(self, prompt: str, *, messages=None, model=None, images=None, **kwargs):
        payload = {
            "model": model or self.model,
            "prompt": prompt,
            "stream": False,
        }
        image_list = []
        for image in images or []:
            normalized = self._normalize_image(image)
            if normalized and normalized.strip():
                image_list.append(normalized)
        if image_list:
            payload["images"] = image_list
        if messages:
            payload["messages"] = messages
        data = json.dumps(payload).encode("utf-8")
        req = request.Request(
            f"{self.base_url}/api/generate",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=120) as response:
                body = response.read().decode("utf-8")
        except error.URLError as exc:
            raise RuntimeError(f"Ollama server unreachable: {exc}") from exc

        try:
            parsed = json.loads(body)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Ollama server returned invalid JSON: {body[:200]}") from exc

        if isinstance(parsed, dict) and isinstance(parsed.get("response"), str):
            return parsed["response"]
        if isinstance(parsed, dict) and isinstance(parsed.get("content"), str):
            return parsed["content"]
        raise RuntimeError(f"Ollama server returned invalid payload: {parsed!r}")
