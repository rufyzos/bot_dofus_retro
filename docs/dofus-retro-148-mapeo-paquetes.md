# Mapeo de paquetes Dofus Retro 1.48 — referencia de protocolo

**Fecha:** Junio 2026 · Catálogo de mensajes para tu bot MITM en Python

---

## 1. Cómo funciona el protocolo (lo mínimo para leer la tabla)

Dofus Retro usa un **protocolo de texto ASCII sobre TCP**. Cada mensaje es:

```
<ID><cuerpo>\x00
```

- **ID** = prefijo de 2-4 caracteres que identifica el tipo de mensaje (`GM`, `GA`, `GDM`, `Af`…). El ID **no es de longitud fija**: para identificarlo se prueba el prefijo más largo que coincida (por eso `GM` y `GM|-` son distintos, y `AM`, `AM?`, `AM-` conviven).
- **cuerpo** = campos separados normalmente por `|` (a veces `;` para listas, o sin separador).
- **`\x00`** (NUL) = terminador de cada mensaje en el stream.

Dirección de los mensajes:
- **C→S (cliente → servidor):** lo que el cliente *pide/hace*. En `retroproto` se llaman `MsgCli` (195 IDs).
- **S→C (servidor → cliente):** lo que el servidor *informa*. Se llaman `MsgSvr` (309 IDs).

> Convención frecuente en respuestas del servidor: sufijo **`K`** = éxito (OK), **`E`** = error. Ej: `ATK` (ticket OK) / `ATE` (ticket error); `ESK` (venta OK) / `ESE` (venta error).

**Fuente canónica:** `kralamoure/retroproto` (Go). Todo lo de abajo está sacado de ahí. Aunque programes en Python, es tu diccionario maestro: define los IDs, y los subpaquetes `msgcli/` y `msgsvr/` definen los campos de cada uno.

---

## 2. Bloque de cifrado y login (lo necesitas si haces login; en MITM lo ves pasar)

`retroproto` expone además las funciones criptográficas del login:

- `EncryptPassword(pwd, key)` — cifra la contraseña usando el **salt** que llega en `HC`. Esta es la función que en C# se pedía traducir a Python en los foros; aquí la tienes como referencia de implementación.
- `Encode64(n)` / `Decode64(ch)` — el "pseudo-base64" propio de Dofus (alfabeto de 64 chars) usado para codificar enteros compactos (IDs de celda, etc.). **Lo vas a usar muchísimo** para decodificar posiciones y datos de mapa.
- `SplitEncodedHostPortTicket(extra)` — parsea el cuerpo de `AYK` (host, puerto, ticket) del game server. Justo lo que reescribes en el MITM.

---

## 3. Handshake completo (orden real de mensajes)

### Fase login
| Paso | Dir | ID | Nombre | Notas |
|------|-----|-----|--------|-------|
| 1 | S→C | `HC` | AksHelloConnect | Envía el **salt** |
| 2 | C→S | `version` | AccountVersion | **Sin ID de protocolo** en el paquete |
| 3 | C→S | `credential` | AccountCredential | **Sin ID**; contraseña cifrada con el salt |
| 4 | S→C | `AlK`/`AlE` | AccountLoginSuccess/Error | |
| 5 | C→S | `Ax` | AccountGetServersList | |
| 6 | S→C | `AxK`/`AxE` | AccountServersListSuccess/Error | Lista de servidores |
| 7 | C→S | `AX` | AccountSetServer | Selección de servidor |
| 8 | S→C | `AYK` | AccountSelectServerPlainSuccess | **host:puerto;ticket** del game server ← *esto reescribes en MITM* |

### Fase game
| Paso | Dir | ID | Nombre | Notas |
|------|-----|-----|--------|-------|
| 9 | S→C | `HG` | AksHelloGame | |
| 10 | C→S | `AT` | AccountSendTicket | Reenvía el ticket |
| 11 | S→C | `ATK`/`ATE` | AccountTicketResponseSuccess/Error | |
| 12 | C→S | `Af` | AccountQueuePosition | Pide cola |
| 13 | S→C | `Af`/`Aq` | AccountNewQueue/AccountQueue | Estado de cola (`Af1|2|0||-1`) |
| 14 | C→S | `AL` | AccountGetCharacters | Pide lista de personajes |
| 15 | S→C | `ALK`/`ALE` | AccountCharactersListSuccess/Error | |
| 16 | C→S | `AS` | AccountSetCharacter | **Selecciona personaje** (gancho auto-login) |
| 17 | S→C | `ASK`/`ASE` | AccountCharacterSelectedSuccess/Error | |
| 18 | C→S | `GC` | GameCreate | Entra al mundo |
| 19 | S→C | `GCK`/`GCE` | GameCreateSuccess/Error | |

---

## 4. Catálogo por dominio funcional

A continuación, los IDs agrupados por lo que vas a querer hacer. **C→S** = lo inyectas tú; **S→C** = lo parseas para leer estado.

### 4.1 Mapa, posición y movimiento (núcleo del bot)
| Dir | ID | Nombre | Para qué |
|-----|-----|--------|----------|
| C→S | `GD` | GameGetMapData | Pedir datos del mapa al entrar |
| S→C | `GDM` | GameMapData | **Datos del mapa** (clave para pathfinding) |
| S→C | `GDK` | GameMapLoaded | Mapa cargado |
| S→C | `GDC` | GameCellData | Datos de celda |
| S→C | `GDZ` | GameZoneData | Zona |
| S→C | `GDO` | GameCellObject | Objeto en celda |
| S→C | `GDF` | GameFrameObject2 | Objetos del decorado |
| C→S | `GA` | GameActionsSendActions | **Acción de juego** (incluye movimiento por celdas) |
| S→C | `GA` | GameActions | Acción confirmada/transmitida |
| S→C | `GAS` | GameActionsStart | Inicio de acción |
| S→C | `GAF` | GameActionsFinish | Fin de acción |
| C→S | `GKK` | GameActionAck | ACK de acción |
| C→S | `GKE` | GameActionCancel | Cancelar acción |
| S→C | `GM` | GameMovement | **Movimiento/aparición de actores** en mapa |
| S→C | `GM\|-` | GameMovementRemove | Actor sale del mapa |
| C→S | `Gp` | GameSetPlayerPosition | Fijar posición (placement) |
| S→C | `GP` | GamePositionStart | Posición de inicio (combate) |
| S→C | `GIC` | GamePlayersCoordinates | Coordenadas de jugadores |
| C→S | `IM` / S→C `IM` | InfosGetMaps/InfoMaps | Info de mapas (cambios de mapa) |
| S→C | `IC` | InfosCompass | Brújula |

> El **movimiento** se envía como un `GA` (GameActionsSendActions) con la acción de tipo desplazamiento y una ruta de celdas codificadas. Las celdas usan el alfabeto Encode64. Mapear `GDM`/`GM`/`GA` es el 80% del trabajo de navegación.

### 4.2 Combate (el otro núcleo)
| Dir | ID | Nombre | Para qué |
|-----|-----|--------|----------|
| S→C | `GS` | GameStartToPlay | Empieza el combate |
| S→C | `GJ` | GameJoin | Unirse a combate |
| C→S | `GR` / S→C `GR` | GameRequestReady/GameReady | **Marcar listo** (pre-combate) |
| S→C | `GTL` | GameTurnList | Orden de turnos |
| S→C | `GTS` | GameTurnStart | **Empieza un turno** (¿es el mío?) |
| S→C | `GTM` | GameTurnMiddle | |
| S→C | `GTF` | GameTurnFinish | Fin de turno |
| S→C | `GTR` | GameTurnReady | |
| C→S | `Gt` / `GT` | GameTurnEnd/GameTurnOk | **Pasar turno** |
| C→S | `GA` | GameActionsSendActions | **Lanzar sortilegio** (acción de combate) |
| S→C | `GIE` | GameEffect | **Efecto aplicado** (daño, buff…) |
| S→C | `GIe` | GameClearAllEffect | Limpiar efectos |
| S→C | `Gc` | GameChallenge | Desafío |
| S→C | `Gt`(svr) | GameTeam | Equipos |
| S→C | `GE` | GameEnd | Fin de combate |
| S→C | `GO` | GameGameOver | Game over |
| C→S | `GQ` | GameRequestLeave | Salir |
| C→S | `Gdi`/S→C `Gd` | ShowFightChallengeTarget/GameFightChallenge | Retos |
| C→S | `fH` | FightsNeedHelp | Pedir ayuda |
| C→S | `fS`/`fP`/`fN` | Block spectators/joiners | Bloquear espectadores/uniones |
| S→C | `fL`/`fD`/`fC` | FightsList/Details/Count | Lista de combates en mapa |

> Patrón de combate: esperas `GTS` (¿soy yo?) → lees `getAllFighters` a partir de los `GM`/`GIC`/`GIE` acumulados → envías `GA` (sortilegio) → recibes `GIE` (efectos) → `Gt` (pasar turno).

### 4.3 Sortilegios
| Dir | ID | Nombre | Para qué |
|-----|-----|--------|----------|
| S→C | `SL` | SpellsList | **Lista de sortilegios del personaje** (de aquí sacas spell_ids) |
| C→S | `SM` | SpellsMoveToUsed | Poner sort en barra |
| C→S | `SB`/S→C `SB` | SpellsBoost/SpellBoost | Subir sort |
| C→S | `SF` | SpellsForget | Olvidar |
| S→C | `SUK`/`SUE` | UpgradeSpell Success/Error | |

### 4.4 Inventario y objetos
| Dir | ID | Nombre | Para qué |
|-----|-----|--------|----------|
| C→S | `OM` / S→C `OM` | ItemsRequestMovement/Movement | Mover objeto (equipar) |
| C→S | `OD`/`Od` | ItemsDrop/Destroy | Tirar/destruir |
| C→S | `OU`/`Ou` | ItemsUseNoConfirm/UseConfirm | **Usar objeto** |
| C→S | `Of` | ItemsFeed | Alimentar (montura/familiar) |
| S→C | `OAK`/`OAE` | ItemsAdd Success/Error | **Objeto añadido** al inventario |
| S→C | `OR` | ItemsRemove | Objeto quitado |
| S→C | `OQ` | ItemsQuantity | Cambio de cantidad |
| S→C | `OC` | ItemsChange | Cambio de objeto |
| S→C | `Ow` | ItemsWeight | **Peso/pods** (gestión de carga) |
| S→C | `OF` | ItemsItemFound | Objeto encontrado (botín) |
| S→C | `Oa` | ItemsAccessories | Accesorios visibles |

### 4.5 Intercambios, banco, HDV, craft (economía)
| Dir | ID | Nombre | Para qué |
|-----|-----|--------|----------|
| C→S | `ER`/S→C `ERK`/`ERE` | ExchangeRequest/Success/Error | **Iniciar intercambio** |
| C→S | `EA`/`EK` | ExchangeAccept/RequestReady | Aceptar/listo |
| C→S | `EV`/S→C `EVK` | ExchangeLeave/Success | Salir del intercambio |
| C→S | `EMO` | ExchangeMovementItems | Mover items en intercambio |
| C→S | `EMG` | ExchangeMovementKamas | Mover kamas |
| C→S | `ES`/S→C `ESK`/`ESE` | ExchangeMovementSell/Success/Error | **Vender** (banco/HDV) |
| C→S | `EB`/S→C `EBK`/`EBE` | ExchangeMovementBuy/Success/Error | **Comprar** |
| C→S | `EHT` | ExchangeBigStoreType | Tipo en HDV |
| C→S | `EHl`/S→C `EHl` | BigStoreItemList | **Lista de items HDV** |
| C→S | `EHB` | ExchangeBigStoreBuy | Comprar en HDV |
| C→S | `EHS`/S→C `EHSK`/`EHSE` | BigStoreSearch/Success/Error | Buscar en HDV |
| C→S | `EHP`/S→C `EHP` | ItemMiddlePrice | **Precio medio** (para fijar precio venta) |
| C→S | `Erp`/`Erg` | PutInShedFromInventory/Inverse | **Banco** (meter/sacar) |
| C→S | `EMR`/`EMr` | RepeatCraft/StopRepeat | Craft repetido |
| S→C | `EcK`/`EcE` | ExchangeCraft Success/Error | Resultado de craft |
| S→C | `EHM+`/`EHM-` | BigStore items add/remove | Stream de items HDV |

### 4.6 Personaje, stats, trabajos
| Dir | ID | Nombre | Para qué |
|-----|-----|--------|----------|
| S→C | `As` | AccountStats | **Stats del personaje** (vida, PA, PM…) |
| S→C | `AN` | AccountNewLevel | Subida de nivel |
| S→C | `As`(stats) | — | Incluye PA/PM actuales (clave para IA) |
| S→C | `JS` | JobSkills | Habilidades de oficio |
| S→C | `JX` | JobXP | XP de oficio |
| S→C | `JN` | JobLevel | Nivel de oficio |
| C→S | `JO`/S→C `JO` | JobChangeStats/Options | Opciones de oficio |
| S→C | `Im` | InfosMessage | **Mensajes del servidor** (textos, errores in-game) |
| S→C | `IQ` | InfosQuantity | Cantidad (recolección) |
| S→C | `ILS`/`ILF` | LifeRestoreTimer Start/Finish | Regeneración de vida |

### 4.7 Diálogos / PNJ (quests, zaaps, banco vía PNJ)
| Dir | ID | Nombre | Para qué |
|-----|-----|--------|----------|
| C→S | `DC`/S→C `DCK`/`DCE` | DialogCreate/Success/Error | **Hablar con PNJ** |
| S→C | `DQ` | DialogQuestion | Pregunta del PNJ (opciones) |
| C→S | `DR` | DialogResponse | **Elegir respuesta** |
| C→S | `DV`/S→C `DV` | DialogLeave | Salir del diálogo |
| C→S | `WU`/S→C `WC`/`WV` | WaypointsUse/Create/Leave | **Zaaps** |
| C→S | `Wu`/S→C `Wc` | SubwayUse/Create | Zaapis (subway) |

### 4.8 Social (grupo, amigos, gremio, chat)
| Dir | ID | Nombre | Para qué |
|-----|-----|--------|----------|
| C→S | `PI`/S→C `PIK`/`PIE` | PartyInvite/Success/Error | **Invitar a grupo** (multicuenta) |
| C→S | `PA`/`PR` | PartyAccept/Refuse | Aceptar/rechazar |
| C→S | `PF`/S→C `PFK`/`PFE` | PartyRequestFollow/Success/Error | **Seguir** (líder/mulas) |
| C→S | `PG` | PartyFollowAll | Seguir a todos |
| S→C | `PM` | PartyMovement | Movimiento de grupo |
| S→C | `PL` | PartyLeader | Líder del grupo |
| C→S | `BM`/S→C `cMK`/`cME` | ChatSend/Success/Error | **Chat** |
| S→C | `cs` | ChatServerMessage | Mensaje de servidor en chat |
| C→S | `FL`/S→C `FL` | FriendsGetList/List | Amigos |
| C→S | `gC`/`gIM`… | Guild* | Gremio (percetores, etc.) |

### 4.9 Básicos / sistema (anti-cheat, ping, checks)
| Dir | ID | Nombre | Para qué |
|-----|-----|--------|----------|
| S→C | `BC`/C→S `BC` | BasicsFileCheck/Answer | **Check de integridad de ficheros** ← relevante anti-cheat |
| C→S | `BD`/S→C `BD` | BasicsGetDate/Date | Fecha in-game |
| S→C | `BT` | BasicsTime | Hora |
| C→S | `BW`/S→C `BWK`/`BWE` | BasicsWhoIs/Success/Error | WhoIs |
| C→S | `BYA`/`BYI` | BasicsAway/Invisible | Estado |
| C→S | `Bp`/S→C `Bp` | RequestAveragePing/AveragePing | **Ping** (timing) |
| S→C | `BN` | BasicsNothing | Keep-alive / nada |
| C→S | `ping`/`qping` | AksPing/QuickPing | Ping de bajo nivel |
| S→C | `M` | AksServerMessage | Mensaje de servidor |
| S→C | `k` | AksServerWillDisconnect | **Aviso de desconexión** |

> **Atención anti-cheat:** `BC` (BasicsFileCheck) es el mensaje con el que el servidor pide al cliente verificar integridad de archivos; en MITM lo ves pasar y **no debes alterarlo**. Junto con la firma/UID en paquetes salientes, es uno de los puntos donde un MITM mal hecho se delata.

---

## 5. Cómo construir tu parser en Python (estrategia)

1. **Tabla de IDs ordenada por longitud descendente.** Como los IDs no son de longitud fija, al recibir un mensaje pruebas a hacer match del prefijo más largo primero (`GM|-` antes que `GM`; `AM?`/`AM-` antes que `AM`). Construye un dict `{id: handler}` y un matcher que recorra de 4→2 chars.

2. **Replica los structs de campos desde `msgcli/` y `msgsvr/`.** El ID solo te dice *qué* mensaje es; los campos (separados por `|`) están definidos en los subpaquetes de `retroproto`. Para cada mensaje que te importe, abre su archivo Go y copia el orden/tipo de campos.

3. **Prioriza por fases.** No mapees los 504 mensajes. Orden recomendado:
   - **Fase 1 (conectar y verse):** handshake (sección 3) + `GDM`, `GM`, `As`.
   - **Fase 2 (moverse):** `GA` movimiento, `IM`, `GDK`.
   - **Fase 3 (combate):** `GS`, `GTS`, `GTL`, `GA` sortilegio, `GIE`, `Gt`.
   - **Fase 4 (recolectar/economía):** `IQ`, `OAK`, `Ow`, intercambios/banco/HDV.
   - **Fase 5 (social/multicuenta):** `PI`, `PF`, `PG`.

4. **Modo log primero (recordatorio).** Captura el tráfico real de TU servidor 1.48 y **valida cada campo** contra la spec — pequeñas variantes entre versiones existen, y `retroproto` es de ~2022.

---

## 6. Resumen de cifras

- **195** mensajes cliente (`MsgCli`).
- **309** mensajes servidor (`MsgSvr`).
- Para un bot funcional (mover + combatir + recolectar + HDV + grupo) necesitas mapear realmente **~40-60 mensajes**, no los 504.

---

## 7. Recursos

- **`kralamoure/retroproto`** — fuente de TODO lo anterior. Archivos clave: `msgcli.go`, `msgsvr.go` (los IDs), `crypto.go` (cifrado/Encode64), subdirs `msgcli/` y `msgsvr/` (los campos de cada mensaje).
- **`dofutils`** (PyPI) — utilidades de serialización Retro ya en Python; te ahorra reescribir `Encode64`/`Decode64` y parte del parsing.
- **`kralamoure/retro` / `retroutil`** — tipos de datos y utilidades de bajo nivel del cliente original (lógica de celdas, mapas).
- APIs de datos (dofapi, moon-bot wiki) — para cruzar spell_ids/items/monstruos con nombres.

---

*Este mapeo es una herramienta de interoperabilidad. Recuerda que su uso para automatización en servidores oficiales infringe las condiciones de Ankama.*
