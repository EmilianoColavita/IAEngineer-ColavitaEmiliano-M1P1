"""Proveedores de LLM detrás de una abstracción común.

`triage.py` solo conoce `LLMProvider`, `LLMResult` y los errores de este módulo. Cada
adaptador (OpenAI, Gemini) traduce desde y hacia su propia API:
  - el formato de los mensajes (roles, system prompt),
  - el conteo de tokens,
  - los errores (a RetryableError / ProviderError).

Agregar un proveedor = escribir un adaptador nuevo y registrarlo en PROVIDERS.
La lógica de negocio no cambia.
"""

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass

import httpx
import httpx2

# Los SDKs reintentan por su cuenta (OpenAI: 2 veces por defecto, en silencio). Se apagan
# acá para que haya UN solo backoff, explícito, logueado y medido: el de triage.py.
REQUEST_TIMEOUT_S = 30

# Errores de red de bajo nivel (conexión caída, timeout) que pueden escaparse de un SDK.
_NETWORK_ERRORS = (httpx.TransportError, httpx2.TransportError)


# --- Contrato ---------------------------------------------------------------


@dataclass
class LLMResult:
    """Lo que devuelve una llamada al LLM: el texto y cuántos tokens consumió."""

    text: str
    input_tokens: int
    output_tokens: int  # incluye tokens de razonamiento/"thinking": se cobran como output
    cached_input_tokens: int = 0


class ProviderError(Exception):
    """Error del proveedor que NO tiene sentido reintentar (key inválida, sin saldo, etc.)."""


class RetryableError(ProviderError):
    """Error transitorio (rate limit, 5xx, timeout, red): vale la pena esperar y reintentar."""

    def __init__(self, message: str, retry_after: float | None = None):
        super().__init__(message)
        self.retry_after = retry_after  # segundos sugeridos por la API, si los informó


class LLMProvider(ABC):
    """Contrato que todo proveedor tiene que cumplir."""

    name: str  # "openai", "gemini"...
    model: str

    @abstractmethod
    def generate(
        self, messages: list[dict], *, temperature: float, max_output_tokens: int
    ) -> LLMResult:
        """Recibe la conversación en formato neutro y devuelve texto + tokens.

        Formato neutro de `messages`: [{"role": "system"|"user"|"assistant", "content": str}].
        Lanza RetryableError ante fallas transitorias y ProviderError ante el resto.
        """


def _require_env(var: str) -> str:
    value = os.getenv(var)
    if not value:
        raise ProviderError(f"Falta la variable {var} en el .env")
    return value


def _parse_retry_after(headers) -> float | None:
    """Lee el header Retry-After (en segundos), si vino y es un número."""
    if headers is None:
        return None
    try:
        return float(headers.get("retry-after"))
    except (TypeError, ValueError):
        return None


# --- OpenAI -----------------------------------------------------------------


class OpenAIProvider(LLMProvider):
    name = "openai"

    def __init__(self, model: str | None = None):
        from openai import OpenAI

        self.model = model or os.getenv("OPENAI_MODEL", "gpt-5.4-nano")
        self._client = OpenAI(
            api_key=_require_env("OPENAI_API_KEY"),
            max_retries=0,  # sin reintentos ocultos del SDK
            timeout=REQUEST_TIMEOUT_S,
        )

    def generate(self, messages, *, temperature, max_output_tokens) -> LLMResult:
        import openai

        try:
            # El formato neutro coincide con el de OpenAI: no hace falta traducir mensajes.
            response = self._client.responses.create(
                model=self.model,
                input=messages,
                temperature=temperature,
                max_output_tokens=max_output_tokens,
            )
        except openai.RateLimitError as e:
            # 429 puede ser "demasiadas requests" (transitorio) o "sin saldo" (no se arregla esperando).
            if e.code == "insufficient_quota":
                raise ProviderError(f"OpenAI sin saldo (insufficient_quota): {e.message}") from e
            raise RetryableError(
                f"OpenAI rate limit: {e.message}", _parse_retry_after(e.response.headers)
            ) from e
        except openai.InternalServerError as e:  # 5xx
            raise RetryableError(f"OpenAI error del servidor {e.status_code}") from e
        except openai.APIConnectionError as e:  # incluye APITimeoutError
            raise RetryableError(f"OpenAI conexión/timeout: {type(e).__name__}") from e
        except openai.APIStatusError as e:  # 400, 401, 403, 404...
            raise ProviderError(f"OpenAI error {e.status_code}: {e.message}") from e
        except _NETWORK_ERRORS as e:
            raise RetryableError(f"OpenAI error de red: {type(e).__name__}") from e

        usage = response.usage
        details = usage.input_tokens_details
        return LLMResult(
            text=response.output_text,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cached_input_tokens=(details.cached_tokens or 0) if details else 0,
        )


# --- Gemini -----------------------------------------------------------------


class GeminiProvider(LLMProvider):
    name = "gemini"

    def __init__(self, model: str | None = None):
        from google import genai
        from google.genai import types

        self.model = model or os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite")
        self._client = genai.Client(
            api_key=_require_env("GEMINI_API_KEY"),
            http_options=types.HttpOptions(
                timeout=REQUEST_TIMEOUT_S * 1000,  # Gemini usa milisegundos
                retry_options=types.HttpRetryOptions(attempts=1),  # sin reintentos del SDK
            ),
        )

    @staticmethod
    def _to_gemini(messages: list[dict]):
        """Formato neutro → (system_instruction, contents) de Gemini.

        Diferencias: el system va aparte, y el rol de la respuesta del modelo se llama
        "model" en lugar de "assistant".
        """
        from google.genai import types

        system = None
        contents = []
        for m in messages:
            if m["role"] == "system":
                system = m["content"]
            else:
                role = "model" if m["role"] == "assistant" else "user"
                contents.append(types.Content(role=role, parts=[types.Part(text=m["content"])]))
        return system, contents

    def generate(self, messages, *, temperature, max_output_tokens) -> LLMResult:
        from google.genai import errors, types

        system, contents = self._to_gemini(messages)
        try:
            response = self._client.models.generate_content(
                model=self.model,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=system,
                    temperature=temperature,
                    max_output_tokens=max_output_tokens,
                ),
            )
        except errors.APIError as e:
            # 429 (cuota/rate limit) y 5xx son transitorios; el resto (400, 401, 403, 404) no.
            if e.code == 429 or e.code >= 500:
                headers = getattr(e.response, "headers", None)
                raise RetryableError(
                    f"Gemini error {e.code} {e.status}", _parse_retry_after(headers)
                ) from e
            raise ProviderError(f"Gemini error {e.code} {e.status}: {e.message}") from e
        except _NETWORK_ERRORS as e:
            raise RetryableError(f"Gemini error de red: {type(e).__name__}") from e

        usage = response.usage_metadata
        return LLMResult(
            # text puede ser None (respuesta bloqueada o cortada): "" hace que falle la
            # validación y entre el retry con feedback, en lugar de romper acá.
            text=response.text or "",
            input_tokens=usage.prompt_token_count or 0,
            # Gemini separa la respuesta visible del "thinking", pero ambos se cobran como output.
            output_tokens=(usage.candidates_token_count or 0) + (usage.thoughts_token_count or 0),
            cached_input_tokens=usage.cached_content_token_count or 0,
        )


# --- Fábrica ----------------------------------------------------------------

PROVIDERS: dict[str, type[LLMProvider]] = {
    "openai": OpenAIProvider,
    "gemini": GeminiProvider,
}


def get_provider(name: str | None = None) -> LLMProvider:
    """Devuelve el proveedor pedido o, si no se indica, el de LLM_PROVIDER en el .env."""
    name = (name or os.getenv("LLM_PROVIDER", "openai")).strip().lower()
    if name not in PROVIDERS:
        raise ProviderError(
            f"Proveedor desconocido '{name}'. Disponibles: {', '.join(PROVIDERS)}"
        )
    return PROVIDERS[name]()
