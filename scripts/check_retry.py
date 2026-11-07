"""Verifica el retry de triage() sin llamar a la API.

Reemplaza `call_llm` por un LLM falso que devuelve respuestas preprogramadas (rotas o
válidas) y comprueba cuántas llamadas se hicieron y qué feedback recibió el modelo.

Uso (desde la raíz del repo):
    python -m scripts.check_retry
"""

from src import triage as triage_module
from src.triage import MAX_RETRIES, TriageError, triage

VALIDO = (
    '{"answer": "Revisamos tu cobro duplicado", "confidence": 0.9, '
    '"category": "billing", "actions": ["Verificar transacciones del cliente"]}'
)
CONFIDENCE_INVALIDA = VALIDO.replace("0.9", "1.3")
JSON_ROTO = VALIDO[:-1]  # sin la llave de cierre
CON_FENCE = f"```json\n{VALIDO}\n```"


def fake_llm(respuestas: list[str]):
    """Devuelve un call_llm falso que responde en orden y registra cada conversación."""
    llamadas = []

    def call_llm(messages: list[dict]) -> str:
        llamadas.append([dict(m) for m in messages])
        return respuestas[len(llamadas) - 1]

    return call_llm, llamadas


def correr(descripcion, respuestas, llamadas_esperadas, deberia_fallar=False):
    call_llm, llamadas = fake_llm(respuestas)
    triage_module.call_llm = call_llm  # reemplazo del proveedor real

    try:
        triage("me cobraron dos veces")
        fallo = False
    except TriageError:
        fallo = True

    ok = len(llamadas) == llamadas_esperadas and fallo == deberia_fallar
    print(f"{'OK   ' if ok else 'FALLA'} {descripcion} (llamadas: {len(llamadas)})")
    return ok, llamadas


def main():
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
