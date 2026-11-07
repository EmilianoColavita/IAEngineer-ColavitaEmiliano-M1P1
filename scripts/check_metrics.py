"""Verifica las métricas de triage() sin llamar a la API.

Usa un LLM falso y un archivo de métricas temporal, y comprueba que cada request deje
una línea con los tokens sumados de todos los intentos y un costo recalculable a mano.

Uso (desde la raíz del repo):
    python -m scripts.check_metrics
"""

import json

from scripts.fake_llm import JSON_ROTO, VALIDO, install_fake_llm, use_temp_metrics
from src import metrics
from src import triage as triage_module
from src.triage import MAX_RETRIES, TriageError, triage

resultados = []


def check(descripcion: str, condicion: bool) -> None:
    print(f"{'OK   ' if condicion else 'FALLA'} {descripcion}")
    resultados.append(condicion)


def ultima_linea(path) -> dict:
    return json.loads(path.read_text(encoding="utf-8").splitlines()[-1])


def costo_a_mano(linea: dict) -> float:
    """La fórmula del README, aplicada solo con datos de la propia línea."""
    return (
        linea["input_tokens"] / 1_000_000 * linea["price_input_per_1m"]
        + linea["output_tokens"] / 1_000_000 * linea["price_output_per_1m"]
    )


def main():
    path = use_temp_metrics()
    triage_module.get_model = lambda: "gpt-5.4-nano"  # modelo fijo con precio conocido

    # 1. Request exitoso en 1 intento
    install_fake_llm([VALIDO], input_tokens=100, output_tokens=50)
    triage("me cobraron dos veces")
    linea = ultima_linea(path)
    check("éxito: se escribe una línea", len(path.read_text(encoding="utf-8").splitlines()) == 1)
    check("éxito: success=true, attempts=1, category=billing",
          linea["success"] and linea["attempts"] == 1 and linea["category"] == "billing")
    check("éxito: tokens 100 in + 50 out = 150 total",
          (linea["input_tokens"], linea["output_tokens"], linea["total_tokens"]) == (100, 50, 150))
    check("éxito: el costo se recalcula a mano desde la línea",
          abs(costo_a_mano(linea) - linea["cost_usd"]) < 1e-9)
    check("éxito: tiene timestamp, latencia, prompt y precios",
          all(k in linea for k in ("timestamp", "latency_s", "prompt", "price_input_per_1m")))

    # 2. Request con retry: los tokens de TODOS los intentos se suman
    #    intento 1: 100 in (2 mensajes) | intento 2: 120 in (4 mensajes: + assistant + feedback)
    install_fake_llm([JSON_ROTO, VALIDO], input_tokens=100, output_tokens=50)
    triage("me cobraron dos veces")
    linea = ultima_linea(path)
    check("retry: attempts=2", linea["attempts"] == 2)
    check("retry: input sumado 100 + 120 = 220 (el 2do intento reenvía el historial)",
          linea["input_tokens"] == 220)
    check("retry: output sumado 50 + 50 = 100", linea["output_tokens"] == 100)

    # 3. Request fallido: también queda registrado (se pagó igual)
    install_fake_llm([JSON_ROTO] * (MAX_RETRIES + 1))
    try:
        triage("me cobraron dos veces")
    except TriageError:
        pass
    linea = ultima_linea(path)
    check("fallo: se registra con success=false y error=TriageError",
          linea["success"] is False and linea["error"] == "TriageError")
    check("fallo: category vacía y costo > 0",
          linea["category"] is None and linea["cost_usd"] > 0)

    # 4. Modelo sin precio: costo vacío, no inventado
    triage_module.get_model = lambda: "modelo-inexistente"
    install_fake_llm([VALIDO])
    triage("me cobraron dos veces")
    linea = ultima_linea(path)
    check("modelo sin precio: cost_usd = null (no se inventa)", linea["cost_usd"] is None)

    # 5. Append-only: 4 requests → 4 líneas
    check("append-only: 4 requests = 4 líneas",
          len(path.read_text(encoding="utf-8").splitlines()) == 4)

    check("el archivo real NO se tocó", metrics.METRICS_PATH == path)

    todo_ok = all(resultados)
    print(f"\n{'Todos los checks OK' if todo_ok else 'Hay checks que fallaron'}")
    raise SystemExit(0 if todo_ok else 1)


if __name__ == "__main__":
    main()
