"""
Inventario — gestión de ítems y pods del personaje.

Parsea paquetes S→C:
  OAK  — objeto añadido (id|modelo|cantidad|efectos)
  OR   — objeto eliminado (id)
  OQ   — cambio de cantidad (id|cantidad)
  Ow   — pods usados/máximos (usados|max)

Expone callbacks:
  on_item_added(item)
  on_item_removed(item_id)
  on_weight(used, max)
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Callable


@dataclass
class Item:
    uid: str        # ID único del objeto en inventario
    model_id: str   # ID de plantilla del objeto
    qty: int        # Cantidad
    effects: str    # Efectos en crudo (str separado por ,)


class Inventory:
    def __init__(self):
        self._items: dict[str, Item] = {}  # uid → Item
        self.pods_used: int = 0
        self.pods_max:  int = 1000

        self.on_item_added:   Callable[[Item], None] | None = None
        self.on_item_removed: Callable[[str], None] | None = None
        self.on_weight:       Callable[[int, int], None] | None = None

    # ------------------------------------------------------------------
    # Acceso
    # ------------------------------------------------------------------

    def all_items(self) -> list[Item]:
        return list(self._items.values())

    def find_by_model(self, model_id: str) -> list[Item]:
        return [i for i in self._items.values() if i.model_id == str(model_id)]

    def total_qty(self, model_id: str) -> int:
        return sum(i.qty for i in self.find_by_model(model_id))

    @property
    def pods_pct(self) -> float:
        if self.pods_max == 0:
            return 0.0
        return self.pods_used / self.pods_max

    # ------------------------------------------------------------------
    # Handlers de paquetes
    # ------------------------------------------------------------------

    def handle_oak(self, fields: list[str]):
        """
        OAK — objeto añadido.
        Formato aproximado: OAK<uid>|<model_id>|<qty>|<efectos>
        """
        if not fields:
            return
        uid      = fields[0]
        model_id = fields[1] if len(fields) > 1 else ""
        try:
            qty = int(fields[2]) if len(fields) > 2 else 1
        except ValueError:
            qty = 1
        effects  = fields[3] if len(fields) > 3 else ""

        item = Item(uid=uid, model_id=model_id, qty=qty, effects=effects)
        self._items[uid] = item
        print(f"[Inventory] +objeto uid={uid} model={model_id} qty={qty}")
        if self.on_item_added:
            self.on_item_added(item)

    def handle_or(self, fields: list[str]):
        """OR — objeto eliminado. Formato: OR<uid>"""
        if not fields:
            return
        uid = fields[0]
        removed = self._items.pop(uid, None)
        if removed:
            print(f"[Inventory] -objeto uid={uid}")
            if self.on_item_removed:
                self.on_item_removed(uid)

    def handle_oq(self, fields: list[str]):
        """OQ — cambio de cantidad. Formato: OQ<uid>|<qty>"""
        if len(fields) < 2:
            return
        uid = fields[0]
        try:
            qty = int(fields[1])
        except ValueError:
            return
        if uid in self._items:
            self._items[uid].qty = qty
            print(f"[Inventory] qty uid={uid} → {qty}")

    def handle_ow(self, fields: list[str]):
        """Ow — pods. Formato: Ow<usados>|<max>"""
        try:
            self.pods_used = int(fields[0]) if fields else 0
            self.pods_max  = int(fields[1]) if len(fields) > 1 else 1000
        except ValueError:
            pass
        print(f"[Inventory] Pods: {self.pods_used}/{self.pods_max} "
              f"({self.pods_pct:.0%})")
        if self.on_weight:
            self.on_weight(self.pods_used, self.pods_max)

    def register_handlers(self, dispatcher):
        from protocol.messages import OAK, OR, OQ, Ow
        from protocol.dispatcher import DIRECTION_SERVER
        dispatcher.on(OAK, self.handle_oak, DIRECTION_SERVER)
        dispatcher.on(OR,  self.handle_or,  DIRECTION_SERVER)
        dispatcher.on(OQ,  self.handle_oq,  DIRECTION_SERVER)
        dispatcher.on(Ow,  self.handle_ow,  DIRECTION_SERVER)
        print("[Inventory] Handlers registrados: OAK, OR, OQ, Ow")


# Instancia global compartida
inventory = Inventory()
