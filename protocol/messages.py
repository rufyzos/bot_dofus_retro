"""
Headers de protocolo de Dofus Retro verificados contra retroproto/retroproxy.

IMPORTANTE — Fase 0:
  Los headers marcados con [CONFIRMAR] son los que el sniffer (tools/sniffer.py)
  DEBE confirmar antes de que CombatAI los use. Captura una pelea real con el
  sniffer y actualiza las constantes y los parsers de este módulo.

Fuente de referencia: https://github.com/kralamoure/retroproto
"""

# ── Login server ──────────────────────────────────────────────────────────────
HC   = "HC"    # S→C  HelloConnect (salt para cifrado de password)
ALK  = "ALK"   # S→C  Lista de personajes OK
ALE  = "ALE"   # S→C  Lista de personajes — error
AlK  = "AlK"   # S→C  Login OK
AlE  = "AlE"   # S→C  Login error (subtipos: AlEf, AlEa, AlEv, AlEb…)
AX   = "AX"    # C→S  Seleccionar servidor
AXK  = "AXK"   # S→C  Server seleccionado (contiene IP:puerto del game server + ticket)
AS   = "AS"    # C→S  Seleccionar personaje
ASK  = "ASK"   # S→C  Personaje seleccionado OK
ASE  = "ASE"   # S→C  Personaje seleccionado — error
AT   = "AT"    # C→S  Enviar ticket al game server (segunda conexión)
ATK  = "ATK"   # S→C  Ticket aceptado
ATE  = "ATE"   # S→C  Ticket rechazado

# ── Game server — entrada al juego ────────────────────────────────────────────
GC   = "GC"    # C→S  GameCreate (entrar al mundo)
GCK  = "GCK"   # S→C  GameCreate OK

# ── Game server — mundo ───────────────────────────────────────────────────────
GM   = "GM"    # S→C  Movimiento de actores en el mapa
GA   = "GA"    # Bidireccional — acciones de juego (incluye interacción con celdas)
Im   = "Im"    # S→C  Mensaje informativo del servidor

# ── Game server — combate ─────────────────────────────────────────────────────
GTS  = "GTS"   # S→C  Turn Start — comienza el turno del fighter con id dado
GTF  = "GTF"   # S→C  Turn Finish — turno terminado
GT   = "GT"    # C→S  Cliente acusa turno recibido (acknowledge)
Gt   = "Gt"    # C→S  Cliente termina su turno (pass turn)
GAS  = "GAS"   # S→C  Inicio de fase de acciones

# Los siguientes DEBEN confirmarse con el sniffer (Fase 0) ───────────────────
# Header para que el cliente castee un hechizo:
CAST_SPELL   = "GA"    # [CONFIRMAR] — probablemente "GA" con acción específica
# Header de fin de combate:
FIGHT_END    = "GE"    # [CONFIRMAR]
# Header de inicio de combate / entrar en fight:
FIGHT_START  = "GJK"   # [CONFIRMAR]


# ── Parsers ───────────────────────────────────────────────────────────────────

def parse(raw: str) -> tuple[str, list[str]]:
    """Extrae (header, fields) de un paquete crudo. Header = primeros 2-3 chars."""
    if len(raw) < 2:
        return raw, []
    # Probar header de 3 chars primero (e.g. ALK, GTS, ATK…)
    for hlen in (3, 2):
        hdr = raw[:hlen]
        rest = raw[hlen:]
        if rest.startswith("|"):
            rest = rest[1:]
        fields = rest.split("|") if rest else []
        # Heurística: si el header son letras/dígitos conocidos, aceptarlo
        if hdr.isalnum() or (len(hdr) == 2 and hdr[0].isupper()):
            return hdr, fields
    return raw[:2], raw[3:].split("|")


def header_of(raw: str) -> str:
    hdr, _ = parse(raw)
    return hdr


def fields_of(raw: str) -> list[str]:
    _, f = parse(raw)
    return f
