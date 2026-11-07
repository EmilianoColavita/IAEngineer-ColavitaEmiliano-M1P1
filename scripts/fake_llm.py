"""Herramientas compartidas por los checks: un proveedor falso y métricas en archivo temporal.

`FakeProvider` implementa el mismo contrato `LLMProvider` que OpenAI y Gemini: triage()
no nota la diferencia. Sirve para probar la lógica propia (retry, backoff, métricas)
gratis y con resultados siempre iguales. No prueba al modelo real.
"""

import tempfile
from pathlib import Path

from src import metrics
from src.providers import LLMProvider, LLMResult

VALIDO = (
    '{"answer": "Revisamos tu cobro duplicado", "confidence": 0.9, '
    '"category": "billing", "actions": ["Verificar transacciones del cliente"]}'
)
CONFIDENCE_INVALIDA = VALIDO.replace("0.9", "1.3")
JSON_ROTO = VALIDO[:-1]  # sin la llave de cierre
CON_FENCE = f"```json\n{VALIDO}\n```"


class FakeProvider(LLMProvider):
    """Proveedor falso: devuelve las respuestas preprogramadas en orden.

    Cada elemento de `respuestas` es un str (texto que "responde el modelo") o una
    excepción (que se lanza, para simular errores de API).
    Cada llamada "consume" input_tokens + 10 por cada mensaje extra del historial,
    para imitar que los reintentos reenvían la conversación (y cuestan más).
    """

    name = "fake"

    def __init__(self, respuestas, model="gpt-5.4-nano", input_tokens=100, output_tokens=50):
        self.model = model  # por defecto un modelo con precio conocido
        self.respuestas = list(respuestas)
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.llamadas: list[list[dict]] = []  # conversación recibida en cada llamada

    def generate(self, messages, *, temperature, max_output_tokens) -> LLMResult:
        self.llamadas.append([dict(m) for m in messages])
        respuesta = self.respuestas[len(self.llamadas) - 1]
        if isinstance(respuesta, Exception):
            raise respuesta
        return LLMResult(
            text=respuesta,
            input_tokens=self.input_tokens + 10 * (len(messages) - 2),
            output_tokens=self.output_tokens,
        )


def use_temp_metrics() -> Path:
    """Apunta las métricas a un archivo temporal nuevo (no toca data/metrics.jsonl)."""
    path = Path(tempfile.mkdtemp()) / "metrics.jsonl"
    metrics.METRICS_PATH = path
    return path
