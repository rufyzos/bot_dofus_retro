"""
Arquetipo a distancia (Cra, Sadida ofensivo, etc.).

Estrategia:
  1. Si el enemigo más cercano está dentro de SAFE_DIST, alejarse (kiting).
  2. Mientras tenga AP: castear hechizo de ataque con mejor rango/LOS.
  3. Si sin hechizo casteable y tiene MP: moverse a celda desde la que pueda castear.
"""

from __future__ import annotations
import config
from game.ai.base import Archetype, TurnContext
from game.ai.util import closest_enemy, castable_spells, best_cast_spell
from game.fight import FightState
from utils.timing import human_delay


class RangedArchetype(Archetype):
    def play_turn(self, ctx: TurnContext) -> tuple[int, int]:
        ap_used = 0
        mp_used = 0

        safe_dist = getattr(config, "SAFE_DIST", 2)

        for _ in range(10):
            if not ctx.enemies:
                break

            target = closest_enemy(ctx.enemies, ctx.me.cell, ctx.fight)
            if not target:
                break

            dist_to_target = FightState.distance(ctx.me.cell, target.cell)

            # Paso 1: kiting — si el enemigo está demasiado cerca, alejarse
            if dist_to_target <= safe_dist and ctx.remaining_mp > 0:
                flee_cell = self._flee_cell(ctx, target)
                if flee_cell is not None:
                    path = ctx.fight.bfs_path(ctx.me.cell, flee_cell)
                    cost = len(path)
                    if cost > 0 and cost <= ctx.remaining_mp:
                        print(f"[RangedAI] Kiting: alejándose a celda {flee_cell}")
                        ctx.actuator.move_to(flee_cell)
                        human_delay(config.DELAY_MOVE_MS, config.DELAY_JITTER)
                        ctx.me.cell = flee_cell
                        ctx.remaining_mp -= cost
                        mp_used += cost
                        continue

            # Paso 2: castear
            castable = castable_spells(ctx.spells, ctx.remaining_ap,
                                       ctx.me.cell, target.cell, ctx.fight,
                                       role="attack")
            spell = best_cast_spell(castable)
            if spell:
                print(f"[RangedAI] Cast {spell} → celda {target.cell}")
                ctx.actuator.cast_spell(spell.slot_key, target.cell)
                human_delay(config.DELAY_CAST_MS, config.DELAY_JITTER)
                ctx.remaining_ap -= spell.ap_cost
                ap_used += spell.ap_cost
                continue

            # Paso 3: moverse para entrar en rango
            moved = self._move_into_range(ctx, target)
            if moved:
                ctx.remaining_mp -= moved
                mp_used += moved
                # Recalcular posición
                me_f = ctx.fight.me()
                if me_f:
                    ctx.me = me_f
                continue

            break  # sin acción posible

        return ap_used, mp_used

    def _flee_cell(self, ctx: TurnContext, threat) -> int | None:
        """Busca la celda alcanzable más lejana del enemigo."""
        reachable = ctx.fight.cells_reachable_in(ctx.me.cell, ctx.remaining_mp)
        if not reachable:
            return None
        return max(reachable, key=lambda c: FightState.distance(c, threat.cell))

    def _move_into_range(self, ctx: TurnContext, target) -> int:
        """Mueve al personaje a la celda casteable más cercana. Devuelve MP usados."""
        if ctx.remaining_mp <= 0:
            return 0
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
            return 0

        path = ctx.fight.bfs_path(ctx.me.cell, best_cell)
        cost = len(path)
        if cost == 0:
            return 0

        print(f"[RangedAI] Moviéndose a celda {best_cell} ({cost} PM)")
        ctx.actuator.move_to(best_cell)
        human_delay(config.DELAY_MOVE_MS, config.DELAY_JITTER)
        ctx.me.cell = best_cell
        return cost
