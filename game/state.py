"""
GameState — estado global de la sesión de juego.

Patrón singleton: un solo objeto compartido por todos los módulos.
Los handlers se registran en el Dispatcher; los módulos downstream
(CombatAI) usan callbacks en lugar de registrar el mismo header dos veces.
"""

from __future__ import annotations
from typing import Callable


class GameState:
    def __init__(self):
        # ── Personaje ──────────────────────────────────────────────────
        self.char_id:   str | None = None
        self.char_name: str | None = None

        # ── Posición en el mundo ───────────────────────────────────────
        self.map_id:  str | None = None
        self.cell_id: str | None = None

        # ── Stats ─────────────────────────────────────────────────────
        self.hp:     int = 0
        self.max_hp: int = 0
        self.ap:     int = 0
        self.mp:     int = 0

        # ── Estado de combate ─────────────────────────────────────────
        self.in_fight:    bool = False
        self.is_my_turn:  bool = False
        self.my_fighter_id: str | None = None

        # ── Callbacks para módulos downstream ─────────────────────────
        # Asignados por CombatAI; no registrar con Dispatcher directamente.
        self.on_fight_start: Callable | None = None
        self.on_my_turn:     Callable | None = None
        self.on_fight_end:   Callable | None = None
        self.on_map_changed: Callable | None = None

    # ------------------------------------------------------------------
    # Handlers de paquetes (llamados desde Dispatcher)
    # ------------------------------------------------------------------

    def handle_gts(self, fields: list[str]):
        """GTS — Game Turn Start: <fighter_id>|<time_ms>"""
        fighter_id = fields[0] if fields else None
        self.is_my_turn = (fighter_id == self.my_fighter_id)
        if self.is_my_turn and self.on_my_turn:
            self.on_my_turn()

    def handle_gtf(self, fields: list[str]):
        """GTF — Game Turn Finish"""
        self.is_my_turn = False

    def handle_fight_start(self, fields: list[str]):
        """[CONFIRMAR header en Fase 0] — inicio de combate"""
        self.in_fight = True
        self.is_my_turn = False
        if self.on_fight_start:
            self.on_fight_start(fields)

    def handle_fight_end(self, fields: list[str]):
        """[CONFIRMAR header en Fase 0] — fin de combate"""
        self.in_fight = False
        self.is_my_turn = False
        if self.on_fight_end:
            self.on_fight_end(fields)

    def handle_map(self, fields: list[str]):
        """GM — movimiento/posición en mapa; actualiza map_id y cell_id."""
        # El formato exacto depende del contexto; se ajusta tras Fase 0.
        # Por ahora extraemos los primeros dos campos si están disponibles.
        if fields:
            self.map_id = fields[0]
        if len(fields) > 1:
            self.cell_id = fields[1]
        if self.on_map_changed:
            self.on_map_changed(fields)

    def register_handlers(self, dispatcher):
        """Registra todos los handlers de GameState en el dispatcher."""
        from protocol.messages import GTS, GTF, GM, FIGHT_START, FIGHT_END
        from protocol.dispatcher import DIRECTION_SERVER

        dispatcher.on(GTS,         self.handle_gts,         DIRECTION_SERVER)
        dispatcher.on(GTF,         self.handle_gtf,         DIRECTION_SERVER)
        dispatcher.on(GM,          self.handle_map,         DIRECTION_SERVER)
        dispatcher.on(FIGHT_START, self.handle_fight_start, DIRECTION_SERVER)
        dispatcher.on(FIGHT_END,   self.handle_fight_end,   DIRECTION_SERVER)

    def __repr__(self):
        return (
            f"<GameState map={self.map_id} cell={self.cell_id} "
            f"hp={self.hp}/{self.max_hp} ap={self.ap} mp={self.mp} "
            f"in_fight={self.in_fight} my_turn={self.is_my_turn}>"
        )


# Instancia global compartida
state = GameState()
