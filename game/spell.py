"""Definición de hechizo — sin dependencias para evitar imports circulares."""


class SpellConfig:
    def __init__(self, spell_id: str, ap_cost: int, min_range: int, max_range: int,
                 line_of_sight: bool = True):
        self.spell_id = spell_id
        self.ap_cost = ap_cost
        self.min_range = min_range
        self.max_range = max_range
        self.line_of_sight = line_of_sight

    def __repr__(self):
        return f"<Spell {self.spell_id} ap={self.ap_cost} range={self.min_range}-{self.max_range}>"
