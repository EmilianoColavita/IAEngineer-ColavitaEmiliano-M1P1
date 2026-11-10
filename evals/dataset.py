"""Dataset de evaluación: formato, carga validada y resumen de cobertura.

Cada línea de `evals/dataset.jsonl` es un caso etiquetado a mano:
    {"id": "billing-01", "query": "...", "expected_category": "billing",
     "acceptable_categories": [], "tags": ["clear"], "notes": "..."}

- expected_category: la respuesta correcta. El score principal es ESTRICTO: solo esta cuenta.
- acceptable_categories: solo para casos genuinamente ambiguos (multi-intención). Una
  respuesta en esta lista NO suma al score principal; se reporta aparte.

Resumen y validación (desde la raíz del repo):
    python -m evals.dataset
"""

import json
import re
import sys
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from src.prompts import available_prompts, load_prompt
from src.schema import Category

DATASET_PATH = Path(__file__).resolve().parent / "dataset.jsonl"

# Vocabulario cerrado de tags: un typo en un tag rompería el reporte por tag sin avisar.
Tag = Literal[
    "clear",  # caso típico, sin ambigüedad
    "frontier",  # en el límite entre dos categorías
    "multi_intent",  # más de un problema en el mensaje
    "vague",  # sin información suficiente
    "short",  # muy corto (1-4 palabras)
    "long",  # largo, con contexto o divagación
    "typos",  # errores de ortografía, sin tildes
    "informal",  # registro coloquial, emojis
    "angry",  # cliente enojado, mayúsculas
    "regional",  # modismos de un país (AR, MX, CO, CL...)
    "off_topic",  # nada que ver con Nubbix
]

# Similitud a partir de la cual un caso se considera "copiado" de un ejemplo de prompt.
CONTAMINATION_THRESHOLD = 0.6


class EvalCase(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id: str = Field(pattern=r"^(billing|technical|account|other)-\d{2}$")
    query: str = Field(min_length=1)
    expected_category: Category
    acceptable_categories: list[Category] = []
    tags: list[Tag] = Field(min_length=1)
    notes: str = ""

    @model_validator(mode="after")
    def _consistente(self):
        if not self.id.startswith(self.expected_category + "-"):
            raise ValueError(f"el id '{self.id}' no coincide con expected_category")
        if self.expected_category in self.acceptable_categories:
            raise ValueError("acceptable_categories no puede repetir expected_category")
        return self


class DatasetError(Exception):
    """El dataset tiene líneas inválidas o ids repetidos."""


def load_dataset(path: Path = DATASET_PATH) -> list[EvalCase]:
    """Carga y valida todo el dataset. Junta TODOS los errores antes de fallar."""
    cases, errores, ids = [], [], set()
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            case = EvalCase.model_validate(json.loads(line))
        except (json.JSONDecodeError, ValidationError) as e:
            errores.append(f"línea {n}: {e}")
            continue
        if case.id in ids:
            errores.append(f"línea {n}: id repetido '{case.id}'")
        ids.add(case.id)
        cases.append(case)
    if errores:
        raise DatasetError("Dataset inválido:\n" + "\n".join(errores))
    return cases


def prompt_examples() -> dict[str, list[str]]:
    """Consultas usadas como ejemplo dentro de los prompts (líneas 'Consulta: ...')."""
    ejemplos = {}
    for name in available_prompts():
        system = load_prompt(name).system
        ejemplos[name] = re.findall(r"^Consulta: (.+)$", system, flags=re.MULTILINE)
    return ejemplos


def contamination(cases: list[EvalCase]) -> list[str]:
    """Casos demasiado parecidos a un ejemplo de algún prompt (inflarían su score)."""
    avisos = []
    for prompt, ejemplos in prompt_examples().items():
        for case in cases:
            for ej in ejemplos:
                ratio = SequenceMatcher(None, case.query.lower(), ej.lower()).ratio()
                if ratio >= CONTAMINATION_THRESHOLD:
                    avisos.append(f"{case.id} se parece {ratio:.0%} a un ejemplo de {prompt}: '{ej}'")
    return avisos


def main() -> int:
    try:
        cases = load_dataset()
    except DatasetError as e:
        print(e, file=sys.stderr)
        return 1

    por_categoria = Counter(c.expected_category for c in cases)
    por_tag = Counter(t for c in cases for t in c.tags)
    ambiguos = [c.id for c in cases if c.acceptable_categories]

    print(f"Casos: {len(cases)} \n")
    print("Por categoría esperada:")
    for cat in ("billing", "technical", "account", "other"):
        print(f"  {cat:10} {por_categoria[cat]:3}")
    print("\nPor tag:")
    for tag, n in por_tag.most_common():
        print(f"  {tag:13} {n:3}")
    print(f"\nCon categorías alternativas aceptables: {len(ambiguos)} ({', '.join(ambiguos)})")

    avisos = []
    if len(cases) < 30:
        avisos.append(f"hay {len(cases)} casos: el enunciado pide al menos 30")
    minimo, maximo = min(por_categoria.values()), max(por_categoria.values())
    if maximo > 1.5 * minimo:
        avisos.append(f"desbalance entre categorías (mín {minimo}, máx {maximo})")
    avisos += contamination(cases)

    print("\nAvisos:" if avisos else "\nSin avisos: dataset válido, balanceado y sin contaminación.")
    for a in avisos:
        print(f"  - {a}")
    return 1 if avisos else 0


if __name__ == "__main__":
    from src.console import use_utf8_output

    use_utf8_output()
    sys.exit(main())
