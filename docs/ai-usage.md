# Uso de IA en el desarrollo

Este proyecto se desarrolló con **Claude Code** (Claude, de Anthropic) como asistente de
programación, dentro de VS Code. Este documento describe qué hizo la IA, qué decidió el autor y
cómo se controló el resultado.

## Cómo se trabajó

El asistente se configuró mediante un `CLAUDE.md` con reglas de trabajo orientadas al
aprendizaje: explicar el concepto y los criterios antes de escribir código, señalar errores
explicando el porqué, avanzar una fase a la vez, presentar el plan de cada fase y esperar
aprobación antes de implementarla, y verificar en la documentación oficial cualquier dato de
APIs que pudiera haber cambiado (modelos, precios, firmas de SDK).

El proyecto se dividió en 12 fases (setup → contrato → flujo mínimo → retry → métricas →
proveedores → dataset → runner → comparación de prompts → guardrails → adversarial → README).

## Qué hizo la IA

| Área | Aporte de la IA |
|---|---|
| Conceptos | Explicaciones de cada fase: contrato con Pydantic, roles system/user, in-context learning, retry con feedback, backoff con jitter, costo por token, contaminación de datasets, sobreajuste, defensa en capas. |
| Código | Redacción de la mayor parte del código de `src/`, `evals/` y `scripts/`, siguiendo las decisiones del autor. |
| Prompts | Redacción de `v1_zero_shot`, `v2_few_shot` y `v3_frontier_rules`. |
| Dataset | Borrador de los 40 casos de `evals/dataset.jsonl` y de los 10 ataques de `evals/adversarial.jsonl`. |
| Verificación | Consulta de la documentación oficial de OpenAI y Google (precios por token, Structured Outputs, parámetros del SDK) e inspección del código de los SDKs instalados (reintentos por defecto, clases de error). |
| Pruebas | Scripts de verificación sin API (`scripts/check_*.py`) y corridas reales de evals. |
| Documentación | Redacción del README y de este documento. |

## Qué decidió el autor

Las decisiones de diseño se tomaron después de que la IA presentara opciones con sus
ventajas y desventajas:

- Arrancar con OpenAI y sumar Gemini como segundo proveedor.
- Tokens cacheados: registrarlos, pero cobrarlos a precio completo (estimación conservadora).
- Versionar `data/metrics.jsonl` y los resultados de evals para que los evaluadores los vean.
- Dataset: que la IA escriba el borrador y revisarlo a mano; sin casos en portugués; permitir
  categorías alternativas solo en casos ambiguos, con score principal estricto.
- Comparación de prompts: crear v3, incluir Gemini, 2 corridas por configuración, y el
  **criterio de decisión aprobado antes de ver los resultados**.

## Cómo se controló a la IA (errores detectados)

La IA se equivocó varias veces; estos son los casos más relevantes y cómo se detectaron:

1. **Contaminación del prompt v1.** Las pistas de categoría del primer v1 copiaban frases de
   los tickets de ejemplo del enunciado (que podían terminar en el dataset). Se detectó al
   revisar si el prompt era "demasiado específico" y se reescribieron como pistas genéricas.
2. **Error de medición en el runner.** En la primera comparación, 19 casos de Gemini sin
   respuesta por rate limit (`429`) se contaron como "JSON inválido", lo que descalificaba
   injustamente a Gemini. Se detectó porque Gemini nunca había devuelto JSON roto en las
   pruebas manuales; se separaron los errores de proveedor del JSON inválido y se re-corrieron
   las evaluaciones espaciando las llamadas.
3. **Falsos positivos en los guardrails de salida.** La primera versión marcaba como "pedido
   de datos sensibles" frases como *"un agente te enviará los pasos para restablecer tu
   contraseña"* y como "promesa" a *"he derivado tu caso"*. Se midieron contra 501 respuestas
   reales guardadas y se ajustaron hasta 0 falsos positivos.
4. **Datos de API no asumidos.** Precios, nombres de modelos y comportamiento de reintentos de
   los SDKs se verificaron en fuentes oficiales o en el código instalado, no de memoria.

## Limitaciones del uso de IA

- **Dataset generado con IA.** Los casos escritos por un modelo tienden a estar "bien escritos"
  y pueden ser más fáciles para otro modelo que los tickets reales. Se mitigó con revisión
  manual de las etiquetas, pero no reemplaza tickets reales.
- **Reglas de v3 escritas viendo los fallos del dataset.** El mismo dataset se usó para escribir
  las reglas y para medirlas: el 95% de v3 puede estar inflado (sobreajuste). Lo correcto sería
  validarlo con un conjunto de casos nuevos (holdout), que quedó pendiente.
