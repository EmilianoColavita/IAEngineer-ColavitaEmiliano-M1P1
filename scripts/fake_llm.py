"""Herramientas compartidas por los checks: un LLM falso y métricas en archivo temporal.

No llama a ninguna API: sirve para probar la lógica propia (retry, métricas) gratis y
con resultados siempre iguales. No prueba al modelo real.
"""

import tempfile
from pathlib import Path

from src import metrics
from src import triage as triage_module
from src.triage import LLMResult

VALIDO = (
    '{"answer": "Revisamos tu cobro duplicado", "confidence": 0.9, '
    '"category": "billing", "actions": ["Verificar transacciones del cliente"]}'
)
CONFIDENCE_INVALIDA = VALIDO.replace("0.9", "1.3")
JSON_ROTO = VALIDO[:-1]  # sin la llave de cierre
CON_FENCE = f"```json\n{VALIDO}\n```"


def install_fake_llm(respuestas: list[str], input_tokens=100, output_tokens=50):
    """Reemplaza call_llm por uno falso que responde en orden.

    Devuelve la lista donde se registra la conversación recibida en cada llamada.
    Cada llamada "consume" input_tokens + 10 por cada mensaje extra del historial,
    para imitar que los reintentos reenvían la conversación (y cuestan más).
    """
    llamadas = []

    def call_llm(messages: list[dict]) -> LLMResult:
        llamadas.append([dict(m) for m in messages])
        return LLMResult(
            text=respuestas[len(llamadas) - 1],
            input_tokens=input_tokens + 10 * (len(messages) - 2),
            output_tokens=output_tokens,
        )

    triage_module.call_llm = call_llm
    return llamadas


def use_temp_metrics() -> Path:
    """Apunta las métricas a un archivo temporal nuevo (no toca data/metrics.jsonl)."""
    path = Path(tempfile.mkdtemp()) / "metrics.jsonl"
    metrics.METRICS_PATH = path
    return path
