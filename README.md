# Nubbix Triage

Servicio de línea de comandos que automatiza el **soporte nivel 1** de Nubbix, un SaaS
(ficticio) de gestión para pymes de Latinoamérica. Recibe una consulta en texto libre y
devuelve un **JSON validado** con la respuesta, la categoría y las acciones sugeridas
para el agente humano:

```json
{
  "answer": "Lamentamos el cobro duplicado. Ya derivamos tu caso para revisarlo.",
  "confidence": 0.92,
  "category": "billing",
  "actions": ["Verificar transacciones del mes", "Gestionar reintegro si corresponde"]
}
```

| Campo | Tipo | Descripción |
|---|---|---|
| `answer` | string no vacío | Respuesta para el cliente |
| `confidence` | número entre 0 y 1 | Qué tan seguro está el modelo de la categoría |
| `category` | `billing` \| `technical` \| `account` \| `other` | Categoría del ticket |
| `actions` | lista de 0 a 5 strings | Acciones sugeridas para el agente humano |

> Proyecto integrador del Módulo 1 del curso AI Engineer. **En desarrollo**: ver
> [Estado del proyecto](#estado-del-proyecto).

## Requisitos

- Python 3.11 o superior
- Una API key de **OpenAI** ([platform.openai.com/api-keys](https://platform.openai.com/api-keys))
  y/o de **Google Gemini** ([aistudio.google.com/apikey](https://aistudio.google.com/apikey))

## Instalación

Desde la raíz del repo:

**Windows (PowerShell)**

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
```

> Si `Activate.ps1` falla por "ejecución de scripts deshabilitada", ejecutá una sola vez
> `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` y volvé a activar.

**Linux / macOS**

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env
```

## Configuración

Completá el archivo `.env` (nunca se sube al repo):

| Variable | Descripción | Ejemplo |
|---|---|---|
| `LLM_PROVIDER` | Proveedor activo | `openai` o `gemini` |
| `OPENAI_API_KEY` | API key de OpenAI | `sk-...` |
| `OPENAI_MODEL` | Modelo de OpenAI | `gpt-5.4-nano` |
| `GEMINI_API_KEY` | API key de Gemini | `AIza...` |
| `GEMINI_MODEL` | Modelo de Gemini | `gemini-3.1-flash-lite` |

## Uso

Todos los comandos se ejecutan **desde la raíz del repo** y con el entorno virtual activado.

**1. Probar la conexión con los proveedores**

```powershell
python scripts/hello_llm.py            # ambos proveedores
python scripts/hello_llm.py openai     # solo OpenAI
python scripts/hello_llm.py gemini     # solo Gemini
```

Imprime la respuesta, los tokens usados y la latencia. Si falla, muestra el tipo de error
(401 key inválida, 404 modelo inexistente, 429 cuota o rate limit).

**2. Verificar el contrato de salida**

```powershell
python -m src.schema
```

Corre los casos de prueba del schema Pydantic (JSON válidos e inválidos) e informa si
cada uno dio el resultado esperado.

**3. Triage de una consulta**

```powershell
python -m src.main "me cobraron dos veces la suscripción"                 # prompt por defecto (v1_zero_shot)
python -m src.main "me cobraron dos veces la suscripción" --prompt v2_few_shot
python -m src.main --help                                                 # ver opciones y prompts disponibles
```

Imprime el JSON validado por stdout. Si el modelo devuelve una respuesta inválida, se
reintenta automáticamente (los avisos salen por stderr). Si algo falla definitivamente
(prompt inexistente, reintentos agotados, error de la API) muestra el motivo y termina con
código de salida distinto de 0.

**4. Verificar el retry (sin llamar a la API)**

```powershell
python -m scripts.check_retry
```

Simula respuestas rotas del modelo y comprueba que el retry se recupere, que le devuelva el
error al modelo y que falle de forma controlada si se agotan los intentos.

**5. Verificar las métricas (sin llamar a la API)**

```powershell
python -m scripts.check_metrics
```

Comprueba con un LLM simulado que cada request deje una línea, que se sumen los tokens de
todos los intentos, que los fallos también se registren y que el costo se recalcule a mano.
Escribe en un archivo temporal: no toca `data/metrics.jsonl`.

## Métricas

Cada request agrega **una línea** a `data/metrics.jsonl` (append-only, una línea JSON por
request, exitoso o no):

```json
{"timestamp": "2026-11-07T15:16:16+00:00", "provider": "openai", "model": "gpt-5.4-nano",
 "prompt": "v1_zero_shot", "attempts": 1, "success": true, "error": null, "category": "account",
 "input_tokens": 515, "cached_input_tokens": 0, "output_tokens": 165, "total_tokens": 680,
 "latency_s": 4.239, "price_input_per_1m": 0.2, "price_output_per_1m": 1.25, "cost_usd": 0.00030925}
```

**Cómo recalcular el costo a mano** (solo con datos de la propia línea):

```
cost_usd = input_tokens / 1.000.000 × price_input_per_1m + output_tokens / 1.000.000 × price_output_per_1m
         = 515 / 1.000.000 × 0.20 + 165 / 1.000.000 × 1.25
         = 0.000103 + 0.00020625 = 0.00030925
```

- **Los precios usados se guardan en cada línea**: si el proveedor cambia la tarifa, las
  líneas viejas se siguen pudiendo auditar con el precio vigente cuando se generaron.
- **Retry**: tokens, costo y latencia son la **suma de todos los intentos** del request.
- **Fallos**: un request que agotó los reintentos también se registra (`success: false`),
  porque se pagó igual.
- **Tokens cacheados**: se registran en `cached_input_tokens` pero se cobran a precio de input
  completo. El costo es una estimación conservadora (techo), más simple de auditar.
- **Precios** (USD por 1M de tokens, tier Standard, verificados el 2026-11-07 en las páginas
  oficiales de [OpenAI](https://developers.openai.com/api/docs/pricing) y
  [Google](https://aistudio.google.com/docs/pricing)):

  | Modelo | Input | Output |
  |---|---|---|
  | `gpt-5.4-nano` | 0.20 | 1.25 |
  | `gpt-5.4-mini` | 0.75 | 4.50 |
  | `gemini-3.1-flash-lite` | 0.25 | 1.50 |

  Si un modelo no está en la tabla, `cost_usd` queda en `null`: no se inventa un precio.

## Estructura del proyecto

```
├── src/
│   ├── main.py            # CLI: lee argumentos, llama a triage e imprime
│   ├── triage.py          # orquesta: prompt → LLM → validación (retry) → métricas
│   ├── prompts.py         # carga y valida los prompts YAML
│   ├── metrics.py         # costo por request + escritura en data/metrics.jsonl
│   └── schema.py          # contrato Pydantic de la respuesta + casos de prueba
├── data/
│   └── metrics.jsonl      # una línea por request (se genera al usar la CLI)
├── prompts/
│   ├── v1_zero_shot.yaml  # prompt versionado: zero-shot
│   └── v2_few_shot.yaml   # prompt versionado: few-shot (mismas instrucciones + 6 ejemplos)
├── scripts/
│   ├── hello_llm.py       # prueba de conexión con OpenAI y Gemini
│   ├── fake_llm.py        # LLM simulado compartido por los checks
│   ├── check_retry.py     # prueba del retry con un LLM simulado
│   └── check_metrics.py   # prueba de las métricas con un LLM simulado
├── docs/                  # enunciado y uso de IA en el desarrollo
├── .env.example           # plantilla de variables de entorno
└── requirements.txt       # dependencias con versiones fijadas
```

## Decisiones técnicas

- **Temperatura 0**: es una tarea de clasificación; se busca que la misma consulta
  devuelva la misma categoría y que los evals sean reproducibles.
- **Prompts en YAML separados de la configuración**: el YAML guarda solo el texto del
  prompt y sus metadatos. El modelo se define en `.env` y los parámetros de sampling en
  el código, para que al comparar versiones de prompt la única variable sea el prompt.
- **Contrato estricto con Pydantic**: se rechazan campos extra y categorías fuera de la
  lista (sin normalizar mayúsculas); `actions` admite lista vacía para no forzar al modelo
  a inventar acciones de relleno.
- **Sin Structured Outputs de la API (por ahora)**: el formato se pide en el prompt y se
  valida con Pydantic, para que el "% de JSON válido" de los evals mida la calidad de cada
  prompt y el retry tenga sentido.
- **Retry con feedback**: ante una respuesta inválida se le devuelve al modelo su respuesta y
  los errores de validación (campo y motivo) para que la corrija. Máximo 2 reintentos (3
  llamadas): cada reintento reenvía el historial completo y es más caro que el primero. Los
  errores de API (429, 500) no se reintentan con feedback: el modelo no se equivocó.
- **Limpieza determinística antes del retry**: si la respuesta viene envuelta en un bloque
  ` ```json `, se limpia en código. Lo que se arregla con certeza en código no gasta una llamada.

## Estado del proyecto

- [x] Setup y prueba de conexión con ambos proveedores
- [x] Contrato de salida con Pydantic
- [x] Flujo mínimo: CLI + prompt YAML + un proveedor (OpenAI)
- [x] Retry ante JSON inválido
- [x] Métricas por request (`data/metrics.jsonl`)
- [ ] Abstracción `LLMProvider` con dos proveedores
- [ ] Dataset y runner de evals
- [ ] Comparación de prompts (zero-shot vs few-shot)
- [ ] Guardrails de entrada y salida
- [ ] Evals adversariales y extra credit

<!-- Secciones a completar en fases siguientes:
     técnica de context engineering y por qué, tabla de resultados de evals, limitaciones. -->
