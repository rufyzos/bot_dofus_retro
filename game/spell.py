"""Definición de hechizo — sin dependencias para evitar imports circulares."""


class SpellConfig:
    # Roles válidos: "attack", "heal", "buff", "summon"
    def __init__(self, spell_id: str, ap_cost: int, min_range: int, max_range: int,
                 line_of_sight: bool = True, slot_key: str = "1",
                 role: str = "attack"):
        self.spell_id = spell_id
        self.ap_cost = ap_cost
        self.min_range = min_range
        self.max_range = max_range
        self.line_of_sight = line_of_sight
        self.slot_key = slot_key
        self.role = role  # "attack" | "heal" | "buff" | "summon"

    def __repr__(self):
        return (f"<Spell {self.spell_id} role={self.role} ap={self.ap_cost} "
                f"range={self.min_range}-{self.max_range} slot={self.slot_key}>")
