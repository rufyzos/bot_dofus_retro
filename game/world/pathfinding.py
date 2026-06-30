"""
A* intra-mapa para navegación de mundo (fuera de combate).

Diferencias respecto al BFS de fight.py:
  - Usa celdas mov=true de MapDatabase (no solo "no ocupadas por fighters").
  - 8 direcciones con coste diferenciado HV (10) vs diagonal (14) — mismo que cliente.
  - Heurística: distancia Manhattan isométrica.

Basado en Pathfinding.as de Emudofus/Dofus y ArakneUtils/arakne-map.
"""

from __future__ import annotations
import heapq

from game.world.map_geometry import (
    MAP_WIDTH, MAP_HEIGHT, MAP_CELLS,
    cell_to_xy, distance, neighbors_8, is_diagonal,
)

COST_HV   = 10   # movimiento horizontal/vertical
COST_DIAG = 14   # movimiento diagonal (~√2 × 10)
# B1 — Anti-aggro: coste extra para celdas adyacentes a monstruos en el mapa.
# Un coste alto (no infinito) hace que el bot rodee a los monstruos si hay
# ruta alternativa, pero pueda pasar por ellos si es la única opción.
COST_AGGRO_PENALTY = 60


def _aggro_cells(monster_cells: set[int]) -> set[int]:
    """Todas las celdas adyacentes (8 dir) a cualquier monstruo."""
    danger: set[int] = set()
    for mc in monster_cells:
        for nb in neighbors_8(mc):
            danger.add(nb)
    return danger


def astar(start: int, goal: int,
          walkable: set[int],
          blocked_extra: set[int] | None = None,
          monster_cells: set[int] | None = None) -> list[int]:
    """
    A* desde start hasta goal sobre el conjunto walkable de cellIds.

    blocked_extra: celdas adicionales a bloquear (entidades en el mapa).
    monster_cells: B1 — celdas donde hay monstruos no combativos en el mapa.
      Las celdas adyacentes a estos monstruos reciben una penalización de coste
      (COST_AGGRO_PENALTY) para que el bot prefiera caminos alejados de la
      zona de aggro, sin bloquearlos por completo.
    Devuelve la lista de celdas [start, ..., goal] o [] si no hay ruta.
    """
    if start == goal:
        return [start]

    blocked = set() if blocked_extra is None else blocked_extra
    danger  = _aggro_cells(monster_cells) if monster_cells else set()

    def h(cell: int) -> int:
        return distance(cell, goal) * COST_HV

    open_heap: list[tuple[int, int]] = []
    heapq.heappush(open_heap, (h(start), start))
    came_from: dict[int, int] = {}
    g: dict[int, int] = {start: 0}
    f: dict[int, int] = {start: h(start)}

    while open_heap:
        _, current = heapq.heappop(open_heap)

        if current == goal:
            path = []
            while current in came_from:
                path.append(current)
                current = came_from[current]
            path.append(start)
            path.reverse()
            return path

        for neighbor in neighbors_8(current):
            if neighbor not in walkable or neighbor in blocked:
                if neighbor != goal:
                    continue
            cost = COST_DIAG if is_diagonal(current, neighbor) else COST_HV
            if neighbor in danger:
                cost += COST_AGGRO_PENALTY
            tentative_g = g[current] + cost
            if tentative_g < g.get(neighbor, 10**9):
                came_from[neighbor] = current
                g[neighbor] = tentative_g
                f[neighbor] = tentative_g + h(neighbor)
                heapq.heappush(open_heap, (f[neighbor], neighbor))

    return []  # sin ruta


def reachable_in(start: int, steps: int,
                 walkable: set[int],
                 blocked_extra: set[int] | None = None) -> dict[int, int]:
    """
    BFS — celdas alcanzables en exactamente `steps` pasos o menos.
    Devuelve {cell: coste_pasos}.
    """
    blocked = set() if blocked_extra is None else blocked_extra
    visited: dict[int, int] = {start: 0}
    queue = [(start, 0)]
    while queue:
        current, cost = queue.pop(0)
        if cost >= steps:
            continue
        for neighbor in neighbors_8(current):
            if neighbor in visited or neighbor not in walkable or neighbor in blocked:
                continue
            visited[neighbor] = cost + 1
            queue.append((neighbor, cost + 1))
    return visited
