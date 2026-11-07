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
- **Al empezar cada fase**, antes de escribir código: explicame de qué trata la fase y presentame
  el plan de desarrollo (qué archivos, qué decisiones, cómo se prueba). Esperá mi OK para codear.
  Al terminarla, resumí qué se hizo en cada archivo y cómo se verificó.
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
- Fase 1 (Contrato Pydantic): **completada y commiteada**. `src/schema.py` con `TriageResponse`
  y 17 casos (`python -m src.schema`). Decisiones: `str_strip_whitespace`, `extra="forbid"`,
  `category` como `Literal` y sin normalizar mayúsculas (lo corrige el retry), `confidence` en
  modo lax (acepta `"0.85"`), `actions` admite lista vacía, máx. 5, sin strings vacíos.
  `model_validate_json` reporta JSON roto como `ValidationError` tipo `json_invalid` (útil en fase 3).
- Fase 2 (Flujo mínimo): **completada**. Detalle: proveedor inicial OpenAI; `temperature=0` verificado OK en `gpt-5.4-nano` y
  `gemini-3.1-flash-lite`; `prompts/v1_zero_shot.yaml` (campos: id, version, technique,
  description, system, user_template con `{query}`; solo user_template se formatea);
  README inicial. Modelo en `.env`, temperatura/límites en código, NO en el YAML.
  `prompts/v2_few_shot.yaml` = system de v1 idéntico + 6 ejemplos de frontera/calibración
  dentro del system (no usa tickets del enunciado, para no contaminar evals).
  `prompts.py` (PromptTemplate Pydantic, ruta desde `__file__`, safe_load, PromptError),
  `triage.py` (call_llm aislada con Responses API, temperature=0, max_output_tokens=500;
  sin Structured Outputs a propósito para que retry y "% JSON válido" midan algo) y
  `main.py` (argparse, `--prompt` con choices) funcionando de punta a punta.
- Fase 3 (Retry): **completada**. En `triage.py`: `MAX_RETRIES=2` (hasta 3 llamadas), retry solo
  ante `ValidationError` (errores de API → backoff en fase 5), feedback = respuesta cruda como
  `assistant` + `RETRY_MESSAGE` con errores `campo: msg` (en código, no en YAML, igual para todas
  las versiones), `clean_raw()` saca ```json en código sin gastar retry, `TriageError` con
  `attempts` y `last_raw`, avisos por stderr. `call_llm(messages)` ahora recibe la conversación.
  `scripts/check_retry.py` lo prueba con un LLM falso (`python -m scripts.check_retry`).
  Verificado con la API real que el historial con `assistant` funciona y el modelo corrige.
- Fase 4 (Métricas): **completada**. `src/metrics.py`: `PRICES` (USD/1M, verificados 2026-11-07: gpt-5.4-nano 0.20/1.25,
  gpt-5.4-mini 0.75/4.50, gemini-3.1-flash-lite 0.25/1.50), `compute_cost` (modelo sin precio →
  null), `log_request` (append, crea `data/`, no rompe el triage si falla la escritura),
  `METRICS_PATH` parcheable. `triage.py`: `call_llm` devuelve `LLMResult` (texto + tokens),
  `RequestStats` suma TODOS los intentos, se loguea en `finally` (también fallos). Cada línea
  guarda los precios usados (auditable). Decisiones de Emiliano: tokens cacheados (a) =
  registrados pero cobrados a precio completo; `data/metrics.jsonl` SE VERSIONA (evaluadores lo
  ven); regenerarlo limpio con los evals en la fase 11. Checks con LLM falso compartido
  (`scripts/fake_llm.py`) escriben en archivo temporal: `check_retry`, `check_metrics` (13 OK).
  Dato real: mismo ticket v1 = 515 in / 165 out ($0.000309); v2 = 1081 in / 115 out ($0.000360):
  v2 duplica el input pero responde más corto → solo +16% de costo.
- Fase 5 (Proveedores + backoff): **completada**. `src/providers.py`: `LLMProvider` (ABC,
  `generate(messages, *, temperature, max_output_tokens) -> LLMResult`), `LLMResult` movido acá,
  `OpenAIProvider` (max_retries=0, timeout 30s) y `GeminiProvider` (HttpRetryOptions attempts=1;
  system → `system_instruction`, assistant → `model`, output = candidates + thoughts),
  errores propios `ProviderError` / `RetryableError(retry_after)`, `get_provider()` con
  `LLM_PROVIDER`. 429 `insufficient_quota` → no reintentable. `triage.py` ya no importa SDKs:
  `triage(query, prompt_name, provider=None)`, `_call_with_backoff` (3 reintentos, 1s·2^n,
  tope 20s, jitter, respeta Retry-After, `_sleep` parcheable), métrica `api_retries`.
  `main.py`: `--provider`. Checks: `FakeProvider` implementa el contrato; `check_backoff` (19 OK,
  incluye excepciones reales de ambos SDKs). Verificado real: ambos proveedores, cambio por
  `LLM_PROVIDER` sin flag, y retry multi-turn con Gemini.
- Fase 6 (Dataset): **completada y commiteada**. Borrador hecho por Claude (opción b), revisado
  por Emiliano. `evals/dataset.jsonl`: 40
  casos, 10 por categoría, sin portugués (decisión de Emiliano). Campos: id
  (`<categoria>-NN`), query, expected_category, acceptable_categories (solo 5 casos
  multi-intención/ambiguos; el enunciado no lo prohíbe; el score principal es ESTRICTO y la
  alternativa se reporta aparte), tags (vocabulario cerrado: clear, frontier, multi_intent,
  vague, short, long, typos, informal, angry, regional, off_topic), notes (por qué esa
  etiqueta). `evals/dataset.py`: `EvalCase` (Pydantic), `load_dataset()` (junta todos los
  errores), chequeo de contaminación vs líneas "Consulta:" de los prompts (difflib ≥ 0.6),
  resumen `python -m evals.dataset`. `Category` se extrajo en `src/schema.py` como única
  fuente de verdad. Pendiente: registrar en `docs/ai-usage.md` que el dataset lo generó IA.
- **Fase actual: 7 (Runner de evals).** Implementada y verificada; falta que Emiliano la revise
  y commitee. Decisiones de Emiliano: resultados SE VERSIONAN en `evals/results/`; soportar
  también `python evals/runner.py` (shim de sys.path); en fase 7 correr solo v1/OpenAI.
  `src/triage.py`: `run_triage(query, prompt, provider, source) -> TriageRun(response, record,
  error)` no lanza TriageError/ProviderError (los devuelve); `triage()` es un wrapper que los
  lanza (CLI sin cambios). Métricas con campo `source` ("cli"/"eval"). `get_provider(name,
  model)`. `evals/runner.py`: `evaluate()` (aborta con `AbortRun` ante ProviderError no
  reintentable), `summarize()` (accuracy estricta global/categoría/tag, % JSON válido, % primer
  intento, matriz de confusión, hits de alternativa aceptable aparte, calibración, costo,
  tokens, latencia, fallos), `print_report()`, `save_results()`. Flags: --prompt --provider
  --model --limit. `scripts/check_runner.py` (11 OK) valida las cuentas con FakeProvider.
  **Resultado real v1 / openai gpt-5.4-nano (40 casos): accuracy 85% (34/40), JSON válido 100%,
  primer intento 100%; billing 90, technical 80, account 90, other 80; frontier 63.6% (7/11),
  el resto de los tags ~100%; 3 de los 6 fallos eligieron la alternativa aceptable; calibración
  NULA (conf media 0.736 al acertar vs 0.728 al fallar); technical-03 (IVA de facturas que emite
  el cliente) → billing con conf 0.9 (error confiado); costo $0.0124 total, 530 in / 163 out
  promedio, latencia 2.0s.** Archivo: `evals/results/20261107-162530_v1_zero_shot_openai_gpt-5.4-nano.json`.
- Contenidos de cursada a tener en cuenta: tokenización/context window, sampling (temperatura, top-p),
  APIs de distintos proveedores, streaming, rate limits/errores, costo por token; system prompts y roles,
  few-shot, chain-of-thought, plantillas/versionado de prompts, variables de contexto.

## Casos observados en pruebas manuales (usar en fases futuras)

| Consulta | Prompt | Resultado | Para qué sirve |
|---|---|---|---|
| "me cobraron dos veces" | v1 | billing, 0.9, 4 actions | El `answer` pidió **"últimos 4 dígitos de la tarjeta"** → dato sensible: caso para el **guardrail de salida (fase 9)** y para el dataset adversarial |
| ídem | v1 | `answer` largo y con voseo | El prompt pedía "breve" y "español neutro": las instrucciones no se cumplen al 100% → justificación de evals |
| "no me deja agregar un usuario nuevo y encima me llego una factura que no entiendo" | v2 | account, **0.55**, actions para ambos temas | Multi-intención calibrada como enseña el ejemplo few-shot → caso para el **dataset (fase 6)** |
| "hola, quería saber si el plan anual tiene descuento" | v2 | other, 0.7 | El `answer` afirma que el plan anual "suele tener descuentos": **inventa condiciones comerciales** → guardrail de salida (fase 9) |
| "no puedo exportar el reporte de ventas a excel, me da error" | v1 | openai: technical 0.86 / gemini: technical 0.95 | Gemini dice **"He derivado tu caso... nos pondremos en contacto a la brevedad"**: afirma acciones que no hizo y promete plazos → guardrail de salida (fase 9). Ambos coinciden en categoría |
| retry real con confidence 1.3 + "Billing" | v1 | gemini corrigió a billing con **confidence 1.0** | Gemini tiende a confidence más alta que OpenAI → calibración distinta por proveedor: medirlo en la comparativa de modelos |
| `--prompt v3` | — | argparse lo rechaza listando los disponibles | Manejo de errores de la CLI |
| `"   "` | — | "consulta vacía", exit 1 | Validación de entrada en `main.py` |

<!-- Actualizá esta sección a medida que avances: fase actual, decisiones nuevas, pendientes. -->
