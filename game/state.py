"""
GameState — estado global de la sesión de juego.

Singleton compartido por todos los módulos.
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
        self.in_fight:      bool = False
        self.is_my_turn:    bool = False
        self.my_fighter_id: str | None = None

        # ── Callbacks para módulos downstream ─────────────────────────
        self.on_fight_start:    Callable | None = None
        self.on_my_turn:        Callable | None = None
        self.on_fight_end:      Callable | None = None
        self.on_map_changed:    Callable | None = None
        self.on_char_id_known:  Callable | None = None  # llamado con char_id al recibir ASK

    # ------------------------------------------------------------------
    # Handlers de paquetes (llamados desde Dispatcher)
    # ------------------------------------------------------------------

    def handle_ask(self, fields: list[str]):
        """
        ASK — Personaje seleccionado OK.
        Formato: ASK<char_id>|<char_name>|<level>|<breed>|<sex>|...
        El char_id también es el fighter_id en combate.
        """
        if not fields or not fields[0]:
            return
        # ASK puede venir con el id pegado al header o como primer field
        # tras la llamada del dispatcher: rest = raw[len("ASK"):] → split("|")
        # fields[0] = char_id, fields[1] = nombre, etc.
        self.char_id      = fields[0]
        self.my_fighter_id = fields[0]
        if len(fields) > 1:
            self.char_name = fields[1]
        print(f"[GameState] Personaje: id={self.char_id} nombre={self.char_name}")
        if self.on_char_id_known:
            self.on_char_id_known(self.char_id)

    def handle_gck(self, fields: list[str]):
        """
        GCK — GameCreate OK: entrada al mundo (también aparece al entrar a combate).
        Formato: GCK|<n>|<nombre>  o  GCK<mapid>  según contexto.
        Lo usamos para confirmar que estamos en el mundo.
        """
        print(f"[GameState] GCK (mundo/combate init): {fields}")

    def handle_gdm(self, fields: list[str]):
        """GDM — Datos del mapa. Formato: GDM<map_id>|<map_key>"""
        if fields:
            self.map_id = fields[0]
            print(f"[GameState] Mapa: {self.map_id}")
            if self.on_map_changed:
                self.on_map_changed(self.map_id)

    def handle_gts(self, fields: list[str]):
        """GTS — Game Turn Start. Formato: GTS<fighter_id>|<time_ms>"""
        fighter_id = fields[0] if fields else None
        print(f"[GameState] GTS raw: {fields} | my_fighter_id={self.my_fighter_id}")
        self.is_my_turn = (fighter_id == self.my_fighter_id)
        if self.is_my_turn and self.on_my_turn:
            self.on_my_turn()

    def handle_gtf(self, fields: list[str]):
        """GTF — Game Turn Finish."""
        self.is_my_turn = False

    def handle_as(self, fields: list[str]):
        """
        As — AccountStats: stats del personaje en el mundo (fuera de combate).
        Formato real (sniffer 2026-06-30):
          raw = As<nivel>|<xp_actual,xp_nivel,xp_siguiente>|<kamas>|<ap>|<iniciativa>|<energy>|<hp,maxhp>|...
          → con header 'As' (2 chars): fields[0]=nivel, fields[3]=ap, fields[6]='hp,maxhp'
        En combate usar GTM (que da ap/mp/hp por fighter, más fiable).
        """
        print(f"[GameState] As (stats) raw: {fields[:8]}")
        if not fields:
            return
        # AP: index 3 (nivel en [0], xp en [1], kamas en [2], ap en [3])
        if len(fields) > 3:
            try:
                self.ap = int(fields[3])
            except ValueError:
                pass
        # HP,MaxHP: index 6, formato "hp,maxhp"
        if len(fields) > 6 and "," in fields[6]:
            parts = fields[6].split(",")
            try:
                self.hp     = int(parts[0])
                self.max_hp = int(parts[1])
            except (ValueError, IndexError):
                pass
        if self.ap > 0:
            print(f"[GameState] As: hp={self.hp}/{self.max_hp} ap={self.ap}")

    def handle_fight_start(self, fields: list[str]):
        """GS — GameStartToPlay: inicio real de combate."""
        self.in_fight   = True
        self.is_my_turn = False
        if self.on_fight_start:
            self.on_fight_start(fields)

    def handle_fight_end(self, fields: list[str]):
        """GE — fin de combate."""
        self.in_fight   = False
        self.is_my_turn = False
        if self.on_fight_end:
            self.on_fight_end(fields)

    def handle_map(self, fields: list[str]):
        """GM — actores en el mapa; no lo usamos para posición propia aquí."""
        if self.on_map_changed:
            self.on_map_changed(fields)

    def register_handlers(self, dispatcher):
        from protocol.messages import GTS, GTF, GM, GCK, GDM, GE, ASK
        from protocol.dispatcher import DIRECTION_SERVER

        dispatcher.on(ASK, self.handle_ask,       DIRECTION_SERVER)
        dispatcher.on(GCK, self.handle_gck,       DIRECTION_SERVER)
        dispatcher.on(GDM, self.handle_gdm,       DIRECTION_SERVER)
        dispatcher.on(GTS, self.handle_gts,       DIRECTION_SERVER)
        dispatcher.on(GTF, self.handle_gtf,       DIRECTION_SERVER)
        dispatcher.on(GM,  self.handle_map,       DIRECTION_SERVER)
        dispatcher.on(GE,  self.handle_fight_end, DIRECTION_SERVER)
        dispatcher.on("As", self.handle_as,       DIRECTION_SERVER)
        # GS lo registra FightState; nos notifica via on_fight_start callback

    def __repr__(self):
        return (
            f"<GameState map={self.map_id} char={self.char_id}/{self.char_name} "
            f"hp={self.hp}/{self.max_hp} ap={self.ap} mp={self.mp} "
            f"in_fight={self.in_fight} my_turn={self.is_my_turn}>"
        )


# Instancia global compartida
state = GameState()
