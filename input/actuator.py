"""
ClickActuator — ejecuta acciones de combate simulando input real al cliente.

En vez de inyectar paquetes C→S (cifrados por Shield), el actuador:
  1. Pulsa la tecla de atajo del slot del hechizo.
  2. Mueve el ratón al centro de la celda objetivo y hace click.
  3. Para pasar turno, pulsa la tecla configurada (por defecto espacio/Tab).

La lógica de combate (qué hechizo, qué celda) sigue siendo de CombatAI.
Este módulo es solo el "brazo" que ejecuta físicamente en la ventana.

MOVIMIENTO BÉZIER:
  En lugar de moveTo lineal (señal clara de bot), _move_bezier genera una
  trayectoria cúbica con dos puntos de control aleatorios que producen el
  arco natural de un ratón humano:
    - Aceleración inicial lenta → pico de velocidad → deceleración al llegar.
    - Puntos de control desplazados perpendicularmente al eje de movimiento.
    - Número de pasos y duración con jitter individual por movimiento.
  Basado en el análisis del paper DMTG (arXiv 2410.18233) sobre propiedades
  de trayectorias humanas.
"""

from __future__ import annotations
import math
import random
import time

import pyautogui

import config
from input.window import WindowRect, find_dofus_window
from input.coords import cell_to_screen
from utils.timing import human_delay

pyautogui.FAILSAFE = False
pyautogui.PAUSE = 0.0


def _move_bezier(x1: int, y1: int, x2: int, y2: int,
                 duration: float | None = None) -> None:
    """
    Mueve el ratón de (x1,y1) a (x2,y2) siguiendo una curva de Bézier cúbica.

    Los dos puntos de control se colocan en posiciones aleatorias a lo largo
    del recorrido, desplazados perpendicularmente para crear el arco natural.
    La duración y el número de pasos varían con jitter para no ser periódicos.
    """
    if duration is None:
        # Duración proporcional a la distancia, con jitter ±25%
        dist = math.hypot(x2 - x1, y2 - y1)
        base = 0.04 + dist * 0.00035          # ~40ms base + ~0.35ms por píxel
        jitter = random.uniform(-0.25, 0.25)
        duration = max(0.04, base * (1 + jitter))

    # Vector perpendicular unitario para los puntos de control
    dx, dy = x2 - x1, y2 - y1
    length = math.hypot(dx, dy) or 1.0
    perp_x, perp_y = -dy / length, dx / length

    # Magnitud del desplazamiento perpendicular (±10–35% de la distancia)
    dev = length * random.uniform(0.10, 0.35) * random.choice([-1, 1])

    # Puntos de control en ~30% y ~70% del recorrido, desviados lateralmente
    cp1_x = x1 + dx * random.uniform(0.25, 0.40) + perp_x * dev * random.uniform(0.5, 1.0)
    cp1_y = y1 + dy * random.uniform(0.25, 0.40) + perp_y * dev * random.uniform(0.5, 1.0)
    cp2_x = x1 + dx * random.uniform(0.60, 0.75) + perp_x * dev * random.uniform(0.5, 1.0)
    cp2_y = y1 + dy * random.uniform(0.60, 0.75) + perp_y * dev * random.uniform(0.5, 1.0)

    # Número de pasos: más pasos = más suave, con jitter para no ser fijo
    steps = max(8, int(duration * random.uniform(55, 75)))
    sleep_per_step = duration / steps

    for i in range(steps + 1):
        t = i / steps
        # Bézier cúbica: B(t) = (1-t)³P0 + 3(1-t)²tP1 + 3(1-t)t²P2 + t³P3
        mt = 1 - t
        px = (mt**3 * x1
              + 3 * mt**2 * t * cp1_x
              + 3 * mt * t**2 * cp2_x
              + t**3 * x2)
        py = (mt**3 * y1
              + 3 * mt**2 * t * cp1_y
              + 3 * mt * t**2 * cp2_y
              + t**3 * y2)
        # Micro-jitter por paso (~0-1px) que simula temblor de mano
        if i > 0 and i < steps:
            px += random.gauss(0, 0.4)
            py += random.gauss(0, 0.4)
        pyautogui.moveTo(int(px), int(py))
        if i < steps:
            time.sleep(sleep_per_step)



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

        # Descartar si el pixel cae fuera del area cliente (calibracion incorrecta)
        if not (rect.left <= px < rect.left + rect.width and
                rect.top  <= py < rect.top  + rect.height):
            print(f"[Actuator] AVISO: celda {target_cell} -> ({px},{py}) fuera de ventana. "
                  f"Recalibra con: python tools/calibrate.py --fit")
            return

        if config.DRY_RUN:
            print(f"[Actuator DRY_RUN] cast slot={slot_key} cell={target_cell} → píxel ({px},{py})")
            return

        print(f"[Actuator] Seleccionar hechizo slot={slot_key}")
        pyautogui.press(slot_key)
        human_delay(config.DELAY_SPELL_SELECT_MS, config.DELAY_JITTER)

        print(f"[Actuator] Click en cell={target_cell} → ({px},{py})")
        cx, cy = pyautogui.position()
        _move_bezier(cx, cy, px, py)
        pyautogui.click()

    def set_placement_cell(self, cell: int):
        """
        Fase de placement: click en la celda de inicio elegida.
        Envía Gp<cell> al servidor (el cliente firma el paquete automáticamente
        al detectar el click en la celda de placement).
        """
        rect = self._ensure_window()
        px, py = cell_to_screen(
            cell, rect,
            config.MAP_ORIGIN_X, config.MAP_ORIGIN_Y, config.MAP_SCALE,
            scale_x=config.MAP_SCALE_X, scale_y=config.MAP_SCALE_Y,
        )
        if config.DRY_RUN:
            print(f"[Actuator DRY_RUN] placement cell={cell} → píxel ({px},{py})")
            return
        print(f"[Actuator] Placement: click cell={cell} → ({px},{py})")
        cx, cy = pyautogui.position()
        _move_bezier(cx, cy, px, py)
        pyautogui.click()

    def ready(self):
        """
        Marca listo en placement (GR). En el cliente de Dofus Retro el botón
        de listo es la tecla ENTER o un botón visible — usamos PASS_TURN_KEY
        que el usuario configura para esa función.
        """
        if config.DRY_RUN:
            print("[Actuator DRY_RUN] ready (GR)")
            return
        print("[Actuator] Ready (GR)")
        pyautogui.press(getattr(config, "READY_KEY", config.PASS_TURN_KEY))

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
        cx, cy = pyautogui.position()
        _move_bezier(cx, cy, px, py)
        pyautogui.click()
