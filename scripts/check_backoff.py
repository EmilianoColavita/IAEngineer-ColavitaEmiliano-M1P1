"""Verifica el backoff y la traducción de errores de los proveedores, sin llamar a la API.

Parte 1: lógica de backoff en triage() con un proveedor falso (las esperas se simulan).
Parte 2: los adaptadores reales (OpenAI, Gemini) reciben excepciones auténticas de cada
SDK y tienen que traducirlas a RetryableError / ProviderError.

Uso (desde la raíz del repo):
    python -m scripts.check_backoff
"""

import os

import httpx2
import openai
from google.genai import errors as gemini_errors

from scripts.fake_llm import VALIDO, FakeProvider, use_temp_metrics
from src import triage as triage_module
from src.providers import GeminiProvider, OpenAIProvider, ProviderError, RetryableError
from src.triage import MAX_API_RETRIES, triage

resultados = []


def check(descripcion: str, condicion: bool) -> None:
    print(f"{'OK   ' if condicion else 'FALLA'} {descripcion}")
    resultados.append(condicion)


def parte_1_backoff():
    print("--- Backoff en triage() ---")
    esperas: list[float] = []
    triage_module._sleep = esperas.append  # no esperar de verdad: solo registrar

    # Transitorio x2 y después responde: se recupera
    esperas.clear()
    p = FakeProvider([RetryableError("429"), RetryableError("503"), VALIDO])
    r = triage("me cobraron dos veces", provider=p)
    check("transitorio x2 → se recupera al 3er intento", r.category == "billing" and len(p.llamadas) == 3)
    check("las esperas crecen (1s+jitter, luego 2s+jitter)",
          len(esperas) == 2 and 1 <= esperas[0] <= 1.5 and 2 <= esperas[1] <= 3)

    # Retry-After de la API se respeta
    esperas.clear()
    triage("hola", provider=FakeProvider([RetryableError("429", retry_after=7), VALIDO]))
    check("respeta Retry-After (espera 7s)", esperas == [7])

    # No reintentable: falla de inmediato, sin esperar
    esperas.clear()
    p = FakeProvider([ProviderError("sin saldo"), VALIDO])
    try:
        triage("hola", provider=p)
        fallo = False
    except ProviderError:
        fallo = True
    check("no reintentable → falla de inmediato, 1 llamada, sin esperas",
          fallo and len(p.llamadas) == 1 and esperas == [])

    # Transitorio persistente: se rinde tras MAX_API_RETRIES
    esperas.clear()
    p = FakeProvider([RetryableError("503")] * (MAX_API_RETRIES + 1))
    try:
        triage("hola", provider=p)
        fallo = False
    except RetryableError:
        fallo = True
    check(f"transitorio persistente → se rinde tras {MAX_API_RETRIES} reintentos",
          fallo and len(p.llamadas) == MAX_API_RETRIES + 1 and len(esperas) == MAX_API_RETRIES)
    check("ninguna espera supera el tope", all(e <= triage_module.BACKOFF_MAX_S * 1.5 for e in esperas))


def _openai_response(status: int, headers=None) -> httpx2.Response:
    req = httpx2.Request("POST", "https://api.openai.com/v1/responses")
    return httpx2.Response(status, request=req, headers=headers or {})


def _clasifica(provider, error) -> str:
    """Hace que el SDK 'lance' `error` y devuelve qué tipo propio produjo el adaptador."""

    def boom(*args, **kwargs):
        raise error

    if isinstance(provider, OpenAIProvider):
        provider._client.responses.create = boom
    else:
        provider._client.models.generate_content = boom
    try:
        provider.generate([{"role": "user", "content": "hola"}], temperature=0, max_output_tokens=10)
    except RetryableError as e:
        return f"retryable:{e.retry_after}" if e.retry_after else "retryable"
    except ProviderError:
        return "fatal"
    return "sin error"


def parte_2_adaptadores():
    print("\n--- Traducción de errores de los SDKs ---")
    os.environ.setdefault("OPENAI_API_KEY", "sk-falsa")  # no se llama a la API
    os.environ.setdefault("GEMINI_API_KEY", "falsa")

    oa = OpenAIProvider()
    req = httpx2.Request("POST", "https://api.openai.com/v1/responses")
    casos_openai = [
        ("429 rate limit → reintentable",
         openai.RateLimitError("rate", response=_openai_response(429), body={"code": "rate_limit_exceeded"}),
         "retryable"),
        ("429 con Retry-After: 7 → reintentable, espera 7",
         openai.RateLimitError("rate", response=_openai_response(429, {"retry-after": "7"}), body=None),
         "retryable:7.0"),
        ("429 insufficient_quota → NO reintentable",
         openai.RateLimitError("quota", response=_openai_response(429), body={"code": "insufficient_quota"}),
         "fatal"),
        ("500 → reintentable",
         openai.InternalServerError("boom", response=_openai_response(500), body=None),
         "retryable"),
        ("timeout → reintentable", openai.APITimeoutError(request=req), "retryable"),
        ("401 key inválida → NO reintentable",
         openai.AuthenticationError("bad key", response=_openai_response(401), body=None),
         "fatal"),
        ("404 modelo inexistente → NO reintentable",
         openai.NotFoundError("no model", response=_openai_response(404), body=None),
         "fatal"),
    ]
    for desc, error, esperado in casos_openai:
        check(f"OpenAI {desc}", _clasifica(oa, error) == esperado)

    gm = GeminiProvider()

    def gerr(cls, code, status):
        return cls(code, {"error": {"code": code, "status": status, "message": status}})

    casos_gemini = [
        ("429 → reintentable", gerr(gemini_errors.ClientError, 429, "RESOURCE_EXHAUSTED"), "retryable"),
        ("503 → reintentable", gerr(gemini_errors.ServerError, 503, "UNAVAILABLE"), "retryable"),
        ("400 → NO reintentable", gerr(gemini_errors.ClientError, 400, "INVALID_ARGUMENT"), "fatal"),
        ("403 key inválida → NO reintentable", gerr(gemini_errors.ClientError, 403, "PERMISSION_DENIED"), "fatal"),
        ("error de red → reintentable", httpx2.ConnectError("sin conexión"), "retryable"),
    ]
    for desc, error, esperado in casos_gemini:
        check(f"Gemini {desc}", _clasifica(gm, error) == esperado)

    # Traducción de mensajes: system aparte y "assistant" → "model"
    system, contents = GeminiProvider._to_gemini([
        {"role": "system", "content": "S"},
        {"role": "user", "content": "U"},
        {"role": "assistant", "content": "A"},
    ])
    check("Gemini: system va aparte y assistant se traduce a 'model'",
          system == "S" and [c.role for c in contents] == ["user", "model"])


def main():
    use_temp_metrics()  # no ensuciar data/metrics.jsonl con datos falsos
    parte_1_backoff()
    parte_2_adaptadores()

    todo_ok = all(resultados)
    print(f"\n{'Todos los checks OK' if todo_ok else 'Hay checks que fallaron'}")
    raise SystemExit(0 if todo_ok else 1)


if __name__ == "__main__":
    main()
