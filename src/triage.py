"""Lógica de triage: prompt → LLM → validación (con retry).

Es la función que reutilizan tanto la CLI (main.py) como, más adelante, el runner de evals.
Fase 3: un solo proveedor (OpenAI), con retry ante respuestas inválidas. Sin métricas todavía.
"""

import os
import re
import sys

from openai import OpenAI
from pydantic import ValidationError

from src.prompts import load_prompt
from src.schema import TriageResponse

DEFAULT_PROMPT = "v1_zero_shot"

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


def call_llm(messages: list[dict]) -> str:
    """Llama a OpenAI con la conversación y devuelve el texto crudo de la respuesta.

    Toda la dependencia con el proveedor queda aislada acá: en la fase 5 esto pasa a
    ser una implementación de LLMProvider.
    """
    model = os.getenv("OPENAI_MODEL", "gpt-5.4-nano")
    client = OpenAI()  # toma OPENAI_API_KEY del entorno

    response = client.responses.create(
        model=model,
        input=messages,
        temperature=TEMPERATURE,
        max_output_tokens=MAX_OUTPUT_TOKENS,
    )
    return response.output_text


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


def triage(query: str, prompt_name: str = DEFAULT_PROMPT) -> TriageResponse:
    """Clasifica una consulta y devuelve la respuesta validada.

    Si la respuesta no cumple el contrato, le devuelve el error al modelo y reintenta
    hasta MAX_RETRIES veces. Lanza PromptError si el prompt no existe, TriageError si
    se agotan los intentos y errores de openai si falla la API.
    """
    prompt = load_prompt(prompt_name)
    messages = [
        {"role": "system", "content": prompt.system},
        {"role": "user", "content": prompt.render_user(query)},
    ]
    total_attempts = MAX_RETRIES + 1

    for attempt in range(1, total_attempts + 1):
        raw = call_llm(messages)
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
