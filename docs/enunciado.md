**Contexto y Objetivos**

Eres un/a AI Engineer contratado/a por **Nubbix**, un SaaS de gestión
para pymes de LATAM con 12.000 clientes. Su mesa de soporte recibe ~400
tickets por día, y el 60% son consultas repetitivas de cuatro tipos:
facturación, problemas técnicos, gestión de cuenta y otros. El equipo de
soporte de nivel 1 está saturado, el tiempo de primera respuesta se fue
a 9 horas y los clientes se quejan.

Tu misión: automatizar el primer nivel de soporte con un servicio que
recibe cada consulta en texto libre, la clasifica, propone una respuesta
y sugiere acciones — con calidad medible, costos controlados y
resistencia a usos maliciosos. Es un proyecto simple e independiente: no
depende de ningún otro módulo.

**🎯 Objetivos (qué vas a entregar y por qué importa):**

- **Integrar LLMs por API con al menos dos proveedores configurables**
  (por ejemplo OpenAI y Anthropic), controlando costo, latencia y
  errores. Esto te obliga a construir una abstracción real, no un
  llamado hardcodeado a un solo proveedor.

- **Aplicar y justificar una técnica de context engineering**, con
  prompts versionados en archivos YAML fuera del código. La versión
  elegida se respalda con datos de evals, no con intuición.

- **Garantizar salidas estructuradas y validadas** (JSON Schema /
  Pydantic), con reintentos automáticos ante parsing inválido. Esto crea
  un contrato estable para quien consuma tu servicio.

- **Mitigar prompt injection y aplicar moderación** de entrada y salida.

- **Construir un dataset de evaluación y una suite de evals
  ejecutable**, con métricas globales y por categoría — así demostrás
  con números que tu sistema funciona, no con una demo manual.

***¿Por qué esto es importante?** Salidas estructuradas + métricas +
decisiones de prompting documentadas y respaldadas por evals son
habilidades centrales para construir sistemas de IA confiables, y son la
base sobre la que vas a construir RAG en el Módulo 2.*

**📢Consigna**

**Construir un servicio que recibe la consulta de un usuario en texto
libre y devuelve una respuesta estructurada, segura y medida.**

El servicio expone una **CLI** (interfaz de línea de comandos) que
recibe la consulta y devuelve JSON validado con el contrato {answer,
confidence, category, actions}, donde category ∈ {billing, technical,
account, other} y actions es una lista de acciones sugeridas para el
agente humano.

Cada ejecución registra tokens consumidos, latencia y costo. El proyecto
incluye un dataset de evaluación etiquetado y una suite de evals que
corre por comando y reporta score global y por categoría. La técnica de
context engineering elegida debe estar documentada y justificada con
resultados, no con opiniones.

**Bonus/opcional dentro de la consigna:** resistencia adversarial — una
suite de 10 prompts maliciosos (injection, jailbreak, exfiltración del
system prompt) documentados, con la mitigación aplicada y su efecto
medido.

**Ejemplos ilustrativos de tickets**

No vas a recibir un dataset armado — construirlo es parte del objetivo
de la Clase 5. Estos ejemplos son solo una referencia de tono y formato
para que tu dataset de evaluación se parezca a tickets reales de
soporte, no una lista para copiar ni una muestra representativa de toda
la variedad que deberías cubrir:

- *Facturación (billing):* "Hola, me cobraron dos veces la suscripción
  de este mes, necesito que me reintegren uno de los cargos."

- *Facturación (billing):* "no me llega la factura de agosto, la
  necesito para mi contador urgente"

- *Técnico (technical):* "El dashboard de reportes me tira error 500
  desde ayer, no puedo generar el cierre de caja."

- *Técnico (technical):* "Se me cayó la integración con Mercado Pago,
  los pagos no se están sincronizando desde esta mañana."

- *Cuenta (account):* "Quiero agregar un usuario nuevo a mi cuenta con
  permisos de solo lectura, ¿cómo lo hago?"

- *Cuenta (account):* "Necesito cambiar el email de administrador de la
  cuenta, el actual ya no existe en mi empresa."

- *Otros (other):* "¿Tienen algún descuento para clientes que llevan más
  de 2 años con Nubbix?"

- *Otros (other):* "hola buenas, quería saber si tienen planes para
  empresas más grandes, somos 80 empleados"

**Entregables del proyecto y requisitos de entrega**

Enviar mediante un enlace público al repositorio en Git. Asegurate de
que el repositorio sea autocontenido y que se pueda ejecutar sin
depender de elementos externos no documentados.

**📂 Estructura de repositorio esperada**

| **Entregable**                    | **Archivo/Formato**                            | **Contenido mínimo**                                                                                                                                                                                                              |
|-----------------------------------|------------------------------------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| **CLI de triage**                 | src/main.py (o similar)                        | Acepta una consulta por línea de comandos; llama a un cliente LLM con ≥2 proveedores configurables; devuelve JSON validado con el contrato {answer, confidence, category, actions}; retry automático ante respuesta no parseable. |
| **Prompts versionados**           | prompts/\*.yaml                                | Al menos 2 versiones de prompt (ej. zero-shot, few-shot, chain-of-thought, con reglas de seguridad, etc.), documentadas y comparadas contra el dataset.                                                                           |
| **Dataset y suite de evals**      | evals/dataset.jsonl + evals/runner.py          | Dataset de ≥30 casos etiquetados; runner ejecutable por comando (script simple, no framework de testing) con score global y por categoría.                                                                                        |
| **Registro de métricas**          | data/metrics.jsonl                             | Log estructurado append-only por request: timestamp, tokens (prompt/completion/total), latencia (s) y costo estimado (USD).                                                                                                       |
| **Guardrails de seguridad**       | dentro de src/                                 | Al menos un guardrail de entrada (moderación / detección de injection) y uno de salida (validación de contenido).                                                                                                                 |
| **README**                        | README.md                                      | Setup y uso (con ejemplos de comando/respuesta), técnica de context engineering elegida y por qué, tabla de resultados de evals, decisiones técnicas.                                                                             |
| **Configuración**                 | .env.example, requirements.txt                 | Variables de entorno documentadas (nunca credenciales reales); dependencias declaradas.                                                                                                                                           |
| **Seguridad adversarial (bonus)** | evals/adversarial.jsonl + sección en el README | Suite de 10 prompts maliciosos documentados, con la mitigación aplicada y su efecto medido.                                                                                                                                       |

**✅ Checklist de entrega**

- Claves de API cargadas por variable de entorno, nunca en el código.
  src/main.py incluido y versionado.

- Al menos una ejecución de la CLI registrada que produzca JSON válido y
  una línea de métricas.

- Suite de evals corrida y con resultados reflejados en el README.

- README y código consistentes entre sí: alguien que clone el repo
  debería poder instalarlo y correrlo sin preguntarte nada.

**Evaluación**

La corrección se realiza mediante rúbrica, con niveles **Excelente /
Satisfactorio / Insuficiente** por categoría. El puntaje mínimo de
aprobación es **70/100**; un puntaje de **81 a 100** se considera que
supera lo esperado.

Categorías evaluadas:

- **Funcionalidad y contrato JSON** — cliente LLM multi-proveedor,
  cumplimiento del esquema Pydantic, retry ante errores de parsing,
  manejo de casos borde.

- **Suite de evals y dataset** — cobertura del dataset (≥30 casos),
  automatización del runner, claridad del reporte.

- **Context engineering y prompting** — versionado de prompts,
  comparativa empírica, selección respaldada por datos.

- **Seguridad y guardrails** — detección y mitigación de prompt
  injection / jailbreak, suite adversarial (si se aborda el bonus).

- **Observabilidad y métricas** — registro estructurado en JSONL con
  tokens, latencia y costo por request.

- **Repositorio, README y extra credits** — calidad y modularidad del
  código, documentación ejecutable, y al menos un extra credit (FastAPI,
  caché con hash MD5, LLM-as-judge en runtime o comparativa de modelos).

**Guía para el desarrollo del proyecto integrador**

**Propósito de esta guía**

Esta guía te acompaña en el desarrollo del Proyecto Integrador de AI
Engineering correspondiente al Módulo 1. No reemplaza la consigna ni
define pasos obligatorios: te orienta para que puedas organizarte,
priorizar correctamente y evitar errores comunes.

El foco está en ayudarte a construir un MVP funcional, claro y bien
documentado, alineado con los estándares esperados para un perfil Junior
en AI Engineering.

**Qué se espera del proyecto**

Se espera que desarrolles una aplicación que integre LLMs a través de su
API, aplicando lo aprendido en el módulo, y que cumpla con los
requisitos definidos en la consigna oficial.

Más allá de la cantidad de funcionalidades, se valorará especialmente:

- Que la CLI funcione correctamente de punta a punta.

- Que el código sea legible, modular y esté bien organizado.

- Que el proyecto esté versionado con Git.

- Que las decisiones de prompting, de proveedor y de diseño estén
  documentadas y justificadas.

- Que la documentación permita entender y ejecutar la aplicación sin
  ayuda externa.  
  **Cómo orientar el desarrollo**

*Antes de escribir código:*

- Lee la consigna completa.

- Asegurate de entender qué problema resuelve el servicio y quién lo va
  a usar (el agente de soporte de Nubbix).

- Identificá las funcionalidades mínimas obligatorias y las opcionales
  (extra credits).

- Definí una estructura simple de archivos (src/, prompts/, evals/,
  data/) antes de empezar a programar.

- Pensá cómo vas a gestionar credenciales de ambos proveedores desde el
  inicio, para no tener que refactorizar después.  
  *Durante el desarrollo:*

- Priorizá que el flujo principal funcione antes de pulir detalles: una
  consulta por CLI que devuelva un JSON válido ya es un punto de partida
  sólido.

- Implementá primero el caso más simple (un proveedor, un prompt) y
  después sumá el segundo proveedor y las versiones adicionales de
  prompt.

- Tratá tus prompts como código: probalos, ajustalos e iterá. La primera
  versión rara vez es la mejor — por eso el proyecto pide comparar al
  menos 2 versiones con datos.

- Probá la CLI con entradas variadas (incluidas ambiguas) para validar
  que la salida se mantiene consistente.

- Hacé commits pequeños y descriptivos.  
  *Al finalizar:*

- Revisá que la CLI funcione sin errores en una ejecución limpia,
  idealmente desde un clon nuevo del repositorio.

- Verificá que la salida sea consumible por otro sistema sin
  transformaciones adicionales.

- Asegurate de que el README explique claramente cómo instalar,
  configurar y ejecutar el proyecto.

- Confirmá que las credenciales sensibles no queden expuestas en el
  repositorio.  
  **Buenas prácticas recomendadas**

**Prompt Engineering**

- Elegí conscientemente la técnica de prompting que vas a usar y dejá
  documentado por qué la elegiste para tu caso.

- Tratá el prompt como una hipótesis: probá al menos 2 versiones y
  compará resultados contra tu dataset antes de decidir.

- Sé explícito en tus instrucciones. Cuanto más concreto sea el prompt,
  menos margen tendrá el modelo para improvisar.

- Versioná cada prompt en su propio archivo YAML, nunca hardcodeado en
  el código.

- Dejá evidencia de tu proceso de iteración en el README: qué probaste,
  qué falló y por qué te quedaste con la versión final.  
  **Salida estructurada**

- Trabajá con la idea de contrato: {answer, confidence, category,
  actions} no cambia a lo largo del proyecto.

- Sé consistente en el naming y en los tipos de datos.

- Validá la salida con Pydantic antes de confiar en ella.

- Definí una estrategia de reintento clara para cuando el modelo no
  respeta el contrato — no asumas que siempre lo va a respetar.  
  **Integración con la API (multi-proveedor)**

- Las credenciales nunca van en el código. Cargalas desde variables de
  entorno y documentá cuáles hacen falta en .env.example.

- Construí una abstracción mínima (LLMProvider o similar) que te permita
  cambiar de proveedor sin tocar la lógica de negocio.

- Configurá los parámetros de la llamada (modelo, temperature, límites
  de tokens) de forma deliberada y dejá registro de por qué elegiste
  esos valores.

- Manejá rate limits y errores de API de forma explícita, no dejes que
  la CLI se caiga ante un error transitorio.  
  **Observabilidad**

- Registrá tus métricas en data/metrics.jsonl (formato append-only, una
  línea por request). Si una métrica no responde una pregunta concreta
  de costo, latencia o consumo, sobra.

- Asegurate de que el costo estimado sea reproducible y auditable:
  alguien debería poder revisar tus números y llegar al mismo resultado.

- No uses SQLite ni una base de datos para esto — JSONL alcanza y evita
  complejidad innecesaria en este módulo.  
  **Seguridad**

- Pensá en capas: un solo guardrail de entrada suele ser fácil de
  evadir.

- Documentá con un ejemplo concreto cómo se comporta tu sistema frente a
  una entrada adversarial: qué detectaste, qué decisión tomó el sistema
  y por qué.

- Si abordás el bonus, una buena defensa no se rompe con variaciones
  triviales del ataque.  
  **Calidad del código**

- Separá responsabilidades en funciones pequeñas: cliente LLM,
  validación, guardrails y métricas no deberían vivir todos en el mismo
  archivo.

- Usá nombres que expliquen la intención.

- Si encontrás lógica repetida, extraela.

- No armes un framework propio: la complejidad va al prompt y a los
  evals, no a la arquitectura ni a las herramientas (el runner de evals
  es un script simple, no pytest ni un framework de testing).  
  **Documentación**

- Tu README es la primera impresión del proyecto. Debe permitir que
  alguien más lo entienda, lo instale y lo ejecute sin necesidad de
  preguntarte nada.

- Explicá las decisiones técnicas clave: qué técnica de prompting usaste
  y por qué, por qué elegiste esos proveedores, qué limitaciones tiene
  tu solución.

- Mantené la documentación sincronizada con el código.  
  **Git y GitHub**

- Usá mensajes de commit claros (por ejemplo: feat: agregar registro de
  métricas).

- Versioná el proyecto desde el inicio.

- Verificá que el repositorio sea público y autocontenido.

- Configurá el repositorio para no subir credenciales, archivos locales
  ni dependencias instaladas.  
  **Errores comunes a evitar**

- Saltar a los extra credits antes de tener el flujo principal
  funcionando.

- Dejar credenciales sensibles dentro del código fuente.

- Asumir que el modelo siempre va a respetar el contrato JSON, sin
  validar la salida.

- Construir un prompt único, sin versionar ni comparar su rendimiento.

- Registrar métricas sin que sea posible verificar de dónde salieron los
  números.

- Implementar un solo proveedor y dejar la abstracción multi-proveedor a
  medias.

- No probar el proyecto en una ejecución limpia antes de entregarlo.  
  **Sobre el uso de IA**

Podés utilizar herramientas de IA como apoyo durante el desarrollo,
siguiendo lo aprendido en el módulo. Documentá los prompts que usaste y
explicá cómo influyeron en las decisiones técnicas del proyecto. El
objetivo del Proyecto Integrador es demostrar tu comprensión sobre cómo
se construye un sistema con LLMs, no delegar esa comprensión a otra
herramienta.

**Cierre**

Esta guía está pensada para ayudarte a tomar buenas decisiones técnicas
y de organización. El objetivo final es que puedas demostrar que
comprendés el flujo completo de integración con LLMs — desde el cliente
multi-proveedor y el diseño del prompt hasta la observabilidad y la
seguridad de tu sistema — y que podés entregar una solución funcional,
robusta y bien presentada.
