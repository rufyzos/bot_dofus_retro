# Anti-cheat de Dofus Retro 1.48 (2026) — detección y supervivencia

**Fecha:** Junio 2026 · Análisis de riesgo para tu bot MITM en servidor oficial

---

## 1. Por qué este reporte importa más que los demás

Los reportes anteriores responden a "¿cómo lo construyo?". Este responde a "¿sobrevive en oficial?". Y la respuesta honesta es: **el riesgo es real, permanente y aumentó en 2026.** Ningún enfoque es indetectable. Lo que sigue te permite minimizar la superficie de detección y decidir con datos si el proyecto compensa.

Conviene separar **tres familias de detección** que Ankama combina, porque cada una se combate distinto:

1. **Detección técnica del cliente** (firma de paquetes, integridad, UID).
2. **Detección de comportamiento** (patrones robóticos, timing, estadística).
3. **Detección social/humana** (reportes de jugadores, moderadores in-game).

---

## 2. Familia 1 — Detección técnica del cliente

### 2.1 Firma de paquetes (lo más relevante para MITM, 2026)
En foros técnicos de Retro de 2026 se discute activamente una **"nueva firma en los paquetes enviados"** por el cliente. Es decir: el cliente oficial **añade una firma/checksum a ciertos paquetes salientes** (C→S), que el servidor valida. Si la firma no cuadra, el servidor sabe que el paquete no salió de un cliente legítimo intacto.

**Implicación directa para tu MITM:**
- **Ventaja:** como tú **reenvías** los paquetes que genera el cliente oficial, la firma es legítima por defecto. Es la razón por la que el MITM sobrevive donde el full-socket no: tú no firmas, firma el cliente real.
- **Peligro:** en el momento en que **reescribes o reordenas** un paquete firmado, rompes la firma → detección. Por eso la regla de oro es **inyectar paquetes nuevos** (acciones que el cliente no iba a enviar) con cuidado, y **no modificar** los que ya van firmados.
- Hay incluso herramientas (MoonBot) que ofrecen "pega un paquete capturado y comprobamos si el cifrado es válido" — señal de que la validez del cifrado/firma es el punto crítico que todos vigilan.

### 2.2 Check de integridad de ficheros (`BC` BasicsFileCheck)
En el mapeo de paquetes viste el mensaje **`BC` (BasicsFileCheck)**: el servidor pide al cliente verificar la integridad de sus archivos y el cliente responde con `BC` (BasicsFileCheckAnswer). Es el mecanismo clásico de checksums/hash sobre archivos del juego: detecta clientes modificados.

**Implicación:** otra razón para **no tocar el cliente** (no parchear `Dofus.exe`, no inyectar DLLs en él). El MITM puro pasa este check porque el cliente está intacto; un bot que modifica el binario o la memoria del cliente lo falla.

### 2.3 UID del cliente
El cliente genera un **UID** (identificador) que envía al servidor. En foros se pedía "traducir la función de generación del UID a Python" — porque un bot full-socket necesita replicarlo y es difícil. En MITM lo genera el cliente real, así que no es tu problema… salvo que lo alteres.

### 2.4 El cliente Electron permite más checks
Desde que Retro corre sobre **Electron** (antes Flash), Ankama puede hacer **verificaciones de integridad más profundas** que antes (paquetes "escondidos" en el cliente, checks adicionales). Esto sube el listón para cualquier modificación del cliente y refuerza por qué el MITM externo (sin tocar el cliente) es la vía más segura técnicamente.

### 2.5 Lo que NO tiene Retro (buenas noticias relativas)
A diferencia de juegos AAA, Retro **no usa anti-cheat a nivel kernel** (tipo BattlEye/EAC con drivers kernel y validación en boot). Esto significa que un proxy externo en otra capa de red no es detectado por un driver del sistema. La detección de Retro es a nivel **servidor + cliente de aplicación**, no a nivel SO. Es una ventaja estructural del enfoque MITM.

---

## 3. Familia 2 — Detección de comportamiento (la que más banea en 2026)

La **ban wave de enero 2026** activó rutinas que apuntan explícitamente a comportamiento, no a firmas. Lo que cazan:

| Patrón detectado | Por qué te delata | Mitigación |
|---|---|---|
| **Clicks/acciones siempre en el mismo píxel/celda exacta** | Un humano nunca repite coordenada exacta | Jitter en celda objetivo y en timing |
| **Tiempos de reacción inhumanos** | Responder en ms constantes tras `GTS` | Delay aleatorio realista antes de actuar |
| **Farmear 24/7 sin pausas** | Ningún humano juega 24h seguidas | Ventanas de actividad + pausas + sueño |
| **Movimiento no idéntico al cliente oficial** | Rutas que el cliente real nunca generaría | Usa el pathfinding REAL del cliente (mismo A\*) |
| **Inyecciones de memoria "sucias"** | Software gratuito/mal hecho modifica memoria visible | No toques memoria del cliente (MITM puro) |

> Hay un caso real documentado: un dev fue baneado con su bot socket/MITM **"porque no me desplazaba exactamente como el cliente oficial"**. Lección: el movimiento generado por tu bot debe ser **indistinguible** del que produciría el cliente. Por eso el reporte de mapas insiste en copiar el pathfinding real (`pointMov`/`pointWeight`/costes HV/D), no inventar uno propio.

### Específico de multicuenta (amplifica todo)
N personajes con comportamiento **correlacionado** es una firma estadística enorme:
- Mulas moviéndose en formación perfecta y al mismo tick → evidente. **Desincroniza** con jitter por cuenta.
- Todas reaccionando en el mismo instante → antinatural. Usa delays escalonados (~200 ms entre mulas, randomizados).
- Misma IP con muchas cuentas → en servidores monocuenta es detección directa (límite "1 cuenta por IP").

---

## 4. Familia 3 — Detección social/humana

Esta no la combates con código. Ankama da a los jugadores herramientas de **reporte directo**:

- En Retro, los jugadores reportan multicuenta/bots haciendo clic en "el ojo" (junto a los PV) → detalles del combate, o con `/whois`. Adjuntan capturas con nicks + `/time`.
- Los reportes alimentan revisión manual de moderadores. Un bot que **se comporta de forma sospechosa a ojos de otros jugadores** (no responde a MP, sigue patrones obvios, está en spots de farmeo conocidos 24/7) acumula reportes.

**Mitigación:** comportamiento discreto. Responder ocasionalmente a MPs, variar spots, no acaparar mapas, no destacar. Los bots que más caen son los más "visibles" socialmente.

Nota: ciertos modos PvP (Prisma, AvA, PvP ranked) tienen **bloqueo técnico de multicuenta** integrado en el cliente, y saltárselo está explícitamente prohibido. No metas el bot ahí.

---

## 5. Cómo funciona la detección por oleadas (y por qué te afecta)

El patrón de la industria, que Ankama replica:
- La detección **no es instantánea**. El sistema acumula señales y banea en **oleadas** (batch), con retardo deliberado.
- **Por qué lo hacen así:** el retardo impide que los cheaters identifiquen rápido qué disparó la detección. Para cuando llega la oleada, ya es tarde para muchos.
- **Qué significa para ti:** que tu bot "lleve semanas sin ban" **no prueba que sea indetectable** — puede estar ya marcado y esperando la próxima oleada. No te confíes por ausencia de ban inmediato.

---

## 6. Jerarquía de riesgo de los enfoques (resumen)

De más seguro a menos, en servidor oficial:

1. **MITM puro, sin tocar cliente, con timing humano** ← tu enfoque. Pasa firma de paquetes y `BC` porque el cliente está intacto. Riesgo principal: comportamiento.
2. **Pixel bot** — no toca red ni memoria, pero es lo que la ban wave 2026 caza primero (clicks al píxel). Riesgo: comportamiento alto.
3. **Bot que modifica memoria del cliente** — falla checks de integridad si la inyección es "sucia". Riesgo: técnico + comportamiento.
4. **Full-socket** — debe replicar firma/UID; cualquier fallo = detección inmediata. Riesgo: técnico alto.

---

## 7. Checklist anti-detección para tu MITM

**Nivel técnico:**
- [ ] No modificar `Dofus.exe` ni inyectar en su memoria (preserva `BC` y UID).
- [ ] No reescribir paquetes firmados; preferir **inyectar** acciones nuevas sobre **modificar** existentes.
- [ ] En multicuenta, aislamiento estricto por sesión (no mezclar buffers → no romper firmas).
- [ ] Usar el pathfinding REAL del cliente (mismo algoritmo y costes).

**Nivel comportamiento:**
- [ ] Delay aleatorio antes de cada acción (no constante).
- [ ] Jitter en celda objetivo (no siempre la misma casilla exacta).
- [ ] Ventanas de actividad con pausas; nada de 24/7.
- [ ] Desincronización entre cuentas (jitter por mula, delays escalonados).
- [ ] Variar rutas y spots de farmeo.

**Nivel social:**
- [ ] Responder ocasionalmente a interacciones.
- [ ] No acaparar mapas ni destacar.
- [ ] No entrar en modos PvP con bloqueo de multicuenta.

**Nivel operacional:**
- [ ] No asumir que "sin ban = seguro" (oleadas con retardo).
- [ ] No usar cuentas que te importen para probar.
- [ ] En monocuenta, una IP por cuenta (residencial).

---

## 8. Veredicto honesto sobre viabilidad

- **Técnicamente**, el MITM puro es el enfoque más resistente a la detección **técnica** de Retro, porque el cliente oficial hace todo el trabajo sensible (firma, integridad, UID) y tú no lo alteras.
- **El punto débil real es el comportamiento.** La mayoría de baneos de 2026 son por patrones, no por firmas rotas. Si tu bot se mueve y actúa de forma estadísticamente humana, sobrevives mucho más.
- **El riesgo nunca es cero.** Es servidor oficial; infringe las condiciones de Ankama; puedes perder la cuenta en cualquier oleada. Botea solo lo que estés dispuesto a perder.

---

## 9. Recursos

- **`Romain-P/Guinness-Bot`** — justifica el MITM precisamente por "aprovechar un cliente limpio" y menciona los checks extra que permite Electron. Referencia de la filosofía anti-detección.
- **`dofus-bot.fr`** — enfoque MITM/passive vía Npcap; ejemplo de bot que "observa sin modificar el cliente".
- Foros técnicos (cadernis.fr, cheat-gam3) — hilos 2026 sobre la nueva firma de paquetes y detección de clientes "sobre los que se leen las claves".
- Soporte Ankama — reglas de reporte de multicuenta/bots y bloqueo técnico en PvP.
- Mapeo de paquetes (reporte previo) — `BC` BasicsFileCheck, ubicación de la firma en paquetes salientes.

---

*Este análisis describe mecanismos de detección con fines de comprensión de riesgo. Automatizar en servidores oficiales de Ankama infringe sus condiciones de uso y puede acarrear el baneo permanente de la cuenta. La información aquí no constituye garantía alguna de no ser detectado.*
