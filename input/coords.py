"""
Conversión cell_id (0-559) → coordenadas de píxel en pantalla.

El grid de combate de Dofus Retro es 14 columnas × 40 filas = 560 celdas (0-559).

Fórmula derivada de 3 puntos medidos con Window Spy en el mapa -2,-1 (2026-06-28):
  Celda 254 (row=18, col=2): Screen (1351, 583)
  Celda 312 (row=22, col=4): Screen (1359, 719)
  Celda 424 (row=30, col=4): Screen (821,  990)
  rect.top=23, rect.left=0

  screen_x = OX + col*DX_COL + row*DX_ROW
  screen_y = rect.top + OY + col*DY_COL + row*DY_ROW

  DX_COL = 138.5    DY_COL = 0.25
  DX_ROW = -67.25   DY_ROW = 33.875

Nota: DX_ROW es negativo — al bajar de fila el mapa se desplaza a la izquierda
(proyección isométrica del rombo Dofus).
"""

from __future__ import annotations
from input.window import WindowRect

MAP_WIDTH = 14

# Pendientes isométricas calibradas (px por unidad de col/row)
DX_PER_COL: float = 138.5    # X avanza ~138.5px por columna
DY_PER_COL: float = 0.25     # Y baja levemente por columna
DX_PER_ROW: float = -67.25   # X retrocede ~67.25px por fila (inclinación isométrica)
DY_PER_ROW: float = 33.875   # Y baja ~33.9px por fila


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

    origin_x: componente X del origen (screen_x cuando row=0, col=0).
    origin_y: componente Y del origen en coordenadas cliente (screen_y - rect.top cuando row=0, col=0).
    scale_x/scale_y: factores adicionales si el cliente está a otro zoom (normalmente 1.0).
    """
    sx = scale_x if scale_x is not None else scale
    sy = scale_y if scale_y is not None else scale

    row = cell // MAP_WIDTH
    col = cell % MAP_WIDTH

    screen_x = int((origin_x + col * DX_PER_COL + row * DX_PER_ROW) * sx)
    screen_y = int(rect.top + (origin_y + col * DY_PER_COL + row * DY_PER_ROW) * sy)
    return screen_x, screen_y
