"""Verifica el retry de triage() sin llamar a la API.

Usa un proveedor falso que devuelve respuestas preprogramadas (rotas o válidas) y
comprueba cuántas llamadas se hicieron y qué feedback recibió el modelo.

Uso (desde la raíz del repo):
    python -m scripts.check_retry
"""

from scripts.fake_llm import (
    CON_FENCE,
    CONFIDENCE_INVALIDA,
    JSON_ROTO,
    VALIDO,
    FakeProvider,
    use_temp_metrics,
)
from src.triage import MAX_RETRIES, TriageError, triage


def correr(descripcion, respuestas, llamadas_esperadas, deberia_fallar=False):
    provider = FakeProvider(respuestas)

    try:
        triage("me cobraron dos veces", provider=provider)
        fallo = False
    except TriageError:
        fallo = True

    llamadas = provider.llamadas
    ok = len(llamadas) == llamadas_esperadas and fallo == deberia_fallar
    print(f"{'OK   ' if ok else 'FALLA'} {descripcion} (llamadas: {len(llamadas)})")
    return ok, llamadas


def main():
    use_temp_metrics()  # no ensuciar data/metrics.jsonl con datos falsos
    resultados = []

    ok, _ = correr("válido al primer intento", [VALIDO], 1)
    resultados.append(ok)

    ok, _ = correr("bloque ```json se limpia sin retry", [CON_FENCE], 1)
    resultados.append(ok)

    ok, llamadas = correr("JSON roto → se recupera en el 2do intento", [JSON_ROTO, VALIDO], 2)
    resultados.append(ok)
    # El 2do intento tiene que incluir la respuesta rota y el feedback del error.
    feedback = llamadas[1][-1]
    ok_feedback = (
        llamadas[1][-2] == {"role": "assistant", "content": JSON_ROTO}
        and feedback["role"] == "user"
        and "(json)" in feedback["content"]
    )
    print(f"{'OK   ' if ok_feedback else 'FALLA'} el retry le muestra al modelo su respuesta y el error")
    resultados.append(ok_feedback)

    ok, llamadas = correr(
        "confidence inválida → se recupera en el 2do intento", [CONFIDENCE_INVALIDA, VALIDO], 2
    )
    resultados.append(ok)
    ok_campo = "- confidence:" in llamadas[1][-1]["content"]
    print(f"{'OK   ' if ok_campo else 'FALLA'} el feedback nombra el campo que falló (confidence)")
    resultados.append(ok_campo)

    ok, _ = correr(
        "siempre inválido → TriageError controlado",
        [JSON_ROTO] * (MAX_RETRIES + 1),
        MAX_RETRIES + 1,
        deberia_fallar=True,
    )
    resultados.append(ok)

    todo_ok = all(resultados)
    print(f"\n{'Todos los checks OK' if todo_ok else 'Hay checks que fallaron'}")
    raise SystemExit(0 if todo_ok else 1)


if __name__ == "__main__":
    main()
