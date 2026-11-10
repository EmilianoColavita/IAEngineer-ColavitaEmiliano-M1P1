"""Compara corridas de evals guardadas en evals/results/ y aplica el criterio de decisión.

Uso, desde la raíz del repo:
    python -m evals.compare                                   # tabla + estabilidad + decisión
    python -m evals.compare --diff v1_zero_shot@openai v2_few_shot@openai   # caso por caso

Todo sale de los archivos de resultados: la tabla del README es reproducible.

Criterio de decisión (acordado ANTES de ver los resultados), por proveedor/modelo:
  1. Se descarta un prompt con JSON válido < 95%.
  2. Gana la mayor accuracy global (promedio de las corridas). Se usa la accuracy sobre los
     casos que la API respondió: un rate limit del proveedor no dice nada del prompt.
  3. Si la diferencia con el siguiente es <= 1 caso (2.5 puntos con 40 casos) es empate:
     se desempata por accuracy en "frontier" y después por menor costo por caso.
"""

import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import argparse  # noqa: E402
import json  # noqa: E402
from collections import defaultdict  # noqa: E402

from evals.runner import RESULTS_DIR, summarize  # noqa: E402

CATEGORIES = ("billing", "technical", "account", "other")
MIN_VALID_JSON = 95.0


def load_runs(results_dir: Path = RESULTS_DIR) -> dict[str, list[dict]]:
    """Corridas completas agrupadas por configuración 'prompt@proveedor/modelo'."""
    grupos = defaultdict(list)
    for path in sorted(results_dir.glob("*.json")):
        run = json.loads(path.read_text(encoding="utf-8"))
        meta = run["meta"]
        if not meta.get("dataset_full"):
            continue  # pruebas con --limit: no comparables
        key = f"{meta['prompt']}@{meta['provider']}/{meta['model']}"
        grupos[key].append(run)
    return dict(grupos)


def _mean(values: list) -> float | None:
    values = [v for v in values if v is not None]
    return round(sum(values) / len(values), 4) if values else None


def aggregate(key: str, runs: list[dict]) -> dict:
    """Promedia las métricas de las corridas de una misma configuración."""
    # Se recalcula desde el detalle por caso con la lógica ACTUAL del runner, así corridas
    # guardadas con una versión anterior del resumen se interpretan igual que las nuevas.
    s = [summarize(r["cases"]) for r in runs]
    accs = [x["accuracy_answered"] for x in s]
    prompt, rest = key.split("@")
    provider, model = rest.split("/", 1)
    return {
        "key": key,
        "prompt": prompt,
        "provider": provider,
        "model": model,
        "runs": len(runs),
        "n": s[0]["n"],
        "accuracy": _mean(accs),
        "accuracy_min": min(accs),
        "accuracy_max": max(accs),
        "per_category": {c: _mean([x["per_category"][c]["accuracy"] for x in s]) for c in CATEGORIES},
        "frontier": _mean([x["per_tag"].get("frontier", {}).get("accuracy") for x in s]),
        "valid_json_pct": _mean([x["valid_json_pct"] for x in s]),
        "provider_errors": sum(x["provider_errors"] for x in s),
        "first_try_pct": _mean([x["first_try_pct"] for x in s]),
        "conf_correct": _mean([x["calibration"]["mean_confidence_correct"] for x in s]),
        "conf_wrong": _mean([x["calibration"]["mean_confidence_wrong"] for x in s]),
        "cost_per_case": _mean([x["cost_usd_per_case"] for x in s]),
        "latency_avg": _mean([x["latency_s_avg"] for x in s]),
        "unstable_cases": unstable_cases(runs),
    }


def predictions(run: dict) -> dict[str, str]:
    return {c["id"]: c["predicted"] for c in run["cases"]}


def unstable_cases(runs: list[dict]) -> list[str]:
    """Casos cuya predicción cambia entre corridas de la MISMA configuración."""
    if len(runs) < 2:
        return []
    preds = [predictions(r) for r in runs]
    # Casos que en alguna corrida no tuvieron respuesta de la API: no son "inestabilidad"
    # del modelo sino del proveedor, se excluyen.
    sin_api = {c["id"] for r in runs for c in r["cases"]
               if c.get("provider_error", c.get("error") == "RetryableError")}
    return sorted(cid for cid in preds[0]
                  if cid not in sin_api and len({p.get(cid) for p in preds}) > 1)


def correct_rate(runs: list[dict]) -> dict[str, float]:
    """Por caso: fracción de corridas en que acertó (0, 0.5, 1 con 2 corridas)."""
    rates = defaultdict(list)
    for r in runs:
        for c in r["cases"]:
            rates[c["id"]].append(c["correct"])
    return {cid: sum(v) / len(v) for cid, v in rates.items()}


def decide(rows: list[dict]) -> dict[str, dict]:
    """Aplica el criterio de decisión por proveedor/modelo. Devuelve ganador y razón."""
    por_modelo = defaultdict(list)
    for row in rows:
        por_modelo[f"{row['provider']}/{row['model']}"].append(row)

    decisiones = {}
    for modelo, candidatos in por_modelo.items():
        validos = [r for r in candidatos if (r["valid_json_pct"] or 0) >= MIN_VALID_JSON]
        if not validos:
            decisiones[modelo] = {"winner": None, "reason": "ningún prompt supera 95% de JSON válido"}
            continue
        ordenados = sorted(validos, key=lambda r: -r["accuracy"])
        mejor = ordenados[0]
        un_caso = 100 / mejor["n"]
        empatados = [r for r in validos if mejor["accuracy"] - r["accuracy"] <= un_caso + 1e-9]
        if len(validos) == 1:
            reason = "único candidato con corridas completas"
            winner = mejor
        elif len(empatados) == 1:
            reason = f"mayor accuracy ({mejor['accuracy']}%), a más de 1 caso del siguiente"
            winner = mejor
        else:
            winner = sorted(empatados, key=lambda r: (-(r["frontier"] or 0), r["cost_per_case"] or 0))[0]
            nombres = ", ".join(r["prompt"] for r in empatados)
            reason = (f"empate en accuracy (≤ 1 caso) entre {nombres}; desempata por frontier "
                      f"({winner['frontier']}%) y luego costo")
        descartados = [r["prompt"] for r in candidatos if r not in validos]
        if descartados:
            reason += f"; descartados por JSON válido < 95%: {', '.join(descartados)}"
        decisiones[modelo] = {"winner": winner["prompt"], "reason": reason}
    return decisiones


def _p(v, decimals=1) -> str:
    return "—" if v is None else f"{v:.{decimals}f}"


def markdown_table(rows: list[dict]) -> str:
    head = ("| Prompt | Proveedor / modelo | Corridas | Accuracy | billing | technical | account "
            "| other | Frontier | JSON válido | 1er intento | Conf. acierto / fallo | Costo / caso (USD) "
            "| Latencia (s) | Sin resp. API |")
    sep = "|" + "---|" * 15
    lines = [head, sep]
    for r in rows:
        acc = f"**{_p(r['accuracy'])}%**"
        if r["runs"] > 1 and r["accuracy_min"] != r["accuracy_max"]:
            acc += f" ({_p(r['accuracy_min'])}–{_p(r['accuracy_max'])})"
        cats = " | ".join(f"{_p(r['per_category'][c])}%" for c in CATEGORIES)
        lines.append(
            f"| {r['prompt']} | {r['provider']} / {r['model']} | {r['runs']} | {acc} | {cats} "
            f"| {_p(r['frontier'])}% | {_p(r['valid_json_pct'])}% | {_p(r['first_try_pct'])}% "
            f"| {_p(r['conf_correct'], 2)} / {_p(r['conf_wrong'], 2)} "
            f"| {_p(r['cost_per_case'], 6)} "
            f"| {_p(r['latency_avg'], 2)} | {r['provider_errors']} |"
        )
    return "\n".join(lines)


def find_group(grupos: dict, spec: str) -> list[dict]:
    """'v1_zero_shot@openai' → corridas de esa configuración (el modelo es opcional)."""
    matches = [k for k in grupos if k == spec or k.startswith(spec + "/")]
    if len(matches) != 1:
        raise SystemExit(f"'{spec}' coincide con {len(matches)} configuraciones: {matches or list(grupos)}")
    return grupos[matches[0]]


def print_diff(grupos: dict, a: str, b: str) -> None:
    ra, rb = correct_rate(find_group(grupos, a)), correct_rate(find_group(grupos, b))
    preds_b = predictions(find_group(grupos, b)[0])
    mejoras = [(cid, ra[cid], rb[cid]) for cid in ra if rb.get(cid, 0) > ra[cid]]
    empeoras = [(cid, ra[cid], rb[cid]) for cid in ra if rb.get(cid, 0) < ra[cid]]
    print(f"\n=== Diff caso por caso: {a} → {b} (tasa de acierto entre corridas) ===")
    print(f"\nArreglados por {b} ({len(mejoras)}):")
    for cid, x, y in mejoras:
        print(f"  {cid:14} {x:.0%} → {y:.0%}")
    print(f"\nEmpeorados por {b} ({len(empeoras)}):")
    for cid, x, y in empeoras:
        print(f"  {cid:14} {x:.0%} → {y:.0%}  (predijo {preds_b.get(cid)})")


def main() -> int:
    parser = argparse.ArgumentParser(description="Compara corridas de evals.")
    parser.add_argument("--diff", nargs=2, metavar=("A", "B"),
                        help="Configuraciones a comparar caso por caso, ej. v1_zero_shot@openai")
    args = parser.parse_args()

    grupos = load_runs()
    if not grupos:
        print("No hay corridas completas en evals/results/.", file=sys.stderr)
        return 1

    if args.diff:
        print_diff(grupos, *args.diff)
        return 0

    rows = sorted((aggregate(k, v) for k, v in grupos.items()),
                  key=lambda r: (r["provider"], r["prompt"]))
    print(markdown_table(rows))

    print("\nEstabilidad (casos que cambian de predicción entre corridas de la misma configuración):")
    for r in rows:
        if r["runs"] > 1:
            casos = ", ".join(r["unstable_cases"]) or "ninguno"
            print(f"  {r['key']:50} {len(r['unstable_cases'])} ({casos})")

    print("\nDecisión según el criterio acordado:")
    for modelo, d in decide(rows).items():
        print(f"  {modelo}: {d['winner']} → {d['reason']}")
    return 0


if __name__ == "__main__":
    from src.console import use_utf8_output

    use_utf8_output()
    sys.exit(main())
