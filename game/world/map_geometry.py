"""
Geometría del mapa completo de Dofus Retro (560 celdas: 14 columnas × 40 filas).

Implementa la conversión cellId↔(x,y) isométrica (MapPoint del cliente),
distancia Manhattan isométrica y vecinos en las 8 direcciones.

Fuente canónica: Emudofus/Dofus — MapPoint.as / ArakneUtils.
"""

from __future__ import annotations

MAP_WIDTH  = 14
MAP_HEIGHT = 40
MAP_CELLS  = MAP_WIDTH * MAP_HEIGHT  # 560


def cell_to_xy(cell: int) -> tuple[int, int]:
    """cellId → coordenadas isométricas (x, y)."""
    row = cell // MAP_WIDTH
    col = cell % MAP_WIDTH
    return col * 2 + (row % 2), row


def xy_to_cell(x: int, y: int) -> int:
    """Coordenadas isométricas → cellId (sin validación de límites)."""
    row = y
    col = (x - (row % 2)) // 2
    return row * MAP_WIDTH + col


def distance(cell_a: int, cell_b: int) -> int:
    """Distancia Manhattan isométrica entre dos celdas."""
    ax, ay = cell_to_xy(cell_a)
    bx, by = cell_to_xy(cell_b)
    return (abs(ax - bx) + abs(ay - by)) // 2


def neighbors_4(cell: int) -> list[int]:
    """4 vecinos cardinales (movimiento normal de personaje)."""
    row = cell // MAP_WIDTH
    col = cell % MAP_WIDTH
    result = []
    if row > 0:
        result.append(cell - MAP_WIDTH)
    if row < MAP_HEIGHT - 1:
        result.append(cell + MAP_WIDTH)
    if col > 0:
        result.append(cell - 1)
    if col < MAP_WIDTH - 1:
        result.append(cell + 1)
    return result


def neighbors_8(cell: int) -> list[int]:
    """8 vecinos (incluye diagonales para A*)."""
    row = cell // MAP_WIDTH
    col = cell % MAP_WIDTH
    result = []
    for dr in (-1, 0, 1):
        for dc in (-1, 0, 1):
            if dr == 0 and dc == 0:
                continue
            r, c = row + dr, col + dc
            if 0 <= r < MAP_HEIGHT and 0 <= c < MAP_WIDTH:
                result.append(r * MAP_WIDTH + c)
    return result


def is_diagonal(cell_a: int, cell_b: int) -> bool:
    """True si los dos vecinos están en diagonal."""
    ra, ca = cell_a // MAP_WIDTH, cell_a % MAP_WIDTH
    rb, cb = cell_b // MAP_WIDTH, cell_b % MAP_WIDTH
    return abs(ra - rb) == 1 and abs(ca - cb) == 1
