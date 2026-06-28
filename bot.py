"""
bot.py — entry point del bot de Dofus Retro.

Prerrequisito: hosts file apunta dofusretro-co-production.ankama-games.com → 127.0.0.1
Ejecutar como administrador (puerto 443).

    python bot.py

Flujo multisesión:
  1. DofusProxy escucha en :443 (login).
  2. Cada cliente que conecta crea una Session propia con puerto game dedicado.
  3. La Session tiene sus propios GameState / FightState / CombatAI / Inventory…
  4. El Orchestrator coordina líder + mulas.
  5. Cada paquete se despacha al Dispatcher de su sesión (buffers aislados).
"""

import time

import config
from proxy.tcp_proxy import DofusProxy
from core.session import Session
from core.orchestrator import orchestrator
from game.world import map_data as map_data_mod
from game.world import world_graph as world_graph_mod

# ── Depuración: headers que se loguean en crudo ───────────────────────────────
DEBUG_HEADERS = {"GS", "GTS", "GTF", "GTL", "GIC", "GIE", "GE", "As", "GA",
                 "HG", "AT", "ATK", "AYK"}


def main():
    print("=" * 60)
    print("  Dofus Retro Bot — Python MITM Multisesión")
    print(f"  DRY_RUN   = {config.DRY_RUN}")
    print(f"  ARCHETYPE = {getattr(config, 'ARCHETYPE', 'ranged')}")
    print(f"  Login upstream: {config.REAL_LOGIN_HOST}:{config.REAL_LOGIN_PORT}")
    print("=" * 60)
    print()
    print("Hosts file debe tener:")
    print("  127.0.0.1  dofusretro-co-production.ankama-games.com")
    print()

    # ── Inicializar BD de mapas y grafo de mundo ───────────────────────
    map_data_mod.init(getattr(config, "MAP_DB_PATH", "data/maps.json"))
    world_graph_mod.init(getattr(config, "WORLD_GRAPH_PATH", "data/world_graph.json"))

    # ── Callback de creación de sesión (multisesión) ───────────────────
    def on_session_created(session_id: int):
        session = Session(session_id)
        session.wire()
        orchestrator.add_session(session)
        orchestrator.hook_session(session)

        def on_packet(direction: str, raw: str):
            from protocol.messages import header_of
            hdr = header_of(raw)
            if hdr in DEBUG_HEADERS:
                print(f"[S{session_id} RAW {direction}] {raw[:120]!r}")
            if direction == "C→S" and session.state.in_fight:
                print(f"[S{session_id} CLIENT C→S] {raw[:120]!r}")
            session.on_packet(direction, raw)

        def on_game(server_sock, client_sock):
            session.on_game_connected(server_sock, client_sock)

        return on_packet, on_game

    # ── Proxy ──────────────────────────────────────────────────────────
    proxy = DofusProxy(
        on_session_created=on_session_created,
        real_login_host=config.REAL_LOGIN_HOST,
        real_login_port=config.REAL_LOGIN_PORT,
    )
    proxy.start()

    print("Proxy activo. Abre el Ankama Launcher → Play.")
    print("Cada cuenta que conecte crea una sesión independiente.")
    print("Ctrl+C para detener.\n")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[Bot] Deteniendo...")
        proxy.stop()
        print("[Bot] Hasta la próxima.")


if __name__ == "__main__":
    main()
