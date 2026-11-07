"""Lógica de triage: prompt → LLM → validación (con retry) → métricas.

Es la función que reutilizan tanto la CLI (main.py) como, más adelante, el runner de evals.
Fase 4: un solo proveedor (OpenAI), con retry y una línea de métricas por request.
"""

import os
import re
import sys
import time
from dataclasses import dataclass

from openai import OpenAI
from pydantic import ValidationError

from src import metrics
from src.prompts import load_prompt
from src.schema import TriageResponse

DEFAULT_PROMPT = "v1_zero_shot"
PROVIDER = "openai"  # fase 5: pasa a ser configurable con LLM_PROVIDER

# Parámetros de sampling: viven en el código, NO en el YAML, para que al comparar
# prompts la única variable sea el texto del prompt.
TEMPERATURE = 0  # clasificación: queremos la misma salida ante la misma entrada
MAX_OUTPUT_TOKENS = 500  # el JSON esperado ocupa ~150 tokens; esto corta respuestas desbocadas

# Reintentos ante respuesta inválida (no ante errores de API: eso es backoff, fase 5).
# 2 reintentos = hasta 3 llamadas. Cada reintento reenvía todo el historial: es caro.
MAX_RETRIES = 2

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
class LLMResult:
    """Lo que devuelve una llamada al LLM: el texto y cuántos tokens consumió."""

    text: str
    input_tokens: int
    output_tokens: int
    cached_input_tokens: int = 0


@dataclass
class RequestStats:
    """Acumulado de un request completo (todos los intentos del retry)."""

    attempts: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cached_input_tokens: int = 0

    def add(self, result: LLMResult) -> None:
        self.attempts += 1
        self.input_tokens += result.input_tokens
        self.output_tokens += result.output_tokens
        self.cached_input_tokens += result.cached_input_tokens


def get_model() -> str:
    return os.getenv("OPENAI_MODEL", "gpt-5.4-nano")


def call_llm(messages: list[dict]) -> LLMResult:
    """Llama a OpenAI con la conversación y devuelve el texto crudo y el uso de tokens.

    Toda la dependencia con el proveedor queda aislada acá: en la fase 5 esto pasa a
    ser una implementación de LLMProvider.
    """
    client = OpenAI()  # toma OPENAI_API_KEY del entorno

    response = client.responses.create(
        model=get_model(),
        input=messages,
        temperature=TEMPERATURE,
        max_output_tokens=MAX_OUTPUT_TOKENS,
    )
    usage = response.usage
    details = usage.input_tokens_details
    return LLMResult(
        text=response.output_text,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,  # incluye tokens de razonamiento, si los hubo
        cached_input_tokens=(details.cached_tokens or 0) if details else 0,
    )


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


def _run_with_retry(messages: list[dict], stats: RequestStats) -> TriageResponse:
    """Llama al LLM y valida; ante respuesta inválida reintenta con feedback."""
    total_attempts = MAX_RETRIES + 1

    for attempt in range(1, total_attempts + 1):
        result = call_llm(messages)
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


def triage(query: str, prompt_name: str = DEFAULT_PROMPT) -> TriageResponse:
    """Clasifica una consulta y devuelve la respuesta validada.

    Si la respuesta no cumple el contrato, le devuelve el error al modelo y reintenta
    hasta MAX_RETRIES veces. Cada request (exitoso o no) deja una línea en metrics.jsonl.
    Lanza PromptError si el prompt no existe, TriageError si se agotan los intentos y
    errores de openai si falla la API.
    """
    prompt = load_prompt(prompt_name)
    messages = [
        {"role": "system", "content": prompt.system},
        {"role": "user", "content": prompt.render_user(query)},
    ]
    model = get_model()
    stats = RequestStats()
    result: TriageResponse | None = None
    error: str | None = None
    start = time.perf_counter()

    try:
        result = _run_with_retry(messages, stats)
        return result
    except Exception as e:
        error = type(e).__name__
        raise
    finally:
        # finally: se registra SIEMPRE, salga bien o mal. Los fallos también cuestan.
        metrics.log_request(
            {
                "provider": PROVIDER,
                "model": model,
                "prompt": prompt_name,
                "attempts": stats.attempts,
                "success": result is not None,
                "error": error,
                "category": result.category if result else None,
                "input_tokens": stats.input_tokens,
                "cached_input_tokens": stats.cached_input_tokens,
                "output_tokens": stats.output_tokens,
                "total_tokens": stats.input_tokens + stats.output_tokens,
                "latency_s": round(time.perf_counter() - start, 3),
                **metrics.compute_cost(model, stats.input_tokens, stats.output_tokens),
            }
        )
