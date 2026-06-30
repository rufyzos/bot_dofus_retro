"""
Geometría del mapa completo de Dofus Retro (560 celdas).

MISMO modelo que input/coords.py y game/fight.py (validado empíricamente,
RMS 2.3px): numeración base-1, filas de ancho alterno (par=14, impar=15
celdas), filas impares desplazadas media celda a la izquierda.

NO usar 'cell // 14' (modelo base-0 de ancho fijo) — es incoherente con la
calibración cell→píxel y haría que la celda lógica del pathfinding y el click
no coincidan. Ver memoria [[project-cell-geometry]] / [[project-dryrun-validated]].

Coordenadas isométricas:
    x = 2*col - (1 si fila impar else 0)   ;   y = fila

Movimiento: en Dofus Retro el personaje solo se mueve a los 4 adyacentes
"rectos isométricos" (deltas de cell_id ±14, ±15), cada uno cuesta 1 PM.
NO hay movimiento diagonal de grid.
"""

from __future__ import annotations

from input.coords import cell_to_colrow

MAP_CELLS  = 560
# Conservados por compatibilidad con importadores antiguos; NO usar para
# aritmética de celda (inducen el modelo base-0 erróneo).
MAP_WIDTH  = 14
MAP_HEIGHT = 40

# Deltas de cell_id de los 4 vecinos de movimiento (cada uno = 1 PM).
_NEIGHBOR_DELTAS = (-15, -14, 14, 15)


def cell_to_xy(cell: int) -> tuple[int, int]:
    """cellId (base-1) → coordenadas isométricas (x, y)."""
    col, fila = cell_to_colrow(cell)
    return 2 * col - (fila % 2), fila


def distance(cell_a: int, cell_b: int) -> int:
    """Distancia Manhattan isométrica entre dos celdas (= PM de movimiento)."""
    ax, ay = cell_to_xy(cell_a)
    bx, by = cell_to_xy(cell_b)
    return (abs(ax - bx) + abs(ay - by)) // 2


def neighbors_4(cell: int) -> list[int]:
    """
    4 vecinos de movimiento (rectos isométricos), cada uno a 1 PM.
    El filtro por distancia==1 descarta los que cruzarían el borde de fila.
    """
    return [
        n for d in _NEIGHBOR_DELTAS
        if 1 <= (n := cell + d) <= MAP_CELLS and distance(cell, n) == 1
    ]
