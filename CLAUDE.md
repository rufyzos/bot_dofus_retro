# Dofus Retro 1.48 Bot — Python MITM

Bot de combate automático para Dofus Retro 1.48, sin OCR, usando un proxy MITM local. Stdlib puro, sin dependencias externas.

## Arquitectura

**Enfoque:** Proxy MITM local — el cliente real de Dofus se abre normalmente y el bot se sienta entre cliente y servidor de Ankama, interceptando y opcionalmente inyectando paquetes.

**Por qué MITM y no cliente directo:** Dofus Retro usa dos servidores separados (login + game) con un ticket de autenticación (`AT`) entre ellos. El cliente real maneja ese handshake; el bot solo proxyea e inyecta en la conexión de juego.

```
Cliente Dofus → proxy:5555 → login.ankama.com:5555
                proxy:5556 → game.ankama.com:<puerto dinámico>
```

El proxy reescribe el paquete `AXK` (server_selection_success) para redirigir la segunda conexión al proxy local en lugar del game server real.

## Estructura de archivos

```
Bot/
├── bot.py                 # Entry point: arranca proxy + CombatAI
├── config.py              # DRY_RUN, SPELLS, delays, TARGET_STRATEGY
├── proxy/
│   ├── tcp_proxy.py       # DofusProxy: acepta conexiones en :5555 y :5556
│   ├── packet_stream.py   # Bufferiza bytes TCP, emite paquetes completos (split por \x00)
│   └── injector.py        # to_server() / to_client() para inyectar paquetes
├── protocol/
│   ├── dispatcher.py      # on(header, callback, direction) + dispatch()
│   └── messages.py        # Constantes de headers verificados + parse(raw)
├── game/
│   ├── state.py           # GameState singleton: posición, HP/AP/MP, in_fight, callbacks
│   ├── fight.py           # FightState: fighters dict, enemies(), nearest_enemy(), distancias
│   └── combat_ai.py       # CombatAI: play_turn(), cast, move, pass turn. Soporta DRY_RUN
├── utils/
│   └── timing.py          # human_delay(base_ms, jitter_pct=0.30)
└── tools/
    └── sniffer.py         # Proxy en modo log-only — Fase 0 de descubrimiento de protocolo
```

## Protocolo de red

- **Transporte:** TCP
- **Login server:** `co.retro.dofus.com:5555`
- **Game server:** IP y puerto enviados dinámicamente en el paquete `AXK`
- **Formato de paquete:** `<HEADER><campo>|<campo>...\x00`
  - Delimitador de paquete: byte nulo `\x00`
  - Delimitador de campos: pipe `|`
  - Encoding: UTF-8
  - El header suele ser 2-3 caracteres alfanuméricos

### Headers principales (verificados contra retroproto)

| Header | Dir | Descripción |
|--------|-----|-------------|
| `HC`  | S→C | HelloConnect (salt) |
| `AlK` | S→C | Login OK |
| `ALK` | S→C | Lista de personajes |
| `AXK` | S→C | Servidor seleccionado — contiene IP:puerto del game server + ticket |
| `AS`  | C→S | Seleccionar personaje |
| `ASK` | S→C | Personaje seleccionado OK |
| `AT`  | C→S | Enviar ticket al game server (segunda conexión) |
| `ATK` | S→C | Ticket aceptado |
| `GTS` | S→C | Game Turn Start (comienza el turno del fighter `<id>`) |
| `GTF` | S→C | Game Turn Finish |
| `Gt`  | C→S | Cliente termina su turno (pass turn) |
| `GM`  | S→C | Movimiento/posición de actores en el mapa |

**Headers pendientes de confirmar con sniffer (Fase 0):**
- Cast de hechizo (C→S) → `CAST_SPELL` en `protocol/messages.py`
- Inicio de combate (S→C) → `FIGHT_START`
- Fin de combate (S→C) → `FIGHT_END`
- Stats de fighters, posiciones iniciales, muertes

## Cómo usar

### Fase 0 — Descubrir headers de combate (hacer primero)

```powershell
# 1. Editar hosts como administrador (añadir al final):
#    127.0.0.1  co.retro.dofus.com
notepad C:\Windows\System32\drivers\etc\hosts

# 2. Correr el sniffer
cd "c:\Users\vicma\OneDrive\Escritorio\Dofus\Bot"
python tools/sniffer.py

# 3. Abrir el cliente de Dofus, iniciar sesión y entrar a una pelea manualmente.
#    Buscar en el log los paquetes C→S al castear y al pasar turno.

# 4. Actualizar protocol/messages.py y game/fight.py con los headers reales.

# 5. Revertir el archivo hosts cuando termines.
```

### Modo DRY_RUN (testear sin riesgo)

`config.py` tiene `DRY_RUN = True` por defecto. En este modo CombatAI **loguea** las acciones que tomaría pero no inyecta nada. Sirve para validar la lógica de decisión antes de activar el bot real.

```powershell
python bot.py
```

### Modo activo

1. Confirmar headers de combate (Fase 0)
2. Configurar hechizos en `config.py`:
   ```python
   SPELLS = [
       SpellConfig(spell_id="3", ap_cost=4, min_range=1, max_range=3),
       ...
   ]
   ```
3. Cambiar `DRY_RUN = False` en `config.py`
4. Correr `python bot.py`

## Patrones de diseño clave

**Un solo handler por (dirección, header):** El `Dispatcher` lanza `ValueError` si intentas registrar el mismo header dos veces. Si dos módulos necesitan el mismo paquete, usar callbacks intermedios en `GameState` (p.ej. `state.on_my_turn`, `state.on_fight_start`). Esto evita el bug de sobreescritura de handlers que ocurrió en la primera sesión.

**Callbacks en GameState, no handlers directos:** `CombatAI` no registra handlers en el Dispatcher. En su lugar asigna `state.on_my_turn = self._play_turn`. `GameState` recibe `GTS` y llama al callback.

**Imports absolutos:** todos los imports usan rutas absolutas desde la raíz del proyecto (`from game.state import state`, no `from ..game.state`). Ejecutar siempre desde `Bot/`.

## Configuración (config.py)

| Variable | Descripción |
|----------|-------------|
| `DRY_RUN` | `True` = solo loguea, no inyecta |
| `SPELLS` | Lista de `SpellConfig(spell_id, ap_cost, min_range, max_range)` |
| `TARGET_STRATEGY` | `"nearest"` o `"lowest_hp"` |
| `DELAY_CAST_MS` | ms entre casts (default 600) |
| `DELAY_MOVE_MS` | ms tras moverse en combate (default 400) |
| `DELAY_PASS_TURN_MS` | ms antes de pasar turno (default 800) |
| `DELAY_JITTER` | fracción de variación aleatoria (default 0.30 = ±30%) |

## Dependencias

- Python 3.10+
- Stdlib puro: `socket`, `threading`, `re`, `random`, `time`, `datetime`
- Sin `pip install` necesario
