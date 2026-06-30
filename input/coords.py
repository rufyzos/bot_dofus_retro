"""
Conversión cell_id → coordenadas de píxel en pantalla.

MODELO GEOMÉTRICO (derivado empíricamente, 2026-06-30, 2560×1440 @ 100%).

Numeración de celdas: base-1, filas de ancho alterno:
    fila 0 (par)   = 14 celdas -> cells 1..14
    fila 1 (impar) = 15 celdas -> cells 15..29   (cell 15 = col 0)
    fila 2 (par)   = 14 celdas -> cells 30..43
    ... patrón: par=14, impar=15, cada par de filas = 29 celdas

cellId -> (col, fila):
    c = cell - 1 ; fila = 0 ; w = 14
    mientras c >= w:  c -= w ; fila += 1 ; w = 14 si fila par, 15 si impar
    col = c

Proyección (las filas impares se desplazan media celda a la IZQUIERDA):
    bloque = fila // 2
    screen_x = OX + col*CELL_W   + (fila impar)*ODD_DX     (ODD_DX < 0)
    screen_y = OY + bloque*ROW_H + (fila impar)*ODD_DY

Validado contra 5 muestras (15,193,463,127,448) — RMS≈2.7px.

Para recalibrar: python tools/calibrate.py --fit
Para verificar:  python tools/calibrate.py --verify
"""

from __future__ import annotations
from input.window import WindowRect

# Anchos de fila alternos (numeración base-1)
ROW_EVEN_CELLS = 14   # filas pares
ROW_ODD_CELLS  = 15   # filas impares

# Constantes de proyección calibradas (px, 2560×1440 @ 100%)
# Ajuste por mínimos cuadrados sobre 5 muestras. rect.left=0, rect.top=23.
CELL_W:  float = 130.45    # avance horizontal por columna
ROW_H:   float =  66.69    # avance vertical por bloque (2 filas)
ODD_DX:  float = -68.44    # desplazamiento X de filas impares (a la izquierda)
ODD_DY:  float =  30.05    # desplazamiento Y de filas impares


def cell_to_colrow(cell: int) -> tuple[int, int]:
    """cell_id (base-1) → (columna, fila visual). Filas alternan 14/15 celdas."""
    c = cell - 1
    fila = 0
    w = ROW_EVEN_CELLS
    while c >= w:
        c -= w
        fila += 1
        w = ROW_EVEN_CELLS if fila % 2 == 0 else ROW_ODD_CELLS
    return c, fila


def cell_to_screen(
    cell: int,
    rect: WindowRect,
    origin_x: float,
    origin_y: float,
    scale: float = 1.0,
    scale_x: float | None = None,
    scale_y: float | None = None,
) -> tuple[int, int]:
    """
    Convierte un cell_id de Dofus al píxel central de esa celda en pantalla.

    origin_x/origin_y: offset de origen (desde config.MAP_ORIGIN_X/Y).
    scale_x/scale_y: factores adicionales si el cliente está a otro zoom.
    """
    sx = scale_x if scale_x is not None else scale
    sy = scale_y if scale_y is not None else scale

    col, fila = cell_to_colrow(cell)
    bloque = fila // 2
    odd = fila % 2

    screen_x = int(rect.left + (origin_x + col * CELL_W + odd * ODD_DX) * sx)
    screen_y = int(rect.top  + (origin_y + bloque * ROW_H + odd * ODD_DY) * sy)
    return screen_x, screen_y
