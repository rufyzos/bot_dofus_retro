"""
Gestión de datos de celdas por mapa (mov/los).

Estrategia: BD local de mapas dumpeados en JSON.
Formato del fichero (config.MAP_DB_PATH):
{
  "<map_id>": {
    "cells": [
      {"id": 0, "mov": true,  "los": true},
      {"id": 1, "mov": false, "los": true},
      ...
    ]
  }
}

Si un map_id no está en la BD, se registra para dumpearlo y se devuelve
un mapa "todo transitable" como fallback (permite al bot funcionar aunque
sin datos reales de mov/los).

El descifrado de archivos .swf del cliente queda como mejora futura
(ver docs/dofus-retro-148-mapas-celdas.md §4).
"""

from __future__ import annotations
import json
import os
from dataclasses import dataclass

from game.world.map_geometry import MAP_CELLS


@dataclass
class CellData:
    id: int
    mov: bool   # ¿se puede caminar?
    los: bool   # ¿bloquea línea de visión?


class MapDatabase:
    def __init__(self, db_path: str):
        self._db_path = db_path
        self._cache: dict[str, list[CellData]] = {}
        self._missing: set[str] = set()
        self._load()

    def _load(self):
        if not os.path.exists(self._db_path):
            return
        try:
            with open(self._db_path, encoding="utf-8") as f:
                raw = json.load(f)
            for map_id, data in raw.items():
                cells = [
                    CellData(id=c["id"], mov=c.get("mov", True), los=c.get("los", True))
                    for c in data.get("cells", [])
                ]
                self._cache[str(map_id)] = cells
        except Exception as e:
            print(f"[MapDB] Error cargando {self._db_path}: {e}")

    def get_cells(self, map_id: str) -> list[CellData]:
        """
        Devuelve los datos de las 560 celdas del mapa.
        Si no está en BD, registra como missing y devuelve fallback (todo transitable).
        """
        map_id = str(map_id)
        if map_id in self._cache:
            return self._cache[map_id]

        if map_id not in self._missing:
            self._missing.add(map_id)
            print(f"[MapDB] Mapa {map_id} no en BD — usando fallback todo-transitable. "
                  f"Añadir a {self._db_path} para datos reales.")

        # Fallback: todas las celdas transitables
        fallback = [CellData(id=i, mov=True, los=True) for i in range(MAP_CELLS)]
        return fallback

    def walkable(self, map_id: str) -> set[int]:
        """Conjunto de cellIds transitables del mapa."""
        return {c.id for c in self.get_cells(map_id) if c.mov}

    def blocks_los(self, map_id: str) -> set[int]:
        """Conjunto de cellIds que bloquean línea de visión."""
        return {c.id for c in self.get_cells(map_id) if not c.los}

    @property
    def missing_maps(self) -> set[str]:
        return set(self._missing)


# Instancia global — inicializada en bot.py cuando se conoce MAP_DB_PATH
_db: MapDatabase | None = None


def init(db_path: str):
    global _db
    _db = MapDatabase(db_path)


def get_db() -> MapDatabase:
    global _db
    if _db is None:
        # Fallback lazy: BD vacía
        _db = MapDatabase("")
    return _db
