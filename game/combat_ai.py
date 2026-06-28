"""
CombatAI — lógica de decisión para el turno de combate.

Flujo por turno:
  1. GameState.on_my_turn dispara play_turn()
  2. Evalúa enemigos en FightState
  3. Elige el mejor hechizo casteable (alcance + AP disponibles)
  4. Opcionalmente mueve para entrar en rango (consume MP)
  5. Castea hasta agotar AP
  6. Pasa turno con Gt

DRY_RUN (config.DRY_RUN = True): solo logea la acción, no inyecta nada.
"""

from __future__ import annotations
import threading

from game.state import GameState
from game.fight import FightState, Fighter
from game.spell import SpellConfig
from proxy.injector import Injector
from utils.timing import human_delay
import config


class CombatAI:
    def __init__(self, state: GameState, fight: FightState, injector: Injector):
        self._state = state
        self._fight = fight
        self._injector = injector
        self._lock = threading.Lock()

    def attach(self):
        """Conecta callbacks de GameState a este AI."""
        self._state.on_fight_start = self._on_fight_start
        self._state.on_my_turn     = self._play_turn
        self._state.on_fight_end   = self._on_fight_end

    def detach(self):
        self._state.on_fight_start = None
        self._state.on_my_turn     = None
        self._state.on_fight_end   = None

    # ------------------------------------------------------------------
    # Callbacks de eventos
    # ------------------------------------------------------------------

    def _on_fight_start(self, fields: list[str]):
        self._fight.reset()
        print("[CombatAI] Combate iniciado.")

    def _on_fight_end(self, fields: list[str]):
        print("[CombatAI] Combate terminado.")

    # ------------------------------------------------------------------
    # Lógica del turno
    # ------------------------------------------------------------------

    def _play_turn(self):
        with self._lock:
            print("[CombatAI] Es mi turno.")
            me = self._fight.me()
            if not me:
                print("[CombatAI] No encontré mi fighter — paso turno.")
                self._pass_turn()
                return

            remaining_ap = me.ap
            remaining_mp = me.mp
            spells: list[SpellConfig] = config.SPELLS

            for _ in range(10):  # máx 10 iteraciones para evitar bucle infinito
                enemies = self._fight.enemies()
                if not enemies:
                    print("[CombatAI] Sin enemigos vivos — paso turno.")
                    break

                target = self._choose_target(enemies, me.cell)
                if not target:
                    break

                spell = self._choose_spell(spells, remaining_ap, me.cell, target.cell)

                if spell is None:
                    # Intentar moverse para entrar en rango
                    moved = self._try_move_into_range(spells, remaining_ap,
                                                       remaining_mp, me, enemies)
                    if moved:
                        remaining_mp -= moved
                        # Recalcular posición de me
                        me = self._fight.me()
                        if not me:
                            break
                        continue
                    else:
                        print("[CombatAI] Sin hechizo casteable ni movimiento útil — paso turno.")
                        break

                # Castear
                self._cast_spell(spell, target)
                remaining_ap -= spell.ap_cost
                human_delay(config.DELAY_CAST_MS, config.DELAY_JITTER)

                if remaining_ap <= 0:
                    break

            self._pass_turn()

    def _choose_target(self, enemies: list[Fighter], my_cell: int) -> Fighter | None:
        strategy = config.TARGET_STRATEGY
        if strategy == "nearest":
            return self._fight.nearest_enemy(my_cell)
        elif strategy == "lowest_hp":
            return min(enemies, key=lambda f: f.hp)
        elif strategy == "scoring":
            return self._score_best_target(enemies, my_cell)
        return enemies[0] if enemies else None

    def _score_best_target(self, enemies: list[Fighter], my_cell: int) -> Fighter | None:
        """
        Scoring function: pondera HP bajo + proximidad.
        Mayor score = mejor objetivo.
        """
        if not enemies:
            return None

        max_hp = max(f.max_hp or 1 for f in enemies)
        max_dist = max(FightState.distance(my_cell, f.cell) for f in enemies) or 1

        def score(f: Fighter) -> float:
            hp_score   = 1.0 - (f.hp / (f.max_hp or 1))   # 1.0 = casi muerto
            dist_score = 1.0 - (FightState.distance(my_cell, f.cell) / max_dist)
            return hp_score * 0.6 + dist_score * 0.4

        return max(enemies, key=score)

    def _choose_spell(self, spells: list[SpellConfig], ap: int,
                      my_cell: int, target_cell: int) -> SpellConfig | None:
        """
        Elige el hechizo con mejor relación eficiencia/AP entre los casteables.
        Prioriza mayor alcance útil y menor coste de AP (más casts por turno).
        """
        dist = FightState.distance(my_cell, target_cell)
        candidates = [
            s for s in spells
            if s.ap_cost <= ap and s.min_range <= dist <= s.max_range
            and (not s.line_of_sight or self._fight.has_line_of_sight(my_cell, target_cell))
        ]
        if not candidates:
            return None
        # Scoring: preferir hechizo con mayor daño implícito (rango útil amplio) y menor AP
        return min(candidates, key=lambda s: s.ap_cost)

    def _try_move_into_range(self, spells: list[SpellConfig], ap: int, mp: int,
                              me: Fighter, enemies: list[Fighter]) -> int:
        """
        Usa BFS para encontrar la celda alcanzable con ≤ mp pasos que maximice
        el número de hechizos casteables. Mueve al mejor destino y retorna
        el número de pasos usados (0 si no se movió).
        """
        if mp <= 0:
            return 0

        reachable = self._fight.cells_reachable_in(me.cell, mp)
        if not reachable:
            return 0

        casteable_spells = [s for s in spells if s.ap_cost <= ap]
        if not casteable_spells:
            return 0

        best_cell = None
        best_score = -1

        for cell in reachable:
            score = sum(
                len(self._fight.enemy_in_range(cell, s.min_range, s.max_range))
                for s in casteable_spells
            )
            if score > best_score:
                best_score = score
                best_cell = cell

        if best_cell is None or best_score == 0:
            return 0

        path = self._fight.bfs_path(me.cell, best_cell)
        if not path:
            return 0

        steps = len(path)
        self._move_to_cell(best_cell)
        me.cell = best_cell  # actualización local optimista
        human_delay(config.DELAY_MOVE_MS, config.DELAY_JITTER)
        return steps

    # ------------------------------------------------------------------
    # Acciones que inyectan paquetes
    # ------------------------------------------------------------------

    def _cast_spell(self, spell: SpellConfig, target: Fighter):
        msg = f"Cast {spell} → fighter {target.id} en celda {target.cell}"
        if config.DRY_RUN:
            print(f"[CombatAI DRY_RUN] {msg}")
            return
        print(f"[CombatAI] {msg}")
        # Header de cast: [CONFIRMAR en Fase 0] — probablemente GA con acción de hechizo.
        # Formato tentativo: GA<action_id>|<spell_id>|<target_cell>
        # ACTUALIZAR tras capturar paquetes reales.
        self._injector.to_server("GA", "304", spell.spell_id, str(target.cell))

    def _move_to_cell(self, cell: int):
        msg = f"Mover a celda {cell}"
        if config.DRY_RUN:
            print(f"[CombatAI DRY_RUN] {msg}")
            return
        print(f"[CombatAI] {msg}")
        # Header de movimiento en combate: [CONFIRMAR en Fase 0]
        # Formato tentativo: GA<action_id>|<cell>
        self._injector.to_server("GA", "1", str(cell))

    def _pass_turn(self):
        human_delay(config.DELAY_PASS_TURN_MS, config.DELAY_JITTER)
        if config.DRY_RUN:
            print("[CombatAI DRY_RUN] Pasar turno (Gt)")
            return
        print("[CombatAI] Pasando turno.")
        self._injector.to_server("Gt")
