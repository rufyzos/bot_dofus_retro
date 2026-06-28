"""
FightState — estado detallado de un combate en curso.

Rastrea todos los fighters (personajes y mobs), sus posiciones, HP y equipo.
Se actualiza con paquetes del servidor durante el combate.

NOTA: Los formatos de payload exactos deben confirmarse en Fase 0 con el sniffer.
Los parsers aquí son una primera aproximación basada en retroproto; ajustar
tras capturar paquetes reales.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from collections import deque


@dataclass
class Fighter:
    id: str
    team: int          # 0 = equipo aliado, 1 = equipo enemigo
    cell: int          # celda actual en el grid de combate
    hp: int = 0
    max_hp: int = 0
    ap: int = 0
    mp: int = 0
    alive: bool = True
    is_me: bool = False


class FightState:
    def __init__(self):
        self._fighters: dict[str, Fighter] = {}
        self.my_team: int = 0

    # ------------------------------------------------------------------
    # Acceso a fighters
    # ------------------------------------------------------------------

    def all_fighters(self) -> list[Fighter]:
        return list(self._fighters.values())

    def enemies(self) -> list[Fighter]:
        return [f for f in self._fighters.values()
                if f.team != self.my_team and f.alive]

    def allies(self) -> list[Fighter]:
        return [f for f in self._fighters.values()
                if f.team == self.my_team and f.alive]

    def me(self) -> Fighter | None:
        for f in self._fighters.values():
            if f.is_me:
                return f
        return None

    def get(self, fighter_id: str) -> Fighter | None:
        return self._fighters.get(fighter_id)

    # ------------------------------------------------------------------
    # Geometría de celdas (grid isométrico Dofus)
    # Dofus usa un grid de 14 columnas × 20 filas = 280 celdas (0-279).
    # ------------------------------------------------------------------

    MAP_WIDTH = 14

    @staticmethod
    def cell_to_xy(cell: int) -> tuple[int, int]:
        row = cell // FightState.MAP_WIDTH
        col = cell % FightState.MAP_WIDTH
        return col, row

    @staticmethod
    def distance(cell_a: int, cell_b: int) -> int:
        ax, ay = FightState.cell_to_xy(cell_a)
        bx, by = FightState.cell_to_xy(cell_b)
        return abs(ax - bx) + abs(ay - by)

    def nearest_enemy(self, from_cell: int) -> Fighter | None:
        enemies = self.enemies()
        if not enemies:
            return None
        return min(enemies, key=lambda f: self.distance(from_cell, f.cell))

    def enemy_in_range(self, from_cell: int, min_range: int, max_range: int) -> list[Fighter]:
        return [
            f for f in self.enemies()
            if min_range <= self.distance(from_cell, f.cell) <= max_range
        ]

    # ------------------------------------------------------------------
    # Línea de visión — algoritmo de Bresenham
    # ------------------------------------------------------------------

    @staticmethod
    def _bresenham_cells(x0: int, y0: int, x1: int, y1: int) -> list[tuple[int, int]]:
        """Devuelve todas las celdas (col, row) que cruza la línea de (x0,y0) a (x1,y1)."""
        cells = []
        dx = abs(x1 - x0)
        dy = abs(y1 - y0)
        sx = 1 if x1 > x0 else -1
        sy = 1 if y1 > y0 else -1
        err = dx - dy
        x, y = x0, y0
        while True:
            cells.append((x, y))
            if x == x1 and y == y1:
                break
            e2 = 2 * err
            if e2 > -dy:
                err -= dy
                x += sx
            if e2 < dx:
                err += dx
                y += sy
        return cells

    def has_line_of_sight(self, from_cell: int, to_cell: int) -> bool:
        """
        True si no hay obstáculos (celdas ocupadas por fighters) en la línea
        recta entre from_cell y to_cell (excluye las celdas de origen y destino).
        """
        fx, fy = self.cell_to_xy(from_cell)
        tx, ty = self.cell_to_xy(to_cell)
        occupied = {
            f.cell for f in self._fighters.values()
            if f.alive and f.cell != from_cell and f.cell != to_cell
        }
        for x, y in self._bresenham_cells(fx, fy, tx, ty)[1:-1]:
            cell_id = y * self.MAP_WIDTH + x
            if cell_id in occupied:
                return False
        return True

    # ------------------------------------------------------------------
    # Pathfinding BFS en el grid de combate
    # ------------------------------------------------------------------

    MAP_HEIGHT = 20  # 280 celdas = 14 × 20

    def bfs_path(self, start: int, goal: int,
                 blocked_extra: set[int] | None = None) -> list[int]:
        """
        BFS desde start hasta goal en el grid de combate (14×20).
        Evita celdas ocupadas por fighters (excepto el propio goal si hay target ahí).
        blocked_extra: celdas adicionales a considerar como bloqueadas.

        Devuelve la lista de cell_ids del camino (sin incluir start, incluyendo goal),
        o lista vacía si no hay camino.
        """
        occupied = {
            f.cell for f in self._fighters.values()
            if f.alive and f.cell != start and f.cell != goal
        }
        if blocked_extra:
            occupied |= blocked_extra

        visited = {start}
        queue: deque[tuple[int, list[int]]] = deque([(start, [])])

        while queue:
            current, path = queue.popleft()
            if current == goal:
                return path

            cx, cy = self.cell_to_xy(current)
            # 4 vecinos (arriba, abajo, izquierda, derecha)
            for nx, ny in ((cx, cy-1), (cx, cy+1), (cx-1, cy), (cx+1, cy)):
                if not (0 <= nx < self.MAP_WIDTH and 0 <= ny < self.MAP_HEIGHT):
                    continue
                neighbor = ny * self.MAP_WIDTH + nx
                if neighbor in visited or neighbor in occupied:
                    continue
                visited.add(neighbor)
                queue.append((neighbor, path + [neighbor]))

        return []  # sin camino

    def cells_reachable_in(self, start: int, mp: int) -> set[int]:
        """Todas las celdas alcanzables desde start usando exactamente ≤ mp pasos."""
        occupied = {
            f.cell for f in self._fighters.values()
            if f.alive and f.cell != start
        }
        visited = {start: 0}
        queue: deque[tuple[int, int]] = deque([(start, 0)])
        while queue:
            current, steps = queue.popleft()
            if steps >= mp:
                continue
            cx, cy = self.cell_to_xy(current)
            for nx, ny in ((cx, cy-1), (cx, cy+1), (cx-1, cy), (cx+1, cy)):
                if not (0 <= nx < self.MAP_WIDTH and 0 <= ny < self.MAP_HEIGHT):
                    continue
                neighbor = ny * self.MAP_WIDTH + nx
                if neighbor in occupied or neighbor in visited:
                    continue
                visited[neighbor] = steps + 1
                queue.append((neighbor, steps + 1))
        return set(visited.keys()) - {start}

    # ------------------------------------------------------------------
    # Handlers de paquetes (a registrar en Dispatcher)
    # ------------------------------------------------------------------

    def handle_fight_join(self, fields: list[str]):
        """
        [CONFIRMAR en Fase 0] Paquete de inicio de combate con lista de fighters.
        Formato aproximado (retroproto): por cada fighter hay campos
        id|team|cell|hp|max_hp|ap|mp|...
        """
        self._fighters.clear()
        # Parseo tentativo — ajustar tras Fase 0
        # Por ahora simplemente logueamos
        print(f"[FightState] fight_join: {fields}")

    def handle_fighter_stats(self, fields: list[str]):
        """
        [CONFIRMAR en Fase 0] Actualiza stats de un fighter.
        Formato aproximado: fighter_id|hp|max_hp|ap|mp
        """
        if len(fields) < 5:
            return
        fid, hp, max_hp, ap, mp = fields[:5]
        if fid in self._fighters:
            f = self._fighters[fid]
            f.hp = int(hp)
            f.max_hp = int(max_hp)
            f.ap = int(ap)
            f.mp = int(mp)

    def handle_fighter_move(self, fields: list[str]):
        """
        [CONFIRMAR en Fase 0] Actualiza celda de un fighter.
        Formato aproximado: fighter_id|cell_id
        """
        if len(fields) < 2:
            return
        fid, cell = fields[0], fields[1]
        if fid in self._fighters:
            try:
                self._fighters[fid].cell = int(cell)
            except ValueError:
                pass

    def handle_fighter_death(self, fields: list[str]):
        """[CONFIRMAR en Fase 0] Marca un fighter como muerto."""
        fid = fields[0] if fields else None
        if fid and fid in self._fighters:
            self._fighters[fid].alive = False

    def add_fighter(self, fighter: Fighter):
        self._fighters[fighter.id] = fighter

    def reset(self):
        self._fighters.clear()

    def register_handlers(self, dispatcher):
        """
        Registra handlers de FightState.
        Los headers marcados [CONFIRMAR] deben actualizarse tras Fase 0.
        """
        from protocol.dispatcher import DIRECTION_SERVER
        # Ejemplo con headers tentativas — ACTUALIZAR tras sniffer:
        # dispatcher.on("GJK", self.handle_fight_join,    DIRECTION_SERVER)
        # dispatcher.on("GHT", self.handle_fighter_stats, DIRECTION_SERVER)
        # dispatcher.on("GAV", self.handle_fighter_move,  DIRECTION_SERVER)
        # dispatcher.on("GKK", self.handle_fighter_death, DIRECTION_SERVER)
        print("[FightState] register_handlers: headers pendientes de confirmar en Fase 0.")

    def __repr__(self):
        return (
            f"<FightState fighters={len(self._fighters)} "
            f"enemies={len(self.enemies())} allies={len(self.allies())}>"
        )
