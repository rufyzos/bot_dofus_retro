"""
Interfaz base para arquetipos de IA de combate.

Cada arquetipo implementa play_turn(ctx) y devuelve True si usó alguna acción,
False si no tiene nada más que hacer (pasar turno).
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from game.fight import FightState, Fighter
    from game.spell import SpellConfig
    from input.actuator import ClickActuator


@dataclass
class TurnContext:
    """Estado disponible durante un turno de combate."""
    me: Fighter
    enemies: list[Fighter]
    allies: list[Fighter]
    remaining_ap: int
    remaining_mp: int
    fight: FightState
    actuator: ClickActuator
    spells: list[SpellConfig]
    turn_number: int = 1


class Archetype:
    """Arquetipo de IA base. Subclasificar para cada rol."""

    def play_turn(self, ctx: TurnContext) -> tuple[int, int]:
        """
        Ejecuta las acciones del turno.
        Devuelve (ap_usados, mp_usados).
        Implementar en subclases.
        """
        raise NotImplementedError
