"""
Orchestrator — coordinación entre sesiones (líder + mulas).

Patrón bus de eventos:
  - Cada Session publica eventos vía publish(event, session, data).
  - El Orchestrator decide qué inyectar en qué sesiones en respuesta.

Eventos disponibles:
  "map_changed"   — el líder cambió de mapa; las mulas deben seguir.
  "fight_started" — el líder entró en combate; las mulas deben unirse.
  "turn_ready"    — es el turno de una mula (para sincronía de combate).
  "pods_full"     — una cuenta tiene pods al límite (ir a HDV).

Anti-detección (docs/dofus-retro-148-multicuenta.md §7):
  - Delays escalonados entre mulas (~200 ms, randomizados).
  - Jitter por cuenta para no actuar en el mismo milisegundo.
"""

from __future__ import annotations
import threading
import time

import config
from utils.timing import human_delay


class Orchestrator:
    def __init__(self):
        self._sessions: dict[int, object] = {}  # session_id → Session
        self._leader_id: int | None = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Gestión de sesiones
    # ------------------------------------------------------------------

    def add_session(self, session) -> None:
        with self._lock:
            self._sessions[session.session_id] = session
            if self._leader_id is None:
                self._leader_id = session.session_id
                print(f"[Orchestrator] Líder: sesión {session.session_id}")
            else:
                print(f"[Orchestrator] Mula: sesión {session.session_id}")

    def remove_session(self, session_id: int) -> None:
        with self._lock:
            self._sessions.pop(session_id, None)
            if self._leader_id == session_id:
                remaining = list(self._sessions)
                self._leader_id = remaining[0] if remaining else None
                print(f"[Orchestrator] Nuevo líder: {self._leader_id}")

    @property
    def leader(self):
        return self._sessions.get(self._leader_id)

    def mulas(self) -> list:
        return [s for sid, s in self._sessions.items() if sid != self._leader_id]

    # ------------------------------------------------------------------
    # Bus de eventos
    # ------------------------------------------------------------------

    def publish(self, event: str, session, data=None):
        """Publicar evento desde una sesión. Procesado en hilo separado."""
        threading.Thread(
            target=self._handle_event,
            args=(event, session, data),
            daemon=True,
        ).start()

    def _handle_event(self, event: str, session, data):
        delay_between = getattr(config, "DELAY_BETWEEN_MULES", 200)
        jitter = getattr(config, "DELAY_JITTER", 0.30)

        if event == "map_changed":
            # El líder cambió de mapa — las mulas siguen con delay escalonado
            if session.session_id != self._leader_id:
                return
            new_map = data
            print(f"[Orchestrator] Líder en mapa {new_map} — coordinando mulas")
            for i, mula in enumerate(self.mulas()):
                # Delay escalonado anti-correlación
                human_delay(delay_between * (i + 1), jitter)
                print(f"[Orchestrator] Mula {mula.session_id}: navegar a mapa {new_map}")
                # La mula usa su propio navigator
                threading.Thread(
                    target=mula.navigator.navigate_to,
                    args=(new_map,),
                    daemon=True,
                ).start()

        elif event == "fight_started":
            # Líder entró en combate
            if session.session_id != self._leader_id:
                return
            print("[Orchestrator] Líder en combate — mulas se unen")
            for i, mula in enumerate(self.mulas()):
                human_delay(delay_between * (i + 1), jitter)
                print(f"[Orchestrator] Mula {mula.session_id}: unirse al combate (GR)")
                # Las mulas ya recibirán GS/GIC normalmente si están en el mismo mapa

        elif event == "pods_full":
            account = session
            threshold = getattr(config, "HDV_PODS_THRESHOLD", 0.85)
            print(f"[Orchestrator] Sesión {account.session_id}: pods al "
                  f"{account.inventory.pods_pct:.0%} — ir a HDV/banco")

    # ------------------------------------------------------------------
    # Hooking de sesiones al bus
    # ------------------------------------------------------------------

    def hook_session(self, session) -> None:
        """Conecta los callbacks de la sesión al bus de eventos."""
        orch = self

        def _on_map(map_id: str):
            session.navigator.on_map_changed(map_id)
            orch.publish("map_changed", session, map_id)

        def _on_fight_start(fields):
            session.state.handle_fight_start(fields)
            orch.publish("fight_started", session)

        def _on_weight(used: int, max_pods: int):
            threshold = getattr(config, "HDV_PODS_THRESHOLD", 0.85)
            if max_pods > 0 and used / max_pods >= threshold:
                orch.publish("pods_full", session)

        session.state.on_map_changed    = _on_map
        session.fight.on_fight_start    = _on_fight_start
        session.inventory.on_weight     = _on_weight


# Instancia global
orchestrator = Orchestrator()
