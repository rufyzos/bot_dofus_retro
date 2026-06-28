# Multicuenta en Dofus Retro 1.48 (servidor MULTICUENTA, oficial, Windows, vía MITM)

**Fecha:** Junio 2026 · Extensión del informe MITM para N cuentas en paralelo

> **Alcance:** este informe asume **servidor multicuenta** (la mayoría de los Retro oficiales), donde el multiboxing está **permitido** y varias ventanas desde una sola IP funcionan sin problema. El caso de servidor **monocuenta** (Draconiros y similares) se trata solo como nota al final (sección 8b), porque ahí las restricciones de IP lo cambian todo.

---

## 1. El cambio de mentalidad

En monocuenta el reto era *conectar*. En multicuenta el reto es *escalar y enrutar*: tienes **N clientes oficiales abiertos a la vez**, cada uno con su propia sesión, y un proxy que debe **distinguir y gestionar N flujos simultáneos sin mezclarlos**. El MITM sigue siendo la base (dejas que el Launcher autentique cada cuenta), pero alrededor aparecen tres problemas nuevos:

1. **Lanzar N clientes** desde el Launcher.
2. **Enrutar N conexiones** en un solo proxy (el reto técnico central).
3. **Coordinar** los personajes entre sí (líder + mulas, sincronía de combate).

En servidor multicuenta, los límites de Ankama **no son un obstáculo de infraestructura**: el multiboxing está permitido y una sola IP basta. El cuello de botella real es **físico** (RAM por cliente) y de **comportamiento** (no parecer un bot), no de IPs ni proxies.

---

## 2. Lo que en servidor multicuenta NO es problema

Buenas noticias: en servidor multicuenta, varias cosas que parecerían bloqueos no lo son.

- **Multiboxing permitido:** correr varias ventanas a la vez es una práctica aceptada y soportada nativamente por el Launcher. No estás saltándote ninguna regla por tener N clientes abiertos.
- **Misma IP, sin problema:** todas tus cuentas pueden conectarse desde la **misma IP/PC**. No necesitas proxies, VPN ni VMs para repartir IPs. El límite estricto de "1 cuenta por IP" es exclusivo de los **servidores monocuenta** (ver sección 8b).
- **Sin arquitectura "Modern" obligatoria:** ese requisito es solo del servidor monocuenta.

**Lo que SÍ debes vigilar incluso en multicuenta:**
- **Ciertos modos PvP** (Prisma, AvA, PvP ranked) tienen **bloqueo técnico de multicuenta** integrado en el cliente, y saltárselo está explícitamente prohibido. No metas el bot ahí.
- **Detección por comportamiento correlacionado** (sección 7): N personajes actuando de forma idéntica y sincronizada es la mayor firma de bot. Esto aplica en cualquier servidor.

---

## 3. Lanzar N clientes oficiales

El Ankama Launcher ya soporta multicuenta de forma nativa (función oficial desde hace años):

- Añades varias cuentas al Launcher (todas del mismo titular).
- Las lanzas una a una desde el menú **Multi-Accounting**, o con el atajo **`Ctrl`+`<número>`**, o con el modo "one-by-one" automático.
- Cada cliente arranca con su propio `instanceId` (recuerda los argumentos Zaap: `--instanceId=$ZAAP_INSTANCE_ID`), lo que permite que varias instancias coexistan.

**Coste en RAM:** Ankama documenta **~2 GB de RAM por cliente**. Para 8 cuentas → ~32 GB sin contar Windows. Es el primer cuello de botella físico real. Desde la 1.79 ya **no se puede lanzar el cliente de 32 bits**, así que cuenta con clientes de 64 bits (más memoria por instancia).

Todos los clientes apuntan al **mismo `config.xml` "Local"** (sección 4 del informe anterior), porque comparten el directorio `…\Ankama\Retro\resources\app\retroclient\`. Es decir: los N clientes se conectarán a tu proxy local. El truco está en cómo los separas.

---

## 4. Las dos arquitecturas de proxy multicuenta

### Opción 1 — Un proxy, N sesiones (recomendada)

Un **único proceso Python** escucha en el puerto de login (`5555`) y acepta **múltiples conexiones entrantes**. Con `asyncio`, cada cliente que se conecta dispara un `handle_login` independiente; el servidor ya es concurrente por diseño. Cada sesión mantiene su propio estado (su `game_target`, su buffer, su personaje).

**Reto del enrutado game server:** en monocuenta reescribíamos `AYK<ip>:<port>` para que el cliente volviera a `127.0.0.1:5556`. Con N clientes, si todos vuelven al **mismo** puerto 5556, el proxy no sabe **qué conexión entrante corresponde a qué sesión de login**. Soluciones:

- **Puerto de game dinámico por sesión:** cuando interceptas el `AYK` de la cuenta *k*, abres un listener efímero en un puerto libre (p. ej. 5600+k) y reescribes `AYK` apuntando a ese puerto. Así cada cliente tiene su propio puerto de game y la correspondencia es 1:1. Es el enfoque más limpio.
- **Correlación por ticket:** el ticket que viaja en `AYK` es único por sesión. Guardas un mapa `ticket → sesión` y, cuando llega la conexión de game con `AT<ticket>`, recuperas a qué cuenta pertenece. (Es justo lo que hace `retroproxy` con su `Storer`/`Ticket{Host,Port,Original,ServerId}` y su `UseTicket(id)`.) Permite reusar un solo puerto de game.

> El patrón "ticket store" de `retroproxy` (`SetTicket`/`UseTicket`/`DeleteOldTickets`) está **pensado exactamente para esto**: desacoplar la fase login de la fase game cuando hay concurrencia. Cópialo.

**Ventajas:** un solo proceso, estado compartido en memoria (ideal para coordinar cuentas entre sí), menor overhead.
**Inconveniente:** si el proceso cae, caen todas las sesiones.

### Opción 2 — N proxies, uno por cliente

Lanzas **una instancia de proxy por cuenta**, cada una en su par de puertos (`5555+k` / `5556+k`). Cada cliente apunta a su proxy. Aislamiento total.

**Problema en Retro:** todos los clientes comparten el mismo `config.xml`, que define un único "Local". Tendrías que generar `config.xml` distintos por cliente, lo cual choca con el directorio compartido. Por eso en Retro la Opción 1 (un proxy, multiplexado) es netamente preferible. La Opción 2 solo tiene sentido si por algún motivo aíslas cada cliente en su propia VM, lo cual en servidor multicuenta no es necesario.

---

## 5. Esqueleto: un proxy, N sesiones (asyncio)

```python
import asyncio, itertools

LOGIN_UPSTREAM = ("dofusretro-co-production.ankama-games.com", 443)
LOGIN_LISTEN   = ("127.0.0.1", 5555)

# Asignación de puertos de game por sesión
_port_gen = itertools.count(5600)

# Estado global: todas las sesiones vivas (para coordinación entre cuentas)
SESSIONS = {}   # session_id -> Session

class Session:
    def __init__(self, sid):
        self.id = sid
        self.game_host = None
        self.game_port = None
        self.local_game_port = next(_port_gen)
        self.character = None
        self.last_map = None

def split_messages(buf):
    parts = buf.split(b"\x00")
    return parts[:-1], parts[-1]

async def pump(reader, writer, transform):
    buf = b""
    try:
        while not reader.at_eof():
            chunk = await reader.read(4096)
            if not chunk: break
            buf += chunk
            msgs, buf = split_messages(buf)
            for raw in msgs:
                if not raw: continue
                out = transform(raw.decode("utf-8", "replace"))
                if out is None: continue
                writer.write(out.encode() + b"\x00")
            await writer.drain()
    finally:
        try: writer.close()
        except: pass

async def handle_login(cr, cw):
    sid = id(cr)
    sess = Session(sid); SESSIONS[sid] = sess
    sr, sw = await asyncio.open_connection(*LOGIN_UPSTREAM)

    # listener de game DEDICADO a esta sesión
    async def handle_game(gcr, gcw):
        gsr, gsw = await asyncio.open_connection(sess.game_host, sess.game_port)
        await asyncio.gather(
            pump(gcr, gsw, lambda m: on_game(sess, "C->S", m)),
            pump(gsr, gcw, lambda m: on_game(sess, "S->C", m)),
        )
    game_srv = await asyncio.start_server(handle_game, "127.0.0.1", sess.local_game_port)

    def on_login(direction, m):
        if direction == "S->C" and m.startswith("AYK"):
            body = m[3:]; addr, _, ticket = body.partition(";")
            host, _, port = addr.partition(":")
            sess.game_host, sess.game_port = host, int(port)
            return f"AYK127.0.0.1:{sess.local_game_port};{ticket}"
        return m

    async with game_srv:
        await asyncio.gather(
            pump(cr, sw, lambda m: on_login("C->S", m)),
            pump(sr, cw, lambda m: on_login("S->C", m)),
        )
    SESSIONS.pop(sid, None)

def on_game(sess, direction, m):
    # estado por sesión + ganchos de coordinación (sección 6)
    if direction == "S->C" and m.startswith("GM"):
        sess.last_map = m  # ejemplo: trackear mapa
    print(f"[{sess.id} {direction}] {m!r}")
    return m

async def main():
    srv = await asyncio.start_server(handle_login, *LOGIN_LISTEN)
    print("Proxy multicuenta en login :5555, game :5600+")
    async with srv:
        await srv.serve_forever()

asyncio.run(main())
```

La clave: **un listener de game por sesión** en puerto propio, y un `Session` por cliente. `SESSIONS` global te da acceso a todas a la vez para coordinarlas.

---

## 6. Coordinación entre cuentas (lo que hace útil el multicuenta)

Aquí está el valor real. Como todas las sesiones viven en el mismo proceso Python, puedes orquestarlas. Patrones típicos (presentes en bots Retro como MoonBot/AnkaBot):

- **Líder + mulas:** un personaje "líder" decide; al detectar que el líder cambia de mapa (`GM`/cambio de mapa S→C), **inyectas** en las sesiones de las mulas el paquete de seguir/cambiar de mapa. Así no controlas N ventanas a mano.
- **Sincronía de combate:** cuando el líder inicia un combate, inyectas las uniones de las mulas; gestionas el orden de turnos leyendo los paquetes de combate de cada sesión y respondiendo por cada una en su turno.
- **Vaciado de banco / intercambios automáticos:** una cuenta recolecta, las demás reciben por intercambio; coordinas los paquetes de trade entre dos sesiones.
- **Coordinación temporal:** los bots multicuenta usan delays entre mulas (`DELAY_JOIN_MULES`, `DELAY_READY_MULES`, `DELAY_CLICK_BETWEEN_MULES`, ~200 ms cada uno en implementaciones reales) para no actuar todos en el mismo milisegundo (lo que sería una firma robótica evidente).

Diseño recomendado: un **bus de eventos** central. Cada sesión publica eventos (`map_changed`, `fight_started`, `turn_ready`), y un **orquestador** suscrito decide qué inyectar en qué sesiones. Esto evita acoplar sesiones entre sí directamente.

---

## 7. Anti-detección en multicuenta (crítico, 2026)

Multicuenta **amplifica el riesgo** porque N personajes con comportamiento correlacionado es una firma estadística enorme. Tras la ban wave de enero 2026, vigila:

- **Movimiento idéntico/sincronizado:** hay reportes concretos de baneo por "no moverse exactamente como el cliente oficial". Si tus N mulas se mueven en formación perfecta y al mismo tick, te delatas. **Desincroniza** con jitter por cuenta.
- **Tiempos correlacionados:** que todas las cuentas reaccionen en el mismo instante es antinatural. Aplica los delays escalonados de la sección 6 y randomízalos.
- **Firma/UID de paquetes:** cada cliente añade su firma; el MITM la preserva si **no reescribes** los paquetes firmados. Con N sesiones, no mezcles buffers entre sesiones (un bug de enrutado que envíe el paquete de una cuenta por el socket de otra rompe la firma y es baneo inmediato). El aislamiento por `Session` del esqueleto evita esto.
- **Volumen por IP:** en servidor multicuenta una sola IP basta y es legítima, pero mantén un volumen razonable — 30 cuentas desde una IP doméstica sigue siendo un patrón llamativo aunque esté permitido. (El límite *estricto* de 1 por IP es solo de monocuenta.)
- **24/7:** N cuentas farmeando sin pausa, todas a la vez, es lo más detectable que hay. Ventanas de actividad con pausas, idealmente desfasadas entre cuentas.

> Nota: existen herramientas comerciales (Frigost, etc.) que hacen **spoofing de HWID**, pensadas sobre todo para permitir multicuenta en servidores **monocuenta** sin VMs. En servidor multicuenta no las necesitas. Son trampa de cara a Ankama y elevan el riesgo de baneo; se mencionan solo para que sepas que existen.

---

## 8. Dimensionamiento práctico (una sola máquina Windows)

| Nº cuentas | RAM mínima (≈2 GB/cliente) | Viabilidad en 1 PC |
|---|---|---|
| 2-3 | 8-16 GB | Cómodo |
| 4-6 | 16-32 GB | Requiere PC potente |
| 8 | 32 GB+ | Límite práctico de una máquina doméstica |
| >8 | Multi-máquina | Necesario repartir por RAM |

Para muchas cuentas, lo habitual es **repartir en varias máquinas** (cada una con su proxy y su tanda de clientes), con un orquestador central. En servidor multicuenta esto es solo por la RAM, no por IPs: todas pueden compartir IP sin problema.

> Alternativa "sin servidor propio": bots cloud como **MoonBot** corren en la nube y gestionan el multicuenta/sincronía por ti (sin RAM local ni VPS). Es la vía sin código, a cambio de confiar en un tercero y los mismos riesgos de baneo.

---

## 8b. Nota: si fuera servidor MONOCUENTA (caso distinto)

Si en algún momento apuntaras a un servidor **monocuenta** (Draconiros y similares), las reglas cambian radicalmente y casi nada de lo anterior aplica tal cual:

- **Límite estricto de 1 cuenta conectada por IP.** Para varias cuentas necesitas **una IP distinta por cuenta**: proxies **residenciales** (los datacenter están casi todos en blacklist de Ankama) o **VMs con red separada**. Multiplica coste y complejidad.
- **Arquitectura "Modern" obligatoria** del cliente, o el servidor te rechaza ("client incompatible").
- **Prohibido** tener una cuenta en modo mercader mientras juegas con otra.
- Es **terreno de alto riesgo**: saltarse el límite de IP es explícitamente sancionable.

En resumen: el multicuenta en monocuenta es un proyecto de infraestructura (IPs/VMs) además de software. Para tu caso (servidor multicuenta) nada de esto te afecta.

---

## 9. Checklist multicuenta

1. [ ] Confirmar que es **servidor multicuenta** (multiboxing permitido, 1 IP basta). Si fuera monocuenta, ver sección 8b antes de seguir.
2. [ ] Comprobar RAM disponible (~2 GB × Nº cuentas).
3. [ ] Añadir todas las cuentas al Ankama Launcher; probar lanzar 2 con `Ctrl`+`2`.
4. [ ] `config.xml` "Local" único (compartido) en `…\retroclient\`.
5. [ ] Proxy Python **multiplexado** (un proceso, listener de game por sesión) — esqueleto sección 5.
6. [ ] Validar en **modo solo-log** con 2 cuentas que los flujos NO se mezclan (cada `Session` ve solo lo suyo).
7. [ ] Implementar bus de eventos + orquestador (líder/mulas).
8. [ ] Añadir jitter y delays escalonados por cuenta desde el primer momento.
9. [ ] Escalar a más cuentas / más máquinas solo cuando 2 funcionen de forma estable.

---

## 10. Recursos adicionales para multicuenta

- **`kralamoure/retroproxy`** — su `Storer`/`Ticket`/`UseTicket` es el patrón de correlación login↔game que necesitas para concurrencia. Imprescindible leerlo.
- **`Romain-P/Guinness-Bot`** — `ProxyClientContext` (1 contexto de proxy por bot) muestra cómo encapsular el estado por cuenta; modelo directo para tu clase `Session`.
- **MoonBot / AnkaBot** — referencia funcional de coordinación líder+mulas, sincronía de combate y delays entre mulas (los nombres de parámetros de delay vienen de implementaciones reales).
- **FAQ Launcher Ankama** + doc de configuraciones recomendadas — multi-accounting nativo, atajo `Ctrl`+nº, requisito de 2 GB/cliente y fin del cliente 32-bit (1.79).
- **Soporte Ankama "single-account mode"** — confirma el límite "1 cuenta por IP" y la exigencia de arquitectura "Modern" en servidores monocuenta.

---

*Recordatorio: el multicuenta automatizado en servidores oficiales infringe las condiciones de uso de Ankama. Aunque el multiboxing manual esté permitido en servidores multicuenta, automatizarlo no lo está. El riesgo de baneo se multiplica con N cuentas correlacionadas: la desincronización de comportamiento entre cuentas es lo que más reduce ese riesgo. Nada de lo aquí descrito garantiza impunidad.*
