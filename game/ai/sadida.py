"""
Arquetipo Sadida — combo AoE para farmeo de grupos (Astrub Forest y similares).

Combo basado en Sadidauto (R3conS) y guías de la comunidad Dofus Retro:

  Turno 1 (posicionamiento):
    - Moverse a celda que maximice enemigos dentro del rango AoE.

  Cada turno:
    1. Earthquake  (rol "aoe")     — glifo de área, daño tierra
    2. Poisoned Wind (rol "aoe")   — AoE daño neutral, más potente
    3. Sylvan Power  (rol "self_buff") — convertirse en árbol: +PA/daño, invulnerable
    4. Bramble       (rol "attack") — remate single-target con PA sobrantes

  Reglas:
    - AoE: se elige la celda epicentro que cubra más enemigos (best_aoe_cell).
    - Sylvan Power: se castea sobre uno mismo (target = my_cell), solo si quedan PA.
    - Bramble/attack: se repite hasta agotar PA, priorizando el enemigo con menos HP.
    - Si hay un solo enemigo, Earthquake/Poisoned Wind se castean sobre su celda.

Configurar en config.py:
    ARCHETYPE = "sadida"
    SPELLS = [
        SpellConfig("X", ap_cost=4, min_range=0, max_range=6, aoe_radius=2,
                    role="aoe", slot_key="1"),          # Earthquake
        SpellConfig("X", ap_cost=3, min_range=1, max_range=6, aoe_radius=2,
                    role="aoe", slot_key="2"),          # Poisoned Wind
        SpellConfig("X", ap_cost=2, min_range=0, max_range=0,
                    role="self_buff", slot_key="3"),    # Sylvan Power (self)
        SpellConfig("X", ap_cost=3, min_range=1, max_range=5,
                    role="attack", slot_key="4"),       # Bramble
    ]
    (Rellenar spell_id "X" con los IDs reales capturados por el sniffer.)
"""

from __future__ import annotations
import config
from game.ai.base import Archetype, TurnContext
from game.ai.util import (
    lowest_hp_enemy, castable_spells, best_cast_spell, best_aoe_cell
)
from game.fight import FightState
from utils.timing import human_delay


class SadidaArchetype(Archetype):

    def play_turn(self, ctx: TurnContext) -> tuple[int, int]:
        ap_used = 0
        mp_used = 0

        # ── Turno 1: reposicionamiento ────────────────────────────────────
        if ctx.turn_number == 1:
            moved = self._reposition(ctx)
            mp_used += moved

        # ── Fase 1: hechizos AoE (Earthquake → Poisoned Wind) ────────────
        aoe_spells = [s for s in ctx.spells if s.role == "aoe"]
        for spell in aoe_spells:
            if ctx.remaining_ap < spell.ap_cost:
                continue
            result = best_aoe_cell(spell, ctx.me.cell, ctx.enemies, ctx.fight)
            if result is None:
                # Sin celda AoE casteable — intentar sobre el enemigo más cercano
                target = lowest_hp_enemy(ctx.enemies)
                if target is None:
                    continue
                dist = FightState.distance(ctx.me.cell, target.cell)
                if not (spell.min_range <= dist <= spell.max_range):
                    continue
                if spell.line_of_sight and not ctx.fight.has_line_of_sight(
                        ctx.me.cell, target.cell):
                    continue
                target_cell = target.cell
                hit_count = 1
            else:
                target_cell, hit_count = result

            print(f"[SadidaAI] AoE {spell} → celda {target_cell} "
                  f"(cubre {hit_count} enemigos)")
            ctx.actuator.cast_spell(spell.slot_key, target_cell)
            human_delay(config.DELAY_CAST_MS, config.DELAY_JITTER)
            ctx.remaining_ap -= spell.ap_cost
            ap_used += spell.ap_cost

        # ── Fase 2: Sylvan Power (self-buff) ────────────────────────────
        self_buffs = [s for s in ctx.spells if s.role == "self_buff"]
        for spell in self_buffs:
            if ctx.remaining_ap < spell.ap_cost:
                continue
            print(f"[SadidaAI] Self-buff {spell} → celda propia {ctx.me.cell}")
            ctx.actuator.cast_spell(spell.slot_key, ctx.me.cell)
            human_delay(config.DELAY_CAST_MS, config.DELAY_JITTER)
            ctx.remaining_ap -= spell.ap_cost
            ap_used += spell.ap_cost

        # ── Fase 3: Bramble — remate single-target ────────────────────────
        for _ in range(8):
            if not ctx.enemies or ctx.remaining_ap <= 0:
                break
            target = lowest_hp_enemy(ctx.enemies)
            if not target:
                break
            attacks = castable_spells(
                ctx.spells, ctx.remaining_ap,
                ctx.me.cell, target.cell, ctx.fight,
                role="attack",
            )
            spell = best_cast_spell(attacks)
            if not spell:
                break
            print(f"[SadidaAI] Remate {spell} → {target.cell} (hp={target.hp})")
            ctx.actuator.cast_spell(spell.slot_key, target.cell)
            human_delay(config.DELAY_CAST_MS, config.DELAY_JITTER)
            ctx.remaining_ap -= spell.ap_cost
            ap_used += spell.ap_cost

        return ap_used, mp_used

    # ------------------------------------------------------------------
    # Reposicionamiento de turno 1
    # ------------------------------------------------------------------

    def _reposition(self, ctx: TurnContext) -> int:
        """
        Turno 1: buscar la celda alcanzable con PM que maximice enemigos
        dentro del rango de los hechizos AoE. Si ya estamos bien posicionados
        (algún AoE cubre ≥2 enemigos) no nos movemos.
        """
        if not ctx.enemies or ctx.remaining_mp <= 0:
            return 0

        aoe_spells = [s for s in ctx.spells if s.role == "aoe"]
        if not aoe_spells:
            return 0

        # Comprobar si ya hay buena posición
        for spell in aoe_spells:
            res = best_aoe_cell(spell, ctx.me.cell, ctx.enemies, ctx.fight)
            if res and res[1] >= 2:
                return 0  # ya cubrimos ≥2 enemigos, no moverse

        # Buscar mejor celda alcanzable con PM
        reachable = ctx.fight.cells_reachable_in(ctx.me.cell, ctx.remaining_mp)
        best_move_cell: int | None = None
        best_hit: int = 0

        for cell in reachable:
            for spell in aoe_spells:
                res = best_aoe_cell(spell, cell, ctx.enemies, ctx.fight)
                if res and res[1] > best_hit:
                    best_hit = res[1]
                    best_move_cell = cell

        if best_move_cell is not None and best_hit >= 2:
            mp_cost = reachable.get(best_move_cell, 1)
            print(f"[SadidaAI] Reposicionar turno 1: "
                  f"{ctx.me.cell}→{best_move_cell} (cubre {best_hit} enemigos)")
            ctx.actuator.move_to(best_move_cell)
            human_delay(config.DELAY_MOVE_MS, config.DELAY_JITTER)
            ctx.me = type(ctx.me)(
                id=ctx.me.id,
                cell=best_move_cell,
                hp=ctx.me.hp,
                max_hp=ctx.me.max_hp,
                ap=ctx.me.ap,
                mp=ctx.me.mp - mp_cost,
                team=ctx.me.team,
                alive=ctx.me.alive,
            )
            ctx.remaining_mp -= mp_cost
            return mp_cost

        return 0
