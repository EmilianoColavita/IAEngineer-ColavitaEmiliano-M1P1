"""Lógica de triage: prompt → LLM → validación.

Es la función que reutilizan tanto la CLI (main.py) como, más adelante, el runner de evals.
Fase 2: un solo proveedor (OpenAI), sin retry ni métricas todavía.
"""

import os

from openai import OpenAI

from src.prompts import load_prompt
from src.schema import TriageResponse

DEFAULT_PROMPT = "v1_zero_shot"

# Parámetros de sampling: viven en el código, NO en el YAML, para que al comparar
# prompts la única variable sea el texto del prompt.
TEMPERATURE = 0  # clasificación: queremos la misma salida ante la misma entrada
MAX_OUTPUT_TOKENS = 500  # el JSON esperado ocupa ~150 tokens; esto corta respuestas desbocadas


def call_llm(system: str, user: str) -> str:
    """Llama a OpenAI y devuelve el texto crudo de la respuesta.

    Toda la dependencia con el proveedor queda aislada acá: en la fase 5 esto pasa a
    ser una implementación de LLMProvider.
    """
    model = os.getenv("OPENAI_MODEL", "gpt-5.4-nano")
    client = OpenAI()  # toma OPENAI_API_KEY del entorno

    response = client.responses.create(
        model=model,
        input=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=TEMPERATURE,
        max_output_tokens=MAX_OUTPUT_TOKENS,
    )
    return response.output_text


def triage(query: str, prompt_name: str = DEFAULT_PROMPT) -> TriageResponse:
    """Clasifica una consulta y devuelve la respuesta validada.

    Lanza PromptError si el prompt no existe, ValidationError si el modelo devuelve
    algo que no cumple el contrato, y errores de openai si falla la API.
    """
    prompt = load_prompt(prompt_name)
    raw = call_llm(prompt.system, prompt.render_user(query))
    return TriageResponse.model_validate_json(raw)
