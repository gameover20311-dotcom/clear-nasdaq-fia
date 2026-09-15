from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


class ProviderError(RuntimeError):
    pass


@dataclass(frozen=True)
class ProviderConfig:
    label: str
    model: str
    timeout_seconds: int = 45


def _extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            raise ProviderError("MODEL_OUTPUT_NOT_JSON")
        try:
            obj = json.loads(match.group(0))
        except json.JSONDecodeError as exc:
            raise ProviderError("MODEL_OUTPUT_INVALID_JSON") from exc
    if not isinstance(obj, dict):
        raise ProviderError("MODEL_OUTPUT_NOT_OBJECT")
    choice = str(obj.get("choice", "")).strip().upper()
    if choice not in {"A", "B", "C", "D"}:
        raise ProviderError("MODEL_OUTPUT_CHOICE_INVALID")
    confidence = obj.get("confidence", 0)
    try:
        confidence = int(confidence)
    except (TypeError, ValueError) as exc:
        raise ProviderError("MODEL_OUTPUT_CONFIDENCE_INVALID") from exc
    confidence = max(0, min(100, confidence))
    reason = str(obj.get("reason", ""))[:1000]
    return {"choice": choice, "confidence": confidence, "reason": reason}


def _request_json(url: str, payload: dict[str, Any], headers: dict[str, str], timeout: int) -> dict[str, Any]:
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            raw = response.read(2_000_000)
    except urllib.error.HTTPError as exc:
        detail = exc.read(1000).decode("utf-8", "replace")
        # Never echo credentials. Provider bodies should not contain them, but
        # redact common key names defensively before surfacing diagnostics.
        detail = re.sub(r'(?i)(api[_-]?key|authorization|key)\s*[:=]\s*[^,}\s]+', r'\1=<redacted>', detail)
        raise ProviderError(f"HTTP_{exc.code}:{detail[:500]}") from exc
    except Exception as exc:
        raise ProviderError(f"TRANSPORT_{type(exc).__name__}") from exc
    try:
        return json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise ProviderError("PROVIDER_RESPONSE_INVALID_JSON") from exc


def call_free_provider(config: ProviderConfig, system_prompt: str, user_prompt: str) -> dict[str, Any]:
    """Call only an explicitly selected free-only provider label.

    Billing safety is enforced by the arena before this function is reached.
    This module never supports generic paid OpenAI/Astra calls.
    """
    label = config.label.upper()

    if label == "GROQ_FREE":
        key = os.getenv("GROQ_API_KEY", "").strip()
        if not key:
            raise ProviderError("GROQ_API_KEY_MISSING")
        data = _request_json(
            "https://api.groq.com/openai/v1/chat/completions",
            {
                "model": config.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0,
                "response_format": {"type": "json_object"},
            },
            {"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            config.timeout_seconds,
        )
        try:
            text = data["choices"][0]["message"]["content"]
        except Exception as exc:
            raise ProviderError("GROQ_RESPONSE_SHAPE_INVALID") from exc
        return _extract_json(text)

    if label == "GEMINI_FREE":
        key = os.getenv("GEMINI_API_KEY", "").strip()
        if not key:
            raise ProviderError("GEMINI_API_KEY_MISSING")
        model = config.model
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
        data = _request_json(
            url,
            {
                "systemInstruction": {"parts": [{"text": system_prompt}]},
                "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
                "generationConfig": {"temperature": 0, "responseMimeType": "application/json"},
            },
            {"Content-Type": "application/json"},
            config.timeout_seconds,
        )
        try:
            text = data["candidates"][0]["content"]["parts"][0]["text"]
        except Exception as exc:
            raise ProviderError("GEMINI_RESPONSE_SHAPE_INVALID") from exc
        return _extract_json(text)

    if label == "LOCAL_OLLAMA":
        endpoint = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
        data = _request_json(
            endpoint + "/api/chat",
            {
                "model": config.model,
                "stream": False,
                "format": "json",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "options": {"temperature": 0},
            },
            {"Content-Type": "application/json"},
            config.timeout_seconds,
        )
        try:
            text = data["message"]["content"]
        except Exception as exc:
            raise ProviderError("OLLAMA_RESPONSE_SHAPE_INVALID") from exc
        return _extract_json(text)

    raise ProviderError("PROVIDER_NOT_ALLOWED")
