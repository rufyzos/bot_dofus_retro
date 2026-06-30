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

from input.coords import cell_to_colrow


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

        # Callback para notificar al GameState cuando se resuelve el fighter_id propio
        self.on_fighter_id_resolved: object = None  # callable(char_id: str)

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
    # Geometría (grid isométrico Dofus Retro 1.48)
    # ------------------------------------------------------------------
    # MISMO modelo que input/coords.py (validado empíricamente, RMS 2.3px):
    # numeración base-1, filas de ancho alterno (par=14, impar=15 celdas),
    # las filas impares se desplazan media celda a la izquierda.
    # NO usar 'cell // 14' (modelo base-0 de ancho fijo) — es incoherente con
    # la calibración cell→píxel y haría que la celda lógica y el click no
    # coincidan. Ver [[project-cell-geometry]].

    TOTAL_CELLS = 560

    @staticmethod
    def cell_to_xy(cell: int) -> tuple[int, int]:
        """
        cell_id (base-1) → coordenadas isométricas (x, y) coherentes con la
        proyección a píxel de coords.py. Los 4 vecinos de movimiento quedan a
        distancia Manhattan 2 (→ distancia de juego 1 tras el //2).
            x = 2*col - (1 si fila impar else 0)   ;   y = fila
        """
        col, fila = cell_to_colrow(cell)
        return 2 * col - (fila % 2), fila

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
        # Coordenadas isométricas (x,y) de los fighters que bloquean la línea.
        # Comparamos en espacio (x,y) — no hay inversa directa cell↔(x,y) en el
        # modelo 14/15, así que proyectamos las celdas ocupadas a (x,y).
        occupied = {
            self.cell_to_xy(f.cell)
            for f in self._fighters.values()
            if f.alive and f.cell != from_cell and f.cell != to_cell
        }
        for x, y in self._bresenham_cells(fx, fy, tx, ty)[1:-1]:
            if (x, y) in occupied:
                return False
        return True

    # ------------------------------------------------------------------
    # Pathfinding BFS
    # ------------------------------------------------------------------

    @staticmethod
    def _neighbors(cell: int) -> list[int]:
        """
        Las 4 celdas adyacentes de movimiento (diagonales en pantalla).
        En el modelo base-1 14/15 los vecinos están a ±14 / ±15; se filtran
        los que cruzarían el borde de fila comprobando que la distancia de
        juego sea exactamente 1.
        """
        return [
            n for d in (-15, -14, 14, 15)
            if 1 <= (n := cell + d) <= FightState.TOTAL_CELLS
            and FightState.distance(cell, n) == 1
        ]

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

    def handle_gjk(self, fields: list[str]):
        """
        GJK — GameJoinKnown: personaje entra en el área de combate (placement).
        Formato real (sniffer): GJK<team>|0|1|0|30000|4
        Llega ANTES de GIC. Reseteamos estado y marcamos fase de placement.
        """
        self._fighters.clear()
        self._turn_order.clear()
        self.my_team   = -1
        self.in_placement  = True
        self.placement_cells = []
        print(f"[FightState] GJK — entrando en placement. fields={fields[:4]}")

    def handle_gpc(self, fields: list[str]):
        """
        GPc — GamePositionCells: celdas de inicio disponibles para placement.
        Formato real (sniffer): GPc<team>|<celdas_codificadas_equipo0>|<celdas_codificadas_equipo1>|0
        Las celdas vienen en encoding Dofus (pares de chars, no enteros).
        Guardamos la string raw; si el bot tiene celda de GIC la usará como fallback.
        """
        print(f"[FightState] GPc — datos de placement: fields={fields[:3]}")
        # Intentar decodificar celdas del primer equipo (fields[1])
        cells = self._decode_placement_cells(fields[1] if len(fields) > 1 else "")
        if not cells and len(fields) > 2:
            cells = self._decode_placement_cells(fields[2])
        self.placement_cells = cells
        print(f"[FightState] GPc — {len(cells)} celdas decodificadas: {cells[:10]}"
              f"{'...' if len(cells) > 10 else ''}")
        if self.on_placement_ready:
            self.on_placement_ready(cells)

    @staticmethod
    def _decode_placement_cells(encoded: str) -> list[int]:
        """
        Decodifica el string de celdas de GPc.
        Encoding Dofus Retro: pares de chars, cada char = índice en charset base64 Dofus.
        charset = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-'
        cell_id = valor_char1 * 64 + valor_char2  (base 1: +1 si 0-indexed)
        """
        _CHARSET = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
        cells = []
        i = 0
        while i + 1 < len(encoded):
            c1, c2 = encoded[i], encoded[i + 1]
            try:
                v1 = _CHARSET.index(c1)
                v2 = _CHARSET.index(c2)
                cells.append(v1 * 64 + v2)
            except ValueError:
                pass
            i += 2
        return cells

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
            # GIC formato real: id;cell;team (3 campos). HP llega en GTM.
            f = Fighter(id=fid, team=team, cell=cell)
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
        fields[0] es el fighter_id del jugador principal — lo usamos como char_id
        si aún no lo sabemos (ASK no siempre llega antes de GTL en el juego real).
        """
        print(f"[FightState] GTL raw: {fields}")
        order = []
        for entry in fields:
            fid = entry.strip().lstrip("+")
            if fid:
                order.append(fid)
        self._turn_order = order
        # Derivar char_id del primer field (siempre el jugador propio)
        if order and not self._my_fighter_id:
            self.set_my_fighter_id(order[0])
            print(f"[FightState] char_id derivado de GTL[0]: {order[0]}")
        elif order and self._my_fighter_id != order[0]:
            # Corregir si ASK dio un id distinto al real (puede pasar en login rápido)
            self.set_my_fighter_id(order[0])
        print(f"[FightState] GTL: orden de turno = {self._turn_order}")
        print(f"[FightState] Combate listo — {len(self._fighters)} fighters, me={self.me()}")
        if self.on_fight_start:
            self.on_fight_start(fields)

    def handle_gtm(self, fields: list[str]):
        """
        GTM — GameTurnMovement/Stats: stats de fighter al inicio/durante turno.
        Formato real (sniffer): GTM<id>;0;hp;ap;mp;cell;;maxhp|<id>;...
        Fighters muertos usan formato corto: <id>;1  (solo 2 campos, 2do=1=muerto).
        Actualiza HP, AP, MP y celda. Sincroniza GameState si es el jugador propio.
        """
        for entry in fields:
            if not entry:
                continue
            parts = entry.split(";")
            fid = parts[0]
            if fid not in self._fighters:
                continue
            fighter = self._fighters[fid]
            # Formato corto: id;1 = fighter muerto
            if len(parts) == 2 and parts[1] == "1":
                fighter.alive = False
                print(f"[FightState] GTM: fighter {fid} marcado muerto")
                continue
            if len(parts) < 6:
                continue
            try:
                fighter.hp = int(parts[2])
                fighter.ap = int(parts[3])
                fighter.mp = int(parts[4])
                fighter.cell = int(parts[5])
                if len(parts) >= 8 and parts[7]:
                    fighter.max_hp = int(parts[7])
                fighter.alive = fighter.hp > 0
            except (ValueError, IndexError):
                pass
            if fighter.is_me:
                try:
                    from game.state import state as _gs
                    _gs.ap = fighter.ap
                    _gs.mp = fighter.mp
                    _gs.hp = fighter.hp
                    _gs.max_hp = fighter.max_hp
                except Exception:
                    pass
            print(f"[FightState] GTM: fighter {fid} hp={fighter.hp} ap={fighter.ap} mp={fighter.mp} cell={fighter.cell}")

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
        Formato real (sniffer): GA|;<action_id>;<caster_id>;<target_id,valor,elemento>|...
        fields[0] empieza con ';' (sequence_id vacío): ';action_id;caster;targets'
        action_id 155 = daño de hechizo (targets: 'target_id,dmg,element' por coma)
        action_id 1   = movimiento (parts[-1] = celda destino)
        """
        for field in fields:
            if not field or not field.startswith(";"):
                continue
            parts = field.split(";")
            # parts[0]='' (seq vacío), parts[1]=action_id, parts[2]=caster, parts[3]=targets
            if len(parts) < 2:
                continue
            try:
                action_id = int(parts[1])
            except ValueError:
                continue

            if action_id == 1 and len(parts) >= 4:
                # Movimiento: destino en la última parte del path
                fid = parts[2]
                if fid in self._fighters:
                    try:
                        dest_cell = int(parts[-1])
                        self._fighters[fid].cell = dest_cell
                        print(f"[FightState] GA mov: fighter {fid} → celda {dest_cell}")
                    except ValueError:
                        pass

            elif action_id == 155 and len(parts) >= 4:
                # Daño de hechizo: parts[3] = 'target_id,dmg,element' (varios targets sep. por algo)
                targets_raw = parts[3]
                # Múltiples targets pueden separarse por coma o por el propio split
                # Formato: 'target_id,dmg,element' o 'target1,dmg1,elem1' (un solo target por GA)
                target_parts = targets_raw.split(",")
                if len(target_parts) >= 2:
                    target_fid = target_parts[0]
                    if target_fid in self._fighters:
                        try:
                            dmg = abs(int(target_parts[1]))
                            fighter = self._fighters[target_fid]
                            fighter.hp = max(0, fighter.hp - dmg)
                            if fighter.hp == 0:
                                fighter.alive = False
                            print(f"[FightState] GA 155: {target_fid} recibe {dmg} dmg → hp={fighter.hp}")
                        except ValueError:
                            pass

    def set_my_fighter_id(self, char_id: str):
        """
        Llamado desde GameState.handle_ask (ASK packet) o derivado de GTL[0].
        En Dofus Retro el fighter_id en combate coincide con el char_id del GM.
        Notifica on_fighter_id_resolved para que GameState.my_fighter_id quede sync.
        """
        self._my_fighter_id = char_id
        if char_id in self._fighters:
            self._fighters[char_id].is_me = True
            self.my_team = self._fighters[char_id].team
            print(f"[FightState] Mi fighter identificado: id={char_id} team={self.my_team}")
        if self.on_fighter_id_resolved:
            self.on_fighter_id_resolved(char_id)

    def register_handlers(self, dispatcher):
        from protocol.messages import GS, GIC, GTL, GIE, GA
        from protocol.dispatcher import DIRECTION_SERVER

        dispatcher.on("GJK", self.handle_gjk, DIRECTION_SERVER)
        dispatcher.on("GPc", self.handle_gpc, DIRECTION_SERVER)
        dispatcher.on("GTM", self.handle_gtm, DIRECTION_SERVER)
        dispatcher.on(GS,   self.handle_gs,   DIRECTION_SERVER)
        dispatcher.on(GIC,  self.handle_gic,  DIRECTION_SERVER)
        dispatcher.on(GTL,  self.handle_gtl,  DIRECTION_SERVER)
        dispatcher.on(GIE,  self.handle_gie,  DIRECTION_SERVER)
        dispatcher.on(GA,   self.handle_ga,   DIRECTION_SERVER)
        print("[FightState] Handlers registrados: GJK, GPc, GTM, GS, GIC, GTL, GIE, GA")

    def __repr__(self):
        return (
            f"<FightState fighters={len(self._fighters)} "
            f"enemies={len(self.enemies())} allies={len(self.allies())}>"
        )
