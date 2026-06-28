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


class CombatAI:
    def __init__(self, state: GameState, fight: FightState, actuator: ClickActuator):
        self._state = state
        self._fight = fight
        self._actuator = actuator
        self._lock = threading.Lock()
        self._turn_number = 0

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
        self._turn_number = 0
        me = self._fight.me()
        archetype = getattr(config, "ARCHETYPE", "ranged")
        print(f"[CombatAI] Combate iniciado — arquetipo={archetype} "
              f"me={me} enemies={len(self._fight.enemies())}")

    def _on_fight_end(self, fields: list[str]):
        print("[CombatAI] Combate terminado.")
        self._turn_number = 0

    # ------------------------------------------------------------------
    # Runner del turno
    # ------------------------------------------------------------------

    def _play_turn(self):
        with self._lock:
            self._turn_number += 1
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

            self._pass_turn()

    def _pass_turn(self):
        human_delay(config.DELAY_PASS_TURN_MS, config.DELAY_JITTER)
        print("[CombatAI] Pasando turno.")
        self._actuator.pass_turn()
