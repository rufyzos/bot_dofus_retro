"""
Headers de protocolo de Dofus Retro — confirmados con sniffer MITM el 2026-06-27.

Fuente de referencia: https://github.com/kralamoure/retroproto
"""

# ── Login server ──────────────────────────────────────────────────────────────
HC   = "HC"    # S→C  HelloConnect (salt)
AH   = "AH"    # S→C  Lista de servidores con estado (AH0 = lista, campos: id;estado;jugadores;completado)
AYK  = "AYK"   # S→C  Server seleccionado — host:port;ticket  (NO AXK — confirmado)
AX   = "AX"    # C→S  Seleccionar servidor (AX<server_id>)
AxK  = "AxK"   # S→C  Confirmación selección servidor (AxK<n>|id1,rank1|id2,rank2…)
Adz  = "Adz"   # S→C  Nombre de cuenta (Adzo|<nombre>)
Ac   = "Ac"    # S→C  Comunidad / tipo de cuenta (Ac4)
AQW  = "AQW"   # S→C  Pregunta de seguridad
Ap   = "Ap"    # C→S  Respuesta servidor inicial (Ap<n>|<subtipo>)
Ai   = "Ai"    # C→S  Credencial / password cifrado
AlK  = "AlK"   # S→C  Login OK (AlK0)
AlE  = "AlE"   # S→C  Login error
ALK  = "ALK"   # S→C  Lista de personajes (ALK<n>|id1;nombre;nivel;…)
AS   = "AS"    # C→S  Seleccionar personaje (AS<id>)
ASK  = "ASK"   # S→C  Personaje seleccionado OK (con stats completos)
ASE  = "ASE"   # S→C  Personaje seleccionado — error
AT   = "AT"    # C→S  Enviar ticket al game server (segunda conexión)
ATK  = "ATK"   # S→C  Ticket aceptado
ATE  = "ATE"   # S→C  Ticket rechazado
AV   = "AV"    # C→S / S→C  Versión (handshake game server)
Af   = "Af"    # Bidireccional  Estado de cola

# ── Game server — entrada al mundo ───────────────────────────────────────────
GCK  = "GCK"   # S→C  GameCreate OK — entrada al mundo (GCK|<n>|<nombre>)
GDM  = "GDM"   # S→C  Datos del mapa (id + key cifrado)
BT   = "BT"    # S→C  Timestamp del servidor
fC   = "fC"    # S→C  Fin de carga del mapa

# ── Game server — mundo ───────────────────────────────────────────────────────
GM   = "GM"    # S→C  Actores en el mapa (+actor = aparece, -id = desaparece)
GA   = "GA"    # Bidireccional — acción de juego
GDK  = "GDK"   # S→C  Fin de carga de actores del mapa
EW   = "EW"    # S→C  Objetos equipados del personaje

# ── Game server — combate ─────────────────────────────────────────────────────
GS   = "GS"    # S→C  GameStartToPlay — empieza el combate
GJ   = "GJ"    # S→C  GameJoin — unirse a combate
GR   = "GR"    # C↔S  GameRequestReady/GameReady — marcar listo (pre-combate)
GIC  = "GIC"   # S→C  GamePlayersCoordinates — coordenadas de fighters en combate
GTL  = "GTL"   # S→C  GameTurnList — orden de turnos (lista de fighter_ids)
GTS  = "GTS"   # S→C  GameTurnStart — comienza el turno del fighter con id dado
GTF  = "GTF"   # S→C  GameTurnFinish — turno terminado
GIE  = "GIE"   # S→C  GameEffect — efecto aplicado (daño, buff, muerte…)
GT   = "GT"    # C→S  Cliente acusa turno recibido (acknowledge)
Gt   = "Gt"    # C→S  Cliente termina su turno (pass turn) — formato: Gt\n\x00
GE   = "GE"    # S→C  GameEnd — Fin de combate

# Oficios (NO son paquetes de combate — confusión anterior)
JS   = "JS"    # S→C  JobSkills — habilidades de oficio
JX   = "JX"    # S→C  JobXP — experiencia de oficio
JO   = "JO"    # S→C  JobChangeStats — opciones de oficio

# Cast de hechizo (C→S): GA<seq>\n<spell_id>;<cell_id>\n\x00
CAST_SPELL  = "GA"
FIGHT_END   = "GE"
FIGHT_START = "GS"   # GS = GameStartToPlay — inicio real del combate


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
