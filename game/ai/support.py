"""
Arquetipo soporte/curador (Eniripsa, Feca, Pandawa).

Estrategia:
  1. Curar al aliado más herido si está por debajo del umbral HEAL_THRESHOLD.
  2. Buff/armadura al aliado con más daño.
  3. Con PA sobrantes, atacar al enemigo más débil.
"""

from __future__ import annotations
import config
from game.ai.base import Archetype, TurnContext
from game.ai.util import (closest_enemy, most_wounded_ally,
                           castable_spells, best_cast_spell)
from game.fight import FightState
from utils.timing import human_delay


class SupportArchetype(Archetype):
    def play_turn(self, ctx: TurnContext) -> tuple[int, int]:
        ap_used = 0
        mp_used = 0

        heal_threshold = getattr(config, "HEAL_THRESHOLD", 0.6)

        # Paso 1: curar aliados heridos
        for _ in range(5):
            wounded = most_wounded_ally(ctx.allies)
            if wounded is None:
                break
            hp_pct = wounded.hp / (wounded.max_hp or 1)
            if hp_pct >= heal_threshold:
                break
            heals = castable_spells(ctx.spells, ctx.remaining_ap,
                                    ctx.me.cell, wounded.cell, ctx.fight,
                                    role="heal")
            spell = best_cast_spell(heals)
            if not spell:
                break
            print(f"[SupportAI] Curando a {wounded.id} (HP {hp_pct:.0%}): {spell}")
            ctx.actuator.cast_spell(spell.slot_key, wounded.cell)
            human_delay(config.DELAY_CAST_MS, config.DELAY_JITTER)
            ctx.remaining_ap -= spell.ap_cost
            ap_used += spell.ap_cost
            wounded.hp = min(wounded.max_hp, wounded.hp + 1)  # estimación local

        # Paso 2: buff al turno 1 sobre sí mismo o aliado
        if ctx.turn_number == 1 and ctx.remaining_ap > 0:
            buffs = castable_spells(ctx.spells, ctx.remaining_ap,
                                    ctx.me.cell, ctx.me.cell, ctx.fight,
                                    role="buff")
            spell = best_cast_spell(buffs)
            if spell:
                print(f"[SupportAI] Buff: {spell}")
                ctx.actuator.cast_spell(spell.slot_key, ctx.me.cell)
                human_delay(config.DELAY_CAST_MS, config.DELAY_JITTER)
                ctx.remaining_ap -= spell.ap_cost
                ap_used += spell.ap_cost

        # Paso 3: atacar con PA sobrantes
        for _ in range(5):
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
            print(f"[SupportAI] Ataque secundario {spell} → celda {target.cell}")
            ctx.actuator.cast_spell(spell.slot_key, target.cell)
            human_delay(config.DELAY_CAST_MS, config.DELAY_JITTER)
            ctx.remaining_ap -= spell.ap_cost
            ap_used += spell.ap_cost

        return ap_used, mp_used
