"""
FightState — estado detallado de un combate en curso.

Headers de combate confirmados según retroproto / docs 2026:
  GS   — GameStartToPlay: el servidor confirma inicio de combate
  GM   — GameMovement: actores en mapa (también fighters durante combate)
  GIC  — GamePlayersCoordinates: coordenadas de jugadores en combate
  GTL  — GameTurnList: orden de turnos (lista de fighter_ids)
  GTS  — GameTurnStart: comienza el turno de un fighter (en GameState)
  GTF  — GameTurnFinish: fin de turno (en GameState)
  GIE  — GameEffect: efecto aplicado (daño, buff, muerte)
  GE   — GameEnd: fin de combate (en GameState)
  GA   — GameActionsSendActions: acción (bidireccional)

Patrón de combate (retroproto):
  GS → GIC (fighters) → GTL (orden) → GTS (turno) → GA (cast) → GIE (efectos) → Gt (fin turno)
"""

from __future__ import annotations
from dataclasses import dataclass, field
from collections import deque


@dataclass
class Fighter:
    id: str
    team: int          # 0 = aliado, 1 = enemigo (relativo al char del bot)
    cell: int
    name: str = ""
    level: int = 0
    hp: int = 0
    max_hp: int = 0
    ap: int = 0
    mp: int = 0
    alive: bool = True
    is_me: bool = False


class FightState:
    def __init__(self):
        self._fighters: dict[str, Fighter] = {}
        self.my_team: int = -1
        self._turn_order: list[str] = []
        self.on_fight_start   = None  # asignado por bot.py → state.handle_fight_start
        self.on_placement_ready = None  # callback(available_cells) al recibir GP
        self._my_fighter_id: str | None = None

        # Fase de placement (pre-combate)
        self.in_placement: bool = False
        self.placement_cells: list[int] = []  # celdas disponibles para colocarse

    # ------------------------------------------------------------------
    # Acceso a fighters
    # ------------------------------------------------------------------

    def all_fighters(self) -> list[Fighter]:
        return list(self._fighters.values())

    def enemies(self) -> list[Fighter]:
        """
        En Dofus Retro el tercer campo de GIC no distingue equipos fiablemente
        (todos aparecen con el mismo valor). Usamos ID negativo como criterio:
        los mobs/NPCs siempre tienen ID negativo, los jugadores ID positivo.
        """
        return [f for f in self._fighters.values()
                if f.id.startswith("-") and f.alive]

    def allies(self) -> list[Fighter]:
        return [f for f in self._fighters.values()
                if not f.id.startswith("-") and f.alive]

    def me(self) -> Fighter | None:
        for f in self._fighters.values():
            if f.is_me:
                return f
        return None

    def get(self, fighter_id: str) -> Fighter | None:
        return self._fighters.get(fighter_id)

    def add_fighter(self, fighter: Fighter):
        self._fighters[fighter.id] = fighter

    def reset(self):
        self._fighters.clear()
        self._turn_order.clear()
        self.my_team = -1

    # ------------------------------------------------------------------
    # Geometría (grid isométrico Dofus: 14 columnas × 20 filas = 280 celdas)
    # ------------------------------------------------------------------

    MAP_WIDTH  = 14
    MAP_HEIGHT = 40  # 560 celdas / 14 columnas = 40 filas

    @staticmethod
    def cell_to_xy(cell: int) -> tuple[int, int]:
        # Rejilla isométrica entrelazada de Dofus Retro (MapPoint del cliente)
        # Filas pares:   x = col*2,     filas impares: x = col*2 + 1
        row = cell // FightState.MAP_WIDTH
        col = cell % FightState.MAP_WIDTH
        return col * 2 + (row % 2), row

    @staticmethod
    def distance(cell_a: int, cell_b: int) -> int:
        # Distancia Manhattan en coordenadas isométricas, dividida entre 2
        ax, ay = FightState.cell_to_xy(cell_a)
        bx, by = FightState.cell_to_xy(cell_b)
        return (abs(ax - bx) + abs(ay - by)) // 2

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
    # Línea de visión (Bresenham)
    # ------------------------------------------------------------------

    @staticmethod
    def _bresenham_cells(x0, y0, x1, y1) -> list[tuple[int, int]]:
        cells = []
        dx, dy = abs(x1 - x0), abs(y1 - y0)
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
                err -= dy; x += sx
            if e2 < dx:
                err += dx; y += sy
        return cells

    def has_line_of_sight(self, from_cell: int, to_cell: int) -> bool:
        fx, fy = self.cell_to_xy(from_cell)
        tx, ty = self.cell_to_xy(to_cell)
        occupied = {
            f.cell for f in self._fighters.values()
            if f.alive and f.cell != from_cell and f.cell != to_cell
        }
        for x, y in self._bresenham_cells(fx, fy, tx, ty)[1:-1]:
            if y * self.MAP_WIDTH + x in occupied:
                return False
        return True

    # ------------------------------------------------------------------
    # Pathfinding BFS
    # ------------------------------------------------------------------

    @staticmethod
    def _neighbors(cell: int) -> list[int]:
        """Las 4 celdas adyacentes en el grid isométrico de Dofus (arriba/abajo/izq/der)."""
        row = cell // FightState.MAP_WIDTH
        col = cell % FightState.MAP_WIDTH
        candidates = []
        # Arriba-derecha e izquierda (fila anterior)
        if row > 0:
            candidates.append(cell - FightState.MAP_WIDTH)
            if col > 0:
                candidates.append(cell - FightState.MAP_WIDTH - 1)
        # Abajo-derecha e izquierda (fila siguiente)
        if row < FightState.MAP_HEIGHT - 1:
            candidates.append(cell + FightState.MAP_WIDTH)
            if col < FightState.MAP_WIDTH - 1:
                candidates.append(cell + FightState.MAP_WIDTH + 1)
        return [c for c in candidates if 0 <= c < FightState.MAP_WIDTH * FightState.MAP_HEIGHT]

    def bfs_path(self, start: int, goal: int,
                 blocked_extra: set[int] | None = None) -> list[int]:
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
            for neighbor in self._neighbors(current):
                if neighbor in visited or neighbor in occupied:
                    continue
                visited.add(neighbor)
                queue.append((neighbor, path + [neighbor]))
        return []

    def cells_reachable_in(self, start: int, mp: int) -> set[int]:
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
            for neighbor in self._neighbors(current):
                if neighbor in occupied or neighbor in visited:
                    continue
                visited[neighbor] = steps + 1
                queue.append((neighbor, steps + 1))
        return set(visited.keys()) - {start}

    # ------------------------------------------------------------------
    # Handlers de paquetes
    # ------------------------------------------------------------------

    def handle_gj(self, fields: list[str]):
        """
        GJ — GameJoin: personaje entra en el área de combate (placement).

        Llega ANTES de GIC. Marca el inicio de la fase de placement.
        Formato: GJ<fighter_id>|<team>|<cell>|<is_solo>|<challenge_id>
        Reseteamos estado de combate anterior aquí para estar listos cuando
        llegue GIC con las coordenadas reales.
        """
        self._fighters.clear()
        self._turn_order.clear()
        self.my_team   = -1
        self.in_placement  = True
        self.placement_cells = []
        print(f"[FightState] GJ — entrando en placement. fields={fields[:4]}")

    def handle_gp(self, fields: list[str]):
        """
        GP — GamePositionStart: lista de celdas de inicio disponibles para
        el equipo del jugador en la fase de placement.

        Formato: GP<cell1>|<cell2>|...
        El bot elige la celda óptima y envía Gp<cell_id> + GR para marcar listo.
        """
        cells = []
        for f in fields:
            f = f.strip()
            if not f:
                continue
            try:
                cells.append(int(f))
            except ValueError:
                pass
        self.placement_cells = cells
        print(f"[FightState] GP — celdas de placement disponibles: {cells[:10]}"
              f"{'...' if len(cells) > 10 else ''}")
        if self.on_placement_ready:
            self.on_placement_ready(cells)

    def handle_gs(self, fields: list[str]):
        """
        GS — GameStartToPlay: confirma inicio de combate.
        Llega antes o después de GIC según la sesión. Solo reseteamos aquí
        si no tenemos fighters (GIC aún no llegó o fue de una sesión anterior).
        La notificación real se hace en GTL (que siempre llega después de GIC+GS).
        """
        self.in_placement = False
        if not self._fighters:
            self._fighters.clear()
            self._turn_order.clear()
            self.my_team = -1
        print(f"[FightState] GS — {len(self._fighters)} fighters en estado")

    def handle_gic(self, fields: list[str]):
        """
        GIC — GamePlayersCoordinates: lista de fighters al entrar en combate.
        Formato confirmado: GIC|<id>;<cell>;<team>|<id>;<cell>;<team>|...
        Llega ANTES de GS — aquí cargamos todos los fighters.
        Los IDs negativos son mobs/NPCs; el char_id propio es el número largo positivo.
        """
        self._fighters.clear()
        self._turn_order.clear()
        self.my_team = -1

        for entry in fields:
            if not entry:
                continue
            parts = entry.split(";")
            if len(parts) < 3:
                continue
            fid = parts[0]
            try:
                cell = int(parts[1])
                team = int(parts[2])
            except ValueError:
                continue
            # GIC puede traer más campos: id;cell;team;level;name;hp;max_hp;...
            hp = max_hp = 0
            if len(parts) >= 7:
                try:
                    hp     = int(parts[5])
                    max_hp = int(parts[6])
                except ValueError:
                    pass
            f = Fighter(id=fid, team=team, cell=cell, hp=hp, max_hp=max_hp)
            # Marcar si es mi personaje
            if self._my_fighter_id and fid == self._my_fighter_id:
                f.is_me = True
                self.my_team = team
            self._fighters[fid] = f

        print(f"[FightState] GIC: {len(self._fighters)} fighters cargados")
        for f in self._fighters.values():
            print(f"  fighter id={f.id} team={f.team} cell={f.cell} is_me={f.is_me}")

    def handle_gtl(self, fields: list[str]):
        """
        GTL — GameTurnList: orden de turnos. Siempre llega después de GIC+GS.
        Es el punto fiable para notificar inicio de combate.
        """
        print(f"[FightState] GTL raw: {fields}")
        order = []
        for entry in fields:
            fid = entry.strip().lstrip("+")
            if fid:
                order.append(fid)
        self._turn_order = order
        print(f"[FightState] GTL: orden de turno = {self._turn_order}")
        print(f"[FightState] Combate listo — {len(self._fighters)} fighters, me={self.me()}")
        if self.on_fight_start:
            self.on_fight_start(fields)

    # GIE action_ids de daño confirmados (retroproto / sniffer):
    #   100 = daño HP genérico (la mayoría de ataques físicos/mágicos)
    #   101 = daño en escudo/armadura (no resta HP real)
    #   102 = muerte del fighter
    #   103 = curación (HP restaurado — valor positivo)
    #   104 = daño en PM (pérdida de PM)
    #   105 = daño en PA (pérdida de PA)
    # Si el action_id no está aquí lo ignoramos (buff visual, etc.)
    _GIE_DAMAGE_IDS  = {100}     # resta HP
    _GIE_HEAL_IDS    = {103}     # suma HP
    _GIE_DEATH_ID    = 102

    def handle_gie(self, fields: list[str]):
        """
        GIE — GameEffect: efecto sobre un fighter (daño, curación, muerte…).
        Formato por efecto: <action_id>;<fighter_id>;<value>[;<extra>...]
        Varios efectos vienen separados por '|' dentro del mismo paquete.
        Actualiza HP y alive en tiempo real para que lowest_hp_enemy sea correcto.
        """
        raw_payload = "|".join(fields)
        for effect in raw_payload.split("|"):
            parts = effect.split(";")
            if len(parts) < 2:
                continue
            try:
                action_id = int(parts[0])
            except ValueError:
                continue
            fid = parts[1] if len(parts) > 1 else None
            if not fid or fid not in self._fighters:
                continue
            fighter = self._fighters[fid]

            if action_id == self._GIE_DEATH_ID:
                fighter.alive = False
                print(f"[FightState] GIE: fighter {fid} muerto")

            elif action_id in self._GIE_DAMAGE_IDS and len(parts) >= 3:
                try:
                    dmg = abs(int(parts[2]))
                    fighter.hp = max(0, fighter.hp - dmg)
                    print(f"[FightState] GIE: fighter {fid} recibe {dmg} daño → hp={fighter.hp}")
                    if fighter.hp == 0:
                        fighter.alive = False
                except ValueError:
                    pass

            elif action_id in self._GIE_HEAL_IDS and len(parts) >= 3:
                try:
                    heal = abs(int(parts[2]))
                    fighter.hp = min(fighter.max_hp or fighter.hp + heal, fighter.hp + heal)
                    print(f"[FightState] GIE: fighter {fid} curado {heal} → hp={fighter.hp}")
                except ValueError:
                    pass

    def handle_ga(self, fields: list[str]):
        """
        GA — GameActionsSendActions: acción de juego (bidireccional).
        Nos interesa el movimiento (action_id=1) para actualizar la celda del fighter.
        Formato: GA<seq>\\n<action_id>;<fighter_id>;<path>\\n
        """
        raw_payload = "|".join(fields)
        lines = [l for l in raw_payload.split("\n") if l.strip()]
        if len(lines) < 2:
            return
        action_str = lines[1].strip()
        parts = action_str.split(";")
        if not parts:
            return
        try:
            action_id = int(parts[0])
        except ValueError:
            return

        if action_id == 1 and len(parts) >= 3:
            fid = parts[1]
            if fid in self._fighters:
                try:
                    dest_cell = int(parts[-1])
                    self._fighters[fid].cell = dest_cell
                    print(f"[FightState] GA mov: fighter {fid} → celda {dest_cell}")
                except ValueError:
                    pass

    def set_my_fighter_id(self, char_id: str):
        """
        Llamado desde GameState.handle_ask con el char_id del personaje.
        En Dofus Retro el fighter_id en combate coincide con el char_id del GM.
        Lo guardamos y marcamos is_me si el fighter ya está cargado.
        """
        self._my_fighter_id = char_id
        if char_id in self._fighters:
            self._fighters[char_id].is_me = True
            self.my_team = self._fighters[char_id].team
            print(f"[FightState] Mi fighter identificado: id={char_id} team={self.my_team}")

    def register_handlers(self, dispatcher):
        from protocol.messages import GJ, GP, GS, GIC, GTL, GIE, GA
        from protocol.dispatcher import DIRECTION_SERVER

        dispatcher.on(GJ,  self.handle_gj,  DIRECTION_SERVER)
        dispatcher.on(GP,  self.handle_gp,  DIRECTION_SERVER)
        dispatcher.on(GS,  self.handle_gs,  DIRECTION_SERVER)
        dispatcher.on(GIC, self.handle_gic, DIRECTION_SERVER)
        dispatcher.on(GTL, self.handle_gtl, DIRECTION_SERVER)
        dispatcher.on(GIE, self.handle_gie, DIRECTION_SERVER)
        dispatcher.on(GA,  self.handle_ga,  DIRECTION_SERVER)
        print("[FightState] Handlers registrados: GJ, GP, GS, GIC, GTL, GIE, GA")

    def __repr__(self):
        return (
            f"<FightState fighters={len(self._fighters)} "
            f"enemies={len(self.enemies())} allies={len(self.allies())}>"
        )
