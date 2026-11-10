"""Runner de evals: corre el dataset contra el sistema y reporta score global y por categoría.

Script simple (no pytest ni framework). Uso, desde la raíz del repo:
    python -m evals.runner --prompt v1_zero_shot
    python -m evals.runner --prompt v2_few_shot --provider gemini
    python -m evals.runner --prompt v1_zero_shot --model gpt-5.4-mini
    python -m evals.runner --prompt v1_zero_shot --limit 5        # prueba rápida y barata
    python evals/runner.py --prompt v1_zero_shot                  # forma equivalente

Cada corrida imprime un reporte y guarda el detalle en evals/results/ (evidencia para el
README). Con --delay N se espacian las llamadas (rate limit). Cada caso también deja su línea en data/metrics.jsonl con source="eval".
"""

import sys
from pathlib import Path

# Permite también `python evals/runner.py`: agrega la raíz del repo al path de imports.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import argparse  # noqa: E402
import json  # noqa: E402
import time  # noqa: E402
from collections import Counter, defaultdict  # noqa: E402
from datetime import datetime, timezone  # noqa: E402
from typing import get_args  # noqa: E402

from dotenv import load_dotenv  # noqa: E402

from evals.dataset import EvalCase, load_dataset  # noqa: E402
from src.prompts import available_prompts  # noqa: E402
from src.providers import (  # noqa: E402
    PROVIDERS,
    LLMProvider,
    ProviderError,
    RetryableError,
    get_provider,
)
from src.schema import Category  # noqa: E402
from src.triage import DEFAULT_PROMPT, run_triage  # noqa: E402

RESULTS_DIR = Path(__file__).resolve().parent / "results"
CATEGORIES = get_args(Category)
INVALID = "(inválido)"  # "categoría predicha" cuando no hubo respuesta válida


class AbortRun(Exception):
    """Error no reintentable del proveedor: los casos restantes fallarían igual."""


# --- Ejecución ----------------------------------------------------------------


def evaluate(
    cases: list[EvalCase],
    prompt_name: str,
    provider: LLMProvider,
    verbose: bool = True,
    delay_s: float = 0.0,
) -> list[dict]:
    """Corre cada caso y devuelve un resultado por caso.

    `delay_s`: pausa entre casos, para no superar el límite de requests por minuto
    del proveedor (ej. el free tier de Gemini).
    """
    results = []
    for i, case in enumerate(cases, start=1):
        if delay_s and i > 1:
            time.sleep(delay_s)
        run = run_triage(case.query, prompt_name, provider, source="eval")

        # Key inválida, sin saldo, modelo inexistente: no tiene sentido seguir.
        if isinstance(run.error, ProviderError) and not isinstance(run.error, RetryableError):
            raise AbortRun(f"{case.id}: {run.error}")

        predicted = run.response.category if run.response else INVALID
        result = {
            "id": case.id,
            "query": case.query,
            "expected": case.expected_category,
            "acceptable": case.acceptable_categories,
            "tags": case.tags,
            "predicted": predicted,
            "confidence": run.response.confidence if run.response else None,
            "correct": predicted == case.expected_category,
            "acceptable_hit": predicted in case.acceptable_categories,
            "valid": run.response is not None,
            "first_try": run.response is not None and run.record["attempts"] == 1,
            # La API no atendió (rate limit/5xx persistente): NO es un problema de formato.
            "provider_error": isinstance(run.error, RetryableError),
            "guardrail": run.record.get("guardrail"),
            "error": run.record["error"],
            "answer": run.response.answer if run.response else None,
            "actions": run.response.actions if run.response else None,
            **{k: run.record[k] for k in (
                "attempts", "api_retries", "input_tokens", "output_tokens", "latency_s", "cost_usd"
            )},
        }
        results.append(result)

        if verbose:
            marca = "✓" if result["correct"] else ("~" if result["acceptable_hit"] else "✗")
            detalle = "" if result["correct"] else f"  (esperada {case.expected_category}, predijo {predicted})"
            print(f"[{i:2}/{len(cases)}] {marca} {case.id}{detalle}", file=sys.stderr)
    return results


# --- Cálculo del reporte --------------------------------------------------------


def _pct(num: int, den: int) -> float | None:
    return round(100 * num / den, 1) if den else None


def _mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 3) if values else None


def _is_provider_error(r: dict) -> bool:
    # Compatibilidad con corridas guardadas antes de existir el campo "provider_error".
    return r.get("provider_error", r.get("error") == "RetryableError")


def summarize(results: list[dict]) -> dict:
    """Calcula todas las métricas del reporte a partir de los resultados por caso.

    Distingue dos fallas que antes se mezclaban:
      - provider_error: la API no atendió (rate limit/5xx persistente). Dice nada del prompt.
      - JSON inválido: la API respondió pero el modelo no cumplió el contrato tras el retry.
    `accuracy` es estricta sobre TODOS los casos; `accuracy_answered` excluye los casos que
    la API no atendió, y es la que se usa para comparar prompts.
    """
    n = len(results)
    correct = sum(r["correct"] for r in results)
    answered = [r for r in results if not _is_provider_error(r)]
    valid = sum(r["valid"] for r in answered)
    guardrails = Counter(r.get("guardrail") for r in results if r.get("guardrail"))

    por_categoria = {}
    for cat in CATEGORIES:
        rs = [r for r in results if r["expected"] == cat]
        ok = sum(r["correct"] for r in rs)
        por_categoria[cat] = {"n": len(rs), "correct": ok, "accuracy": _pct(ok, len(rs))}

    por_tag = defaultdict(lambda: {"n": 0, "correct": 0})
    for r in results:
        for tag in r["tags"]:
            por_tag[tag]["n"] += 1
            por_tag[tag]["correct"] += r["correct"]
    por_tag = {
        t: {**v, "accuracy": _pct(v["correct"], v["n"])}
        for t, v in sorted(por_tag.items(), key=lambda kv: -kv[1]["n"])
    }

    # Matriz de confusión: esperada → {predicha: cantidad}
    confusion = {cat: dict(Counter(r["predicted"] for r in results if r["expected"] == cat))
                 for cat in CATEGORIES}

    con_alternativa = [r for r in results if r["acceptable"]]
    costos = [r["cost_usd"] for r in results if r["cost_usd"] is not None]

    return {
        "n": n,
        "correct": correct,
        "accuracy": _pct(correct, n),
        "answered": len(answered),
        "provider_errors": n - len(answered),
        "accuracy_answered": _pct(sum(r["correct"] for r in answered), len(answered)),
        "valid_json_pct": _pct(valid, len(answered)),  # sobre lo que la API respondió
        "first_try_pct": _pct(sum(r["first_try"] for r in answered), len(answered)),
        "guardrails_triggered": dict(guardrails),
        "per_category": por_categoria,
        "per_tag": por_tag,
        "confusion": confusion,
        "acceptable": {
            "cases": len(con_alternativa),
            "correct": sum(r["correct"] for r in con_alternativa),
            "acceptable_hits": sum(r["acceptable_hit"] for r in con_alternativa),
        },
        "calibration": {
            "mean_confidence_correct": _mean([r["confidence"] for r in results if r["correct"]]),
            "mean_confidence_wrong": _mean(
                [r["confidence"] for r in results if r["valid"] and not r["correct"]]
            ),
        },
        "cost_usd_total": round(sum(costos), 6) if costos else None,
        "cost_usd_per_case": round(sum(costos) / len(costos), 8) if costos else None,
        "input_tokens_avg": _mean([r["input_tokens"] for r in results]),
        "output_tokens_avg": _mean([r["output_tokens"] for r in results]),
        "latency_s_avg": _mean([r["latency_s"] for r in results]),
        "latency_s_max": max((r["latency_s"] for r in results), default=None),
        "api_retries_total": sum(r["api_retries"] for r in results),
        "failures": [
            {k: r[k] for k in ("id", "expected", "predicted", "confidence", "acceptable_hit", "query")}
            for r in results if not r["correct"]
        ],
    }


# --- Presentación ---------------------------------------------------------------


def _fmt(value, suffix="") -> str:
    return "—" if value is None else f"{value}{suffix}"


def print_report(meta: dict, s: dict) -> None:
    print(f"\n=== Evals: {meta['prompt']} | {meta['provider']} / {meta['model']} | {s['n']} casos ===\n")
    print(f"Accuracy global (estricta): {_fmt(s['accuracy'], '%')}  ({s['correct']}/{s['n']})")
    if s["provider_errors"]:
        print(f"Sin respuesta de la API:    {s['provider_errors']} casos (rate limit/5xx persistente)")
        print(f"Accuracy sobre respondidos: {_fmt(s['accuracy_answered'], '%')}  (de {s['answered']})")
    print(f"JSON válido:                {_fmt(s['valid_json_pct'], '%')}")
    if s["guardrails_triggered"]:
        print(f"Guardrails activados:       {s['guardrails_triggered']}")
    print(f"Válido al primer intento:   {_fmt(s['first_try_pct'], '%')}")

    print("\nPor categoría:")
    for cat, v in s["per_category"].items():
        print(f"  {cat:10} {_fmt(v['accuracy'], '%'):>7}  ({v['correct']}/{v['n']})")

    print("\nPor tag:")
    for tag, v in s["per_tag"].items():
        print(f"  {tag:13} {_fmt(v['accuracy'], '%'):>7}  ({v['correct']}/{v['n']})")

    print("\nMatriz de confusión (filas: esperada, columnas: predicha):")
    cols = list(CATEGORIES) + [INVALID]
    print("  " + " " * 10 + "".join(f"{c[:9]:>10}" for c in cols))
    for cat in CATEGORIES:
        fila = s["confusion"][cat]
        print(f"  {cat:10}" + "".join(f"{fila.get(c, 0) or '.':>10}" for c in cols))

    a = s["acceptable"]
    print(f"\nCasos ambiguos con alternativa: {a['cases']} → aciertos estrictos {a['correct']}, "
          f"eligió la alternativa aceptable {a['acceptable_hits']} (no suma al score)")

    c = s["calibration"]
    print(f"\nCalibración: confidence media al acertar {_fmt(c['mean_confidence_correct'])}"
          f" | al fallar {_fmt(c['mean_confidence_wrong'])}")

    print(f"\nCosto total: ${_fmt(s['cost_usd_total'])}  (por caso ${_fmt(s['cost_usd_per_case'])})")
    print(f"Tokens promedio: {_fmt(s['input_tokens_avg'])} in / {_fmt(s['output_tokens_avg'])} out")
    print(f"Latencia: promedio {_fmt(s['latency_s_avg'], 's')}, máxima {_fmt(s['latency_s_max'], 's')}"
          f" | reintentos de API: {s['api_retries_total']}")

    if s["failures"]:
        print(f"\nFallos ({len(s['failures'])}):")
        for f in s["failures"]:
            alt = " [alternativa aceptable]" if f["acceptable_hit"] else ""
            print(f"  {f['id']:13} esperada {f['expected']:9} predijo {f['predicted']:9} "
                  f"conf {_fmt(f['confidence'])}{alt}\n      \"{f['query'][:90]}\"")


def save_results(meta: dict, summary: dict, results: list[dict]) -> Path:
    RESULTS_DIR.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    path = RESULTS_DIR / f"{stamp}_{meta['prompt']}_{meta['provider']}_{meta['model']}.json"
    payload = {"meta": meta, "summary": summary, "cases": results}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


# --- CLI --------------------------------------------------------------------------


def main() -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Corre el dataset de evals contra el sistema.")
    parser.add_argument("--prompt", default=DEFAULT_PROMPT, choices=available_prompts())
    parser.add_argument("--provider", choices=list(PROVIDERS), help="Por defecto: LLM_PROVIDER del .env")
    parser.add_argument("--model", help="Pisa el modelo del .env (comparativa de modelos)")
    parser.add_argument("--limit", type=int, help="Correr solo los primeros N casos")
    parser.add_argument("--delay", type=float, default=0.0,
                        help="Segundos de pausa entre casos (evita el rate limit, ej. Gemini free tier)")
    args = parser.parse_args()

    cases = load_dataset()
    if args.limit:
        cases = cases[: args.limit]

    try:
        provider = get_provider(args.provider, args.model)
    except ProviderError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    meta = {
        "prompt": args.prompt,
        "provider": provider.name,
        "model": provider.model,
        "cases": len(cases),
        "dataset_full": args.limit is None,
        "delay_s": args.delay,
        "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }

    try:
        results = evaluate(cases, args.prompt, provider, delay_s=args.delay)
    except AbortRun as e:
        print(f"\nCorrida abortada por error no reintentable del proveedor: {e}", file=sys.stderr)
        return 2

    summary = summarize(results)
    print_report(meta, summary)
    path = save_results(meta, summary, results)
    print(f"\nResultados guardados en {path.relative_to(RESULTS_DIR.parent.parent)}")
    return 0


if __name__ == "__main__":
    from src.console import use_utf8_output

    use_utf8_output()
    sys.exit(main())
