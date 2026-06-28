# Conectar a Dofus Retro 1.48 desde Python — Informe técnico

**Fecha:** Junio 2026 · **Versión objetivo:** Dofus Retro 1.48 (cliente Electron/`retroclient`, distribuido vía Ankama Launcher)

---

## 1. Resumen ejecutivo

Conectar a Dofus Retro 1.48 desde Python es "complejo por el launcher" por dos motivos que conviene separar desde el principio:

1. **El arranque del cliente ya no es directo.** Ankama eliminó los accesos directos a `Dofus.exe`. El juego se lanza desde el **Ankama Launcher (Zaap)**, que pasa un **token de conexión** y parámetros (`--port`, `--gameName`, `--gameRelease`, `--instanceId`…) al cliente. El login con usuario/contraseña ya no ocurre en la pantalla del juego, sino en el Launcher.

2. **El protocolo de juego en sí es relativamente sencillo y bien documentado.** Dofus Retro usa un protocolo **TCP de texto** (mensajes ASCII tipo `HC<salt>`, `AT<ticket>`, `Af1|2|0||-1`…), heredado del cliente Flash original. Esto es mucho más fácil de replicar que el protocolo binario de Dofus 2/3.

La consecuencia práctica: **la dificultad real no está en hablar con el servidor, sino en obtener credenciales válidas (el ticket de sesión) sin pelearte con el Launcher.** Por eso casi todas las soluciones modernas que funcionan en servidores oficiales usan un enfoque **MITM (man-in-the-middle)**: dejas que el cliente oficial y el Launcher hagan el login real, y tu código Python se sienta en medio leyendo/escribiendo el flujo TCP ya autenticado.

A continuación se detallan las arquitecturas posibles, ordenadas de la más recomendable a la menos.

> **Aviso importante:** automatizar el juego en servidores **oficiales** de Ankama viola sus condiciones de uso y conlleva oleadas de baneos (la más reciente, enero 2026). Todo lo descrito aquí es válido y de bajo riesgo en **servidores privados/emuladores propios**; en oficiales asume el riesgo. Más sobre detección en la sección 7.

---

## 2. Cómo arranca y se autentica el juego (lo que el launcher esconde)

Entender el flujo completo es lo que te permite elegir dónde "engancharte".

### 2.1 Flujo Launcher → Cliente (Zaap)

1. Te logueas en el **Ankama Launcher** con tu cuenta Ankama (esto pasa por el sistema Zaap; el token de conexión caduca si no usas la cuenta en ~30 días).
2. Al pulsar *Play*, el Launcher arranca el cliente Electron de Retro pasándole variables/argumentos: `--port=$ZAAP_PORT`, `--gameName=$ZAAP_GAME`, `--gameRelease=$ZAAP_RELEASE`, `--instanceId=$ZAAP_INSTANCE_ID`, además de un **token** que el cliente intercambia por un **ticket de sesión**.
3. El cliente abre una conexión local con el Launcher (Zaap actúa como pequeño servidor local en `$ZAAP_PORT`) para validar ese token.

En Linux esto es visible en el script `zaap-start.sh`, donde aparecen literalmente esas variables de entorno — útil como documentación del contrato Launcher↔cliente.

### 2.2 Flujo de red Cliente → Servidores (el protocolo que te interesa)

Dos servidores TCP, igual que el viejo cliente Flash:

| Fase | Servidor | Puerto típico | Qué ocurre |
|------|----------|---------------|------------|
| **Login / Auth** | `dofusretro-co-production.ankama-games.com` | 443 | Handshake, versión de protocolo, credenciales/ticket, lista de servidores |
| **Game** | IP del servidor de juego elegido | variable | Selección de personaje, mapa, combate, etc. |

**Handshake de login (mensajes de texto):**

```
Servidor → Cliente:  HC<salt>            (AksHelloConnect — envía un "salt" aleatorio)
Cliente → Servidor:  <version>           (AccountVersion, sin ID de protocolo)
Cliente → Servidor:  <credencial cifrada> (AccountCredential, sin ID de protocolo)
...
Servidor → Cliente:  AlK...              (lista de servidores)
Cliente → Servidor:  AX<id_servidor>     (selección de servidor)
Servidor → Cliente:  AYK<ip>:<puerto>;<ticket>   (dirección del game server + ticket)
```

**Handshake de game server:**

```
Cliente → Servidor:  AT<ticket>          (AccountTicket — reutiliza el ticket recibido)
Servidor → Cliente:  ATK0                (ticket aceptado)
Cliente → Servidor:  Af                  (pide posición en cola)
Servidor → Cliente:  Af1|2|0||-1         (estado de cola)
...                                       luego lista de personajes, etc.
```

> Los códigos (`HC`, `AT`, `Af`, `AX`, `AlK`…) son los **IDs de mensaje** de 2 letras del protocolo Retro. La librería de referencia que los cataloga todos (cliente y servidor, serialización/deserialización) es **`kralamoure/retroproto`** (Go), perfectamente legible como especificación aunque programes en Python.

### 2.3 El detalle del cifrado de contraseña

En el handshake de login, la contraseña **no viaja en claro**: se combina con el `salt` recibido en `HC` mediante el algoritmo histórico de Dofus (cifrado XOR/sustitución sobre el salt). Esta es la única parte "criptográfica" del login y está implementada en múltiples proyectos open source (p. ej. la función de cifrado de cuenta en clientes/emuladores Retro). Si haces login full-socket necesitas replicarla; **si haces MITM no la necesitas** porque el cliente oficial ya la calcula.

---

## 3. Opción A — MITM / Proxy local (RECOMENDADA)

**Idea:** no reemplazas al cliente; te pones **en medio** del tráfico TCP entre el `Dofus.exe`/`retroclient` oficial y los servidores de Ankama. El cliente y el Launcher hacen todo el login real (token Zaap, ticket, cifrado de contraseña, checks de integridad). Tu proxy en Python ve el flujo ya descifrado en texto plano y puede **leer, reenviar, descartar o reinyectar** paquetes.

### Por qué es la mejor opción

- **Esquivas por completo el problema del launcher y del cifrado de login.** El ticket de sesión te lo entrega el propio cliente.
- Funciona en servidores oficiales y privados.
- Es la arquitectura que usan los bots Retro serios actuales (AnkaBot, Guinness-Bot, dofus-bot, Dyshay/Bot-Dofus-Retro, MoonBot…).

### Cómo redirigir el tráfico hacia tu proxy

El cliente Retro trae una pantalla de configuración de conexión. La vía limpia y soportada es la que usa **`kralamoure/retroproxy`**:

1. Sustituir el `config.xml` del cliente (`…/Ankama/Retro/resources/app/retroclient/config.xml`) por uno que ofrezca un perfil de servidor **"Local"**.
2. Arrancar Retro desde el Launcher (*Play*).
3. En la pantalla de conexión elegir **`With Launcher` → `Local`** y pulsar OK.
4. El cliente se conecta a tu proxy local (`127.0.0.1:5555` login / `5556` game), que reenvía a `dofusretro-co-production.ankama-games.com:443`.

`retroproxy` está en Go, pero su `config.xml` y su esquema de puertos son directamente reutilizables; tú reescribes la lógica del proxy en Python.

### Esqueleto mínimo en Python (asyncio)

```python
import asyncio

ANKAMA_LOGIN = ("dofusretro-co-production.ankama-games.com", 443)
LISTEN = ("127.0.0.1", 5555)

async def pipe(reader, writer, label, on_packet):
    try:
        buffer = b""
        while not reader.at_eof():
            data = await reader.read(4096)
            if not data:
                break
            buffer += data
            # Los mensajes Retro terminan en '\x00' (NUL)
            while b"\x00" in buffer:
                raw, buffer = buffer.split(b"\x00", 1)
                msg = raw.decode("utf-8", "replace")
                msg = on_packet(label, msg)        # inspecciona / modifica
                if msg is None:                     # DISCARD
                    continue
                writer.write(msg.encode() + b"\x00")
            await writer.drain()
    finally:
        writer.close()

def on_packet(label, msg):
    print(f"[{label}] {msg!r}")
    # ejemplo: detectar el header del game server, el ticket, etc.
    return msg  # FORWARD tal cual

async def handle_client(client_reader, client_writer):
    server_reader, server_writer = await asyncio.open_connection(*ANKAMA_LOGIN)
    await asyncio.gather(
        pipe(client_reader, server_writer, "CLIENT→SRV", on_packet),
        pipe(server_reader, client_writer, "SRV→CLIENT", on_packet),
    )

async def main():
    srv = await asyncio.start_server(handle_client, *LISTEN)
    async with srv:
        await srv.serve_forever()

asyncio.run(main())
```

A partir de ahí, parsear cada mensaje según su ID de 2 letras (usando `retroproto` como tabla de referencia) te da el estado del juego: lista de personajes, mapa actual, lista de monstruos, etc. La librería **`dofutils`** (PyPI, Python ≥3.8) aporta utilidades de serialización Retro ya en Python y te ahorra parte del trabajo.

### Patrón de control (visto en Guinness-Bot)

Los bots MITM modernos funcionan con **handlers por tipo de mensaje** y una operación asociada:
- `FORWARD` — reenviar al otro extremo.
- `DISCARD` — no reenviar (el otro lado no se entera).
- `MIRROR` — devolver al emisor (eco).

Y permiten **inyectar** paquetes en cualquier dirección y con retardo (`upstream().write(...)`, `post(..., 5s)`), lo que es la base del auto-login, auto-combate, recolección, etc.

---

## 4. Opción B — Cliente full-socket (sin cliente oficial)

**Idea:** tu Python **es** el cliente. Abres el socket al login server, replicas el handshake completo (versión + contraseña cifrada con el salt), seleccionas servidor, te conectas al game server con el ticket y gestionas todo el protocolo a mano.

### Cuándo tiene sentido

- **Servidores privados / emuladores propios** (Starloco, etc.), donde *tú* controlas el login server y no hay Zaap ni anti-cheat. Aquí es la opción ideal y limpia.
- Cuando quieres correr **decenas/cientos de instancias** sin abrir clientes gráficos (los bots socket escalan muchísimo mejor que los MITM, que necesitan un cliente abierto por cuenta).

### El problema en servidores oficiales

En oficiales, el login ya **no** acepta usuario/contraseña directa del modo clásico: espera el flujo del Launcher con token Zaap. Para full-socket contra oficiales tendrías que **emular el lado Zaap** y obtener un token válido tú mismo. Esto existe como concepto:

- **`jordanamr/DivaZaap`** emula el protocolo **Launcher ↔ Zaap (Apache Thrift)** y permite conectar a cualquier auth server con tu propio token — pensado sobre todo para Dofus Unity, pero ilustra el enfoque.
- En el ecosistema **Starloco** hay proyectos Python que hacen exactamente esto a pequeña escala: un *launcher* Python con **handoff local del token Zaap**, flujo de auth y UI (CustomTkinter), más un backend **FastAPI** que valida hashes de contraseña y **genera tokens Zaap**. Son la mejor referencia práctica de "login Retro en Python de principio a fin".

### Componentes que necesitas implementar

1. Conexión TCP al login server.
2. Recepción de `HC<salt>` → cifrado de la contraseña con el salt (algoritmo Dofus clásico).
3. Envío de versión + credencial.
4. Parseo de la lista de servidores, selección (`AX`).
5. Recepción de IP:puerto + ticket (`AYK`).
6. Conexión al game server, `AT<ticket>`, gestión de cola (`Af`), selección de personaje.
7. Bucle de mensajes de juego.

`retroproto` (Go, como spec) + `dofutils` (Python) cubren la capa de mensajes; el resto es tu máquina de estados.

---

## 5. Opción C — Pixel bot (sin tocar la red)

**Idea:** no tocas el protocolo en absoluto. El cliente oficial corre normal y tu Python actúa por **visión + input**: lee píxeles de la pantalla (OpenCV/captura) y mueve ratón/teclado (PyAutoGUI).

- **Referencias:** `escarrie/DofusRetroBot` (PyAutoGUI), `Gamerium/Dindo-Bot` (Python+GTK, multi-cuenta, pathfinding por mapas).
- **Ventajas:** trivial respecto al launcher (te da igual cómo arranca el juego), no hay que entender el protocolo, no modifica memoria ni tráfico.
- **Desventajas:** frágil (resolución/tema/posición de ventana), lento, una instancia por pantalla, y los anti-cheat de 2026 **apuntan específicamente** a clicks "siempre al mismo píxel" y tiempos de reacción inhumanos. Hay que randomizar mucho.

Buena opción para tareas simples (pesca/recolección puntual) o como complemento; mala para algo robusto y escalable.

---

## 6. Comparativa de opciones

| Criterio | A — MITM/Proxy | B — Full-socket | C — Pixel bot |
|---|---|---|---|
| Esquiva el problema del launcher | ✅ (el cliente loguea por ti) | ⚠️ (debes emular Zaap en oficiales) | ✅ (irrelevante) |
| Necesita cliente oficial abierto | Sí (1 por cuenta) | No | Sí (1 por pantalla) |
| Acceso a estado exacto del juego | ✅ Total (paquetes) | ✅ Total | ❌ Solo lo visible |
| Escalabilidad (nº cuentas) | Media | ✅ Muy alta | Baja |
| Complejidad de implementación | Media | Alta | Baja |
| Ideal para servidor privado | ✅ | ✅✅ | ✅ |
| Viable en oficial (técnicamente) | ✅ | ⚠️ (requiere token Zaap) | ✅ |
| Riesgo de detección/ban | Medio | Medio | Medio-alto (2026) |

**Recomendación según tu caso:**
- **Servidor privado propio (Starloco/emulador):** Opción **B** (full-socket) — la más limpia y escalable; tú controlas el login.
- **Servidor oficial 1.48 o no controlas el auth server:** Opción **A** (MITM) — dejas que el cliente oficial resuelva el launcher/Zaap/cifrado y tú trabajas sobre el flujo ya autenticado.
- **Prototipo rápido o tarea trivial:** Opción **C**.

---

## 7. Anti-bot y detección (estado 2026)

Contexto real reciente para que dimensiones el riesgo:

- En **enero 2026** hubo una **oleada de baneos** importante. Ankama activó nuevas rutinas de detección que apuntan a: comportamiento robótico (clicks idénticos al píxel), inyecciones de memoria "sucias" o mal hechas, y patrones inhumanos (farmear 24/7 sin pausas).
- Para MITM existe **detección por checksum/integridad del cliente** y validación del **cifrado de paquetes**: un proxy que reescribe paquetes puede romper firmas que el cliente añade. En foros técnicos se discute activamente una "nueva signature dans les packets envoyés" (2026) y detección de clientes Retro "sobre los que se leen las claves".
- El cliente Electron permite a Ankama hacer **más checks de integridad** que el viejo Flash.

**Implicaciones de diseño si te importa no ser detectado:**
- Randomizar tiempos de acción y reacción; introducir pausas y ventanas de actividad realistas.
- Evitar precisión sobrehumana (en pixel bots, jitter en coordenadas).
- En MITM, no romper el orden ni las firmas de paquetes que el cliente espera.
- Asumir que **nada es indetectable**; en oficiales el riesgo de ban es permanente.

---

## 8. Recursos clave (todos verificados)

**Protocolo / librerías**
- `kralamoure/retroproto` (Go) — catálogo completo de mensajes Retro cliente/servidor, serialización. La mejor "spec" del protocolo.
- `kralamoure/retroproxy` (Go) — proxy de referencia + `config.xml` y método "With Launcher → Local". Plantilla directa para tu MITM.
- `dofutils` (PyPI, Python) — utilidades de bot/emulador Retro en Python 3.8+.

**Bots de referencia (arquitecturas)**
- `Romain-P/Guinness-Bot` (Kotlin) — MITM event-driven; patrón handlers + FORWARD/DISCARD/MIRROR e inyección con retardo. Excelente para copiar el diseño.
- `Dyshay/Bot-Dofus-Retro` — MITM Retro con control por Discord.
- `escarrie/DofusRetroBot`, `Gamerium/Dindo-Bot` — pixel bots en Python.
- `XeLiT/retro-dbot` — bot Retro en Python.

**Login / Zaap en Python (servidor privado)**
- Proyectos Starloco en `github.com/topics/dofus-retro`: launcher Python con handoff de token Zaap (CustomTkinter) + backend FastAPI que valida hashes y genera tokens Zaap.
- `jordanamr/DivaZaap` (Go) — emulación del protocolo Launcher↔Zaap (Thrift), conceptual para tokens propios.

**Lectura de fondo**
- TFM académico "Game Hacking: Reverse engineering Dofus" (UPCommons) — metodología de RE del protocolo.

---

## 9. Ruta sugerida para empezar

1. **Define el servidor objetivo.** ¿Oficial o privado? Esto decide A vs B y cambia todo lo demás.
2. **Monta primero un proxy pasivo (Opción A, solo lectura).** Usa el `config.xml` "Local" estilo `retroproxy`, arranca el cliente desde el Launcher, conéctate vía tu proxy Python y **loguea todos los paquetes** a fichero. Esto te enseña el protocolo real de TU servidor en 1.48 sin riesgo de romper nada.
3. **Mapea los mensajes** que ves contra `retroproto` para identificar IDs y campos.
4. **Pasa a activo:** empieza con auto-login (responder a la lista de personajes), luego movimiento, luego combate.
5. Si vas a **servidor privado y quieres escalar**, migra a full-socket (Opción B) reaprovechando todo lo aprendido del protocolo, e implementa el cifrado de contraseña con el salt.

---

*Nota final: este informe describe arquitecturas y recursos públicos con fines de comprensión técnica e interoperabilidad (especialmente útil para servidores privados propios). Automatizar cuentas en servidores oficiales de Ankama infringe sus condiciones de uso.*
