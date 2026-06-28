"""
bot.py — entry point del bot de Dofus Retro.

Modos de uso:
  python bot.py          → arranca el proxy + CombatAI (DRY_RUN según config.py)
  python tools/sniffer.py → solo sniffer, sin lógica de bot (Fase 0)

Flujo:
  1. Arranca DofusProxy (escucha en :5555 y :5556)
  2. Registra el Dispatcher con los handlers de GameState
  3. CombatAI se enlaza a los callbacks de GameState
  4. El proxy llama a dispatcher.dispatch() por cada paquete observado
  5. El Injector se activa cuando se establece la sesión de juego
"""

import sys
import time
import threading

import config
from proxy.tcp_proxy import DofusProxy
from proxy.injector import Injector
from protocol.dispatcher import Dispatcher, DIRECTION_CLIENT, DIRECTION_SERVER
from game.state import state
from game.fight import FightState
from game.combat_ai import CombatAI


def main():
    print("=" * 60)
    print("  Dofus Retro Bot — Python MITM")
    print(f"  DRY_RUN = {config.DRY_RUN}")
    print("=" * 60)

    # ── Inicializar componentes ────────────────────────────────────────
    dispatcher = Dispatcher()
    injector   = Injector()
    fight      = FightState()
    ai         = CombatAI(state, fight, injector)

    # Registrar handlers de estado del juego
    state.register_handlers(dispatcher)
    fight.register_handlers(dispatcher)

    # Conectar CombatAI a los callbacks de GameState
    ai.attach()

    # ── Proxy ─────────────────────────────────────────────────────────
    def on_packet(direction: str, raw: str):
        dispatcher.dispatch(direction, raw)

    proxy = DofusProxy(
        on_packet=on_packet,
        real_login_host=config.REAL_LOGIN_HOST,
        real_login_port=config.REAL_LOGIN_PORT,
    )
    proxy.start()

    print("\nProxy activo. Abre el cliente de Dofus y conéctate.")
    print("El cliente debe apuntar a 127.0.0.1 (edita el archivo hosts).")
    print("Ctrl+C para detener.\n")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[Bot] Deteniendo...")
        ai.detach()
        proxy.stop()
        print("[Bot] Hasta la próxima.")


if __name__ == "__main__":
    main()
