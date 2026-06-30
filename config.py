"""
Configuración central del bot.
Edita este archivo para ajustar el comportamiento sin tocar el código.
"""

from game.spell import SpellConfig

# ── Modo de prueba ─────────────────────────────────────────────────────────────
# True  → CombatAI loguea las acciones pero NO inyecta paquetes (seguro para testear)
# False → CombatAI inyecta paquetes reales (activa el bot)
DRY_RUN = True

# ── Servidores ────────────────────────────────────────────────────────────────
# IP directa — evita el bucle con el hosts file que redirige el hostname.
# Si cambia: nslookup dofusretro-co-production.ankama-games.com 8.8.8.8
REAL_LOGIN_HOST = "52.17.187.227"
REAL_LOGIN_PORT = 443

# ── Hechizos configurados ─────────────────────────────────────────────────────
# Añade aquí los hechizos de tu personaje.
# spell_id : ID numérico del hechizo (confirmar con el sniffer en Fase 0)
# ap_cost  : PA que consume
# min_range: alcance mínimo (0 = cuerpo a cuerpo posible)
# max_range: alcance máximo
# line_of_sight: True si requiere línea de visión
SPELLS: list[SpellConfig] = [
    # Zarzas Múltiples nivel 5 — Sadida — confirmado con sniffer 2026-06-27
    # GA;300 muestra spell_id=191, ap_cost=5, rango 1-4, sin línea de visión requerida
    # slot_key="2" confirmado por pantallazo: slot 2 de la barra de acciones inferior
    SpellConfig(spell_id="191", ap_cost=5, min_range=1, max_range=9, line_of_sight=False, slot_key="2"),
]

# ── Estrategia de selección de objetivo ───────────────────────────────────────
# "nearest"   → atacar al enemigo más cercano
# "lowest_hp" → atacar al enemigo con menos HP
TARGET_STRATEGY = "nearest"

# ── Stats por defecto (si el servidor no los ha enviado aún vía As) ──────────
# Ajusta según tu clase/nivel. Se usan solo como fallback hasta recibir As.
DEFAULT_AP = 6   # Sadida base
DEFAULT_MP = 3   # Sadida base

# ── Input por clicks (actuador MITM híbrido) ─────────────────────────────────
# El bot no puede inyectar paquetes C→S (cifrados por Shield AES-256-CBC).
# En su lugar simula inputs reales sobre el cliente.

# Subcadena del título de la ventana de Dofus para auto-detección.
# Título real: "Rufyzos - Dofus Retro v1.48.16"
WINDOW_TITLE_SUBSTR = "Dofus Retro"

# Origen del mapa isométrico en coordenadas cliente (px).
# Calibrado para 2560x1440 @ 100% escala de pantalla.
# Recalibrar con: python tools/calibrate.py --fit  (>=5 celdas, minimos cuadrados)
# Verificar:      python tools/calibrate.py --verify
# Cursor visual:  python tools/calibrate.py <cell_id> [...]
MAP_ORIGIN_X: float = 76.562  # client_x celda 0 (rect.left=0), modelo isométrico canónico
MAP_ORIGIN_Y: float =  4.727  # client_y celda 0 (rect.top=23),  modelo isométrico canónico
MAP_SCALE_X:  float = 1.0     # escala extra (constantes en coords.py absorben el zoom)
MAP_SCALE_Y:  float = 1.0
MAP_SCALE:    float = 1.0

# Tecla para pasar turno (Enter o Tab en Dofus Retro por defecto).
# Confirmar en configuración de atajos del cliente.
PASS_TURN_KEY = "enter"

# Tecla del botón "Listo" en la fase de placement (mismo que pasar turno en Dofus Retro).
READY_KEY = "enter"

# ms entre elegir celda de placement y hacer click / marcar listo
DELAY_PLACEMENT_MS = 700

# ms entre pulsar la tecla del slot y hacer click en la celda
DELAY_SPELL_SELECT_MS = 250

# ── Navegación de mundo ───────────────────────────────────────────────────────
# BD de celdas por mapa (JSON). Si no existe, se usa fallback todo-transitable.
MAP_DB_PATH      = "data/maps.json"
# Grafo de conexiones entre mapas (se construye automáticamente por observación).
WORLD_GRAPH_PATH = "data/world_graph.json"
# Ruta scripted (lista de pasos). Vacía = bot no navega automáticamente.
# Ejemplo: [{"map": "123456", "exit_cell": 452}, {"map": "654321", "exit_cell": 100}]
ROUTES: list[dict] = []

# ── HDV (Hôtel de Vente) ─────────────────────────────────────────────────────
# Estrategia de precio: "middle_pct" (recomendado), "-1kama", "fixed"
HDV_PRICE_STRATEGY = "middle_pct"
# Para "middle_pct": vender al X% del precio medio (0.95 = 95%)
HDV_MIDDLE_PCT = 0.95
# Para "fixed": diccionario model_id → precio base (por unidad)
HDV_FIXED_PRICES: dict = {}
# Pods máximos antes de ir a HDV/banco (fracción 0.0–1.0)
HDV_PODS_THRESHOLD = 0.85

# ── Arquetipo de IA de combate ────────────────────────────────────────────────
# "ranged"   → distancia/kiting (Cra, Sadida ofensivo…)
# "melee"    → cuerpo a cuerpo (Iop, Sacrieur…)
# "support"  → curador/buffer (Eniripsa, Feca…)
# "summoner" → invocador (Osamodas, Sadida invocador…)
ARCHETYPE = "ranged"

# Distancia mínima de seguridad para arquetipo ranged (kiting)
SAFE_DIST = 2

# Umbral de HP para curación del arquetipo support (0.0–1.0)
HEAL_THRESHOLD = 0.6

# Número máximo de invocaciones simultáneas (arquetipo summoner)
MAX_SUMMONS = 3

# ── Delays anti-detección (milisegundos) ─────────────────────────────────────
DELAY_CAST_MS      = 600    # Entre casts
DELAY_MOVE_MS      = 400    # Movimiento en combate
DELAY_PASS_TURN_MS = 800    # Antes de pasar turno
DELAY_JITTER       = 0.30   # ± 30% de variación aleatoria

# ── Watchdog de turno ─────────────────────────────────────────────────────────
# Segundos máximos por turno antes de forzar pass_turn (Dofus timeout ≈ 30s).
TURN_TIMEOUT_S = 25

# ── Descansos mid-sesión (anti-detección) ─────────────────────────────────────
# Intervalo aleatorio entre descansos (minutos). Paper arXiv 2508.20578:
# los humanos paran ~cada 20-40 min; los bots nunca — señal primaria.
BOT_BREAK_INTERVAL_MIN = (18, 42)
# Duración del descanso (segundos): de 1.5 min a 8 min.
BOT_BREAK_DURATION_S   = (90, 480)
