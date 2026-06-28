"""
ClickActuator — ejecuta acciones de combate simulando input real al cliente.

En vez de inyectar paquetes C→S (cifrados por Shield), el actuador:
  1. Pulsa la tecla de atajo del slot del hechizo.
  2. Mueve el ratón al centro de la celda objetivo y hace click.
  3. Para pasar turno, pulsa la tecla configurada (por defecto espacio/Tab).

La lógica de combate (qué hechizo, qué celda) sigue siendo de CombatAI.
Este módulo es solo el "brazo" que ejecuta físicamente en la ventana.
"""

from __future__ import annotations
import time

import pyautogui

import config
from input.window import WindowRect, find_dofus_window
from input.coords import cell_to_screen
from utils.timing import human_delay

# Desactiva el failsafe de pyautogui (mover a esquina superior izquierda)
# para evitar abortos accidentales durante el combate.
pyautogui.FAILSAFE = False
# Velocidad de movimiento del ratón (segundos); 0 = instantáneo.
# Un valor pequeño (0.05-0.1) es más natural.
pyautogui.PAUSE = 0.0


class ClickActuator:
    def __init__(self):
        self._rect: WindowRect | None = None
        self._rect_ts: float = 0.0
        # TTL de caché del rect de ventana (segundos).
        # Después de TTL vuelve a buscar la ventana por si se movió.
        self._rect_ttl = 5.0

    # ------------------------------------------------------------------
    # Detección de ventana
    # ------------------------------------------------------------------

    def _ensure_window(self) -> WindowRect:
        now = time.monotonic()
        if self._rect is None or (now - self._rect_ts) > self._rect_ttl:
            self._rect = find_dofus_window(config.WINDOW_TITLE_SUBSTR)
            self._rect_ts = now
        return self._rect

    def invalidate_window(self):
        """Fuerza re-detección de ventana en la próxima acción."""
        self._rect = None

    # ------------------------------------------------------------------
    # Acciones de combate
    # ------------------------------------------------------------------

    def cast_spell(self, slot_key: str, target_cell: int):
        """
        Castea el hechizo del slot `slot_key` sobre la celda `target_cell`.
        Si DRY_RUN, solo loguea — no mueve el ratón ni pulsa teclas.
        """
        rect = self._ensure_window()
        px, py = cell_to_screen(
            target_cell, rect,
            config.MAP_ORIGIN_X, config.MAP_ORIGIN_Y, config.MAP_SCALE,
            scale_x=config.MAP_SCALE_X, scale_y=config.MAP_SCALE_Y,
        )

        if config.DRY_RUN:
            print(f"[Actuator DRY_RUN] cast slot={slot_key} cell={target_cell} → píxel ({px},{py})")
            return

        print(f"[Actuator] Seleccionar hechizo slot={slot_key}")
        pyautogui.press(slot_key)
        human_delay(config.DELAY_SPELL_SELECT_MS, config.DELAY_JITTER)

        print(f"[Actuator] Click en cell={target_cell} → ({px},{py})")
        pyautogui.moveTo(px, py, duration=0.08)
        pyautogui.click()

    def pass_turn(self):
        """
        Pasa el turno. Usa la tecla configurada en PASS_TURN_KEY.
        Si DRY_RUN, solo loguea.
        """
        if config.DRY_RUN:
            print(f"[Actuator DRY_RUN] pass_turn (tecla '{config.PASS_TURN_KEY}')")
            return

        print(f"[Actuator] Pasar turno (tecla '{config.PASS_TURN_KEY}')")
        pyautogui.press(config.PASS_TURN_KEY)

    def move_to(self, cell: int):
        """
        Mueve el personaje haciendo click en la celda destino.
        El cliente calcula y firma el GA de movimiento — no inyectamos nada.
        """
        rect = self._ensure_window()
        px, py = cell_to_screen(
            cell, rect,
            config.MAP_ORIGIN_X, config.MAP_ORIGIN_Y, config.MAP_SCALE,
            scale_x=config.MAP_SCALE_X, scale_y=config.MAP_SCALE_Y,
        )

        if config.DRY_RUN:
            print(f"[Actuator DRY_RUN] move_to cell={cell} → píxel ({px},{py})")
            return

        print(f"[Actuator] Click movimiento cell={cell} → ({px},{py})")
        pyautogui.moveTo(px, py, duration=0.06)
        pyautogui.click()
