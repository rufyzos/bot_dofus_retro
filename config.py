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
    SpellConfig(spell_id="191", ap_cost=5, min_range=1, max_range=9, line_of_sight=False),
]

# ── Estrategia de selección de objetivo ───────────────────────────────────────
# "nearest"   → atacar al enemigo más cercano
# "lowest_hp" → atacar al enemigo con menos HP
TARGET_STRATEGY = "nearest"

# ── Stats por defecto (si el servidor no los ha enviado aún vía As) ──────────
# Ajusta según tu clase/nivel. Se usan solo como fallback hasta recibir As.
DEFAULT_AP = 6   # Sadida base
DEFAULT_MP = 3   # Sadida base

# ── Delays anti-detección (milisegundos) ─────────────────────────────────────
DELAY_CAST_MS      = 600    # Entre casts
DELAY_MOVE_MS      = 400    # Movimiento en combate
DELAY_PASS_TURN_MS = 800    # Antes de pasar turno
DELAY_JITTER       = 0.30   # ± 30% de variación aleatoria
