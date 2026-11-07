"""CLI de Nubbix Triage.

Uso:
    python -m src.main "me cobraron dos veces"
    python -m src.main "me cobraron dos veces" --prompt v2_few_shot

Responsabilidad única: leer argumentos, llamar a triage() e imprimir el resultado.
"""

import argparse
import sys

import openai
from dotenv import load_dotenv

from src.prompts import PromptError, available_prompts
from src.triage import DEFAULT_PROMPT, TriageError, triage


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Triage de consultas de soporte de Nubbix. Devuelve JSON validado."
    )
    parser.add_argument("query", help="Consulta del cliente, entre comillas.")
    parser.add_argument(
        "--prompt",
        default=DEFAULT_PROMPT,
        choices=available_prompts(),
        help=f"Versión del prompt a usar (por defecto: {DEFAULT_PROMPT}).",
    )
    return parser.parse_args()


def main() -> int:
    load_dotenv()
    args = parse_args()

    query = args.query.strip()
    if not query:
        print("ERROR: la consulta está vacía.", file=sys.stderr)
        return 1

    try:
        result = triage(query, args.prompt)
    except PromptError as e:
        print(f"ERROR de prompt: {e}", file=sys.stderr)
        return 1
    except TriageError as e:
        # Se agotaron los reintentos: el modelo nunca cumplió el contrato.
        print(f"ERROR: {e}\nÚltima respuesta del modelo:\n{e.last_raw}", file=sys.stderr)
        return 1
    except openai.APIError as e:
        # 401 key inválida, 404 modelo inexistente, 429 cuota/rate limit, errores de red...
        print(f"ERROR de la API ({type(e).__name__}): {e}", file=sys.stderr)
        return 1

    print(result.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
