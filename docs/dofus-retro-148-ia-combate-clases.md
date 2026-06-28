# IAs de combate por clase para Dofus Retro 1.48 — recursos y plantillas

**Fecha:** Junio 2026 · Sobre tu bot MITM multicuenta

---

## 1. Realidad del ecosistema: hay menos "configs por clase" de lo esperado

Lo primero que conviene saber: **casi todas las soluciones serias de Retro NO traen una IA cerrada por clase, sino un motor Lua genérico** sobre el que tú (o la comunidad) escribís el comportamiento. Es decir, "configuración de clase" en Retro = un **script Lua** que decide qué sortilegio lanzar y dónde, usando la API de combate del bot.

Los repositorios públicos con scripts ya hechos son escasos y suelen centrarse en **trayectos/farm** más que en IA de combate por clase. Los motores potentes (MoonBot, AnkaBot, SnowBot) tienen IA configurable pero **propietaria**: te dan la API y plantillas, no un "Cra.lua" descargable y completo.

Conclusión práctica: vas a **partir de plantillas genéricas por arquetipo** y adaptarlas. Abajo te doy las fuentes reales y plantillas listas para empezar.

---

## 2. Recursos públicos reales (verificados)

| Recurso | Qué aporta | Estado |
|---|---|---|
| **`amrm121/Dofus-Bot-Script`** (GitHub) | Scripts Lua de **SnowBot** para Retro. Carpeta "Fighting - Combat" con plantillas plug-and-play (incl. "Incarnam Starter" con mapas por clase de salida). | Útil como base de combate y rutas |
| **`simp37/LUA_Scripts_BOT_Dofus-Retro`** (GitHub) | Scripts de **fight + farming**; sobre todo PATHS (trayectos). | Más rutas que IA |
| **`Azzary/NebulaR-Bot`** (GitHub) | Bot Retro en C# con **motor Lua**; ejemplos de `function Fight()` con `GetTurn()`, lanzamiento de sortilegios y movimiento. | Buena referencia de estructura de IA |
| **`gilliorem/dofus_retro_bot`** (GitHub) | Script Python que automatiza combate y oficios en Retro. | Referencia Python |
| **Scripts LUA Moonbot Rétro** (topic `dofus-script` en GitHub) | Colección comunitaria de `.lua` listos: combat, farm, pêche, récolte, déplacement. | La colección más activa |
| **MoonBot API** (moon-bot.io) | 395 funciones en 20 namespaces (combat, map, inventory, group…), documentadas con ejemplos. | API de referencia, motor de pago |
| **Doc del "FREE-BETA BOT PYTHON"** (cheat-gam3) | Documenta funciones reales de combate Lua (ver sección 3) y delays multi-mula. | Doc de API concreta |

> Aviso: muchos scripts "garantizados sin ban" que se venden en foros (cheat-gam3, etc.) son humo o están desactualizados tras la ban wave de enero 2026. Trátalos con escepticismo.

---

## 3. La API de combate real (lo que usan los scripts)

Estas son funciones reales documentadas de motores Retro (formato `fight:`/`map:`/`global:`). Tu capa Python sobre el MITM debe exponer equivalentes para poder portar/escribir IAs:

**Lectura del estado de combate**
- `fight:getAllFighters()` — lista de combatientes (aliados y enemigos).
- `fight:getEffect(fighterid)` — efectos activos sobre un combatiente (cada uno con `spell_id`, `spell_name`, `duration`, `caster_id`, `action_id`, `value`).
- `fight:isEffectActive(fighterid, spell_id)` — booleano.
- `fight:getSpellCooldown(spellid)` — cooldown por **spell_id real** (no el nº en la barra).
- Cálculo de **distancia**, **línea de vista** y **mejor sortilegio de zona** (citados como parte de la API de IA avanzada).

**Acción**
- Lanzar sortilegio sobre celda/objetivo (castSpell).
- `fightPlacement` — colocación en fase de pre-combate (con fallback a celda aleatoria si la pedida falla).
- Pasar turno.

**Multi-mula (coordinación, clave para tu caso multicuenta)**
- `function fightManagementMules()` — se llama automáticamente cuando es el turno de una mula.
- `DELAY_JOIN_MULES`, `DELAY_READY_MULES`, `DELAY_CLICK_BETWEEN_MULES` (~200 ms) — desfase entre mulas.
- `map:cleanMules()`, `global:clickAllMules()`, `global:sendKeyAllMules()`.

**Estructura típica de una IA (patrón NebulaR/SnowBot):**
```lua
function Fight()
    if botInstance:GetTurn() == 1 then
        -- buff inicial / colocación
    end
    -- bucle de decisión: mientras tenga PA y haya objetivo válido
end
```

---

## 4. Plantillas de IA por arquetipo de clase

Las 12 clases de Retro se agrupan en **arquetipos de comportamiento**. En vez de 12 configs, programa **5 patrones** y parametrízalos. Pseudocódigo Lua-style (adáptalo a tu API):

### 4.1 Distancia / DPS a rango — **Cra** (y Sram a distancia)
La IA de referencia "Cra kiting" es el caso canónico: mantener distancia y pegar.
```lua
function Fight()
    local me = fight:getSelf()
    local target = closestEnemy()
    -- 1. Mantener distancia (kiting): si el enemigo está demasiado cerca, alejarse
    if distance(me, target) < SAFE_DIST then
        moveAwayFrom(target.cell)
    end
    -- 2. Pegar a rango mientras haya PA y línea de vista
    while me.pa >= COST[SPELL_ATTACK] and hasLineOfSight(me, target) do
        castSpell(SPELL_ATTACK, target.cell)
        if fight:getSpellCooldown(SPELL_ATTACK) > 0 then break end
    end
    -- 3. Si sobran PA, reposicionar para el próximo turno
end
```
Parámetros Cra: `SAFE_DIST` alto, priorizar Flecha Mágica/Punitiva, usar Retroceso si el enemigo pega cuerpo a cuerpo.

### 4.2 Cuerpo a cuerpo / melee — **Iop, Sacrieur, Ecaflip, Ouginak**
```lua
function Fight()
    local target = lowestHpEnemy() or closestEnemy()
    -- 1. Acercarse hasta estar adyacente / a rango del sort
    if distance(me, target) > RANGE[SPELL_MELEE] then
        moveToward(target.cell, RANGE[SPELL_MELEE])
    end
    -- 2. Buff si turno 1 (Iop: Poder/Coléra; Sacri: Castigo)
    if me.turn == 1 then castSpell(SPELL_BUFF, me.cell) end
    -- 3. Vaciar PA en el objetivo
    while me.pa >= COST[SPELL_MELEE] do castSpell(SPELL_MELEE, target.cell) end
end
```

### 4.3 Soporte / curador — **Eniripsa, Feca, Pandawa**
```lua
function Fight()
    -- 1. Curar al aliado más herido si baja de umbral
    local ally = mostWoundedAlly()
    if ally and ally.hpPercent < HEAL_THRESHOLD then
        castSpell(SPELL_HEAL, ally.cell)
    end
    -- 2. Feca: armaduras/glifos; Pandawa: empujar/estabilizar
    if me.turn == 1 then castSpell(SPELL_ARMOR, mainDps().cell) end
    -- 3. Si sobran PA, pegar al enemigo más débil
    if me.pa >= COST[SPELL_ATTACK] then castSpell(SPELL_ATTACK, closestEnemy().cell) end
end
```

### 4.4 Invocador — **Osamodas, Sadida**
```lua
function Fight()
    -- 1. Invocar al principio si hay huecos y PA
    if countSummons() < MAX_SUMMONS and me.pa >= COST[SPELL_SUMMON] then
        castSpell(SPELL_SUMMON, freeAdjacentCell(me.cell))
    end
    -- 2. Buff a invocaciones (Osa) / poner muñecos (Sadida)
    -- 3. Pegar con PA restantes
end
```

### 4.5 Utilidad / control — **Enutrof, Steamer (Eliotrope/Zobal en D2)**
```lua
function Fight()
    -- Enutrof: maldición/prospección sobre enemigo, luego pegar
    -- Steamer: torretas + posicionamiento
    if me.turn == 1 then castSpell(SPELL_UTILITY, closestEnemy().cell) end
    attackWithRemainingPa()
end
```

> **Nota sobre `spell_id`:** los IDs de sortilegio en Retro son globales y distintos del número de barra. Necesitas una **tabla `spell_id` por clase** (la sacas leyendo paquetes de tu propio personaje en modo log, o de una API de datos como la de moon-bot/dofapi). Esto es lo primero que debes mapear por clase.

---

## 5. Cómo integrarlo en tu bot Python MITM

Como tú estás construyendo el bot en Python (no usas el motor Lua de un tercero), tienes dos caminos:

**A. Motor de reglas en Python (recomendado).** Implementas las funciones de la sección 3 leyendo los paquetes de combate del MITM (estado de combatientes, PA/PM, posiciones) e inyectando los paquetes de `castSpell`/movimiento. La IA por clase es entonces una función Python por arquetipo, parametrizada por una tabla de sortilegios por clase. Ventaja: todo en un lenguaje, integración directa con tu orquestador multicuenta.

**B. Embeber Lua en Python** (con `lupa`, binding de LuaJIT). Te permite **reutilizar scripts Lua existentes** (SnowBot/MoonBot-like) casi tal cual, exponiendo tu API a Lua. Ventaja: aprovechas la colección comunitaria de `.lua`. Inconveniente: tienes que replicar fielmente la API que esos scripts esperan (`fight:`, `map:`, `global:`).

Para multicuenta, la **coordinación líder/mulas** vive por encima de la IA de clase: el orquestador (del informe anterior) decide el foco (a qué enemigo pega el equipo) y cada `Session` ejecuta su IA de clase contra ese foco compartido. `fightManagementMules()` es el gancho equivalente.

---

## 6. Tabla de datos que necesitas montar por clase

Antes de escribir cualquier IA, construye esta tabla (una fila por clase que vayas a botear):

| Campo | Ejemplo (Cra) | Cómo obtenerlo |
|---|---|---|
| `spell_ids` | Flecha Mágica=161, Punitiva=164… | Log de paquetes de tu personaje / API de datos |
| `pa_cost` por sortilegio | 4, 5… | Tooltip in-game / API |
| `range` por sortilegio | 6-8 con LdV | API |
| Rol/arquetipo | distancia/kiting | Manual |
| Buffs turno 1 | — | Manual |
| Umbral de cura (soportes) | n/a | Manual |
| `SAFE_DIST` / `MELEE_RANGE` | alto | Tuning |

Las **APIs de datos de Retro** (moon-bot wiki API, dofapi) te dan sortilegios/IDs/efectos sin clave y con CORS abierto, lo que acelera montar esta tabla.

---

## 7. Recomendación de arranque

1. **Empieza por UN arquetipo y UNA clase** (Cra a distancia es el más simple y documentado: kiting + flecha).
2. Monta la **tabla de `spell_ids`** de esa clase leyendo tus propios paquetes en modo log.
3. Implementa el **bucle de decisión mínimo**: objetivo más cercano → ¿tengo LdV y PA? → lanzar → reposicionar.
4. Prueba en combates fáciles (Incarnam) con el "Incarnam Starter" de `amrm121` como referencia de rutas.
5. Añade **delays aleatorios** entre acciones desde el principio (anti-detección).
6. Solo entonces generaliza a melee/soporte/invocador y conecta la coordinación multicuenta (foco compartido).

---

## 8. Enlaces directos

- `github.com/amrm121/Dofus-Bot-Script` → carpeta "Fighting - Combat"
- `github.com/simp37/LUA_Scripts_BOT_Dofus-Retro` → PATHS
- `github.com/Azzary/NebulaR-Bot` → ejemplos `function Fight()`
- `github.com/gilliorem/dofus_retro_bot` → combate en Python
- `github.com/topics/dofus-script` → colección comunitaria Lua
- MoonBot API docs (moon-bot.io) → referencia de 395 funciones
- APIs de datos: moon-bot wiki API, dofapi → spell_ids/efectos

---

*Recordatorio: estos scripts y APIs están pensados para automatización que, en servidores oficiales de Ankama, infringe las condiciones de uso. La IA de combate correlacionada entre varias cuentas es especialmente detectable; randomiza tiempos y comportamiento.*
