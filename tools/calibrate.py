"""
Herramienta de calibración del origen del mapa.

Mueve el cursor (sin hacer click) al píxel calculado para un cell_id dado.
Úsalo para afinar MAP_ORIGIN_X, MAP_ORIGIN_Y y MAP_SCALE en config.py
hasta que el cursor caiga centrado en la celda correcta.

Uso:
    python tools/calibrate.py <cell_id>
    python tools/calibrate.py <cell_id> <cell_id2> ...  (varias celdas)

Ejemplo:
    python tools/calibrate.py 0 200 400 559

El cursor se moverá a cada celda con 1.5s de pausa entre ellas.
Observa si el cursor cae sobre la celda correcta en el cliente de Dofus.
Si no, ajusta MAP_ORIGIN_X/Y en config.py y repite.

El cliente debe estar abierto en el mapa (no en menú).
"""

import sys
import time
import os

# Asegura imports desde la raíz del proyecto
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pyautogui
import config
from input.window import find_dofus_window
from input.coords import cell_to_screen

pyautogui.FAILSAFE = False


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        print("Uso: python tools/calibrate.py <cell_id> [cell_id2 ...]")
        sys.exit(1)

    cell_ids = []
    for arg in sys.argv[1:]:
        try:
            cell_ids.append(int(arg))
        except ValueError:
            print(f"cell_id inválido: {arg!r}")
            sys.exit(1)

    print(f"Buscando ventana '{config.WINDOW_TITLE_SUBSTR}'...")
    rect = find_dofus_window(config.WINDOW_TITLE_SUBSTR)
    print(f"  Ventana: left={rect.left} top={rect.top} {rect.width}×{rect.height}")
    print(f"  MAP_ORIGIN=({config.MAP_ORIGIN_X},{config.MAP_ORIGIN_Y}) scale={config.MAP_SCALE}")
    print()

    print("Iniciando en 2s — pon el foco en la ventana de Dofus...")
    time.sleep(2)

    for cell in cell_ids:
        px, py = cell_to_screen(cell, rect, config.MAP_ORIGIN_X, config.MAP_ORIGIN_Y, config.MAP_SCALE,
                                scale_x=config.MAP_SCALE_X, scale_y=config.MAP_SCALE_Y)
        print(f"  cell={cell:>4} → ({px:>5}, {py:>5})")
        pyautogui.moveTo(px, py, duration=0.15)
        time.sleep(1.5)

    print("\nCalibración completada.")
    print("Si el cursor no cae en la celda correcta, ajusta MAP_ORIGIN_X/Y en config.py.")


if __name__ == "__main__":
    main()
