"""Contrato de salida del triage de Nubbix.

Define la forma exacta del JSON que el LLM tiene que devolver. Todo lo que entre
al sistema desde el modelo pasa por `TriageResponse` antes de usarse.

Prueba manual:
    python -m src.schema
"""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

# Las 4 categorías del contrato. Única fuente de verdad: la usan el schema y el dataset de evals.
Category = Literal["billing", "technical", "account", "other"]

# Una acción es un string no vacío (después de recortar espacios).
Action = Annotated[str, Field(min_length=1)]


class TriageResponse(BaseModel):
    model_config = ConfigDict(
        str_strip_whitespace=True,  # "   " se recorta a "" y lo rechaza min_length
        extra="forbid",  # campos que no están en el contrato → error
    )

    answer: str = Field(min_length=1, description="Respuesta para el cliente.")
    confidence: float = Field(ge=0, le=1, description="Seguridad del modelo, 0 a 1.")
    category: Category
    actions: list[Action] = Field(
        max_length=5, description="Acciones sugeridas para el agente humano."
    )


# --- Casos de prueba --------------------------------------------------------
# Método: un caso BASE válido y cada caso cambia UNA sola cosa respecto de él.

CASOS = [
    # (descripción, json_crudo, debería_pasar)
    # Base
    (
        "base válido",
        '{"answer": "Revisamos tu cobro duplicado", "confidence": 0.9, '
        '"category": "billing", "actions": ["Verificar transacciones del cliente"]}',
        True,
    ),
    # answer
    (
        "answer vacío falla",
        '{"answer": "", "confidence": 0.9, '
        '"category": "billing", "actions": ["Verificar transacciones del cliente"]}',
        False,
    ),
    (
        "answer solo espacios falla",
        '{"answer": "   ", "confidence": 0.9, '
        '"category": "billing", "actions": ["Verificar transacciones del cliente"]}',
        False,
    ),
    # confidence
    (
        "confidence mayor a 1 falla",
        '{"answer": "Revisamos tu cobro duplicado", "confidence": 1.3, '
        '"category": "billing", "actions": ["Verificar transacciones del cliente"]}',
        False,
    ),
    (
        "confidence negativo falla",
        '{"answer": "Revisamos tu cobro duplicado", "confidence": -0.1, '
        '"category": "billing", "actions": ["Verificar transacciones del cliente"]}',
        False,
    ),
    (
        "confidence 0 exacto pasa",
        '{"answer": "Revisamos tu cobro duplicado", "confidence": 0, '
        '"category": "billing", "actions": ["Verificar transacciones del cliente"]}',
        True,
    ),
    (
        "confidence 1 exacto pasa",
        '{"answer": "Revisamos tu cobro duplicado", "confidence": 1, '
        '"category": "billing", "actions": ["Verificar transacciones del cliente"]}',
        True,
    ),
    (
        "confidence como string pasa (se convierte)",
        '{"answer": "Revisamos tu cobro duplicado", "confidence": "0.85", '
        '"category": "billing", "actions": ["Verificar transacciones del cliente"]}',
        True,
    ),
    # category
    (
        "category inexistente falla",
        '{"answer": "Revisamos tu cobro duplicado", "confidence": 0.9, '
        '"category": "sales", "actions": ["Verificar transacciones del cliente"]}',
        False,
    ),
    (
        "category en mayúscula falla",
        '{"answer": "Revisamos tu cobro duplicado", "confidence": 0.9, '
        '"category": "Billing", "actions": ["Verificar transacciones del cliente"]}',
        False,
    ),
    # actions
    (
        "actions vacío pasa",
        '{"answer": "Revisamos tu cobro duplicado", "confidence": 0.9, '
        '"category": "billing", "actions": []}',
        True,
    ),
    (
        "acción vacía dentro de la lista falla",
        '{"answer": "Revisamos tu cobro duplicado", "confidence": 0.9, '
        '"category": "billing", "actions": [""]}',
        False,
    ),
    (
        "acción solo espacios dentro de la lista falla",
        '{"answer": "Revisamos tu cobro duplicado", "confidence": 0.9, '
        '"category": "billing", "actions": ["   "]}',
        False,
    ),
    (
        "más de 5 acciones falla",
        '{"answer": "Revisamos tu cobro duplicado", "confidence": 0.9, '
        '"category": "billing", "actions": ["a1", "a2", "a3", "a4", "a5", "a6"]}',
        False,
    ),
    # formato
    (
        "falta el campo category falla",
        '{"answer": "Revisamos tu cobro duplicado", "confidence": 0.9, '
        '"actions": ["Verificar transacciones del cliente"]}',
        False,
    ),
    (
        "campo extra falla",
        '{"answer": "Revisamos tu cobro duplicado", "confidence": 0.9, '
        '"category": "billing", "actions": ["Verificar transacciones del cliente"], '
        '"reasoning": "parece un cobro duplicado"}',
        False,
    ),
    (
        "JSON roto (sin llave de cierre) falla",
        '{"answer": "Revisamos tu cobro duplicado", "confidence": 0.9, '
        '"category": "billing", "actions": ["Verificar transacciones del cliente"]',
        False,
    ),
]


def correr_casos() -> bool:
    """Valida cada caso y compara con lo esperado. Devuelve True si todos dan bien."""
    todos_ok = True
    for descripcion, json_crudo, deberia_pasar in CASOS:
        try:
            TriageResponse.model_validate_json(json_crudo)
            paso, detalle = True, ""
        except ValidationError as e:
            paso = False
            # Primer error: tipo + campo, para ver POR QUÉ falló.
            err = e.errors()[0]
            campo = ".".join(str(p) for p in err["loc"]) or "(json)"
            detalle = f"  [{err['type']} en {campo}]"

        ok = paso == deberia_pasar
        todos_ok &= ok
        print(f"{'OK   ' if ok else 'FALLA'} {descripcion}{detalle}")

    print(f"\n{'Todos los casos OK' if todos_ok else 'Hay casos que no dieron lo esperado'}")
    return todos_ok


if __name__ == "__main__":
    from src.console import use_utf8_output

    use_utf8_output()
    raise SystemExit(0 if correr_casos() else 1)
