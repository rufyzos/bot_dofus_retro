"""
Navigator — orquesta la navegación de mundo fuera de combate.

Responsabilidades:
  1. Recibir el mapa actual (on_map_changed) y registrar cambios.
  2. Ejecutar rutas predefinidas (config.ROUTES) como secuencia de pasos.
  3. Para cada paso: A* intra-mapa → click en celda de borde → esperar GDM nuevo.
  4. Registrar transiciones observadas en WorldGraph.

Limitación actual: los clicks usan las mismas constantes de calibración del
combate (MAP_ORIGIN_*). Si la vista de mundo difiere de la de combate, puede
necesitar un segundo set de constantes.

DRY_RUN: loguea la ruta sin hacer clicks.
"""

from __future__ import annotations
import threading
import time

import config
from game.world.map_data import get_db
from game.world.pathfinding import astar
from game.world.world_graph import get_graph
from input.actuator import ClickActuator
from utils.timing import human_delay


class Navigator:
    def __init__(self, actuator: ClickActuator):
        self._actuator = actuator
        self._current_map: str | None = None
        self._prev_cell: int | None = None
        self._map_arrived = threading.Event()
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Integración con GameState
    # ------------------------------------------------------------------

    def on_map_changed(self, map_id: str):
        """Llamado por GameState cuando llega un paquete GDM con nuevo map_id."""
        with self._lock:
            prev = self._current_map
            self._current_map = str(map_id)
            print(f"[Navigator] Mapa: {prev} → {self._current_map}")
            # Registrar transición si conocemos la celda de salida anterior
            if prev and self._prev_cell is not None:
                get_graph().record_transition(prev, self._prev_cell, self._current_map)
            self._map_arrived.set()

    def on_cell_changed(self, cell: int):
        """Llamado cuando el personaje se mueve a una celda nueva (fuera de combate)."""
        self._prev_cell = cell

    # ------------------------------------------------------------------
    # Navegación a una celda de borde (cambio de mapa)
    # ------------------------------------------------------------------

    def go_to_exit_cell(self, exit_cell: int, timeout: float = 10.0) -> bool:
        """
        Calcula la ruta A* al exit_cell y hace click.
        Espera hasta timeout segundos a que llegue el nuevo GDM.
        Devuelve True si el cambio de mapa se confirmó.
        """
        map_id = self._current_map
        if map_id is None:
            print("[Navigator] go_to_exit_cell: mapa actual desconocido")
            return False

        db = get_db()
        walkable = db.walkable(map_id)
        path = astar(self._prev_cell or 0, exit_cell, walkable)

        if not path:
            print(f"[Navigator] Sin ruta a celda {exit_cell} en mapa {map_id}")
            return False

        print(f"[Navigator] Ruta a celda {exit_cell}: {path} ({len(path)} celdas)")

        if config.DRY_RUN:
            print(f"[Navigator DRY_RUN] Omitiría {len(path)} clicks para llegar a {exit_cell}")
            return False

        # Hacer click en cada celda intermedia con delay
        for cell in path[1:]:  # saltar la celda inicial
            self._actuator.move_to(cell)
            human_delay(config.DELAY_MOVE_MS, config.DELAY_JITTER)

        # Esperar confirmación GDM
        self._map_arrived.clear()
        arrived = self._map_arrived.wait(timeout=timeout)
        if not arrived:
            print(f"[Navigator] Timeout esperando GDM tras salir a celda {exit_cell}")
        return arrived

    # ------------------------------------------------------------------
    # Ejecución de ruta scripted (config.ROUTES)
    # ------------------------------------------------------------------

    def run_route(self, route: list[dict]) -> bool:
        """
        Ejecuta una ruta predefinida.

        Formato de cada paso:
          {"map": "123456", "exit_cell": 452}
          {"map": "123456", "exit_dir": "right"}   # si no hay exit_cell concreto

        Devuelve True si completó todos los pasos.
        """
        for step in route:
            dest_map = str(step.get("map", ""))
            exit_cell = step.get("exit_cell")

            if exit_cell is None:
                # Buscar en WorldGraph por dirección o destino
                graph = get_graph()
                exit_cell = graph.exit_cell_for(self._current_map or "", dest_map)
                if exit_cell is None:
                    print(f"[Navigator] Sin celda de salida conocida para ir a {dest_map}")
                    return False

            print(f"[Navigator] Paso → mapa {dest_map} vía celda {exit_cell}")
            ok = self.go_to_exit_cell(exit_cell)
            if not ok:
                return False

        return True

    # ------------------------------------------------------------------
    # Navegación automática punto a punto (usa BFS del grafo de mundo)
    # ------------------------------------------------------------------

    def navigate_to(self, dest_map: str) -> bool:
        """
        Calcula la ruta entre mapas y la ejecuta.
        Requiere que WorldGraph tenga los bordes correspondientes.
        """
        if self._current_map is None:
            print("[Navigator] Mapa actual desconocido — abortando")
            return False

        route_maps = get_graph().bfs_route(self._current_map, dest_map)
        if not route_maps:
            print(f"[Navigator] Sin ruta de {self._current_map} a {dest_map}")
            return False

        print(f"[Navigator] Ruta entre mapas: {' → '.join(route_maps)}")
        steps = []
        for i in range(len(route_maps) - 1):
            from_m = route_maps[i]
            to_m   = route_maps[i + 1]
            exit_c = get_graph().exit_cell_for(from_m, to_m)
            if exit_c is None:
                print(f"[Navigator] Sin celda de borde para {from_m} → {to_m}")
                return False
            steps.append({"map": to_m, "exit_cell": exit_c})

        return self.run_route(steps)


# Instancia global
_navigator: Navigator | None = None


def init(actuator: ClickActuator):
    global _navigator
    _navigator = Navigator(actuator)


def get_navigator() -> Navigator:
    global _navigator
    if _navigator is None:
        raise RuntimeError("Navigator no inicializado — llamar world.navigator.init(actuator)")
    return _navigator
