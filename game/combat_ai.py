"""
CombatAI — runner de turno de combate.

Construye el TurnContext y delega la decisión al Archetype configurado
en config.ARCHETYPE ("ranged", "melee", "support", "summoner").

Flujo:
  1. GameState.on_my_turn dispara _play_turn()
  2. Se construye TurnContext con el estado actual
  3. El Archetype elegido ejecuta su estrategia
  4. Se pasa turno con ClickActuator.pass_turn()

DRY_RUN (config.DRY_RUN = True): solo logea acciones, no mueve el ratón.
"""

from __future__ import annotations
import threading

from game.state import GameState
from game.fight import FightState
from game.ai.base import TurnContext
from game.ai.registry import get_archetype
from input.actuator import ClickActuator
from utils.timing import human_delay
import config

# Segundos máximos que el bot puede estar procesando un turno antes del watchdog.
# Dofus Retro tiene un timeout de ~30s por turno; usamos 25s como margen.
_TURN_TIMEOUT_S = 25


class CombatAI:
    def __init__(self, state: GameState, fight: FightState, actuator: ClickActuator):
        self._state = state
        self._fight = fight
        self._actuator = actuator
        self._lock = threading.Lock()
        self._turn_number = 0
        self._watchdog: threading.Timer | None = None

    def attach(self):
        """Conecta callbacks de GameState y FightState a este AI."""
        self._state.on_fight_start        = self._on_fight_start
        self._state.on_my_turn            = self._play_turn
        self._state.on_fight_end          = self._on_fight_end
        self._fight.on_placement_ready    = self._on_placement_ready

    def detach(self):
        self._state.on_fight_start        = None
        self._state.on_my_turn            = None
        self._state.on_fight_end          = None
        self._fight.on_placement_ready    = None

    # ------------------------------------------------------------------
    # Callbacks de eventos
    # ------------------------------------------------------------------

    def _on_placement_ready(self, available_cells: list[int]):
        """
        GP recibido — el servidor ofrece celdas de inicio.

        Estrategia de elección de celda según arquetipo:
          - ranged/sadida : celda más alejada de los enemigos (maximiza distancia inicial)
          - melee         : celda más cercana a los enemigos (menos PM gastados en turno 1)
          - support       : celda más alejada (detrás del grupo aliado)
          - summoner      : celda con más adyacentes libres (para invocar en turno 1)

        Tras elegir la celda hace click (set_placement_cell) y luego ready().
        El delay entre ambas simula tiempo humano de decisión.
        """
        if not available_cells:
            print("[CombatAI] Placement: no hay celdas disponibles — GR directo")
            human_delay(config.DELAY_PASS_TURN_MS, config.DELAY_JITTER)
            self._actuator.ready()
            return

        enemies = self._fight.enemies()
        archetype_name = getattr(config, "ARCHETYPE", "ranged")

        best_cell = self._choose_placement_cell(available_cells, enemies, archetype_name)
        print(f"[CombatAI] Placement: eligiendo celda {best_cell} "
              f"(arquetipo={archetype_name}, {len(available_cells)} disponibles)")

        # Delay de "decisión" humana antes de hacer click
        human_delay(getattr(config, "DELAY_PLACEMENT_MS", 800), config.DELAY_JITTER)
        self._actuator.set_placement_cell(best_cell)
        human_delay(getattr(config, "DELAY_PLACEMENT_MS", 500), config.DELAY_JITTER)
        self._actuator.ready()

    def _choose_placement_cell(self, cells: list[int],
                               enemies: list, archetype: str) -> int:
        """
        Elige la celda de placement óptima según el arquetipo.
        Si no hay enemigos aún (GIC no llegó), devuelve la primera celda.
        """
        if not enemies or not cells:
            return cells[0]

        if archetype in ("ranged", "sadida", "support"):
            # Maximizar distancia mínima a cualquier enemigo
            return max(
                cells,
                key=lambda c: min(
                    FightState.distance(c, e.cell) for e in enemies
                ),
            )

        if archetype == "melee":
            # Minimizar distancia al enemigo más cercano
            return min(
                cells,
                key=lambda c: min(
                    FightState.distance(c, e.cell) for e in enemies
                ),
            )

        if archetype == "summoner":
            # Maximizar celdas adyacentes libres (para invocar en turno 1)
            occupied = {e.cell for e in enemies}
            return max(
                cells,
                key=lambda c: sum(
                    1 for nb in FightState._neighbors(c)
                    if nb not in occupied and nb not in cells
                ),
            )

        # Fallback: primera celda disponible
        return cells[0]

    def _on_fight_start(self, fields: list[str]):
        self._turn_number = 0
        self._cancel_watchdog()
        me = self._fight.me()
        archetype = getattr(config, "ARCHETYPE", "ranged")
        print(f"[CombatAI] Combate iniciado — arquetipo={archetype} "
              f"me={me} enemies={len(self._fight.enemies())}")

    def _on_fight_end(self, fields: list[str]):
        print("[CombatAI] Combate terminado.")
        self._turn_number = 0
        self._cancel_watchdog()

    # ------------------------------------------------------------------
    # Watchdog de turno
    # ------------------------------------------------------------------

    def _start_watchdog(self):
        self._cancel_watchdog()
        timeout = getattr(config, "TURN_TIMEOUT_S", _TURN_TIMEOUT_S)
        self._watchdog = threading.Timer(timeout, self._watchdog_fire)
        self._watchdog.daemon = True
        self._watchdog.start()

    def _cancel_watchdog(self):
        if self._watchdog:
            self._watchdog.cancel()
            self._watchdog = None

    def _watchdog_fire(self):
        print(f"[CombatAI] ⚠ WATCHDOG: turno #{self._turn_number} excedió "
              f"{getattr(config, 'TURN_TIMEOUT_S', _TURN_TIMEOUT_S)}s — forzando pass_turn")
        self._state.is_my_turn = False
        try:
            self._actuator.pass_turn()
        except Exception as e:
            print(f"[CombatAI] Watchdog error en pass_turn: {e}")

    # ------------------------------------------------------------------
    # Runner del turno
    # ------------------------------------------------------------------

    def _play_turn(self):
        with self._lock:
            self._turn_number += 1
            self._start_watchdog()
            print(f"[CombatAI] Mi turno #{self._turn_number}")

            me = self._fight.me()
            if not me:
                print("[CombatAI] No encontré mi fighter — paso turno.")
                self._pass_turn()
                return

            enemies = self._fight.enemies()
            if not enemies:
                print("[CombatAI] Sin enemigos vivos — paso turno.")
                self._pass_turn()
                return

            # AP/MP: preferir los del fighter, luego GameState, luego config
            remaining_ap = (me.ap if me.ap > 0
                            else (self._state.ap if self._state.ap > 0
                                  else config.DEFAULT_AP))
            remaining_mp = (me.mp if me.mp > 0
                            else (self._state.mp if self._state.mp > 0
                                  else config.DEFAULT_MP))
            print(f"[CombatAI] AP={remaining_ap} MP={remaining_mp} cell={me.cell}")

            ctx = TurnContext(
                me=me,
                enemies=enemies,
                allies=self._fight.allies(),
                remaining_ap=remaining_ap,
                remaining_mp=remaining_mp,
                fight=self._fight,
                actuator=self._actuator,
                spells=config.SPELLS,
                turn_number=self._turn_number,
            )

            try:
                archetype = get_archetype()
                ap_used, mp_used = archetype.play_turn(ctx)
                print(f"[CombatAI] Turno completado — AP usados={ap_used} MP usados={mp_used}")
            except Exception as exc:
                print(f"[CombatAI] ERROR en arquetipo: {exc}")
            finally:
                self._cancel_watchdog()

            self._pass_turn()

    def _pass_turn(self):
        human_delay(config.DELAY_PASS_TURN_MS, config.DELAY_JITTER)
        print("[CombatAI] Pasando turno.")
        self._actuator.pass_turn()
