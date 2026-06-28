# Conectar a Dofus Retro 1.48 (servidor OFICIAL Ankama) desde Python en Windows

**Fecha:** Junio 2026 · **Caso concreto:** servidor oficial de Ankama · SO Windows · Python

---

## 1. Conclusión directa

Para servidor **oficial** en **Windows**, la única vía realista es **MITM (proxy local)**. Las otras dos quedan descartadas:

- **Full-socket** ❌ — en oficiales el login pasa por el token Zaap del Ankama Launcher. No puedes generarlo tú sin emular todo el lado Zaap, y aunque lo lograras, replicar la firma/UID del cliente que Ankama valida es justo lo que dispara baneos. No merece la pena.
- **Pixel bot** ⚠️ — técnicamente funciona pero es frágil y es precisamente lo que la ban wave de enero 2026 caza primero (clicks al píxel, tiempos inhumanos).
- **MITM** ✅ — dejas que el **cliente oficial + Launcher** hagan TODO el trabajo sucio (token Zaap, ticket, cifrado de contraseña, checks de integridad) y tu Python se sienta en medio del TCP **ya autenticado y en texto plano**.

La idea central del MITM: **nunca tocas el login**. El cliente real se autentica; tú solo lees y manipulas el flujo de paquetes que pasa por delante.

---

## 2. Arquitectura

```
┌─────────────────┐      ┌──────────────────┐      ┌────────────────────────┐
│ Ankama Launcher │─────▶│  Cliente Retro   │      │  Servidores Ankama     │
│ (Zaap, token)   │ play │  (retroclient)   │      │  login :443 / game     │
└─────────────────┘      └────────┬─────────┘      └───────────▲────────────┘
                                  │ config.xml "Local"          │
                                  ▼                             │
                         ┌────────────────────┐                │
                         │  TU PROXY PYTHON   │────────────────┘
                         │  127.0.0.1:5555    │   reenvía a Ankama
                         │  127.0.0.1:5556    │   y observa/modifica
                         └────────────────────┘
```

- El cliente oficial se conecta a **tu proxy** (localhost) en lugar de directamente a Ankama.
- Tu proxy abre la conexión real a Ankama y hace de puente.
- Como el cliente ya pasó el handshake de login con el ticket que le dio el Launcher, **tú ves el flujo descifrado** (Retro es protocolo de texto: `HC`, `AT`, `Af`, `GM`, `GA`…).

---

## 3. Montaje paso a paso en Windows

### Paso 1 — Localizar el cliente

Ruta típica del cliente Retro en Windows:

```
C:\Users\<TU_USUARIO>\Ankama\Retro\resources\app\retroclient\
```

Ahí dentro están `Dofus.exe` y el `config.xml` que vas a sustituir. (Confirmado por la doc de AnkaBot, que usa exactamente `…\Ankama\Retro\resources\app\retroclient`.)

> Haz **copia de seguridad** del `config.xml` original antes de tocar nada.

### Paso 2 — Sustituir `config.xml` por un perfil "Local"

El proyecto de referencia **`kralamoure/retroproxy`** trae un `config.xml` (en su carpeta `assets/`) que añade un perfil de servidor **"Local"** apuntando a `127.0.0.1`. Cópialo sobre el `config.xml` del cliente.

El mecanismo: el cliente Retro lee de `config.xml` la lista de servidores que muestra en la pantalla de conexión. El perfil "Local" hace que apunte a tu proxy en vez de a Ankama. Lo que necesitas que defina:

- Host de login → `127.0.0.1`
- Puerto de login → `5555` (el que escuche tu proxy)

> Es más cómodo coger el `config.xml` ya hecho del repo `retroproxy` (`assets/config.xml`) que escribirlo a mano, porque el formato exacto de etiquetas varía entre builds del cliente. Clónalo: `git clone https://github.com/kralamoure/retroproxy` y mira `assets/`.

### Paso 3 — Arrancar tu proxy Python

(Ver código en sección 4.) Escucha en `5555` (login) y `5556` (game), reenviando a `dofusretro-co-production.ankama-games.com:443`.

### Paso 4 — Lanzar el juego y elegir "Local"

1. Abre el **Ankama Launcher**, pulsa **Play** en Dofus Retro (deja que el Launcher haga su login con token Zaap — esto es lo que te ahorra todo el problema).
2. Cuando el cliente arranca, en la pantalla de conexión elige **`With Launcher` → `Local`** y pulsa OK.
3. El cliente se conecta a tu proxy; tu consola empieza a ver paquetes.

---

## 4. Proxy MITM en Python (base funcional)

Maneja el doble salto login→game: cuando el login server responde con la dirección del game server (`AYK<ip>:<puerto>;<ticket>`), reescribes esa dirección para que el cliente vuelva a conectarse a **tu** proxy (al puerto 5556), y desde ahí tú rediriges al game server real. Ese reescribir es la parte clave en Retro.

```python
import asyncio

LOGIN_UPSTREAM = ("dofusretro-co-production.ankama-games.com", 443)
LOGIN_LISTEN   = ("127.0.0.1", 5555)
GAME_LISTEN    = ("127.0.0.1", 5556)
GAME_PUBLIC    = "127.0.0.1:5556"   # lo que anunciamos al cliente

# Guardamos a dónde redirigir realmente el game server tras leer AYK
game_target = {"host": None, "port": None}

def split_messages(buffer: bytes):
    """Los mensajes Retro se separan por NUL (\\x00)."""
    parts = buffer.split(b"\x00")
    return parts[:-1], parts[-1]  # completos, resto

async def pump(reader, writer, transform, tag):
    buffer = b""
    try:
        while not reader.at_eof():
            chunk = await reader.read(4096)
            if not chunk:
                break
            buffer += chunk
            msgs, buffer = split_messages(buffer)
            for raw in msgs:
                if not raw:
                    continue
                msg = raw.decode("utf-8", "replace")
                out = transform(tag, msg)   # observa/modifica/descarta
                if out is None:
                    continue
                writer.write(out.encode() + b"\x00")
            await writer.drain()
    except Exception as e:
        print(f"[{tag}] error: {e}")
    finally:
        try: writer.close()
        except Exception: pass

# ---------- LOGIN ----------
def on_login(tag, msg):
    print(f"[LOGIN {tag}] {msg!r}")
    if tag == "S->C" and msg.startswith("AYK"):
        # AYK<ip>:<port>;<ticket>  -> redirigimos al cliente a NUESTRO game proxy
        body = msg[3:]
        addr, _, ticket = body.partition(";")
        host, _, port = addr.partition(":")
        game_target["host"], game_target["port"] = host, int(port)
        print(f"  > game server real = {host}:{port}; redirijo cliente a {GAME_PUBLIC}")
        gh, gp = GAME_PUBLIC.split(":")
        return f"AYK{gh}:{gp};{ticket}"
    return msg

async def handle_login(cr, cw):
    sr, sw = await asyncio.open_connection(*LOGIN_UPSTREAM)
    await asyncio.gather(
        pump(cr, sw, on_login, "C->S"),
        pump(sr, cw, on_login, "S->C"),
    )

# ---------- GAME ----------
def on_game(tag, msg):
    print(f"[GAME {tag}] {msg!r}")
    # Aquí va tu lógica: parsear GM (mapa), GDF (objetos), combate, etc.
    return msg

async def handle_game(cr, cw):
    if not game_target["host"]:
        cw.close(); return
    sr, sw = await asyncio.open_connection(game_target["host"], game_target["port"])
    await asyncio.gather(
        pump(cr, sw, on_game, "C->S"),
        pump(sr, cw, on_game, "S->C"),
    )

async def main():
    login_srv = await asyncio.start_server(handle_login, *LOGIN_LISTEN)
    game_srv  = await asyncio.start_server(handle_game,  *GAME_LISTEN)
    print("Proxy escuchando: login 5555, game 5556")
    async with login_srv, game_srv:
        await asyncio.gather(login_srv.serve_forever(), game_srv.serve_forever())

asyncio.run(main())
```

> **Nota sobre TLS:** el login oficial está en `:443`. Si el cliente Retro usa la conexión en claro contra ese puerto (es el caso histórico del protocolo Retro), el código de arriba sirve tal cual. Si en algún punto Ankama envolviera en TLS, tendrías que terminar TLS en el proxy. La forma fiable de saberlo es empezar en **modo pasivo solo-log** (Paso siguiente) y observar.

---

## 5. Empieza SIEMPRE en modo pasivo (solo lectura)

Antes de modificar o inyectar nada:

1. Lanza el proxy con `on_login`/`on_game` que **solo imprimen** (devuelven `msg` sin cambios).
2. Juega normal unos minutos: muévete, entra a combate, abre banco, recoge un recurso.
3. Vuelca todo a un fichero de log.

Esto te da el **protocolo real de la 1.48 de TU servidor**, que es lo único 100% fiable. Luego mapeas cada ID de 2 letras contra la spec.

---

## 6. Mapear paquetes: tu diccionario de referencia

Aunque programes en Python, usa **`kralamoure/retroproto`** (Go) como **catálogo de mensajes**: define todos los IDs cliente (`msgcli`) y servidor (`msgsvr`) con sus campos y separadores. Lo lees como documentación. Ejemplos de IDs que verás:

| ID | Dirección | Significado |
|----|-----------|-------------|
| `HC` | S→C | Hello connect (salt del login) |
| `AT` | C→S | Account ticket (handshake game) |
| `Af` | C↔S | Estado de cola (`Af1|2|0||-1`) |
| `AxK`/`ALK` | S→C | Lista de personajes / servidores |
| `GM` | S→C | Movimiento/actores en mapa |
| `GA` | C→S | Acción de juego (combate, etc.) |

Para parsear en Python directamente, la librería **`dofutils`** (PyPI, `pip install dofutils`, Python ≥3.8) aporta utilidades de serialización Retro ya portadas.

---

## 7. Patrón de bot sobre el proxy

Una vez parseas, organiza la lógica como **handlers por tipo de mensaje** con una acción (modelo de `Guinness-Bot`):

- **FORWARD** — reenviar al otro extremo (lo normal).
- **DISCARD** — no reenviar (ocultar algo a un lado).
- **MIRROR** — devolver al emisor (eco).
- **INJECT** — meter un paquete que tú generas, opcionalmente con retardo.

Ejemplos típicos:
- *Auto-login de personaje:* al recibir la lista de personajes (S→C), inyectas tú la selección (C→S) sin que el usuario pulse.
- *Auto-recolección / movimiento:* inyectas paquetes de acción de juego con timing realista.

---

## 8. Anti-bot y riesgo (oficial, 2026) — léelo

Esto es servidor **oficial**, así que el riesgo es real y permanente:

- **Ban wave de enero 2026:** Ankama activó detección que apunta a comportamiento robótico (acciones idénticas, sin pausas), inyecciones de memoria visibles y tiempos de reacción inhumanos.
- **Firma de paquetes / UID del cliente:** el cliente Retro añade una **firma** y un **UID** a ciertos paquetes que envía (en foros técnicos de 2026 se habla de una "nueva signature dans les packets envoyés" y de detección de clientes "sobre los que se leen las claves"). **Ventaja del MITM:** como reenvías los paquetes que genera el cliente oficial, esa firma es legítima — siempre que **no rompas el orden ni el contenido** de los paquetes firmados. Si los reescribes mal, te delatas.
- Hay reportes concretos de baneo de bots socket/MITM por **moverse de forma no idéntica al cliente oficial**.

Mitigaciones de diseño:
- Randomiza tiempos entre acciones; mete pausas y ventanas de inactividad humanas.
- No reescribas paquetes que lleven firma salvo que sepas exactamente qué haces; prioriza **inyectar** acciones nuevas con timing realista sobre **modificar** las existentes.
- Considera no farmear 24/7 con el mismo personaje.
- Asume que **ningún método es indetectable** y que puedes perder la cuenta.

> Recordatorio: automatizar en servidores oficiales infringe las condiciones de uso de Ankama. Lo de arriba es la realidad técnica, no una garantía de impunidad.

---

## 9. Checklist de arranque

1. [ ] Backup del `config.xml` original en `…\Ankama\Retro\resources\app\retroclient\`.
2. [ ] `git clone https://github.com/kralamoure/retroproxy` → copiar su `assets/config.xml` al cliente.
3. [ ] Escribir/lanzar el proxy Python (sección 4) en modo **solo-log**.
4. [ ] Launcher → Play → pantalla conexión → **With Launcher → Local** → OK.
5. [ ] Confirmar que ves paquetes en consola; volcar a fichero jugando manualmente.
6. [ ] Mapear IDs contra `retroproto`; instalar `dofutils` para parsear en Python.
7. [ ] Pasar a activo: primero auto-login de personaje, luego movimiento, luego acciones.
8. [ ] Añadir randomización de timings desde el principio.

---

## 10. Recursos (verificados)

- **`kralamoure/retroproxy`** — proxy de referencia + `config.xml` "Local" + método "With Launcher → Local". Tu plantilla principal.
- **`kralamoure/retroproto`** — catálogo completo de mensajes Retro (la "spec"). Go, legible como doc.
- **`kralamoure/retroutil` / `retro`** — utilidades de bajo nivel del cliente original (incluye lógica de cifrado/UID útil de leer).
- **`dofutils`** (PyPI) — utilidades de serialización Retro en Python.
- **`Romain-P/Guinness-Bot`** (Kotlin) — patrón handlers FORWARD/DISCARD/MIRROR + inyección con retardo. Cópialo como diseño.
- **`Dyshay/Bot-Dofus-Retro`** — MITM Retro con control por Discord, referencia de bot completo.
- Doc **AnkaBot** ("Chemin DofusRetro et MITM") — confirma rutas Windows y flujo de activación MITM.

---

*Este documento describe la realidad técnica para interoperar con el cliente. Automatizar cuentas en servidores oficiales de Ankama viola sus condiciones de uso y puede acarrear el baneo permanente de la cuenta.*
