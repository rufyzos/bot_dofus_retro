# Plan de implementación de mejoras del bot Dofus Retro 1.48

## Context

El bot (`bot.py` + `proxy/` + `protocol/` + `game/` + `input/`) hoy hace **solo combate básico monocuenta**: lee el estado de combate por paquetes S→C (MITM) y actúa por **clicks de ratón** (`ClickActuator`), no por inyección de paquetes C→S. Esta elección es deliberada y correcta según [docs/dofus-retro-148-anticheat-2026.md](dofus-retro-148-anticheat-2026.md): el cliente firma los paquetes salientes, y reescribirlos = baneo. Por eso el **modelo confirmado es híbrido**: *leer siempre por paquetes, actuar siempre por clicks/teclas*.

Existen 6 documentos de mejoras en `docs/` que describen funcionalidad aún no implementada. Se quieren abordar las 4 áreas: **(1) movimiento en combate, (2) navegación de mundo + pathfinding, (3) IA de combate por arquetipo/clase, (4) HDV + inventario + multicuenta**.

Estado actual relevante (verificado en código):
- `game/fight.py` YA tiene geometría isométrica: `cell_to_xy`, `distance`, `bfs_path`, `cells_reachable_in`, `has_line_of_sight`. **No hay que reimplementarla.**
- `input/coords.py::cell_to_screen` + calibración (`tools/calibrate.py`, `config.MAP_ORIGIN_*`) ya convierten celda→píxel.
- `combat_ai.py::_try_move_into_range` y `actuator.move_to` son TODO (retornan 0 / log).
- El proxy (`proxy/tcp_proxy.py`) es **monosesión** de game; no parsea `GDM` más allá del `map_id`; no hay HDV/inventario/diálogos/orquestador.
- Patrón de diseño obligado (CLAUDE.md): **un handler por (dirección, header)**; módulos downstream se enganchan vía callbacks en `GameState`, no registran handlers duplicados.

El resultado buscado es cerrar el ciclo de farmeo (navegar → combatir bien → vender), por fases incrementales que mantengan `DRY_RUN` y la arquitectura de callbacks existente.

---

## Principios que el plan respeta

1. **Híbrido fijo**: estado por paquetes S→C; acción por clicks/teclas vía `ClickActuator`. Nunca reescribir/inyectar paquetes C→S firmados.
2. **No reinventar geometría**: reusar `game/fight.py` (`cell_to_xy`, `distance`, `bfs_path`, `has_line_of_sight`) y `input/coords.py`.
3. **Callbacks en `GameState`, no handlers duplicados** (evita el `ValueError` del Dispatcher).
4. **`DRY_RUN` siempre**: cada acción nueva loguea en seco antes de tocar la ventana.
5. **Anti-detección desde el inicio**: todo delay pasa por `utils/timing.human_delay`; jitter de celda y de timing en cada acción.

---

## Fase 1 — Movimiento en combate (gap más inmediato)

Completa lo que ya está casi montado. **No requiere nuevos ficheros.**

- `input/actuator.py::ClickActuator.move_to(cell)`: implementar como click en el píxel de la celda destino (`cell_to_screen`) + `human_delay(DELAY_MOVE_MS)`. Respetar `DRY_RUN`.
- `game/combat_ai.py::_try_move_into_range(...)`: reemplazar el `return 0` por lógica real:
  1. Calcular celdas alcanzables con `fight.cells_reachable_in(me.cell, remaining_mp)` (ya existe).
  2. Para cada enemigo objetivo, encontrar la celda alcanzable desde la que **algún hechizo de `config.SPELLS` quede casteable** (rango + LOS con `has_line_of_sight`).
  3. Elegir la celda que minimice MP gastado (o que maximice distancia de kiting según arquetipo — se conecta en Fase 2).
  4. Devolver el nº de MP consumidos para que `_play_turn` actualice `remaining_mp`.
- Tras moverse, `_play_turn` ya recalcula `me` y reintenta el bucle (la estructura del `for _ in range(10)` ya lo soporta).

**Config nueva**: ninguna imprescindible; reusar `DELAY_MOVE_MS`, `DELAY_JITTER`.

**Verificación**: en `DRY_RUN`, provocar un combate donde el enemigo esté fuera de rango y confirmar en logs la secuencia `cells_reachable_in → celda elegida → move_to(px,py) → cast`.

---

## Fase 2 — IA de combate por arquetipo/clase

Generaliza la IA genérica actual a arquetipos parametrizados, sin romper el flujo de `_play_turn`. Basado en [docs/dofus-retro-148-ia-combate-clases.md](dofus-retro-148-ia-combate-clases.md) (5 arquetipos: distancia/melee/soporte/invocador/utilidad).

**Ficheros nuevos:**
```
game/ai/
├── __init__.py
├── base.py        # Archetype: interfaz play_turn(ctx) → lista de Action
├── ranged.py      # Cra/distancia: kiting (alejarse si enemigo cerca) + pegar a rango
├── melee.py       # Iop/Sacri: acercarse + buff turno 1 + vaciar PA
├── support.py     # Eni/Feca: curar aliado herido + armadura/buff + pegar
├── summoner.py    # Osa/Sadida: invocar si hay huecos + pegar
└── registry.py    # mapea config.ARCHETYPE → clase de Archetype
```

**Refactor de `combat_ai.py`**: `CombatAI` pasa a ser el **runner** que construye un contexto de turno (`me`, `enemies`, `allies`, `remaining_ap/mp`, `fight`, `actuator`) y delega la decisión al `Archetype` configurado. Las funciones actuales (`_choose_target`, `_choose_spell`, `_score_best_target`) se mueven a helpers reutilizables por los arquetipos (p.ej. `game/ai/util.py`: `closest_enemy`, `lowest_hp_enemy`, `castable_spells`).

**Tabla de hechizos por clase** (`config.py` o `game/spells_table.py`): extender `SpellConfig` con `role` (attack/heal/buff/summon) y opcionalmente `class_id`. Mantener la lista `SPELLS` manual (el .md confirma que los spell_ids se sacan por log/API, no hay fuente automática).

**Config nueva en `config.py`**: `ARCHETYPE = "ranged"` (o melee/support/summoner), `SAFE_DIST`, `HEAL_THRESHOLD`, `MAX_SUMMONS`.

**Verificación**: con `ARCHETYPE="ranged"` y un enemigo adyacente, confirmar en log que primero se aleja (kiting) y luego castea; cambiar a `"melee"` y confirmar que se acerca.

---

## Fase 3 — Navegación de mundo + pathfinding (bloque grande)

Mover el bot entre celdas fuera de combate y entre mapas. Basado en [docs/dofus-retro-148-mapas-celdas.md](dofus-retro-148-mapas-celdas.md). **Actuación por clicks** (click en celda destino; el cliente real calcula y firma el `GA` de movimiento).

**Ficheros nuevos:**
```
game/world/
├── __init__.py
├── map_geometry.py   # cellId↔(x,y) y distancia para mapa COMPLETO (560 celdas, no solo combate)
├── map_data.py       # parse de GDM (mapId|dateKey|encryptedData); carga de celdas mov/los
├── pathfinding.py    # A* intra-mapa sobre celdas mov=true (8 direcciones, coste HV vs D)
├── world_graph.py    # grafo mapa→mapa (borde/dirección), construido por observación (modo log)
└── navigator.py      # orquesta: ir a (mapId/coords) → A* intra-mapa → click → esperar GDM nuevo
```

**Datos de mapa (decisión clave)**: el .md indica que los datos de celda (`mov`/`los`) vienen **cifrados** en `GDM` y se descifran con los `.swf` del cliente instalado. Para evitar el coste de descifrado, el plan recomienda **empezar con una BD de mapas dumpeada** (mapId → celdas mov/los) cargada a fichero local, y dejar el descifrado SWF como mejora posterior. `map_data.py` expone una interfaz `get_cells(map_id)` que primero busca en la BD local; si falta, registra el `map_id` para dumpearlo.

**Integración**:
- `GameState` ya parsea `map_id` de `GDM` ([game/state.py:72](../game/state.py#L72)); extender para exponer `on_map_changed` con `map_id` y disparar el `Navigator`.
- `Navigator` decide la celda de borde (cambio de mapa) y hace click vía un nuevo `actuator.move_to_world_cell(cell)` (mismo `cell_to_screen`, distinto contexto de calibración fuera de combate — puede requerir un segundo set de constantes `MAP_ORIGIN_*` para vista de mapa-mundo).
- Zaaps (`WU`/diálogo): se modelan como interacción PNJ (ver Fase 4, diálogos) + selección de destino.

**Config nueva**: `ROUTES` (lista de pasos `{map, exit_dir/exit_cell}`) estilo script de trayecto; ruta de la BD de mapas.

**Verificación**: en `DRY_RUN`, cargar un `map_id` conocido, pedir al `Navigator` ir a una celda de borde, y confirmar A* → secuencia de celdas → click destino. Validar cambio de mapa observando el nuevo `GDM`.

---

## Fase 4 — Inventario + HDV + multicuenta

Cierra el ciclo de farmeo. Basado en [docs/dofus-retro-148-hdv.md](dofus-retro-148-hdv.md) y [docs/dofus-retro-148-multicuenta.md](dofus-retro-148-multicuenta.md).

### 4a. Inventario y diálogos PNJ (cimiento de HDV)
**Ficheros nuevos:**
```
game/inventory.py   # parse OAK/OR/OQ/Ow → estado de items + pods. Callbacks on_item_added, on_weight
game/dialog.py      # máquina de estados PNJ: DC→DCK, DQ→DR; helpers para abrir HDV/zaap
```
Registrar handlers S→C (`OAK`, `OR`, `OQ`, `Ow`, `DCK`, `DQ`) en el Dispatcher; añadir constantes en `protocol/messages.py`. Actuación (elegir opción de diálogo, abrir HDV) **por clicks** sobre la UI.

### 4b. HDV
**Fichero nuevo:** `game/hdv.py` — flujos VENDER/COMPRAR del .md como secuencias de clicks, con:
- Lectura de precios por paquetes S→C (`EHl`, `EHP` precio medio).
- **Validación de lote x1/x10/x100 obligatoria** antes de confirmar (el error de lote es la pérdida más cara — sección 9 del .md).
- Estrategia de precio configurable (`config.HDV_PRICE_STRATEGY`: `"middle_pct"` recomendado sobre `"-1kama"`), cálculo de rentabilidad con taxa 2%.
- Refrescos espaciados y aleatorios (`human_delay`) anti-detección.

### 4c. Multicuenta (el cambio arquitectónico mayor)
Requiere convertir el proxy monosesión en **multisesión**, siguiendo [docs/dofus-retro-148-multicuenta.md](dofus-retro-148-multicuenta.md) §4-5:
- `proxy/tcp_proxy.py`: de `_game_lock` único a **una `Session` por cliente** con **listener de game en puerto dedicado por sesión** (5600+k) y reescritura de `AYK` apuntando a ese puerto. Aislamiento estricto de buffers (no mezclar → no romper firmas).
- **Ficheros nuevos:**
  ```
  core/session.py       # Session: GameState+FightState+Injector+actuator propios por cuenta
  core/orchestrator.py  # bus de eventos + lógica líder/mulas (seguir al líder, sincronía de combate)
  ```
- Cada `Session` tiene su propio `GameState`/`FightState`/`CombatAI` (hoy son singletons globales — **refactor necesario**: `state` global pasa a instancia por sesión). Este es el punto de mayor impacto: conviene hacerlo solo cuando Fases 1-3 estén estables.
- Coordinación con **delays escalonados por mula** (`DELAY_BETWEEN_MULES`) y **jitter por cuenta** (anti-detección correlacionada, crítica según anticheat .md §3).

**Verificación**: en `DRY_RUN`, lanzar 2 clientes y confirmar en log que cada `Session` ve **solo** sus paquetes (flujos no mezclados — checklist §6 del .md multicuenta).

---

## Orden de ejecución recomendado

1. **Fase 1** (movimiento combate) — pequeña, alto valor inmediato, sin ficheros nuevos.
2. **Fase 2** (arquetipos) — refactor contenido de `combat_ai.py`.
3. **Fase 3** (navegación mundo) — bloque grande e independiente.
4. **Fase 4a/4b** (inventario/diálogos/HDV) — depende de navegación (llegar al HDV).
5. **Fase 4c** (multicuenta) — **último**: implica refactor de singletons → por-sesión; hacerlo sobre una base estable.

Cada fase mantiene `DRY_RUN=True` por defecto y es verificable de forma aislada antes de pasar a la siguiente.

---

## Ficheros clave a modificar (resumen)

| Fichero | Fase | Cambio |
|---|---|---|
| `input/actuator.py` | 1, 3, 4 | `move_to`, `move_to_world_cell`, clicks de HDV/diálogo |
| `game/combat_ai.py` | 1, 2 | `_try_move_into_range` real; refactor a runner de arquetipos |
| `game/ai/*` (nuevo) | 2 | arquetipos + helpers |
| `game/world/*` (nuevo) | 3 | geometría completa, GDM, A*, grafo, navigator |
| `game/state.py` | 3, 4c | exponer `on_map_changed(map_id)`; dejar de ser singleton global (4c) |
| `game/inventory.py`, `game/dialog.py`, `game/hdv.py` (nuevo) | 4a/4b | inventario, PNJ, HDV |
| `proxy/tcp_proxy.py` | 4c | monosesión → multisesión (puerto game por sesión) |
| `core/session.py`, `core/orchestrator.py` (nuevo) | 4c | sesión por cuenta + líder/mulas |
| `protocol/messages.py` | 3, 4 | constantes de headers nuevos (GDM ya está; añadir OAK/OR/OQ/Ow/DC*/EH*) |
| `config.py` | todas | `ARCHETYPE`, `SAFE_DIST`, `HEAL_THRESHOLD`, `ROUTES`, `HDV_PRICE_STRATEGY`, `DELAY_BETWEEN_MULES`, etc. |

---

## Verificación global (end-to-end)

1. **Sniffer primero** (`tools/sniffer.py`): para cada fase nueva, capturar en `sniffer.log` el formato real de los paquetes implicados (GDM, EHl, EHP, OAK...) y validar campos contra las tablas de los `.md`, porque `retroproto` es de ~2022 y pueden variar.
2. **DRY_RUN por fase**: cada acción nueva debe loguear su intención (celda, píxel, precio, lote) sin ejecutar, y revisarse antes de activar.
3. **Activación gradual**: `DRY_RUN=False` solo tras validar en seco, una fase a la vez, en combates/operaciones de bajo riesgo (Incarnam, ítems baratos).
4. **Multicuenta**: validar aislamiento de sesiones con 2 cuentas en modo log antes de orquestar.
