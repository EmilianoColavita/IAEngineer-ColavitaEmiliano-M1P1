"""Guardrails de entrada y de salida, en capas.

Defensa en profundidad: ninguna capa es perfecta, cada una tapa lo que se le escapa a la
anterior.

  ENTRADA (antes de llamar al LLM: un ataque detectado no gasta tokens)
    1. Largo máximo del mensaje.
    2. Detección heurística de prompt injection / jailbreak: patrones de "ignorá las
       instrucciones", pedidos de revelar el prompt, cambios de rol, etiquetas de sistema
       falsas, intentos de forzar la clasificación.
    → Si bloquea: respuesta segura que cumple el contrato y deriva a un humano.

  MODELO
    3. El system prompt define rol y tarea; la consulta va separada en el mensaje user.
    4. Contrato Pydantic (schema.py): estructura, tipos, rangos, categorías.

  SALIDA (sobre la respuesta ya validada)
    5. BLOQUEA (reemplaza el answer) si hay filtración del system prompt o si la respuesta
       le pide al cliente datos sensibles (tarjeta, CVV, contraseña).
    6. MARCA para revisión humana (sin bloquear) si hay promesas no autorizadas
       (reintegros, plazos) o afirma acciones que el bot no puede haber hecho.

Limitaciones: son heurísticas (regex). Un ataque reformulado puede evadir la capa de entrada;
por eso existe la de salida. Ver la suite adversarial en evals/adversarial.jsonl.
"""

import re
import unicodedata
from dataclasses import dataclass, field

from src.schema import TriageResponse

MAX_QUERY_CHARS = 4000


def normalize(text: str) -> str:
    """Minúsculas y sin tildes: 'Ignorá' y 'ignora' matchean el mismo patrón."""
    text = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in text if not unicodedata.combining(c))


# --- Entrada ------------------------------------------------------------------

INJECTION_PATTERNS: dict[str, re.Pattern] = {
    "ignore_instructions": re.compile(
        r"(ignor|olvid|descart|omit|saltea|desobedec)\w*\b.{0,40}"
        r"(instruccion|regla|indicacion|directiva|prompt|orden)"
    ),
    "ignore_instructions_en": re.compile(
        r"\b(ignore|disregard|forget|override)\b.{0,40}\b(instructions?|rules|prompt|directives)\b"
    ),
    "reveal_prompt": re.compile(
        r"(revel|mostr|muestr|deci|deci|repet|copi|peg|imprim|escrib|traduc|translate|print|show|reveal|repeat|output)"
        r"\w*\b.{0,60}(system prompt|prompt del sistema|prompt de sistema|tus instrucciones|tu prompt|"
        r"el prompt|instrucciones (iniciales|del sistema|originales|internas)|mensaje del sistema|"
        r"your (instructions|prompt)|system message)"
    ),
    "role_override": re.compile(
        r"(a partir de ahora|desde ahora|de ahora en mas|from now on)\b.{0,40}"
        r"\b(sos|eres|seras|actua|responde|you are|act as)\b"
        r"|\b(actua|comportate|hace de cuenta|fingi|finge|simula)\w*\s+(como|que sos|que eres)\b"
    ),
    "jailbreak_keywords": re.compile(
        r"\b(jailbreak|dan mode|modo dan|developer mode|modo desarrollador|modo dios|god mode|"
        r"sin restricciones|sin filtros|no restrictions)\b|\bsos dan\b|\beres dan\b"
    ),
    "fake_system_tags": re.compile(
        r"<\s*/?\s*(system|assistant|sistema|instrucciones|consulta)\s*>|\[/?(system|inst)\]"
        r"|#{2,}\s*(system|sistema|instrucciones)"
    ),
    "forced_classification": re.compile(
        r"clasific\w*\s+(esto|este (mensaje|ticket)|la consulta|mi consulta)\s+como"
        r"|confidence\s*(=|:|de|en)?\s*(1(\.0+)?|100)\b"
    ),
}


@dataclass
class InputCheck:
    blocked: bool
    reason: str | None = None  # nombre del patrón o "too_long"


def check_input(query: str) -> InputCheck:
    if len(query) > MAX_QUERY_CHARS:
        return InputCheck(True, "too_long")
    text = normalize(query)
    for name, pattern in INJECTION_PATTERNS.items():
        if pattern.search(text):
            return InputCheck(True, name)
    return InputCheck(False)


def blocked_response(check: InputCheck) -> TriageResponse:
    """Respuesta segura ante una entrada bloqueada: cumple el contrato y deriva a un humano.

    confidence 0.0: la categoría no la decidió el modelo (no se lo llamó).
    """
    motivo = "mensaje demasiado largo" if check.reason == "too_long" else (
        f"posible intento de prompt injection ({check.reason})"
    )
    return TriageResponse(
        answer=(
            "No pudimos procesar tu mensaje de forma automática. Un agente de soporte lo va a "
            "revisar personalmente. Si tenés una consulta sobre Nubbix, contanos el problema "
            "con tus palabras."
        ),
        confidence=0.0,
        category="other",
        actions=[
            f"Revisión humana: entrada bloqueada por guardrail ({motivo})",
            "No responder automáticamente; verificar la intención del mensaje",
        ],
    )


# --- Salida -------------------------------------------------------------------

# Pedido de datos sensibles: un pedido DIRIGIDO AL CLIENTE ("nos confirmes", "envianos") +
# dato sensible cerca. "Un agente te enviará los pasos para cambiar tu contraseña" no es un
# pedido de datos (el verbo es del agente): por eso no alcanza con cualquier verbo.
_SENSITIVE_REQUEST = re.compile(
    r"(\bnos\s+(envies|envie|compartas|comparta|indiques|indique|confirmes|confirme|pases|pase|"
    r"digas|diga|proporciones|facilites|mandes|escribas|brindes)"
    r"|\b(envianos|compartinos|indicanos|confirmanos|pasanos|decinos|mandanos|escribinos|brindanos|"
    r"enviarnos|compartirnos|indicarnos|confirmarnos|pasarnos|decirnos|proporcionarnos|facilitarnos|"
    r"dame|decime|pasame|necesitamos|necesitaremos|necesito|solicitamos|ingresa aqui|escribi aca)\b)"
    r".{0,60}"
    r"(numero (completo )?de (la |tu )?tarjeta|datos de (la |tu )?tarjeta|digitos de (la |tu )?tarjeta|"
    r"ultimos \d+ digitos|cvv|cvc|codigo de seguridad|(tu|la|su) contrasena|(tu|la|su) clave|\bpin\b|"
    r"codigo de verificacion)"
)

# Promesas que el bot no puede garantizar.
_UNAUTHORIZED_PROMISES = re.compile(
    r"\b(te|le|les)\s+(vamos a |voy a )?(reintegr|devolv|reembols|bonific)\w*"
    r"|\bgarantiz\w*"
    r"|\ben (las )?(proximas )?\d+\s*(hs|horas|dias|minutos)\b"
    # Afirmar que algo YA se resolvió (el bot no ejecuta acciones). "He derivado tu caso" NO
    # se marca: es cierto (el triage deriva a un humano) y marcarlo generaba ruido.
    r"|\b(he|hemos)\s+(procesado|reintegrado|devuelto|corregido|solucionado|aplicado|acreditado|"
    r"reembolsado|anulado|cancelado)\b"
    r"|\bya\s+(te\s+)?(reintegramos|devolvimos|solucionamos|corregimos|acreditamos|reembolsamos)\b"
    r"|reintegro total|sin revisar"
)

# Marcadores estructurales del system prompt (aparecen en todas las versiones).
_PROMPT_MARKERS = ("## categorias", "## campos de la respuesta", "## formato de salida",
                   "## reglas de desempate", "user_template", "respondé unicamente con un objeto json")

SAFE_ANSWER = (
    "Recibimos tu consulta. Un agente de soporte la va a revisar y te va a responder por este "
    "medio. Por seguridad, nunca te vamos a pedir contraseñas ni datos completos de tarjetas."
)


@dataclass
class OutputCheck:
    response: TriageResponse
    blocked: list[str] = field(default_factory=list)  # motivos que reemplazaron el answer
    flagged: list[str] = field(default_factory=list)  # motivos marcados para revisión humana

    @property
    def triggered(self) -> bool:
        return bool(self.blocked or self.flagged)


def _prompt_lines(system_prompt: str) -> list[str]:
    """Líneas distintivas del system prompt (largas, para no dar falsos positivos)."""
    return [normalize(line.strip(" -")) for line in system_prompt.splitlines()
            if len(line.strip()) >= 45 and not line.strip().startswith(("Consulta:", "Respuesta:"))]


def leaks_prompt(text: str, system_prompt: str) -> bool:
    norm = normalize(text)
    return any(m in norm for m in _PROMPT_MARKERS) or any(
        line in norm for line in _prompt_lines(system_prompt)
    )


def _match_without_negation(pattern: re.Pattern, text: str) -> bool:
    """Como pattern.search, pero ignora coincidencias precedidas por 'no' / 'nunca'.

    "Nunca compartas tu contraseña" es un buen consejo, no un pedido de datos.
    """
    for m in pattern.finditer(text):
        before = text[max(0, m.start() - 12): m.start()]
        if not re.search(r"\b(no|nunca|jamas)\s+(\w+\s+)?$", before):
            return True
    return False


def asks_sensitive_data(text: str) -> bool:
    return _match_without_negation(_SENSITIVE_REQUEST, normalize(text))


def makes_unauthorized_promise(text: str) -> bool:
    return bool(_UNAUTHORIZED_PROMISES.search(normalize(text)))


def check_output(response: TriageResponse, system_prompt: str) -> OutputCheck:
    """Valida el CONTENIDO de una respuesta que ya cumplió la estructura."""
    full_text = " ".join([response.answer, *response.actions])
    blocked, flagged = [], []

    if leaks_prompt(full_text, system_prompt):
        blocked.append("prompt_leak")
    if asks_sensitive_data(response.answer):
        blocked.append("sensitive_data_request")
    if makes_unauthorized_promise(full_text):
        flagged.append("unauthorized_promise")

    if not (blocked or flagged):
        return OutputCheck(response)

    answer = SAFE_ANSWER if blocked else response.answer
    # Si hubo filtración, las acciones también pueden contenerla: se descartan.
    actions = [] if "prompt_leak" in blocked else list(response.actions)
    aviso = f"Revisión humana antes de enviar: guardrail de salida ({', '.join(blocked + flagged)})"
    actions = actions[:4] + [aviso]  # el contrato admite hasta 5 acciones
    safe = TriageResponse(
        answer=answer, confidence=response.confidence, category=response.category, actions=actions
    )
    return OutputCheck(safe, blocked, flagged)
