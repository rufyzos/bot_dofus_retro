"""
Conversión cell_id (0-559) → coordenadas de píxel en pantalla.

El grid de combate de Dofus Retro es 14 columnas × 40 filas = 560 celdas (0-559).
La numeración de celdas es DIAGONAL (Arakne/CoordinateCell):

    WIDTH = 14
    line   = cell // (WIDTH*2 - 1)     # = cell // 27
    column = cell - line * (WIDTH*2-1)
    offset = column % WIDTH
    y = line - offset
    x = (cell - (WIDTH-1) * y) // WIDTH

Sobre (x, y) Arakne, la rejilla isométrica se expresa con
tres identidades exactas (verificadas para las 560 celdas):

    row    = x + y                      # fila visual 0..39
    parity = row % 2                    # 1 = fila impar (desplazada HW a la derecha)
    col    = (x - y - parity) // 2     # posición dentro de la fila

Proyección canónica (derivada de MapRenderer-DR/main.js + skew observado):
    screen_x = OX + col*CELL_W + parity*CELL_HW + row*CELL_RW
    screen_y = OY + row*CELL_HH + col*CELL_CY

donde CELL_RW es el skew horizontal por fila (~-8px) y CELL_CY es el descenso
en Y por columna (~0.3px), ambos de la geometría isométrica real del cliente.
Ajuste exacto sobre 4 muestras MITM — RMS<0.5px.

Para recalibrar: python tools/calibrate.py --fit
Para verificar:  python tools/calibrate.py --verify
"""

from __future__ import annotations
from input.window import WindowRect

MAP_WIDTH = 14

# Constantes isométricas canónicas calibradas (px, 2560×1440 @ 100%)
# Fit exacto sobre muestras MITM (450,456,18,255). rect.left=0, rect.top=23.
# Fuente del modelo: MapRenderer-DR + análisis de skew del grid real.
CELL_W:  float = 129.667   # ancho de columna en px
CELL_HW: float = 106.802   # offset fila impar (absorbe el skew inicial de parity)
CELL_HH: float =  31.235   # altura de media fila en px
CELL_RW: float =  -8.031   # skew horizontal por fila (el grid se inclina ~-8px/fila a la izq.)
CELL_CY: float =   0.305   # descenso en Y por columna (componente Y de la inclinación)


def cell_to_arakne(cell: int) -> tuple[int, int]:
    """Convierte cell_id al sistema de coordenadas diagonal de Dofus (Arakne)."""
    line = cell // (MAP_WIDTH * 2 - 1)
    column = cell - line * (MAP_WIDTH * 2 - 1)
    offset = column % MAP_WIDTH
    y = line - offset
    x = (cell - (MAP_WIDTH - 1) * y) // MAP_WIDTH
    return x, y


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

    x, y = cell_to_arakne(cell)
    row    = x + y
    parity = row % 2
    col    = (x - y - parity) // 2

    screen_x = int(rect.left + (origin_x + col * CELL_W + parity * CELL_HW + row * CELL_RW) * sx)
    screen_y = int(rect.top  + (origin_y + row * CELL_HH + col * CELL_CY) * sy)
    return screen_x, screen_y
