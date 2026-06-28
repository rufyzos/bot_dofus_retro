# Dofus Retro 1.48 Bot — Python MITM

Bot de combate automático para Dofus Retro 1.48, sin OCR, usando un proxy MITM local. Stdlib puro, sin dependencias externas.

## Arquitectura

**Enfoque:** Proxy MITM local — el cliente real de Dofus se abre normalmente y el bot se sienta entre cliente y servidor de Ankama, interceptando y opcionalmente inyectando paquetes.

**Por qué MITM y no cliente directo:** El Launcher de Ankama gestiona la autenticación con token Zaap. El cliente real maneja todo el handshake; el bot solo proxyea e inyecta en la conexión ya autenticada.

```
Cliente Dofus → (hosts file) → proxy:443 → dofusretro-co-production.ankama-games.com:443
                               proxy:5556 → game.ankama-games.com:<puerto dinámico>
```

El proxy reescribe el paquete `AYK` (server_selection_success) para redirigir la segunda conexión al proxy local en lugar del game server real.

## Estructura de archivos

```
Bot/
├── bot.py                 # Entry point: arranca proxy + CombatAI
├── config.py              # DRY_RUN, SPELLS, delays, TARGET_STRATEGY
├── proxy/
│   ├── tcp_proxy.py       # DofusProxy: acepta conexiones en :443 y :5556
│   ├── packet_stream.py   # Bufferiza bytes TCP, emite paquetes completos (split por \x00)
│   └── injector.py        # to_server() / to_client() para inyectar paquetes
├── protocol/
│   ├── dispatcher.py      # on(header, callback, direction) + dispatch()
│   └── messages.py        # Constantes de headers confirmados + parse(raw)
├── game/
│   ├── state.py           # GameState singleton: posición, HP/AP/MP, in_fight, callbacks
│   ├── fight.py           # FightState: fighters dict, enemies(), nearest_enemy(), distancias
│   └── combat_ai.py       # CombatAI: play_turn(), cast, move, pass turn. Soporta DRY_RUN
├── utils/
│   └── timing.py          # human_delay(base_ms, jitter_pct=0.30)
└── tools/
    └── sniffer.py         # Proxy MITM en modo log-only (Fase 1 completada)
```

## Protocolo de red

- **Transporte:** TCP en texto plano (NO TLS — el puerto 443 es solo para evitar firewalls)
- **Login server:** `dofusretro-co-production.ankama-games.com:443` (IP directa: `52.17.187.227`)
- **Game server:** hostname y puerto enviados dinámicamente en el paquete `AYK`
- **Formato de paquete:** `<HEADER><campo>|<campo>...\x00`
  - Delimitador de paquete: byte nulo `\x00`
  - Delimitador de campos: pipe `|`
  - Encoding: UTF-8
  - El header suele ser 2-4 caracteres alfanuméricos

### Headers confirmados con sniffer MITM (2026-06-27)

| Header | Dir   | Descripción |
|--------|-------|-------------|
| `HC`   | S→C   | HelloConnect (salt) |
| `AH`   | S→C   | Lista de servidores con estado |
| `AxK`  | S→C   | Confirmación selección servidor |
| `AYK`  | S→C   | Game server seleccionado — `AYK<host>:<port>;<ticket>` |
| `AX`   | C→S   | Seleccionar servidor |
| `Adz`  | S→C   | Nombre de cuenta |
| `AlK`  | S→C   | Login OK |
| `ALK`  | S→C   | Lista de personajes |
| `AS`   | C→S   | Seleccionar personaje |
| `ASK`  | S→C   | Personaje seleccionado OK (con stats completos) |
| `AT`   | C→S   | Enviar ticket al game server (segunda conexión) |
| `ATK`  | S→C   | Ticket aceptado |
| `HG`   | S→C   | HelloGame (primer paquete del game server) |
| `GCK`  | S→C   | Entrada al mundo (GameCreate OK) |
| `GDM`  | S→C   | Datos del mapa (id + key cifrado) |
| `GM`   | S→C   | Actores en el mapa (+aparece / -desaparece) |
| `GDK`  | S→C   | Fin de carga de actores del mapa |
| `GA`   | C→S   | Acción de juego (cast, movimiento en combate) |
| `GS`   | S→C   | GameStartToPlay — inicio real de combate |
| `GJ`   | S→C   | GameJoin — unirse a combate |
| `GR`   | C↔S   | GameRequestReady/GameReady — marcar listo (pre-combate) |
| `GIC`  | S→C   | GamePlayersCoordinates — coordenadas de fighters en combate |
| `GTL`  | S→C   | GameTurnList — orden de turnos (lista de fighter_ids) |
| `GTS`  | S→C   | GameTurnStart — comienza el turno del fighter `<id>` |
| `GTF`  | S→C   | GameTurnFinish — fin de turno |
| `GIE`  | S→C   | GameEffect — efecto aplicado (daño, buff, muerte) |
| `Gt`   | C→S   | Pasar turno — formato: `Gt\n\x00` |
| `GE`   | S→C   | GameEnd — fin de combate |
| `JS`   | S→C   | **JobSkills** — oficios (NO es de combate, confusión anterior) |
| `JX`   | S→C   | **JobXP** — XP de oficio (NO es de combate) |
| `JO`   | S→C   | **JobChangeStats** — opciones de oficio (NO es de combate) |

**Nota importante sobre `AYK`:** el game server viene como hostname, no IP numérica.  
Ejemplo: `AYKdofusretro-ga-fallanster-2.ankama-games.com:443;<ticket>`

## Cómo usar

### Requisito previo — hosts file (una sola vez, requiere admin)

Abre Notepad como administrador y edita `C:\Windows\System32\drivers\etc\hosts`:

```
127.0.0.1  dofusretro-co-production.ankama-games.com
```

### Arrancar el sniffer / bot (requiere admin para puerto 443)

```powershell
# Terminal como administrador:
cd "c:\Users\vicma\OneDrive\Escritorio\Dofus\Bot"
python tools/sniffer.py
```

Luego abre el Ankama Launcher y pulsa Play. El cliente conecta automáticamente al proxy.

### Modo DRY_RUN (testear sin riesgo)

`config.py` tiene `DRY_RUN = True` por defecto. En este modo CombatAI **loguea** las acciones que tomaría pero no inyecta nada.

```powershell
python bot.py
```

### Modo activo

1. Configurar hechizos en `config.py`:
   ```python
   SPELLS = [
       SpellConfig(spell_id="3", ap_cost=4, min_range=1, max_range=3),
   ]
   ```
2. Cambiar `DRY_RUN = False` en `config.py`
3. Correr `python bot.py` como administrador

## Patrones de diseño clave

**Un solo handler por (dirección, header):** El `Dispatcher` lanza `ValueError` si intentas registrar el mismo header dos veces. Si dos módulos necesitan el mismo paquete, usar callbacks intermedios en `GameState` (p.ej. `state.on_my_turn`, `state.on_fight_start`). Esto evita el bug de sobreescritura de handlers que ocurrió en la primera sesión.

**Callbacks en GameState, no handlers directos:** `CombatAI` no registra handlers en el Dispatcher. En su lugar asigna `state.on_my_turn = self._play_turn`. `GameState` recibe `GTS` y llama al callback.

**Headers de combate reales (corregido 2026-06-27):** `JS`/`JX`/`JO` son de **oficios** (JobSkills/JobXP/JobChangeStats), NO de combate. El combate usa `GS` (inicio), `GIC` (coordenadas fighters), `GTL` (orden turnos), `GIE` (efectos/daño), `GTS` (turno start), `GE` (fin combate).

**Imports absolutos:** todos los imports usan rutas absolutas desde la raíz del proyecto (`from game.state import state`, no `from ..game.state`). Ejecutar siempre desde `Bot/`.

**El proxy usa IP directa para el upstream de login** (`52.17.187.227:443`) para evitar el bucle con el hosts file. Si la IP cambia, resolverla con `nslookup dofusretro-co-production.ankama-games.com 8.8.8.8`.

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
- Stdlib puro: `asyncio`, `socket`, `re`, `random`, `time`, `datetime`
- Sin `pip install` necesario
- Requiere ejecutar como **administrador** (puerto 443)
