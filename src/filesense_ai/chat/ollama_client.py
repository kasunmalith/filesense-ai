from __future__ import annotations

import ipaddress
import json
import urllib.error
import urllib.request
from collections.abc import Iterator
from urllib.parse import urlparse


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, new_url):
        return None


class OllamaClient:
    def __init__(self, base_url: str = "http://127.0.0.1:11434", timeout: float = 20.0) -> None:
        parsed = urlparse(base_url)
        try:
            loopback = bool(parsed.hostname and ipaddress.ip_address(parsed.hostname).is_loopback)
        except ValueError:
            loopback = False
        if parsed.scheme != "http" or not loopback or parsed.username or parsed.password:
            raise ValueError("Ollama is restricted to an HTTP loopback address")
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._opener = urllib.request.build_opener(_NoRedirect)

    def _request(self, endpoint: str, payload: dict | None = None) -> bytes:
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = urllib.request.Request(
            self.base_url + endpoint, data=data, headers={"Content-Type": "application/json"}
        )
        with self._opener.open(request, timeout=self.timeout) as response:
            return response.read()

    def available(self) -> bool:
        try:
            self._request("/api/tags")
            return True
        except (OSError, urllib.error.URLError, TimeoutError):
            return False

    def models(self) -> list[str]:
        body = json.loads(self._request("/api/tags"))
        return [item["name"] for item in body.get("models", []) if item.get("name")]

    def stream_chat(self, model: str, system: str, prompt: str) -> Iterator[str]:
        payload = {
            "model": model,
            "stream": True,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
        }
        request = urllib.request.Request(
            self.base_url + "/api/chat",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
        )
        with self._opener.open(request, timeout=self.timeout) as response:
            for line in response:
                if line.strip():
                    value = json.loads(line)
                    content = value.get("message", {}).get("content", "")
                    if content:
                        yield content
                    if value.get("done"):
                        break
