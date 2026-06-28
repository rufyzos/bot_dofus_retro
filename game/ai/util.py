"""Helpers compartidos por todos los arquetipos de IA."""

from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from game.fight import FightState, Fighter
    from game.spell import SpellConfig


def closest_enemy(enemies: list[Fighter], from_cell: int,
                  fight: FightState) -> Fighter | None:
    if not enemies:
        return None
    return min(enemies, key=lambda f: fight.distance(from_cell, f.cell))


def lowest_hp_enemy(enemies: list[Fighter]) -> Fighter | None:
    if not enemies:
        return None
    return min(enemies, key=lambda f: f.hp)


def most_wounded_ally(allies: list[Fighter]) -> Fighter | None:
    if not allies:
        return None
    return min(allies, key=lambda f: (f.hp / (f.max_hp or 1)))


def castable_spells(spells: list[SpellConfig], ap: int,
                    my_cell: int, target_cell: int,
                    fight: FightState, role: str | None = None) -> list[SpellConfig]:
    """Hechizos casteables: AP suficiente, rango válido y LOS si requerida."""
    from game.fight import FightState as FS
    dist = FS.distance(my_cell, target_cell)
    result = []
    for s in spells:
        if role is not None and s.role != role:
            continue
        if s.ap_cost > ap:
            continue
        if not (s.min_range <= dist <= s.max_range):
            continue
        if s.line_of_sight and not fight.has_line_of_sight(my_cell, target_cell):
            continue
        result.append(s)
    return result


def best_cast_spell(spells: list[SpellConfig]) -> SpellConfig | None:
    """De los hechizos casteables, elige el de menor coste AP (más casts/turno)."""
    if not spells:
        return None
    return min(spells, key=lambda s: s.ap_cost)
