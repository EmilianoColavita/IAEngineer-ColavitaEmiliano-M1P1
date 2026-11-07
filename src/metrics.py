"""Métricas por request: costo estimado y registro append-only en `data/metrics.jsonl`.

Cada request (una consulta, aunque internamente haya tenido reintentos) agrega UNA línea
JSON. Cada línea guarda los tokens y los precios unitarios usados, así el costo se puede
recalcular a mano aunque los precios cambien en el futuro:

    cost_usd = input_tokens / 1_000_000 * price_input_per_1m
             + output_tokens / 1_000_000 * price_output_per_1m

Tokens cacheados: se registran (`cached_input_tokens`) pero se cobran a precio de input
completo. Es una estimación conservadora (techo) y más simple de auditar.
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Se lee en cada escritura (no se copia al importar): los checks lo apuntan a un archivo
# temporal para no ensuciar las métricas reales con datos de un LLM falso.
METRICS_PATH = ROOT / "data" / "metrics.jsonl"

# Precios en USD por 1M de tokens, tier Standard.
# Verificados el 2026-11-07 en:
#   - https://developers.openai.com/api/docs/pricing
#   - https://aistudio.google.com/docs/pricing (output incluye tokens de "thinking")
PRICES = {
    "gpt-5.4-nano": {"input": 0.20, "output": 1.25},
    "gpt-5.4-mini": {"input": 0.75, "output": 4.50},
    "gemini-3.1-flash-lite": {"input": 0.25, "output": 1.50},
}


def compute_cost(model: str, input_tokens: int, output_tokens: int) -> dict:
    """Devuelve el costo y los precios usados. Modelo desconocido → todo en None.

    No se inventa un precio: un costo vacío es honesto, uno inventado es un dato falso.
    """
    prices = PRICES.get(model)
    if prices is None:
        print(f"[metrics] AVISO: sin precio para '{model}', costo no calculado.", file=sys.stderr)
        return {"price_input_per_1m": None, "price_output_per_1m": None, "cost_usd": None}

    cost = (
        input_tokens / 1_000_000 * prices["input"]
        + output_tokens / 1_000_000 * prices["output"]
    )
    return {
        "price_input_per_1m": prices["input"],
        "price_output_per_1m": prices["output"],
        "cost_usd": round(cost, 8),
    }


def log_request(record: dict) -> None:
    """Agrega una línea al JSONL. Si no se puede escribir, avisa pero no rompe el triage."""
    line = {"timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"), **record}
    try:
        METRICS_PATH.parent.mkdir(parents=True, exist_ok=True)
        # "a" = append: nunca se reescriben líneas anteriores.
        with METRICS_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")
    except OSError as e:
        print(f"[metrics] AVISO: no se pudo escribir {METRICS_PATH}: {e}", file=sys.stderr)
