# Nubbix Triage — Proyecto Integrador Módulo 1 (curso AI Engineer)

## Quién soy y cómo quiero que me ayudes

Soy Emiliano, desarrollador junior en IA (vengo de desarrollo web/backend). Este es el **primer
trabajo entregable** de un curso de AI Engineer. El objetivo es que yo aprenda a construirlo.

Reglas de trabajo (importantes):

- Antes de escribir codigo, explicame el concepto y los criterios
- Cuando revises, señalá errores y mejoras explicando el **por qué**.
- Dame pistas antes que soluciones. Preguntas para pensar son bienvenidas.
- Boilerplate trivial (por ejemplo, contenido de `.gitignore`) podés sugerirlo si te lo pido.
- Respondé en español rioplatense.
- Avanzamos **paso a paso, una fase a la vez**. No adelantes fases futuras salvo que te pregunte.
- Si consultás algo de una API/SDK que pudo haber cambiado (nombres de modelos, precios,
  firmas del SDK), verificalo en la documentación oficial en vez de asumirlo.

El enunciado completo está en `D:\IA Engineer\M1P1 integrador\Nubbix-AIEngineer\enunciado.md`. Leelo si necesitás detalle de un requisito.

## Qué hay que construir

Nubbix es un SaaS ficticio de gestión para pymes LATAM. Hay que automatizar el soporte nivel 1:
un servicio (**CLI**) que recibe una consulta en texto libre y devuelve **JSON validado**:

```json
{"answer": "...", "confidence": 0.0-1.0, "category": "billing|technical|account|other", "actions": ["..."]}
```

`actions` = acciones sugeridas para el agente humano.

### Requisitos obligatorios

- Cliente LLM con **≥2 proveedores configurables** detrás de una abstracción (`LLMProvider`).
  Cambiar de proveedor sin tocar la lógica de negocio. Manejo explícito de errores/rate limits.
- **Prompts versionados en YAML** (`prompts/*.yaml`), ≥2 versiones (ej. zero-shot vs few-shot),
  comparadas contra el dataset. La técnica elegida se justifica **con datos de evals**.
- Salida validada con **Pydantic** + **retry automático** ante JSON no parseable / inválido.
- **Guardrails**: ≥1 de entrada (moderación / detección de prompt injection) y ≥1 de salida
  (validación de contenido). Pensar en capas.
- **Métricas**: `data/metrics.jsonl` append-only, una línea por request: timestamp, tokens
  (prompt/completion/total), latencia (s), costo estimado USD (reproducible y auditable).
  Nada de SQLite ni bases de datos.
- **Evals**: `evals/dataset.jsonl` (≥30 casos etiquetados) + `evals/runner.py` (script simple,
  **no** pytest ni framework) con score global y por categoría.
- **README**: setup, uso con ejemplos, técnica de context engineering y por qué, tabla de
  resultados de evals, decisiones técnicas, limitaciones.
- `.env.example` + `requirements.txt`. Nunca credenciales en el código ni en el repo.
- Repo público en GitHub, autocontenido, commits chicos y descriptivos (`feat: ...`, `chore: ...`).
- Documentar en `docs/ai-usage.md` cómo se usó IA en el desarrollo (lo pide el enunciado).

### Bonus / extra credits

- Bonus: `evals/adversarial.jsonl` con 10 prompts maliciosos (injection, jailbreak, exfiltración
  del system prompt), mitigación aplicada y efecto medido, documentado en el README.
- Al menos un extra credit: FastAPI, caché con hash MD5, LLM-as-judge en runtime o **comparativa
  de modelos** (probablemente el más barato si el runner acepta `--provider`/`--model`).

### Evaluación

Rúbrica Excelente/Satisfactorio/Insuficiente. Aprobación 70/100, destacado 81+.
Categorías: funcionalidad y contrato JSON · evals y dataset · context engineering ·
seguridad · observabilidad · repo/README/extra credits.

## Decisiones tomadas

- Lenguaje: **Python 3.11+**, venv.
- Proveedores: **Google Gemini** (API key gratuita de Google AI Studio, SDK `google-genai` —
  NO el viejo `google-generativeai`, deprecado) y **OpenAI** (Api paga, SDK `openai`).
  ⚠️ Todavia no se tomo la decision de que proveedor correto elegir pero por ahora son esas.
  Evaluar en consola la respuesta de la API, Si da `429 insufficient_quota`, evaluar cargar saldo o reemplazar por Groq.
- Modelos: chicos/baratos (familia flash en Gemini, mini/nano en OpenAI), configurables por env.
- Dependencias base: `openai`, `google-genai`, `python-dotenv`, `pydantic`, `pyyaml` (versiones fijadas).
- Variables de entorno: `LLM_PROVIDER`, `GEMINI_API_KEY`, `GEMINI_MODEL`, `OPENAI_API_KEY`, `OPENAI_MODEL`.

## Estructura del repo prevista

```
nubbix-triage/
├── src/
│   ├── main.py          # CLI: parsea args y orquesta
│   ├── schema.py        # contrato Pydantic
│   ├── providers.py     # LLMProvider + implementaciones OpenAI / Gemini
│   ├── prompts.py       # carga de prompts YAML
│   ├── triage.py        # lógica: llamar, validar, reintentar
│   ├── guardrails.py    # guardrails de entrada y salida
│   └── metrics.py       # cálculo de costo + append a JSONL
├── prompts/             # v1_zero_shot.yaml, v2_few_shot.yaml, ...
├── evals/               # dataset.jsonl, runner.py, adversarial.jsonl
├── data/                # metrics.jsonl
├── scripts/             # hello_llm.py (prueba de conexión)
├── docs/                # enunciado.md, ai-usage.md
├── .env.example  requirements.txt  .gitignore  README.md  CLAUDE.md
```

Flujo: `consulta → guardrail entrada → prompt YAML → LLMProvider → parseo + Pydantic (retry)
→ guardrail salida → JSON + línea en metrics.jsonl`.

## Plan por fases

| # | Fase | Terminada cuando… |
|---|------|-------------------|
| 0 | Setup: repo, venv, .gitignore, .env.example, requirements, `scripts/hello_llm.py` | El script responde e imprime tokens con **ambos** proveedores; `.env` fuera del repo; primer commit pusheado |
| 1 | Contrato Pydantic (`schema.py`) | Valida un JSON bueno y rechaza uno malo (category inválida, confidence fuera de rango) |
| 2 | Flujo mínimo: 1 proveedor + 1 prompt YAML + CLI | `python -m src.main "me cobraron dos veces"` imprime JSON válido |
| 3 | Retry ante parseo/validación inválida (feedback del error al modelo) | Se recupera de una salida rota o falla de forma controlada |
| 4 | Métricas en `data/metrics.jsonl` | Cada request agrega línea con tokens, latencia y costo recalculable a mano |
| 5 | Segundo proveedor + abstracción + backoff | Cambiar `LLM_PROVIDER` en `.env` sin tocar `triage.py` |
| 6 | Dataset ≥30 (ideal 40–50) balanceado, con casos ambiguos/typos/multi-intención | Etiquetado a mano en JSONL |
| 7 | Runner de evals | `python evals/runner.py --prompt v1` imprime accuracy global y por categoría, % JSON válido |
| 8 | Comparar prompts (v1 zero-shot, v2 few-shot, opcional v3) | Tabla comparativa y elección justificada con datos |
| 9 | Guardrails entrada/salida | Un intento de injection se detecta y se responde de forma segura |
| 10 | Bonus adversarial + extra credit | 10 ataques documentados con efecto medido |
| 11 | README final + prueba desde clon limpio | Alguien clona y corre sin preguntar nada |

## Estado actual

- Fase 0 (Setup): **completada** (venv + `hello_llm.py` funcionando).
- **Fase actual: 1 (Contrato Pydantic en `src/schema.py`).**
  Al retomar, preguntame en qué punto de la fase 1 estoy y revisá lo que haya hecho.
- Contenidos de cursada a tener en cuenta: tokenización/context window, sampling (temperatura, top-p),
  APIs de distintos proveedores, streaming, rate limits/errores, costo por token; system prompts y roles,
  few-shot, chain-of-thought, plantillas/versionado de prompts, variables de contexto.

<!-- Actualizá esta sección a medida que avances: fase actual, decisiones nuevas, pendientes. -->
