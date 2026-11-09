"""Verifica la lógica de decisión de evals/compare.py con filas inventadas, sin API.

La decisión del prompt ganador sale de `decide()`: si tuviera un error, la elección
"respaldada por datos" no lo estaría. Se prueban los tres caminos del criterio.

Uso (desde la raíz del repo):
    python -m scripts.check_compare
"""

from evals.compare import decide

resultados = []


def check(descripcion: str, condicion: bool) -> None:
    print(f"{'OK   ' if condicion else 'FALLA'} {descripcion}")
    resultados.append(condicion)


def fila(prompt, accuracy, frontier=50.0, cost=0.0003, valid=100.0, model="m"):
    return {"prompt": prompt, "provider": "p", "model": model, "n": 40, "accuracy": accuracy,
            "frontier": frontier, "cost_per_case": cost, "valid_json_pct": valid}


def ganador(rows):
    return decide(rows)["p/m"]["winner"]


def main():
    check("gana la mayor accuracy si supera por más de 1 caso (90 vs 85)",
          ganador([fila("a", 85.0), fila("b", 90.0)]) == "b")
    check("empate (≤ 1 caso: 87.5 vs 85) → desempata por frontier",
          ganador([fila("a", 87.5, frontier=60), fila("b", 85.0, frontier=80)]) == "b")
    check("empate con igual frontier → gana el más barato",
          ganador([fila("a", 87.5, cost=0.0004), fila("b", 86.25, cost=0.0003)]) == "b")
    check("JSON válido < 95% → descartado aunque tenga mejor accuracy",
          ganador([fila("a", 85.0), fila("b", 95.0, valid=90.0)]) == "a")
    check("se decide por separado para cada modelo",
          set(decide([fila("a", 90.0), fila("b", 80.0, model="x")])) == {"p/m", "p/x"})

    todo_ok = all(resultados)
    print(f"\n{'Todos los checks OK' if todo_ok else 'Hay checks que fallaron'}")
    raise SystemExit(0 if todo_ok else 1)


if __name__ == "__main__":
    main()
