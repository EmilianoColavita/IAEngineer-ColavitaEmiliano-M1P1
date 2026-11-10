"""Verifica que el runner de evals calcule bien el reporte, sin llamar a la API.

Un evaluador con errores de cálculo invalida todas las conclusiones: por eso también se
testea. Se arman 4 casos con un proveedor falso cuyas respuestas se conocen de antemano,
y se comparan las métricas con las calculadas a mano.

Uso (desde la raíz del repo):
    python -m scripts.check_runner
"""

import json

from evals.dataset import EvalCase
from evals.runner import INVALID, AbortRun, evaluate, summarize
from scripts.fake_llm import JSON_ROTO, FakeProvider, use_temp_metrics
from src.providers import ProviderError
from src.triage import MAX_RETRIES

resultados = []


def check(descripcion: str, condicion: bool) -> None:
    print(f"{'OK   ' if condicion else 'FALLA'} {descripcion}")
    resultados.append(condicion)


def respuesta(category: str, confidence: float) -> str:
    return json.dumps({"answer": "Respuesta", "confidence": confidence,
                       "category": category, "actions": []})


def main():
    use_temp_metrics()

    cases = [
        EvalCase(id="billing-01", query="q1", expected_category="billing", tags=["clear"]),
        EvalCase(id="technical-01", query="q2", expected_category="technical", tags=["frontier"]),
        EvalCase(id="account-01", query="q3", expected_category="account", tags=["clear"]),
        EvalCase(id="other-01", query="q4", expected_category="other",
                 acceptable_categories=["billing"], tags=["frontier"]),
    ]
    # Respuestas en orden de llamada:
    #   q1 → billing 0.9 (acierto) | q2 → billing 0.6 (fallo)
    #   q3 → JSON roto 3 veces (inválido) | q4 → billing 0.5 (fallo, pero alternativa aceptable)
    provider = FakeProvider(
        [respuesta("billing", 0.9), respuesta("billing", 0.6)]
        + [JSON_ROTO] * (MAX_RETRIES + 1)
        + [respuesta("billing", 0.5)]
    )
    results = evaluate(cases, "v1_zero_shot", provider, verbose=False)
    s = summarize(results)

    check("accuracy global estricta = 1/4 = 25%", s["accuracy"] == 25.0 and s["correct"] == 1)
    check("JSON válido = 3/4 = 75%", s["valid_json_pct"] == 75.0)
    check("válido al primer intento = 3/4 = 75%", s["first_try_pct"] == 75.0)
    check("por categoría: billing 100%, technical/account/other 0%",
          [s["per_category"][c]["accuracy"] for c in ("billing", "technical", "account", "other")]
          == [100.0, 0.0, 0.0, 0.0])
    check("por tag: clear 1/2 = 50%, frontier 0/2 = 0%",
          s["per_tag"]["clear"]["accuracy"] == 50.0 and s["per_tag"]["frontier"]["accuracy"] == 0.0)
    check("confusión: technical→billing 1, account→inválido 1, other→billing 1",
          s["confusion"]["technical"] == {"billing": 1}
          and s["confusion"]["account"] == {INVALID: 1}
          and s["confusion"]["other"] == {"billing": 1})
    check("alternativa aceptable: 1 caso, 1 hit, y NO suma al score",
          s["acceptable"] == {"cases": 1, "correct": 0, "acceptable_hits": 1})
    check("calibración: 0.9 al acertar, (0.6+0.5)/2 = 0.55 al fallar",
          s["calibration"] == {"mean_confidence_correct": 0.9, "mean_confidence_wrong": 0.55})
    check("costo total = suma de los costos de cada caso",
          abs(s["cost_usd_total"] - sum(r["cost_usd"] for r in results)) < 1e-9)
    check("3 fallos listados (technical-01, account-01, other-01)",
          [f["id"] for f in s["failures"]] == ["technical-01", "account-01", "other-01"])

    # Error no reintentable: la corrida se aborta en lugar de fallar 40 veces
    try:
        evaluate(cases, "v1_zero_shot", FakeProvider([ProviderError("sin saldo")]), verbose=False)
        abortada = False
    except AbortRun:
        abortada = True
    check("error no reintentable del proveedor → corrida abortada", abortada)

    todo_ok = all(resultados)
    print(f"\n{'Todos los checks OK' if todo_ok else 'Hay checks que fallaron'}")
    raise SystemExit(0 if todo_ok else 1)


if __name__ == "__main__":
    from src.console import use_utf8_output

    use_utf8_output()
    main()
