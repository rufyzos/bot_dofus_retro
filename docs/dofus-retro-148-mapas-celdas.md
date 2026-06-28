# Sistema de mapas y celdas en Dofus Retro 1.48 — referencia técnica

**Fecha:** Junio 2026 · Para navegación, pathfinding y combate de tu bot

---

## 1. Modelo mental: el mundo en tres niveles

Dofus Retro organiza el espacio en tres capas que tu bot debe distinguir:

1. **Mundo (coordenadas X,Y):** cada mapa tiene unas coordenadas tipo `4,-19`. Útiles para describir trayectos, **pero ambiguas**: varios mapas comparten las mismas coordenadas (interior/exterior de un edificio, mapas de Pandala divididas en dos). Por eso para esos casos se usa el **mapId**.
2. **Mapa (mapId):** identificador único y entero de cada mapa concreto. Se obtiene en el juego escribiendo `/mapid` en el chat. Es lo que de verdad identifica dónde estás cuando las coordenadas no bastan.
3. **Celda (cellId):** dentro de un mapa, cada casilla tiene un número (`cellId`). Una mapa de Dofus tiene **560 celdas** (0–559), dispuestas en una rejilla isométrica.

Tu sistema de navegación trabaja en los tres: trayectos a alto nivel por coordenadas/mapId, movimiento fino por cellId.

---

## 2. La rejilla isométrica: de cellId a (x,y)

Las celdas no están en una rejilla cuadrada simple, sino **isométrica entrelazada** (el patrón de rombos de Dofus). La clave es la clase `MapPoint` del cliente (visible en la fuente decompilada `Emudofus/Dofus`):

- **Ancho de mapa:** 14 celdas "anchas" + 14 "estrechas" alternadas → constante interna típica `15` para el cálculo.
- **Conversión cellId → coordenadas (x,y):**
  ```
  row    = cellId / 14        (división entera, aprox.)
  // por el entrelazado, la fórmula real usa el ancho 'realWidth' del mapa
  // MapPoint.fromCellId(cellId) devuelve (x, y)
  ```
- `MapPoint.fromCoords(x, y)` hace la conversión inversa.
- `MapPoint.distanceToCell(other)` da la **distancia de Manhattan** entre celdas (la que usa el juego para alcance de sortilegios y PM).

> No reinventes esta aritmética: está resuelta en `ArakneUtils` (módulo `arakne-map`) y en la fuente decompilada. Cópiala literalmente, porque el entrelazado tiene casos borde fáciles de equivocar.

**Direcciones:** Dofus usa 8 direcciones (0–7), con las pares (0,2,4,6) como las cuatro diagonales principales del isométrico. El movimiento entre celdas adyacentes es siempre por una de estas direcciones.

---

## 3. El paquete `GDM`: cómo llega el mapa

Cuando entras a un mapa, el servidor te manda **`GDM`** (GameMapData). Su cuerpo tiene tres campos separados por `|`:

```
GDM<mapId>|<dateKey>|<encryptedMapData>
```

- `mapId` — entero, el ID del mapa.
- `dateKey` — fecha/versión del archivo de mapa (parte de la clave de descifrado).
- `encryptedMapData` — **los datos de celdas, cifrados**.

El cliente real **no recibe la geometría completa por red**: recibe este puntero + clave, y carga el archivo `.swf` del mapa desde sus propios ficheros (o CDN), lo descifra con la clave, y obtiene los datos de las 560 celdas.

(Referencia directa: el handler de `SwfMapLoader` hace exactamente `data.split("|")` → `loader.load(mapId, dateKey, encryptedData)`.)

---

## 4. El problema del cifrado de mapas (importante)

Los datos de celda están **cifrados**. La clave de descifrado depende de la versión del mapa y no viaja completa por la red de forma trivial. Esto significa:

- **Si tienes los archivos del cliente** (los `.swf` de mapas instalados): puedes descifrar localmente con la clave. Es lo que hacen los parsers (`Arakne/php-map-parser`, `SwfMapLoader`). **En tu caso MITM en Windows tienes el cliente instalado**, así que tienes acceso a esos archivos. Esta es la vía recomendada.
- **Si NO tienes la clave:** existen herramientas que **crackean las claves de mapa** a partir solo de los datos cifrados (`arbll/dofus-key-finder`, `hussein-aitlahcen/dofus-map-key`), aprovechando que los datos tienen estructura conocida. Útil para emuladores, innecesario si tienes el cliente.

Conclusión práctica: como vas en MITM con cliente oficial instalado, **no necesitas crackear nada**. Lee los `.swf` del cliente o usa una **base de datos de mapas ya descifrada** (existen dumps comunitarios de mapas+triggers en SQL).

---

## 5. Qué contiene cada celda (los datos que necesitas)

Tras descifrar, cada una de las 560 celdas te da un registro con, entre otros campos:

| Campo | Para qué sirve |
|---|---|
| **`mov` (movible)** | ¿se puede caminar por esta celda? Base del pathfinding. |
| **`los` (line of sight)** | ¿bloquea la línea de vista? Crítico para combate (¿puedo lanzar el sortilegio?). |
| **`layerObject` / GFX** | objeto gráfico en la celda (decorado). |
| **`groundLevel` / `slope`** | altura del suelo (para line of sight 3D). |
| **`interactive` / `layerObject2`** | objetos interactivos (recursos, puertas, palancas). |

Estos son los campos que alimentan las dos funciones nucleares: **pathfinding** (usa `mov`) y **línea de vista** (usa `los` + altura).

---

## 6. Pathfinding (de A a B dentro de un mapa)

El cliente usa **A\*** sobre la rejilla isométrica. La lógica está en `Pathfinding.as` (fuente decompilada). Conceptos clave que verás en esa fuente:

- `pointMov(x, y, allowThroughEntity, previousCell, endCell)` — ¿es transitable esa celda? Considera si permites atravesar entidades (otros jugadores/monstruos).
- `pointWeight(x, y)` — coste de la celda (las celdas con entidades pesan más para que el path las evite si puede).
- `isChangeZone(cellA, cellB)` — detecta si dos celdas están en zonas separadas (no conectables a pie). Evita rutas imposibles.
- Coste de movimiento: distingue **HV (horizontal/vertical)** vs **D (diagonal)** con costes distintos (`_nHVCost`, `_nDCost`).
- Hay una fase de **suavizado** del path al final (eliminar zigzags innecesarios comprobando distancias 1–2 entre nodos).

Para tu bot Python: implementa A\* sobre el grafo de celdas `mov=true`, con vecinos en las 8 direcciones y el mismo esquema de costes HV/D. `ArakneUtils/arakne-map` ya trae Pathfinding y line-of-sight listos como referencia algorítmica.

---

## 7. Cambio de mapa (de un mapa al siguiente)

Para ir de un mapa a otro caminas hasta una **celda de borde** (las que tienen flag de cambio de mapa) en la dirección deseada. El patrón que usan los bots (sintaxis AnkaBot, pero el concepto es universal):

- **Dirección:** `top` / `bottom` / `right` / `left`. Por defecto el personaje cambia de mapa por cualquier celda de borde disponible en esa dirección.
- **Celda específica:** a veces el cambio es por una celda concreta (los "soles"). Se indica como `bottom(454)` o directamente un cellId. Necesario en mapas que se dividen en dos (Pandala).
- **Aleatoriedad:** se pueden dar varias celdas alternativas (`256|45|489`) para no usar siempre la misma — útil anti-detección.
- **mapId obligatorio** cuando las coordenadas son ambiguas (interiores).

A nivel de paquetes, el cambio de mapa se ejecuta como un movimiento (`GA` con la ruta a la celda de borde); el servidor responde con el nuevo `GDM` y `IM`/`GDK`.

---

## 8. Teletransportes (zaaps, zaapis, havre-sac)

Atajos del mapa-mundo que evitan caminar:

- **Zaap:** `zaap(mapIdDestino)` — usa el zaap de la mapa actual para saltar a otro zaap. A nivel paquete: interacción con el PNJ/objeto zaap (`WU` WaypointsUse) + diálogo de destino.
- **Zaapi:** `zaapi(mapIdDestino)` — red de zaapis urbanos (subway, `Wu`).
- **Havre-sac (havenbag):** entrar/salir de tu refugio personal.

Tu planificador de rutas debe decidir cuándo caminar vs cuándo usar zaap (coste en kamas vs tiempo). Una buena heurística: para distancias largas, ir al zaap más cercano → saltar → caminar el tramo final.

---

## 9. Trayectos de alto nivel (el "script de ruta")

Por encima del pathfinding intra-mapa está la **ruta entre mapas**: la lista ordenada de "en el mapa X, sal por la dirección Y". Es lo que la comunidad llama un "script de trayecto". Estructura típica:

```lua
-- En coordenadas o mapId, con dirección de salida
{ map = "1,1",     path = "right" },
{ map = "2,1",     path = "bottom(452)" },
{ map = "2,2",     path = "left" },
{ map = "9856523", path = "bank", door = 406 },  -- acción especial en banco
```

Para construir rutas reales necesitas un **grafo del mundo** (qué mapa conecta con qué mapa por qué borde). Esto lo puedes:
- Construir **observando** tu propio juego (modo log: cada cambio de mapa registra origen→dirección→destino).
- Importar de proyectos como `crimson-med/Dofus-Discovery` (genera overview del mundo + pathfinder) o las bases de datos de mapas comunitarias.

---

## 10. Recursos (todos verificados)

**Ecosistema Arakne (referencia maestra, Dofus 1.29/Retro):**
- **`Arakne/ArakneUtils`** (Java) — `arakne-map` (pathfinding + line of sight), `arakne-encoding` (codificación del protocolo), `arakne-value` (estructuras). **La referencia algorítmica más limpia.**
- **`Arakne/SwfMapLoader`** (Java) — carga y parsea mapas desde SWF/CDN; muestra el handler real del paquete `GDM`.
- **`Arakne/php-map-parser`** (PHP) — parsea y renderiza mapas Retro desde los SWF del cliente; da los datos de celda en formato estructurado.

**Fuente decompilada del cliente:**
- **`Emudofus/Dofus`** — código ActionScript del cliente: `MapPoint` (cellId↔coords), `Pathfinding.as` (A\* real con `pointMov`/`pointWeight`/`isChangeZone`).

**Cifrado de mapas (solo si no tienes cliente):**
- `arbll/dofus-key-finder`, `hussein-aitlahcen/dofus-map-key` — crackean claves de mapa desde datos cifrados.

**Datos del mundo / herramientas:**
- `crimson-med/Dofus-Discovery` — overview del mundo + pathfinder.
- `hadamrd/retrodata` — datos Retro estructurados (NPCs con MapId/CellId/Direction, triggers por mapa+celda).
- dofus-map.com, dofus-retro.co — mapas interactivos con recursos (útil para localizar spots de farmeo).

---

## 11. Orden recomendado de implementación

1. **cellId ↔ (x,y) + distancia** (copia de ArakneUtils). Sin esto no haces nada.
2. **Parseo de `GDM`** → obtener `mapId`/`dateKey`/datos cifrados.
3. **Descifrado/carga de celdas** desde los `.swf` del cliente (tienes el cliente instalado) o desde una BD de mapas dumpeada.
4. **Pathfinding A\*** intra-mapa usando `mov`.
5. **Line of sight** usando `los`+altura (lo necesitas para combate, no para moverse).
6. **Cambio de mapa** (caminar a celda de borde + leer nuevo `GDM`).
7. **Grafo del mundo** + planificador de rutas (caminar vs zaap).

---

*Este material es para interoperabilidad técnica. Su uso para automatización en servidores oficiales de Ankama infringe sus condiciones de uso.*
