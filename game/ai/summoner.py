"""
Arquetipo invocador (Osamodas, Sadida invocador).

Estrategia:
  1. Invocar si hay huecos y PA disponibles.
  2. Atacar con PA sobrantes.
"""

from __future__ import annotations
import config
from game.ai.base import Archetype, TurnContext
from game.ai.util import closest_enemy, castable_spells, best_cast_spell
from game.fight import FightState
from utils.timing import human_delay


class SummonerArchetype(Archetype):
    def play_turn(self, ctx: TurnContext) -> tuple[int, int]:
        ap_used = 0
        mp_used = 0

        max_summons = getattr(config, "MAX_SUMMONS", 3)
        # Contar invocaciones (aliados que no son "yo")
        current_summons = sum(
            1 for f in ctx.allies
            if not f.is_me and f.alive
        )

        # Paso 1: invocar si hay capacidad
        if current_summons < max_summons:
            summons = castable_spells(ctx.spells, ctx.remaining_ap,
                                     ctx.me.cell, ctx.me.cell, ctx.fight,
                                     role="summon")
            spell = best_cast_spell(summons)
            if spell:
                # Buscar celda adyacente libre
                free_cell = self._free_adjacent(ctx)
                if free_cell is not None:
                    print(f"[SummonerAI] Invocar {spell} en celda {free_cell}")
                    ctx.actuator.cast_spell(spell.slot_key, free_cell)
                    human_delay(config.DELAY_CAST_MS, config.DELAY_JITTER)
                    ctx.remaining_ap -= spell.ap_cost
                    ap_used += spell.ap_cost

        # Paso 2: atacar con PA sobrantes
        for _ in range(10):
            if not ctx.enemies or ctx.remaining_ap <= 0:
                break
            target = closest_enemy(ctx.enemies, ctx.me.cell, ctx.fight)
            if not target:
                break
            attacks = castable_spells(ctx.spells, ctx.remaining_ap,
                                      ctx.me.cell, target.cell, ctx.fight,
                                      role="attack")
            spell = best_cast_spell(attacks)
            if not spell:
                break
            print(f"[SummonerAI] Ataque {spell} → celda {target.cell}")
            ctx.actuator.cast_spell(spell.slot_key, target.cell)
            human_delay(config.DELAY_CAST_MS, config.DELAY_JITTER)
            ctx.remaining_ap -= spell.ap_cost
            ap_used += spell.ap_cost

        return ap_used, mp_used

    def _free_adjacent(self, ctx: TurnContext) -> int | None:
        occupied = {f.cell for f in ctx.fight.all_fighters() if f.alive}
        for neighbor in ctx.fight._neighbors(ctx.me.cell):
            if neighbor not in occupied:
                return neighbor
        return None
