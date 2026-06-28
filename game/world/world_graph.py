"""
Grafo del mundo: conexiones entre mapas (mapa_id → vecinos por borde).

El grafo se construye por observación (modo log): cada vez que el personaje
cambia de mapa, se registra el par (origen, celda_borde, destino).

Formato de persistencia (config.WORLD_GRAPH_PATH), JSON:
{
  "<map_id>": [
    {"exit_cell": 123, "dest_map": "456789", "direction": "right"},
    ...
  ]
}

"direction": top | bottom | left | right | (vacío si se conoce solo la celda)
"""

from __future__ import annotations
import json
import os
from dataclasses import dataclass, field, asdict


@dataclass
class MapExit:
    exit_cell: int       # cellId desde el que se sale del mapa
    dest_map: str        # map_id destino
    direction: str = ""  # "top" | "bottom" | "left" | "right"


class WorldGraph:
    def __init__(self, graph_path: str):
        self._path = graph_path
        self._exits: dict[str, list[MapExit]] = {}
        self._load()

    def _load(self):
        if not os.path.exists(self._path):
            return
        try:
            with open(self._path, encoding="utf-8") as f:
                raw = json.load(f)
            for map_id, exits in raw.items():
                self._exits[str(map_id)] = [MapExit(**e) for e in exits]
        except Exception as e:
            print(f"[WorldGraph] Error cargando {self._path}: {e}")

    def _save(self):
        try:
            os.makedirs(os.path.dirname(self._path) or ".", exist_ok=True)
            raw = {
                map_id: [asdict(e) for e in exits]
                for map_id, exits in self._exits.items()
            }
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(raw, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[WorldGraph] Error guardando: {e}")

    def record_transition(self, from_map: str, exit_cell: int,
                          to_map: str, direction: str = ""):
        """Registra una transición observada entre mapas."""
        from_map = str(from_map)
        to_map   = str(to_map)
        exits = self._exits.setdefault(from_map, [])
        # Evitar duplicados
        for e in exits:
            if e.exit_cell == exit_cell and e.dest_map == to_map:
                return
        exits.append(MapExit(exit_cell=exit_cell, dest_map=to_map, direction=direction))
        print(f"[WorldGraph] Nuevo borde: {from_map} → celda {exit_cell} → {to_map}")
        self._save()

    def exits_from(self, map_id: str) -> list[MapExit]:
        return self._exits.get(str(map_id), [])

    def exit_cell_for(self, from_map: str, dest_map: str) -> int | None:
        """Devuelve la celda de salida para ir de from_map a dest_map."""
        for e in self.exits_from(from_map):
            if e.dest_map == str(dest_map):
                return e.exit_cell
        return None

    def neighbors(self, map_id: str) -> list[str]:
        return [e.dest_map for e in self.exits_from(map_id)]

    def bfs_route(self, start_map: str, goal_map: str) -> list[str]:
        """BFS en el grafo de mundo. Devuelve lista de map_ids [start,...,goal]."""
        from collections import deque
        start_map = str(start_map)
        goal_map  = str(goal_map)
        if start_map == goal_map:
            return [start_map]
        visited = {start_map}
        queue: deque[list[str]] = deque([[start_map]])
        while queue:
            path = queue.popleft()
            current = path[-1]
            for neighbor in self.neighbors(current):
                if neighbor in visited:
                    continue
                new_path = path + [neighbor]
                if neighbor == goal_map:
                    return new_path
                visited.add(neighbor)
                queue.append(new_path)
        return []  # sin ruta conocida


# Instancia global
_graph: WorldGraph | None = None


def init(graph_path: str):
    global _graph
    _graph = WorldGraph(graph_path)


def get_graph() -> WorldGraph:
    global _graph
    if _graph is None:
        _graph = WorldGraph("")
    return _graph
