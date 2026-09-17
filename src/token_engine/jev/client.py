"""Jev client protocol + HTTP fallback (typesafe-sdk optional)."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any, Protocol

from token_engine.jev.types import ChoiceAnswer, JevEvaluateResult


class JevUnavailableError(RuntimeError):
    """Raised when Jev cannot be used (missing key, SDK, network, circuit)."""


class JevClient(Protocol):
    def evaluate(
        self,
        state: str,
        questions: dict[str, Any],
        *,
        model: str,
        timeout_seconds: float,
    ) -> JevEvaluateResult: ...


class HttpJevClient:
    """Minimal HTTP client for POST /v1/systemone. Reads TYPESAFE_API_KEY from env only."""

    def __init__(
        self,
        *,
        base_url: str = "https://api.typesafe.ai",
        api_key: str | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key if api_key is not None else os.environ.get("TYPESAFE_API_KEY", "")

    def evaluate(
        self,
        state: str,
        questions: dict[str, Any],
        *,
        model: str,
        timeout_seconds: float,
    ) -> JevEvaluateResult:
        if not self._api_key:
            raise JevUnavailableError(
                "TYPESAFE_API_KEY is not set. Export it in the environment; never put it in config JSON."
            )
        body = json.dumps({"state": state, "model": model, "questions": questions}).encode()
        req = urllib.request.Request(
            f"{self._base_url}/v1/systemone",
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
                payload = json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:
            # Do not include response body (may contain sensitive upstream data)
            raise JevUnavailableError(f"TypeSafe HTTP {exc.code}") from exc
        except TimeoutError as exc:
            raise JevUnavailableError("TypeSafe request timed out") from exc
        except Exception as exc:  # noqa: BLE001 — boundary: network
            raise JevUnavailableError(f"TypeSafe transport error: {type(exc).__name__}") from exc

        if not isinstance(payload, dict) or "answers" not in payload:
            raise JevUnavailableError("TypeSafe response missing answers")

        usage = payload.get("usage") or {}
        return JevEvaluateResult(
            answers=payload.get("answers") or {},
            usage_input_tokens=int(usage.get("input_tokens") or 0),
            usage_output_tokens=int(usage.get("output_tokens") or 0),
            model=str(payload.get("model") or model),
        )


def try_typesafe_sdk_client() -> JevClient | None:
    """Lazy optional SDK. Returns None if typesafe-sdk is not installed."""
    try:
        from typesafe_sdk import TypeSafeClient  # type: ignore[import-not-found]
    except ImportError:
        return None

    class SdkJevClient:
        def evaluate(
            self,
            state: str,
            questions: dict[str, Any],
            *,
            model: str,
            timeout_seconds: float,
        ) -> JevEvaluateResult:
            if not os.environ.get("TYPESAFE_API_KEY"):
                raise JevUnavailableError("TYPESAFE_API_KEY is not set")

            def _call() -> JevEvaluateResult:
                from typesafe_sdk import Choice, TypeSafeClient  # type: ignore[import-not-found]

                client = TypeSafeClient()
                try:
                    typed: dict[str, Any] = {}
                    for key, q in questions.items():
                        if q.get("type") == "choice":
                            typed[key] = Choice(
                                instructions=q.get("instructions", ""),
                                criteria=q.get("criteria") or {},
                            )
                        else:
                            typed[key] = q
                    response = client.system_one(state=state, questions=typed, model=model)
                finally:
                    close = getattr(client, "close", None)
                    if callable(close):
                        close()

                answers: dict[str, Any] = {}
                choices = getattr(response, "choices", None) or getattr(response, "answers", {})
                if hasattr(choices, "items"):
                    for key, ans in choices.items():
                        if hasattr(ans, "choice"):
                            answers[key] = {
                                "type": "choice",
                                "choice": ans.choice,
                                "confidence": float(getattr(ans, "confidence", 0.0) or 0.0),
                                "probabilities": dict(getattr(ans, "probabilities", {}) or {}),
                            }
                        else:
                            answers[key] = ans
                usage = getattr(response, "usage", None)
                return JevEvaluateResult(
                    answers=answers,
                    usage_input_tokens=int(getattr(usage, "input_tokens", 0) or 0),
                    usage_output_tokens=int(getattr(usage, "output_tokens", 0) or 0),
                    model=model,
                )

            from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout

            with ThreadPoolExecutor(max_workers=1) as pool:
                fut = pool.submit(_call)
                try:
                    return fut.result(timeout=max(0.1, float(timeout_seconds)))
                except FuturesTimeout as exc:
                    raise JevUnavailableError("typesafe SDK call timed out") from exc
                except JevUnavailableError:
                    raise
                except Exception as exc:  # noqa: BLE001 — boundary
                    raise JevUnavailableError(f"typesafe SDK error: {type(exc).__name__}") from exc

    return SdkJevClient()


def parse_choice_answer(raw: Any) -> ChoiceAnswer | None:
    if raw is None:
        return None
    if isinstance(raw, ChoiceAnswer):
        return raw
    if not isinstance(raw, dict):
        return None
    choice = raw.get("choice")
    if not choice:
        return None
    return ChoiceAnswer(
        choice=str(choice),
        confidence=float(raw.get("confidence") or 0.0),
        probabilities={str(k): float(v) for k, v in (raw.get("probabilities") or {}).items()},
    )
