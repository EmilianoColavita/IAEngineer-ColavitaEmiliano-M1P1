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

**3. Triage de una consulta** *(en construcción)*

```powershell
python -m src.main "me cobraron dos veces la suscripción"
```

## Estructura del proyecto

```
├── src/
│   └── schema.py          # contrato Pydantic de la respuesta + casos de prueba
├── prompts/
│   └── v1_zero_shot.yaml  # prompt versionado: zero-shot
├── scripts/
│   └── hello_llm.py       # prueba de conexión con OpenAI y Gemini
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

## Estado del proyecto

- [x] Setup y prueba de conexión con ambos proveedores
- [x] Contrato de salida con Pydantic
- [ ] Flujo mínimo: CLI + prompt YAML + un proveedor
- [ ] Retry ante JSON inválido
- [ ] Métricas por request (`data/metrics.jsonl`)
- [ ] Abstracción `LLMProvider` con dos proveedores
- [ ] Dataset y runner de evals
- [ ] Comparación de prompts (zero-shot vs few-shot)
- [ ] Guardrails de entrada y salida
- [ ] Evals adversariales y extra credit

<!-- Secciones a completar en fases siguientes:
     técnica de context engineering y por qué, tabla de resultados de evals, limitaciones. -->
