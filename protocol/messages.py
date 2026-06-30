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
GS   = "GS"    # S→C  GameStartToPlay — empieza el combate real (tras GR de todos)
GJ   = "GJ"    # S→C  GameJoin — personaje entra en combate; llega ANTES de GIC
                #        Formato: GJ<fighter_id>|<team>|<cell>|<is_solo>|<challenge_id>
GP   = "GP"    # S→C  GamePositionStart — celdas de inicio disponibles para placement
                #        Formato: GP<cell1>|<cell2>|...  (celdas de tu equipo disponibles)
Gp   = "Gp"    # C→S  GameSetPlayerPosition — elegir celda de inicio en placement
                #        Formato: Gp<cell_id>
GR   = "GR"    # C→S  GameRequestReady — marcar listo (fin de placement)
                #        Formato: GR  (sin cuerpo)
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

# ── Inventario / objetos ───────────────────────────────────────────────────────
OAK  = "OAK"   # S→C  Objeto añadido al inventario
OR   = "OR"    # S→C  Objeto eliminado del inventario
OQ   = "OQ"    # S→C  Cambio de cantidad de objeto
Ow   = "Ow"    # S→C  Peso/pods del inventario

# ── Diálogos PNJ ──────────────────────────────────────────────────────────────
DC   = "DC"    # C→S  Iniciar diálogo con PNJ
DCK  = "DCK"   # S→C  Diálogo creado (éxito)
DCE  = "DCE"   # S→C  Diálogo error
DQ   = "DQ"    # S→C  Pregunta/opciones del PNJ
DR   = "DR"    # C→S  Respuesta del jugador
DV   = "DV"    # C↔S  Salir del diálogo

# ── HDV (Exchange big-store) ──────────────────────────────────────────────────
EHT  = "EHT"   # C→S  Seleccionar tipo/categoría de HDV
EHL  = "EHL"   # S→C  Lista de tipos de ítems en HDV
EHl  = "EHl"   # C→S/S→C  Pedir/recibir lotes de un ítem concreto
EHP  = "EHP"   # C→S/S→C  Pedir/recibir precio medio de un ítem
EHB  = "EHB"   # C→S  Comprar lote en HDV
EHS  = "EHS"   # C→S  Buscar ítem en HDV
EHSK = "EHSK"  # S→C  Resultado de búsqueda en HDV (éxito)
EHSE = "EHSE"  # S→C  Resultado de búsqueda en HDV (error)
ES   = "ES"    # C→S  Poner en venta (ExchangeMovementSell)
ESK  = "ESK"   # S→C  Venta exitosa
ESE  = "ESE"   # S→C  Error en venta
EBK  = "EBK"   # S→C  Compra exitosa
EBE  = "EBE"   # S→C  Error en compra
EV   = "EV"    # C→S  Salir de intercambio/HDV

# Cast de hechizo (C→S): GA<seq>\n<spell_id>;<cell_id>\n\x00
CAST_SPELL  = "GA"
FIGHT_END   = "GE"
FIGHT_START = "GS"   # GS = GameStartToPlay — inicio real del combate


# ── Parsers ───────────────────────────────────────────────────────────────────

# Headers conocidos, ordenados por longitud descendente para hacer matching por
# prefijo (el más largo que case gana). Esto evita el bug de partir mal headers
# de 2 letras seguidos de dígitos: 'As9739192...' debe dar header 'As', no 'As9'.
# Importante: en Dofus Retro el cuerpo de muchos paquetes de combate empieza por
# dígitos pegados al header (p.ej. 'GTS2264765|...' → header 'GTS', campo '2264765').
_KNOWN_HEADERS = sorted(
    {
        # Login
        "HC", "AH", "AYK", "AX", "AxK", "Adz", "Ac", "AQW", "Ap", "Ai",
        "AlK", "AlE", "ALK", "AS", "ASK", "ASE", "AT", "ATK", "ATE", "AV", "Af",
        # Mundo
        "GCK", "GDM", "BT", "fC", "GM", "GA", "GDK", "EW",
        # Combate
        "GS", "GJ", "GP", "Gp", "GR", "GIC", "GTL", "GTS", "GTF", "GIE",
        "GT", "Gt", "GE", "GJK", "GPc", "GTM", "GTR", "GAS", "GAF", "GA0",
        "As", "GdOK", "Gd", "SC", "ILF", "ILS", "BN",
        # Oficios / inventario
        "JS", "JX", "JO", "jO", "OAK", "OR", "OQ", "Ow",
        # Diálogos
        "DC", "DCK", "DCE", "DQ", "DR", "DV",
        # HDV
        "EHT", "EHL", "EHl", "EHP", "EHB", "EHS", "EHSK", "EHSE",
        "ES", "ESK", "ESE", "EBK", "EBE", "EV",
    },
    key=len, reverse=True,
)


def parse(raw: str) -> tuple[str, list[str]]:
    """
    Extrae (header, fields) de un paquete crudo.

    El header se identifica por prefijo contra _KNOWN_HEADERS (el más largo que
    case). El resto del paquete son los campos, separados por '|'. Si ningún
    header conocido casa, se usa el fallback de letras iniciales (2-3 chars).
    """
    if len(raw) < 2:
        return raw, []

    hdr = None
    for h in _KNOWN_HEADERS:
        if raw.startswith(h):
            hdr = h
            break

    if hdr is None:
        # Fallback: tomar las letras iniciales (no dígitos) como header.
        i = 0
        while i < len(raw) and not raw[i].isdigit() and raw[i] not in "|;":
            i += 1
        hdr = raw[:i] if i > 0 else raw[:2]

    rest = raw[len(hdr):]
    if rest.startswith("|"):
        rest = rest[1:]
    fields = rest.split("|") if rest else []
    return hdr, fields


def header_of(raw: str) -> str:
    hdr, _ = parse(raw)
    return hdr


def fields_of(raw: str) -> list[str]:
    _, f = parse(raw)
    return f
