"""Lógica de triage: prompt → LLM → validación (con retry) → métricas.

Es la función que reutilizan tanto la CLI (main.py) como, más adelante, el runner de evals.
No conoce a ningún proveedor concreto: habla con `LLMProvider` (ver providers.py).

Dos capas de reintento, una adentro de la otra:
  - retry de validación: el modelo respondió algo inválido → feedback → nueva llamada.
  - backoff de API: la llamada falló (rate limit, 5xx, red) → esperar → misma llamada.
"""

import random
import re
import sys
import time
from dataclasses import dataclass

from pydantic import ValidationError

from src import metrics
from src.guardrails import blocked_response, check_input, check_output
from src.prompts import load_prompt
from src.providers import LLMProvider, LLMResult, ProviderError, RetryableError, get_provider
from src.schema import TriageResponse

# Elegido con datos de evals (ver README, "Context engineering"): mayor accuracy con el
# proveedor por defecto (OpenAI gpt-5.4-nano), según el criterio acordado antes de medir.
DEFAULT_PROMPT = "v3_frontier_rules"

# Parámetros de sampling: viven en el código, NO en el YAML, para que al comparar
# prompts la única variable sea el texto del prompt. Se pasan a cualquier proveedor.
TEMPERATURE = 0  # clasificación: queremos la misma salida ante la misma entrada
MAX_OUTPUT_TOKENS = 500  # el JSON esperado ocupa ~150 tokens; esto corta respuestas desbocadas

# Retry de validación: 2 reintentos = hasta 3 llamadas. Cada uno reenvía todo el historial.
MAX_RETRIES = 2

# Backoff de API: hasta 3 reintentos por llamada, espera 1s, 2s, 4s... (tope 20s) + jitter.
MAX_API_RETRIES = 3
BACKOFF_BASE_S = 1.0
BACKOFF_MAX_S = 20.0

# Se usa a través de esta variable para que los checks puedan simular la espera.
_sleep = time.sleep

# Mensaje de feedback al modelo. Vive en código (no en el YAML) porque es igual para
# todas las versiones de prompt: así no altera la comparación entre v1 y v2.
RETRY_MESSAGE = """Tu respuesta anterior no cumple el formato requerido. Errores:
{errors}

Respondé de nuevo ÚNICAMENTE con el objeto JSON corregido, sin texto adicional."""

# ```json ... ``` o ``` ... ``` envolviendo toda la respuesta.
_CODE_FENCE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL)


class TriageError(Exception):
    """El modelo no devolvió una respuesta válida después de todos los intentos."""

    def __init__(self, message: str, attempts: int, last_raw: str):
        super().__init__(message)
        self.attempts = attempts
        self.last_raw = last_raw  # última respuesta cruda: clave para depurar


@dataclass
class RequestStats:
    """Acumulado de un request completo (todos los intentos)."""

    attempts: int = 0  # llamadas que devolvieron respuesta (retry de validación)
    api_retries: int = 0  # reintentos por errores de API (backoff)
    input_tokens: int = 0
    output_tokens: int = 0
    cached_input_tokens: int = 0

    def add(self, result: LLMResult) -> None:
        self.attempts += 1
        self.input_tokens += result.input_tokens
        self.output_tokens += result.output_tokens
        self.cached_input_tokens += result.cached_input_tokens


def clean_raw(raw: str) -> str:
    """Saca espacios y un bloque de código markdown que envuelva la respuesta.

    Es un error cosmético y predecible: arreglarlo en código es gratis y determinístico,
    mientras que un retry costaría una llamada entera.
    """
    raw = raw.strip()
    match = _CODE_FENCE.match(raw)
    return match.group(1) if match else raw


def format_errors(error: ValidationError) -> str:
    """Convierte un ValidationError en una lista breve y legible para el modelo."""
    lines = []
    for err in error.errors(include_url=False):
        campo = ".".join(str(p) for p in err["loc"]) or "(json)"
        lines.append(f"- {campo}: {err['msg']}")
    return "\n".join(lines)


def backoff_delay(retry_number: int, retry_after: float | None = None) -> float:
    """Segundos a esperar antes del reintento N (0, 1, 2...).

    Si la API dijo cuánto esperar (Retry-After), se respeta. Si no: exponencial
    (1s, 2s, 4s...) con tope, más jitter para que muchos clientes no reintenten juntos.
    """
    if retry_after is not None:
        return min(retry_after, BACKOFF_MAX_S)
    delay = min(BACKOFF_BASE_S * 2**retry_number, BACKOFF_MAX_S)
    return delay + random.uniform(0, delay / 2)


def _call_with_backoff(
    provider: LLMProvider, messages: list[dict], stats: RequestStats
) -> LLMResult:
    """Llama al proveedor; ante errores transitorios espera y reintenta.

    ProviderError (no reintentable) se propaga de inmediato: esperar no lo arregla.
    """
    for retry_number in range(MAX_API_RETRIES + 1):
        try:
            return provider.generate(
                messages, temperature=TEMPERATURE, max_output_tokens=MAX_OUTPUT_TOKENS
            )
        except RetryableError as e:
            if retry_number == MAX_API_RETRIES:
                raise
            delay = backoff_delay(retry_number, e.retry_after)
            stats.api_retries += 1
            print(
                f"[backoff] {e} → reintento {retry_number + 1}/{MAX_API_RETRIES} en {delay:.1f}s",
                file=sys.stderr,
            )
            _sleep(delay)


def _run_with_retry(
    provider: LLMProvider, messages: list[dict], stats: RequestStats
) -> TriageResponse:
    """Llama al LLM y valida; ante respuesta inválida reintenta con feedback."""
    total_attempts = MAX_RETRIES + 1

    for attempt in range(1, total_attempts + 1):
        result = _call_with_backoff(provider, messages, stats)
        stats.add(result)  # se cuenta ANTES de validar: un intento fallido también se paga
        raw = result.text
        try:
            return TriageResponse.model_validate_json(clean_raw(raw))
        except ValidationError as e:
            errors = format_errors(e)
            # stderr: stdout queda reservado para el JSON final.
            print(f"[retry] intento {attempt}/{total_attempts} inválido:\n{errors}", file=sys.stderr)
            # Feedback: lo que respondió + qué estuvo mal, para que corrija.
            messages += [
                {"role": "assistant", "content": raw},
                {"role": "user", "content": RETRY_MESSAGE.format(errors=errors)},
            ]

    raise TriageError(
        f"El modelo no devolvió una respuesta válida en {total_attempts} intentos.",
        attempts=total_attempts,
        last_raw=raw,
    )


@dataclass
class TriageRun:
    """Resultado completo de un request: la respuesta (o el error) + su línea de métricas."""

    response: TriageResponse | None
    record: dict  # la misma línea que se escribió en metrics.jsonl
    error: Exception | None = None
    raw_response: TriageResponse | None = None  # la del modelo, ANTES del guardrail de salida


def run_triage(
    query: str,
    prompt_name: str = DEFAULT_PROMPT,
    provider: LLMProvider | None = None,
    source: str = "cli",
    guardrails: bool = True,
) -> TriageRun:
    """Clasifica una consulta y devuelve respuesta + métricas, sin lanzar errores esperables.

    Flujo: guardrail de entrada → LLM (retry + backoff) → Pydantic → guardrail de salida.
    Pensada para quien necesita los números de cada request (el runner de evals).
    TriageError y ProviderError quedan en `TriageRun.error` en lugar de lanzarse.
    `source` ("cli" / "eval" / "adversarial") distingue el origen en metrics.jsonl.
    `guardrails=False` solo se usa para MEDIR su efecto en la suite adversarial.
    Cada request (exitoso o no) deja una línea en metrics.jsonl.
    """
    prompt = load_prompt(prompt_name)  # PromptError sí se lanza: es un error de uso
    provider = provider or get_provider()
    messages = [
        {"role": "system", "content": prompt.system},
        {"role": "user", "content": prompt.render_user(query)},
    ]
    stats = RequestStats()
    response: TriageResponse | None = None
    raw_response: TriageResponse | None = None
    error: Exception | None = None
    guardrail: str | None = None
    start = time.perf_counter()

    try:
        input_check = check_input(query) if guardrails else None
        if input_check and input_check.blocked:
            # Bloqueado ANTES del LLM: no se gastan tokens en un ataque.
            guardrail = f"input:{input_check.reason}"
            response = blocked_response(input_check)
            print(f"[guardrail] entrada bloqueada ({input_check.reason})", file=sys.stderr)
        else:
            raw_response = response = _run_with_retry(provider, messages, stats)
            if guardrails:
                out = check_output(raw_response, prompt.system)
                if out.triggered:
                    response = out.response
                    guardrail = "output:" + ",".join(out.blocked + out.flagged)
                    print(f"[guardrail] salida: {', '.join(out.blocked + out.flagged)}", file=sys.stderr)
    except (TriageError, ProviderError) as e:
        error = e  # esperables: se devuelven, no se lanzan
    except Exception as e:
        error = e  # inesperado (un bug): se registra y se relanza
        raise
    finally:
        # finally: se registra SIEMPRE, salga bien o mal. Los fallos también cuestan.
        record = {
            "source": source,
            "provider": provider.name,
            "model": provider.model,
            "prompt": prompt_name,
            "attempts": stats.attempts,
            "api_retries": stats.api_retries,
            "success": response is not None,
            "error": type(error).__name__ if error else None,
            "guardrail": guardrail,
            "category": response.category if response else None,
            "input_tokens": stats.input_tokens,
            "cached_input_tokens": stats.cached_input_tokens,
            "output_tokens": stats.output_tokens,
            "total_tokens": stats.input_tokens + stats.output_tokens,
            # incluye las esperas del backoff: es la latencia que vive el usuario
            "latency_s": round(time.perf_counter() - start, 3),
            **metrics.compute_cost(provider.model, stats.input_tokens, stats.output_tokens),
        }
        metrics.log_request(record)

    return TriageRun(response, record, error, raw_response)


def triage(
    query: str,
    prompt_name: str = DEFAULT_PROMPT,
    provider: LLMProvider | None = None,
) -> TriageResponse:
    """Clasifica una consulta y devuelve la respuesta validada (uso desde la CLI).

    `provider`: si no se pasa, se usa el de LLM_PROVIDER en el .env.
    Lanza PromptError si el prompt no existe, TriageError si se agotan los intentos de
    validación y ProviderError si falla el proveedor (incluido RetryableError agotado).
    """
    run = run_triage(query, prompt_name, provider, source="cli")
    if run.error:
        raise run.error
    return run.response
