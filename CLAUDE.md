# Dofus Retro 1.48 Bot — Python MITM

Bot de combate/farmeo automático. MITM local: lee estado por paquetes S→C, actúa por clicks/teclas (pyautogui). Nunca inyectar C→S (Shield firma los paquetes → ban).

## Flujo

```
Cliente Dofus → (hosts file) → proxy:443 → login.ankama (52.17.187.227:443)
                               proxy:5556 → game server (reescrito en AYK)
```

## Estructura

```
Bot/
├── bot.py              # Entry point multisesión
├── config.py           # DRY_RUN, SPELLS, ARCHETYPE, delays, rutas BD
├── core/               # Session (estado por cuenta) + Orchestrator (líder/mulas)
├── proxy/              # tcp_proxy.py (multisesión), packet_stream.py, injector.py
├── protocol/           # dispatcher.py (1 handler por header), messages.py (headers)
├── game/
│   ├── state.py        # GameState: mapa, HP/AP/MP, callbacks
│   ├── fight.py        # FightState: fighters, BFS, LOS
│   ├── combat_ai.py    # Runner de arquetipos
│   ├── ai/             # Arquetipos: ranged, melee, support, summoner
│   ├── world/          # map_geometry, map_data (BD JSON), pathfinding A*, world_graph, navigator
│   ├── inventory.py    # Items + pods (OAK/OR/OQ/Ow)
│   ├── dialog.py       # Diálogos PNJ (DCK/DQ/DV)
│   ├── hdv.py          # Venta/compra HDV con validación de lote
│   └── spell.py        # SpellConfig(spell_id, ap_cost, min_range, max_range, role)
├── input/              # actuator.py (clicks pyautogui), coords.py (celda→píxel)
├── utils/              # timing.py (human_delay con jitter)
├── data/               # maps.json (celdas mov/los), world_graph.json (grafo observado)
├── docs/               # Documentación técnica y plan de mejoras
└── tools/
    ├── sniffer.py      # MITM log-only
    ├── dump_maps.py    # Captura GDM → descifra → puebla data/maps.json
    └── calibrate.py    # Calibrar MAP_ORIGIN para cell→píxel
```

## Estado de calibración (2026-06-30)

Grid isométrico de combate **calibrado y validado** para 2560×1440 @ 100%.

- Modelo: numeración base-1, filas alternas 14 celdas (par) / 15 celdas (impar). Las filas impares se desplazan a la **izquierda** (ODD_DX negativo, ≈-68px).
- Constantes en `input/coords.py`: `CELL_W=130.45, ROW_H=66.69, ODD_DX=-68.44, ODD_DY=30.05`
- Origen en `config.py`: `MAP_ORIGIN_X=501.6, MAP_ORIGIN_Y=0.5` (con `rect.top=23` sumado aparte)
- 6 muestras en `data/calibration_samples.txt` → **RMS=2.31px, MAX=3.2px ✓**
- Las fórmulas canónicas de Arakne/Emudofus/ArakneUtils **no coinciden** con este servidor; el modelo se derivó empíricamente midiendo vectores con Window Spy.

```powershell
python tools/calibrate.py --verify          # regresión automática
python tools/calibrate.py 15 268 463        # mover cursor a celdas (visual)
python tools/calibrate.py --fit             # recalibrar si se mueve la ventana
```

## Reglas de diseño

- **1 handler por (dirección, header)** — Dispatcher lanza ValueError si se duplica. Usar callbacks en GameState para compartir paquetes entre módulos.
- **Imports absolutos** desde `Bot/`. Ejecutar siempre desde ahí.
- **DRY_RUN=True** por defecto — loguea acciones sin ejecutarlas.
- **IP directa** para login upstream (`52.17.187.227:443`) para evitar bucle con hosts file.
- **data/maps.json** se puebla con `tools/dump_maps.py` mientras se juega (XOR descifrado en vivo).
- **data/world_graph.json** se puebla por observación al cambiar de mapa.

## Inicio rápido

```powershell
# hosts file (una vez, como admin):
# 127.0.0.1  dofusretro-co-production.ankama-games.com

# Poblar BD de mapas (admin):
python tools/dump_maps.py

# Bot activo (admin):
python bot.py
```
