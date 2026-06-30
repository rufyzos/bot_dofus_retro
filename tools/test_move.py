"""
Prueba aislada de movimiento a una celda (Fase 1 del plan de validación).

Aísla `ClickActuator.move_to(cell)` del A* / grafo de mundo / espera de GDM:
le pasas uno o varios cell_id y, para cada uno, calcula el píxel con la
calibración ya validada (config.MAP_ORIGIN_*) y hace el CLICK REAL para que
el personaje camine a esa celda. El cliente real calcula y firma el GA de
movimiento — el script nunca inyecta paquetes (cumple la regla MITM).

Es el espejo de `tools/calibrate.py <cell>` (que solo MUEVE el cursor) pero
este HACE CLICK para provocar el movimiento.

Uso (con Dofus abierto, personaje en un mapa, ventana visible):

    python tools/test_move.py 256                 # un destino
    python tools/test_move.py 256 270 285         # secuencia
    python tools/test_move.py --force 256         # click real aunque DRY_RUN=True
    python tools/test_move.py --delay 5 256       # 5s de cuenta atrás inicial

Notas:
  - El movimiento real requiere config.DRY_RUN=False (en DRY_RUN move_to solo
    loguea el píxel). Usa --force para forzar el click sin tocar config.py.
  - La calibración actual es de la vista de COMBATE. Si el personaje aterriza
    desplazado de forma consistente, la vista de mundo necesita su propio
    origen (MAP_ORIGIN_WORLD_*) — ver el plan, Fase 1.
"""

from __future__ import annotations
import argparse
import sys
import time
from pathlib import Path

# Permite ejecutar desde tools/ o desde Bot/ (imports absolutos desde Bot/).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import utils.console  # noqa: F401 — fuerza UTF-8 en stdout
import config
from input.actuator import ClickActuator
from input.coords import cell_to_screen
from utils.timing import human_delay


def _preview_pixels(actuator: ClickActuator, cells: list[int]) -> None:
    """Imprime el píxel destino de cada celda (sin clickar)."""
    rect = actuator._ensure_window()
    print(f"[test_move] Ventana Dofus: left={rect.left} top={rect.top} "
          f"w={rect.width} h={rect.height}")
    for cell in cells:
        px, py = cell_to_screen(
            cell, rect,
            config.MAP_ORIGIN_X, config.MAP_ORIGIN_Y, config.MAP_SCALE,
            scale_x=config.MAP_SCALE_X, scale_y=config.MAP_SCALE_Y,
        )
        inside = rect.left <= px <= rect.left + rect.width and \
                 rect.top <= py <= rect.top + rect.height
        flag = "OK" if inside else "FUERA DE VENTANA"
        print(f"[test_move]   cell {cell:>4} -> pixel ({px}, {py})  [{flag}]")


def main() -> int:
    parser = argparse.ArgumentParser(description="Prueba de movimiento a celda(s).")
    parser.add_argument("cells", nargs="+", type=int, help="cell_id(s) destino")
    parser.add_argument("--force", action="store_true",
                        help="hacer el click real aunque config.DRY_RUN sea True")
    parser.add_argument("--delay", type=float, default=4.0,
                        help="segundos de cuenta atrás antes del primer click")
    args = parser.parse_args()

    actuator = ClickActuator()

    # 1. Vista previa de píxeles — siempre, sirve para cotejar con calibrate.py.
    try:
        _preview_pixels(actuator, args.cells)
    except Exception as exc:
        print(f"[test_move] ERROR detectando ventana / calculando píxel: {exc}")
        print("[test_move] ¿Está Dofus abierto y visible? "
              f"(WINDOW_TITLE_SUBSTR='{config.WINDOW_TITLE_SUBSTR}')")
        return 1

    will_click = (not config.DRY_RUN) or args.force
    if not will_click:
        print("[test_move] DRY_RUN=True y sin --force: solo vista previa, NO se "
              "hará click. Usa --force o pon DRY_RUN=False para mover de verdad.")
        return 0

    # 2. --force tiene que saltarse el guard DRY_RUN de move_to.
    if args.force and config.DRY_RUN:
        print("[test_move] --force activo: forzando click real (DRY_RUN sigue True "
              "en config, no se toca).")
        config.DRY_RUN = False  # override en memoria, solo para este proceso

    # 3. Cuenta atrás para que el usuario ponga Dofus en foco.
    print(f"[test_move] Pon la ventana de Dofus en foco. Empezando en "
          f"{args.delay:.0f}s...")
    for s in range(int(args.delay), 0, -1):
        print(f"  {s}...")
        time.sleep(1)

    # 4. Click real en cada celda, con delay humano entre destinos.
    for i, cell in enumerate(args.cells):
        print(f"[test_move] -> Moviendo a celda {cell} ({i+1}/{len(args.cells)})")
        actuator.move_to(cell)
        if i < len(args.cells) - 1:
            human_delay(config.DELAY_MOVE_MS, config.DELAY_JITTER)

    print("[test_move] Hecho. Verifica que el personaje llegó a la(s) celda(s) "
          "correcta(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
