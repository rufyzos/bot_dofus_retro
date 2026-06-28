"""
Configuración central del bot.
Edita este archivo para ajustar el comportamiento sin tocar el código.
"""

from game.spell import SpellConfig

# ── Modo de prueba ─────────────────────────────────────────────────────────────
# True  → CombatAI loguea las acciones pero NO inyecta paquetes (seguro para testear)
# False → CombatAI inyecta paquetes reales (activa el bot)
DRY_RUN = True

# ── Servidores (solo cambiar si usas un server privado) ───────────────────────
REAL_LOGIN_HOST = "co.retro.dofus.com"
REAL_LOGIN_PORT = 5555

# ── Hechizos configurados ─────────────────────────────────────────────────────
# Añade aquí los hechizos de tu personaje.
# spell_id : ID numérico del hechizo (confirmar con el sniffer en Fase 0)
# ap_cost  : PA que consume
# min_range: alcance mínimo (0 = cuerpo a cuerpo posible)
# max_range: alcance máximo
# line_of_sight: True si requiere línea de visión
SPELLS: list[SpellConfig] = [
    SpellConfig(spell_id="3",  ap_cost=4, min_range=1, max_range=3),   # Ejemplo: hechizo 1
    SpellConfig(spell_id="6",  ap_cost=3, min_range=1, max_range=4),   # Ejemplo: hechizo 2
    SpellConfig(spell_id="13", ap_cost=2, min_range=0, max_range=1),   # Ejemplo: cuerpo a cuerpo
]

# ── Estrategia de selección de objetivo ───────────────────────────────────────
# "nearest"   → atacar al enemigo más cercano
# "lowest_hp" → atacar al enemigo con menos HP
TARGET_STRATEGY = "nearest"

# ── Delays anti-detección (milisegundos) ─────────────────────────────────────
DELAY_CAST_MS      = 600    # Entre casts
DELAY_MOVE_MS      = 400    # Movimiento en combate
DELAY_PASS_TURN_MS = 800    # Antes de pasar turno
DELAY_JITTER       = 0.30   # ± 30% de variación aleatoria
