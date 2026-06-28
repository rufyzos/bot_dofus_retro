"""
bot.py — entry point del bot de Dofus Retro.

Prerrequisito: hosts file apunta dofusretro-co-production.ankama-games.com → 127.0.0.1
Ejecutar como administrador (puerto 443).

    python bot.py

Flujo:
  1. DofusProxy escucha en :443 (login) y :5556 (game).
  2. El cliente conecta → proxy reenvía al servidor real.
  3. Al recibir AYK, el proxy reescribe host:port → 127.0.0.1:5556.
  4. Cuando la sesión de game se abre, el Injector se engancha a los sockets.
  5. Dispatcher despacha cada paquete a GameState / FightState.
  6. CombatAI reacciona via callbacks de GameState.
"""

import sys
import time
import signal
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
    print(f"  Login upstream: {config.REAL_LOGIN_HOST}:{config.REAL_LOGIN_PORT}")
    print("=" * 60)
    print()
    print("Hosts file debe tener:")
    print("  127.0.0.1  dofusretro-co-production.ankama-games.com")
    print()

    # ── Inicializar componentes ────────────────────────────────────────
    dispatcher = Dispatcher()
    injector   = Injector()
    fight      = FightState()
    ai         = CombatAI(state, fight, injector)

    state.register_handlers(dispatcher)
    fight.register_handlers(dispatcher)
    ai.attach()

    # GS lo parsea FightState (handle_gs) y luego notifica a GameState
    fight.on_fight_start = state.handle_fight_start
    # Cuando GameState recibe ASK y conoce el char_id, avisar a FightState
    state.on_char_id_known = fight.set_my_fighter_id

    # ── Proxy ─────────────────────────────────────────────────────────
    # Headers que queremos ver crudos para depurar el mapeo de IDs de combate.
    DEBUG_HEADERS = ("GS", "GTS", "GTF", "GTL", "GIC", "GIE", "GE", "As", "GA")

    def on_packet(direction: str, raw: str):
        from protocol.messages import header_of
        hdr = header_of(raw)
        if hdr in DEBUG_HEADERS:
            print(f"[RAW {direction}] {raw[:120]!r}")
        # Loguear todo C→S durante combate para capturar el formato real del cast
        if direction == "C→S" and state.in_fight:
            print(f"[CLIENT C→S] {raw[:120]!r}")
        dispatcher.dispatch(direction, raw)

    def on_game_session(server_sock, client_sock):
        """Llamado cuando la conexión al game server se establece."""
        print("[Bot] Sesión de game activa — Injector conectado.")
        injector.attach(server_sock, client_sock)

    proxy = DofusProxy(
        on_packet=on_packet,
        on_game_session=on_game_session,
        real_login_host=config.REAL_LOGIN_HOST,
        real_login_port=config.REAL_LOGIN_PORT,
    )
    proxy.start()

    print("Proxy activo. Abre el Ankama Launcher → Play.")
    print("Ctrl+C para detener.\n")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[Bot] Deteniendo...")
        ai.detach()
        injector.detach()
        proxy.stop()
        print("[Bot] Hasta la próxima.")


if __name__ == "__main__":
    main()
