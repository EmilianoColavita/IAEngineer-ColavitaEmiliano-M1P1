"""Prueba de humo: verifica que las API keys y los SDKs funcionan.

Uso:
    python scripts/hello_llm.py            # prueba ambos proveedores
    python scripts/hello_llm.py openai     # solo OpenAI
    python scripts/hello_llm.py gemini     # solo Gemini
"""

import os
import sys
import time

from dotenv import load_dotenv

load_dotenv()

PROMPT = "Respondé en una sola oración: ¿qué es un SaaS?"

# Temperatura 0: misma entrada → (casi) misma salida. Clave para clasificar y para evals reproducibles.
TEMPERATURE = 0


def hello_openai():
    from openai import OpenAI

    model = os.getenv("OPENAI_MODEL", "gpt-5.4-nano")
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

    start = time.perf_counter()
    response = client.responses.create(model=model, input=PROMPT, temperature=TEMPERATURE)
    latency = time.perf_counter() - start

    usage = response.usage
    return model, response.output_text, usage.input_tokens, usage.output_tokens, usage.total_tokens, latency


def hello_gemini():
    from google import genai
    from google.genai import types

    model = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite")
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

    start = time.perf_counter()
    response = client.models.generate_content(
        model=model,
        contents=PROMPT,
        config=types.GenerateContentConfig(temperature=TEMPERATURE),
    )
    latency = time.perf_counter() - start

    usage = response.usage_metadata
    # total_token_count puede incluir tokens de "thinking", por eso no siempre es prompt + completion
    return (
        model,
        response.text,
        usage.prompt_token_count,
        usage.candidates_token_count,
        usage.total_token_count,
        latency,
    )


PROVIDERS = {"openai": hello_openai, "gemini": hello_gemini}


def main():
    selected = sys.argv[1:] or list(PROVIDERS)
    failed = False

    for name in selected:
        print(f"\n=== {name} ===")
        try:
            model, text, prompt_tok, completion_tok, total_tok, latency = PROVIDERS[name]()
        except KeyError as e:
            print(f"ERROR: falta la variable de entorno o el proveedor no existe: {e}")
            failed = True
            continue
        except Exception as e:
            # Mostramos el tipo de error: acá aparecen 401 (key inválida), 404 (modelo), 429 (cuota/rate limit)
            print(f"ERROR {type(e).__name__}: {e}")
            failed = True
            continue

        print(f"modelo:     {model}")
        print(f"respuesta:  {text.strip()}")
        print(f"tokens:     prompt={prompt_tok} completion={completion_tok} total={total_tok}")
        print(f"latencia:   {latency:.2f}s")

    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    # Este script corre suelto (sin importar src/): misma lógica que src/console.py.
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")
    main()
