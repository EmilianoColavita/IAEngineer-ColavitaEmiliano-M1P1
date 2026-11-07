"""CLI de Nubbix Triage.

Uso:
    python -m src.main "me cobraron dos veces"
    python -m src.main "me cobraron dos veces" --prompt v2_few_shot
    python -m src.main "me cobraron dos veces" --provider gemini

Responsabilidad única: leer argumentos, llamar a triage() e imprimir el resultado.
"""

import argparse
import sys

from dotenv import load_dotenv

from src.prompts import PromptError, available_prompts
from src.providers import PROVIDERS, ProviderError, RetryableError, get_provider
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
    parser.add_argument(
        "--provider",
        choices=list(PROVIDERS),
        help="Proveedor de LLM. Si no se indica, se usa LLM_PROVIDER del .env.",
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
        provider = get_provider(args.provider)
        result = triage(query, args.prompt, provider)
    except PromptError as e:
        print(f"ERROR de prompt: {e}", file=sys.stderr)
        return 1
    except TriageError as e:
        # Se agotaron los reintentos: el modelo nunca cumplió el contrato.
        print(f"ERROR: {e}\nÚltima respuesta del modelo:\n{e.last_raw}", file=sys.stderr)
        return 1
    except RetryableError as e:
        # Error transitorio que no se resolvió ni con backoff.
        print(f"ERROR del proveedor (persistió tras los reintentos): {e}", file=sys.stderr)
        return 1
    except ProviderError as e:
        # Key inválida, sin saldo, modelo inexistente...: reintentar no lo arregla.
        print(f"ERROR del proveedor: {e}", file=sys.stderr)
        return 1

    print(result.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
