"""
Arquetipo cuerpo a cuerpo (Iop, Sacrieur, Ecaflip, Ouginak).

Estrategia:
  1. Buff en turno 1 si hay hechizo de rol "buff".
  2. Acercarse al objetivo hasta estar a rango del hechizo melee.
  3. Vaciar PA en el objetivo.
"""

from __future__ import annotations
import config
from game.ai.base import Archetype, TurnContext
from game.ai.util import lowest_hp_enemy, closest_enemy, castable_spells, best_cast_spell
from game.fight import FightState
from utils.timing import human_delay


class MeleeArchetype(Archetype):
    def play_turn(self, ctx: TurnContext) -> tuple[int, int]:
        ap_used = 0
        mp_used = 0

        # Buff en turno 1
        if ctx.turn_number == 1:
            buff_castable = castable_spells(ctx.spells, ctx.remaining_ap,
                                            ctx.me.cell, ctx.me.cell, ctx.fight,
                                            role="buff")
            spell = best_cast_spell(buff_castable)
            if spell:
                print(f"[MeleeAI] Buff turno 1: {spell}")
                ctx.actuator.cast_spell(spell.slot_key, ctx.me.cell)
                human_delay(config.DELAY_CAST_MS, config.DELAY_JITTER)
                ctx.remaining_ap -= spell.ap_cost
                ap_used += spell.ap_cost

        for _ in range(10):
            if not ctx.enemies:
                break

            target = lowest_hp_enemy(ctx.enemies) or closest_enemy(ctx.enemies, ctx.me.cell, ctx.fight)
            if not target:
                break

            # Intentar castear
            castable = castable_spells(ctx.spells, ctx.remaining_ap,
                                       ctx.me.cell, target.cell, ctx.fight,
                                       role="attack")
            spell = best_cast_spell(castable)
            if spell:
                print(f"[MeleeAI] Cast {spell} → celda {target.cell}")
                ctx.actuator.cast_spell(spell.slot_key, target.cell)
                human_delay(config.DELAY_CAST_MS, config.DELAY_JITTER)
                ctx.remaining_ap -= spell.ap_cost
                ap_used += spell.ap_cost
                continue

            # Sin hechizo: acercarse
            if ctx.remaining_mp > 0:
                moved = self._move_toward(ctx, target)
                if moved:
                    ctx.remaining_mp -= moved
                    mp_used += moved
                    me_f = ctx.fight.me()
                    if me_f:
                        ctx.me = me_f
                    continue

            break

        return ap_used, mp_used

    def _move_toward(self, ctx: TurnContext, target) -> int:
        """Mueve hacia el objetivo buscando la celda desde la que pueda castear."""
        reachable = ctx.fight.cells_reachable_in(ctx.me.cell, ctx.remaining_mp)
        best_cell = None
        best_cost = ctx.remaining_mp + 1

        for cell in reachable:
            for spell in ctx.spells:
                if spell.role != "attack" or spell.ap_cost > ctx.remaining_ap:
                    continue
                dist = FightState.distance(cell, target.cell)
                if not (spell.min_range <= dist <= spell.max_range):
                    continue
                if spell.line_of_sight and not ctx.fight.has_line_of_sight(cell, target.cell):
                    continue
                path = ctx.fight.bfs_path(ctx.me.cell, cell)
                cost = len(path)
                if cost < best_cost:
                    best_cost = cost
                    best_cell = cell
                break

        if best_cell is None:
            # Al menos acercarse al máximo posible
            best_cell = min(reachable,
                            key=lambda c: FightState.distance(c, target.cell),
                            default=None)
            if best_cell is None:
                return 0
            path = ctx.fight.bfs_path(ctx.me.cell, best_cell)
            best_cost = len(path)

        if best_cost == 0:
            return 0

        print(f"[MeleeAI] Acercándose a celda {best_cell} ({best_cost} PM)")
        ctx.actuator.move_to(best_cell)
        human_delay(config.DELAY_MOVE_MS, config.DELAY_JITTER)
        ctx.me.cell = best_cell
        return best_cost
