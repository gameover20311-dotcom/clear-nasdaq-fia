from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from typing import Any, Dict, Optional

from .local_llm import LocalModelError, _extract_json, _loads_strict

GROQ_BASE = "https://api.groq.com/openai/v1"
GROQ_MODEL = "openai/gpt-oss-20b"


def _rate_limit_delay(exc: urllib.error.HTTPError, detail: str, attempt: int) -> float:
    """Respect provider-directed HTTP 429 windows without altering model semantics."""
    candidates = []
    try:
        raw = str(exc.headers.get("Retry-After") or "").strip()
        if raw:
            candidates.append(float(raw))
    except Exception:
        pass

    text = str(detail or "")
    # Groq normally reports seconds, but accept minute+second wording too so a
    # provider-directed window is never shortened by the client.
    for pattern in (
        r"try again in\s+([0-9]+(?:\.[0-9]+)?)s",
        r"retry after\s+([0-9]+(?:\.[0-9]+)?)s",
    ):
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            try:
                candidates.append(float(match.group(1)))
            except Exception:
                pass
    for pattern in (
        r"try again in\s+([0-9]+)m\s*([0-9]+(?:\.[0-9]+)?)s",
        r"retry after\s+([0-9]+)m\s*([0-9]+(?:\.[0-9]+)?)s",
    ):
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            try:
                candidates.append(float(match.group(1)) * 60.0 + float(match.group(2)))
            except Exception:
                pass

    if candidates:
        # Provider-directed waits are authoritative. Add one second of jitter-safe
        # margin; do not cap the window and immediately re-hit the same TPM limit.
        return max(1.0, max(candidates) + 1.0)

    # Only the no-header/no-detail fallback is bounded locally.
    return max(1.0, min(60.0, 15.0 * (attempt + 1)))


def _smaller_completion_budget(detail: str, current: int) -> int:
    """Fit the SAME prompt/schema under a provider request-token ceiling.

    Groq reports e.g. `Limit 8000, Requested 9620`. The hosted request accounting
    includes completion budget, so reduce only max_completion_tokens. Evidence,
    prompt, schema and validators remain byte-for-byte unchanged.
    """
    limit = requested = None
    m = re.search(
        r"Limit\s+([0-9]+).*?Requested\s+([0-9]+)",
        str(detail or ""),
        flags=re.IGNORECASE | re.DOTALL,
    )
    if m:
        try:
            limit = int(m.group(1)); requested = int(m.group(2))
        except Exception:
            limit = requested = None
    if limit and requested and requested > limit:
        over = requested - limit
        target = current - over - 384
    else:
        target = int(current * 0.65)
    # Keep enough room for strict structured output while guaranteeing progress.
    target = max(768, target)
    if target >= current:
        target = max(768, current - 512)
    return target


class GroqClient:
    def __init__(
        self,
        base_url: str,
        model: str,
        timeout: int = 420,
        num_ctx: int = 24576,
        reasoning_effort: str = "high",
        num_predict: int = 3072,
    ):
        self.base_url = str(base_url).rstrip("/")
        self.model = str(model)
        if self.base_url != GROQ_BASE:
            raise ValueError("Groq base URL must remain pinned to official endpoint")
        if self.model != GROQ_MODEL:
            raise ValueError("Groq model must remain pinned to openai/gpt-oss-20b")
        if reasoning_effort not in {"low", "medium", "high"}:
            raise ValueError("invalid reasoning_effort")
        self.timeout = int(timeout)
        self.num_ctx = int(num_ctx)
        self.num_predict = int(num_predict)
        self.reasoning_effort = reasoning_effort
        self.runtime_provenance = {
            "provider": "groq",
            "provider_model": self.model,
            "runtime_identity_scope": "HOSTED_PROVIDER_RUNTIME_NOT_LOCAL_WEIGHT_DIGEST",
            "system_fingerprints": [],
            "last_request_id": None,
            "last_usage": None,
            "rate_limit_retries": 0,
            "request_size_retries": 0,
        }

    def _key(self) -> str:
        key = str(os.getenv("GROQ_API_KEY") or "").strip()
        if not key:
            raise LocalModelError("GROQ_API_KEY_NOT_CONFIGURED")
        return key

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": "Bearer " + self._key(),
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "CLEAR-NASDAQ-FIA/1.0",
        }

    def health(self) -> Dict[str, Any]:
        try:
            req = urllib.request.Request(
                self.base_url + "/models",
                headers=self._headers(),
                method="GET",
            )
            with urllib.request.urlopen(req, timeout=10) as r:
                raw = r.read(2_000_001)
            if len(raw) > 2_000_000:
                raise LocalModelError("Groq health response too large")
            data = _loads_strict(raw.decode("utf-8"))
            models = [
                str(x.get("id") or "")
                for x in (data.get("data") or [])
                if isinstance(x, dict)
            ]
            return {
                "ok": True,
                "model_present": self.model in models,
                "provider": "groq",
                "provider_model": self.model,
                "models": models[:100],
                "model_digest": None,
                "digest_verifiable": False,
                "identity_note": "Hosted Groq runtime; not claimed identical to local Ollama weight/runtime digest.",
            }
        except Exception as e:
            return {
                "ok": False,
                "model_present": False,
                "provider": "groq",
                "provider_model": self.model,
                "error": type(e).__name__ + ": " + str(e)[:300],
            }

    def ask_json(
        self,
        system: str,
        user: str,
        temperature: float = 0.1,
        seed: int = 0,
        reasoning_effort: Optional[str] = None,
        timeout: Optional[int] = None,
        num_ctx: Optional[int] = None,
        num_predict: Optional[int] = None,
        response_schema: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        t = float(temperature)
        if not 0.0 <= t <= 2.0:
            raise ValueError("temperature outside [0,2]")
        effort = reasoning_effort or self.reasoning_effort
        if effort not in {"low", "medium", "high"}:
            raise ValueError("invalid reasoning_effort")
        ctx = int(num_ctx if num_ctx is not None else self.num_ctx)
        predict = int(num_predict if num_predict is not None else self.num_predict)
        if not 4096 <= ctx <= 131072:
            raise ValueError("num_ctx outside safe range")
        if not 256 <= predict <= 8192:
            raise ValueError("num_predict outside safe range")
        if response_schema is not None and not isinstance(response_schema, dict):
            raise ValueError("response_schema must be a dict")

        if response_schema is not None:
            encoded = json.dumps(response_schema, allow_nan=False, separators=(",", ":"))
            if len(encoded) > 100000:
                raise ValueError("response_schema too large")
            response_format = {
                "type": "json_schema",
                "json_schema": {
                    "name": "clear_nasdaq_fia_response",
                    "strict": True,
                    "schema": response_schema,
                },
            }
        else:
            response_format = {"type": "json_object"}

        base_payload = {
            "model": self.model,
            "stream": False,
            "messages": [
                {"role": "system", "content": str(system)},
                {"role": "user", "content": str(user)},
            ],
            "temperature": t,
            "seed": int(seed),
            "reasoning_effort": effort,
            "include_reasoning": False,
            "response_format": response_format,
        }
        request_timeout = int(timeout if timeout is not None else self.timeout)
        try:
            max_rate_retries = int(os.getenv("GROQ_RATE_LIMIT_RETRIES", "8"))
        except Exception:
            max_rate_retries = 8
        max_rate_retries = max(0, min(max_rate_retries, 12))

        response = None
        rate_attempt = 0
        size_attempt = 0
        active_predict = predict
        while True:
            payload = dict(base_payload)
            payload["max_completion_tokens"] = active_predict
            raw = json.dumps(payload, allow_nan=False).encode("utf-8")
            req = urllib.request.Request(
                self.base_url + "/chat/completions",
                data=raw,
                headers=self._headers(),
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=request_timeout) as r:
                    body = r.read(20_000_001)
                if len(body) > 20_000_000:
                    raise LocalModelError("Groq response too large")
                response = _loads_strict(body.decode("utf-8"))
                break
            except urllib.error.HTTPError as e:
                try:
                    detail = e.read(4000).decode("utf-8", "replace")
                except Exception:
                    detail = ""
                if int(e.code) == 429 and rate_attempt < max_rate_retries:
                    delay = _rate_limit_delay(e, detail, rate_attempt)
                    rate_attempt += 1
                    self.runtime_provenance["rate_limit_retries"] = int(
                        self.runtime_provenance.get("rate_limit_retries") or 0
                    ) + 1
                    print(
                        "GROQ_RATE_LIMIT_RETRY",
                        json.dumps({"attempt": rate_attempt, "sleep_seconds": round(delay, 2), "provider_model": self.model}, sort_keys=True),
                        flush=True,
                    )
                    time.sleep(delay)
                    continue
                # Groq can reject a single request whose prompt + completion budget
                # exceeds the service-tier TPM ceiling. Preserve the exact prompt and
                # schema; only reduce max_completion_tokens and retry.
                if (
                    int(e.code) == 413
                    and "rate_limit_exceeded" in detail
                    and size_attempt < 3
                    and active_predict > 768
                ):
                    new_predict = _smaller_completion_budget(detail, active_predict)
                    if new_predict < active_predict:
                        size_attempt += 1
                        self.runtime_provenance["request_size_retries"] = int(
                            self.runtime_provenance.get("request_size_retries") or 0
                        ) + 1
                        print(
                            "GROQ_REQUEST_SIZE_RETRY",
                            json.dumps(
                                {
                                    "attempt": size_attempt,
                                    "from_max_completion_tokens": active_predict,
                                    "to_max_completion_tokens": new_predict,
                                    "provider_model": self.model,
                                },
                                sort_keys=True,
                            ),
                            flush=True,
                        )
                        active_predict = new_predict
                        rate_attempt = 0
                        continue
                raise LocalModelError("Groq HTTP %s: %s" % (e.code, detail[:1000])) from e
            except LocalModelError:
                raise
            except Exception as e:
                raise LocalModelError(type(e).__name__ + ": " + str(e)[:500]) from e

        if not isinstance(response, dict):
            raise LocalModelError("Groq response unavailable after retries")

        fingerprint = str(response.get("system_fingerprint") or "").strip()
        if fingerprint:
            fps = self.runtime_provenance["system_fingerprints"]
            if fingerprint not in fps:
                fps.append(fingerprint)
        self.runtime_provenance["last_request_id"] = (
            (response.get("x_groq") or {}).get("id")
            if isinstance(response.get("x_groq"), dict)
            else None
        )
        self.runtime_provenance["last_usage"] = response.get("usage")

        choices = response.get("choices") or []
        if not choices or not isinstance(choices[0], dict):
            raise LocalModelError("Groq response missing choices")
        message = choices[0].get("message") or {}
        content = message.get("content") or ""
        try:
            return _extract_json(content)
        except LocalModelError as e:
            finish = str(choices[0].get("finish_reason") or "unknown")
            raise LocalModelError(
                f"{e}; finish_reason={finish}; content_chars={len(content)}"
            ) from e