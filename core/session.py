"""
Session — estado completo de una cuenta conectada.

En multicuenta cada cliente tiene su propia Session con:
  - GameState / FightState / CombatAI propios (no singletons globales)
  - Dispatcher propio (handlers no se mezclan entre cuentas)
  - Injector propio (sockets aislados)
  - ClickActuator propio (ventana propia)
  - Navigator / Inventory / Dialog / HDV propios

El Orchestrator mantiene el diccionario {session_id: Session}.
"""

from __future__ import annotations
import itertools
import threading

from game.state import GameState
from game.fight import FightState
from game.combat_ai import CombatAI
from game.inventory import Inventory
from game.dialog import DialogManager
from game.hdv import HdvManager
from game.world.navigator import Navigator
from input.actuator import ClickActuator
from protocol.dispatcher import Dispatcher
from proxy.injector import Injector

import config

# Generador de puertos de game dedicados: 5600, 5601, 5602...
_port_counter = itertools.count(5600)


class Session:
    def __init__(self, session_id: int):
        self.session_id = session_id
        self.local_game_port = next(_port_counter)

        # Credenciales de game extraídas del AYK de esta sesión
        self.real_game_host: str | None = None
        self.real_game_port: int | None = None

        # Componentes propios de esta cuenta
        self.dispatcher = Dispatcher()
        self.injector   = Injector()
        self.actuator   = ClickActuator()
        self.state      = GameState()
        self.fight      = FightState()
        self.ai         = CombatAI(self.state, self.fight, self.actuator)
        self.inventory  = Inventory()
        self.dialog     = DialogManager()
        self.hdv        = HdvManager()
        self.navigator  = Navigator(self.actuator)

        self._wired = False

    def wire(self):
        """Conecta todos los handlers y callbacks de esta sesión."""
        if self._wired:
            return
        self._wired = True

        # Registrar handlers de paquetes
        self.state.register_handlers(self.dispatcher)
        self.fight.register_handlers(self.dispatcher)
        self.inventory.register_handlers(self.dispatcher)
        self.dialog.register_handlers(self.dispatcher)
        self.hdv.register_handlers(self.dispatcher)

        # Conectar callbacks internos
        self.fight.on_fight_start        = self.state.handle_fight_start
        self.state.on_char_id_known       = self.fight.set_my_fighter_id
        # Cuando FightState resuelve char_id (via GTL[0] o ASK), sync GameState.my_fighter_id
        self.fight.on_fighter_id_resolved = lambda cid: setattr(self.state, "my_fighter_id", cid)
        self.state.on_map_changed         = self.navigator.on_map_changed

        # Arrancar IA
        self.ai.attach()

        print(f"[Session {self.session_id}] Wired. "
              f"Game port local: {self.local_game_port}")

    def on_packet(self, direction: str, raw: str):
        self.dispatcher.dispatch(direction, raw)

    def on_game_connected(self, server_sock, client_sock):
        print(f"[Session {self.session_id}] Game activo.")
        self.injector.attach(server_sock, client_sock)

    def teardown(self):
        self.ai.detach()
        self.injector.detach()
        print(f"[Session {self.session_id}] Cerrada.")
