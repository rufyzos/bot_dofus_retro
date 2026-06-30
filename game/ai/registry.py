"""
Registro de arquetipos: mapea config.ARCHETYPE → instancia de Archetype.

Uso en CombatAI:
    from game.ai.registry import get_archetype
    archetype = get_archetype()
    ap_used, mp_used = archetype.play_turn(ctx)
"""

from __future__ import annotations
import config
from game.ai.base import Archetype
from game.ai.ranged import RangedArchetype
from game.ai.melee import MeleeArchetype
from game.ai.support import SupportArchetype
from game.ai.summoner import SummonerArchetype
from game.ai.sadida import SadidaArchetype

_REGISTRY: dict[str, type[Archetype]] = {
    "ranged":   RangedArchetype,
    "melee":    MeleeArchetype,
    "support":  SupportArchetype,
    "summoner": SummonerArchetype,
    "sadida":   SadidaArchetype,
}


def get_archetype() -> Archetype:
    name = getattr(config, "ARCHETYPE", "ranged")
    cls = _REGISTRY.get(name)
    if cls is None:
        valid = ", ".join(_REGISTRY)
        raise ValueError(f"ARCHETYPE='{name}' desconocido. Válidos: {valid}")
    return cls()
