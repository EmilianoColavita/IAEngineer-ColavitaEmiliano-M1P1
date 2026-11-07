"""Carga de prompts versionados desde `prompts/*.yaml`.

Responsabilidad única: leer un YAML, validar que tenga los campos esperados y completar
la plantilla del mensaje user con la consulta. No sabe nada de proveedores de LLM.
"""

from pathlib import Path

import yaml
from pydantic import BaseModel, ValidationError

# Ruta absoluta a prompts/, calculada desde ESTE archivo (src/prompts.py → raíz → prompts/).
# Así funciona sin importar desde qué carpeta se ejecute el programa.
PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


class PromptError(Exception):
    """El prompt pedido no existe o su YAML está mal formado."""


class PromptTemplate(BaseModel):
    """Estructura que todo YAML de prompt tiene que cumplir."""

    id: str
    version: int
    technique: str
    description: str
    system: str
    user_template: str

    def render_user(self, query: str) -> str:
        """Completa la plantilla del mensaje user con la consulta del cliente."""
        return self.user_template.format(query=query)


def available_prompts() -> list[str]:
    """Nombres de los prompts disponibles (archivos .yaml sin extensión)."""
    return sorted(p.stem for p in PROMPTS_DIR.glob("*.yaml"))


def load_prompt(name: str) -> PromptTemplate:
    """Carga y valida `prompts/<name>.yaml`."""
    # Solo se aceptan nombres de la lista: evita rutas raras como "../.env".
    disponibles = available_prompts()
    if name not in disponibles:
        raise PromptError(
            f"No existe el prompt '{name}'. Disponibles: {', '.join(disponibles)}"
        )

    path = PROMPTS_DIR / f"{name}.yaml"
    try:
        # safe_load: solo construye tipos básicos (dict, list, str...). yaml.load podría
        # instanciar objetos Python arbitrarios definidos en el archivo.
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        return PromptTemplate.model_validate(data)
    except (yaml.YAMLError, ValidationError) as e:
        raise PromptError(f"El prompt '{name}' tiene un formato inválido:\n{e}") from e
