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
