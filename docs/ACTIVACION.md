# Guía de activación del bot

## Paso 1 — Redirigir el cliente al proxy (requiere admin)

Abre Notepad **como Administrador** y edita:

```
C:\Windows\System32\drivers\etc\hosts
```

Añade al final:

```
127.0.0.1  co.retro.dofus.com
```

Guarda y cierra. Esto hace que el cliente de Dofus se conecte a tu proxy local en lugar de al servidor real de Ankama.

---

## Paso 2 — Fase 0: descubrir los headers reales de combate

```powershell
cd "c:\Users\vicma\OneDrive\Escritorio\Dofus\Bot"
python tools/sniffer.py
```

Abre el cliente de Dofus normalmente (ahora pasará por el proxy). Inicia sesión, entra a una pelea **manualmente** y haz estas acciones mientras miras la consola del sniffer:

1. **Inicia el combate** — anota el header S→C que aparece al entrar (algo como `GJK`)
2. **Cuando sea tu turno** — ya deberías ver `GTS` (turn start)
3. **Castea un hechizo** — anota el paquete C→S (probablemente `GA` con campos)
4. **Muévete en el mapa de combate** — anota el paquete C→S de movimiento
5. **Pasa el turno** — deberías ver `Gt` C→S
6. **Cuando termine el combate** — anota el header S→C de fin de pelea

Ejemplo de salida del sniffer:

```
[14:32:01] C→S  GTS  []
[14:32:05] C→S  GA   ['304', '6', '145']    ← cast de hechizo
[14:32:07] C→S  GA   ['1', '89']            ← movimiento en combate
[14:32:09] C→S  Gt   []                     ← pasar turno
[14:32:15] S→C  GE   ['1']                  ← fin de combate
```

---

## Paso 3 — Actualizar los headers en el código

Con los datos del sniffer, edita `protocol/messages.py` y reemplaza los valores marcados `[CONFIRMAR]`:

```python
CAST_SPELL  = "GA"     # C→S — reemplazar con el header real
FIGHT_START = "GJK"    # S→C — reemplazar con el header real
FIGHT_END   = "GE"     # S→C — reemplazar con el header real
```

Luego edita `game/fight.py` en `register_handlers()` y descomenta las líneas con los headers reales:

```python
def register_handlers(self, dispatcher):
    from protocol.dispatcher import DIRECTION_SERVER
    dispatcher.on("GJK", self.handle_fight_join,    DIRECTION_SERVER)  # header real de inicio
    dispatcher.on("GHT", self.handle_fighter_stats, DIRECTION_SERVER)  # header real de stats
    dispatcher.on("GAV", self.handle_fighter_move,  DIRECTION_SERVER)  # header real de movimiento
    dispatcher.on("GKK", self.handle_fighter_death, DIRECTION_SERVER)  # header real de muerte
```

---

## Paso 4 — Configurar tus hechizos

Edita `config.py` con los spell IDs reales de tu personaje (los verás en los paquetes C→S de cast capturados en el paso 2):

```python
SPELLS = [
    SpellConfig(spell_id="6",  ap_cost=4, min_range=1, max_range=5),  # hechizo principal
    SpellConfig(spell_id="13", ap_cost=3, min_range=1, max_range=3),  # hechizo secundario
]
TARGET_STRATEGY = "nearest"   # opciones: "nearest", "lowest_hp", "scoring"
```

---

## Paso 5 — Validar en DRY_RUN

Asegúrate de que `config.py` tiene `DRY_RUN = True` (es el default). Corre el bot:

```powershell
python bot.py
```

Abre el cliente, inicia sesión, entra a una pelea. El bot debe imprimir lo que **haría** sin inyectar nada:

```
[CombatAI] Es mi turno.
[CombatAI DRY_RUN] Cast <Spell 6 ap=4 range=1-5> → fighter mob_1 en celda 145
[CombatAI DRY_RUN] Pasar turno (Gt)
```

Si la lógica parece correcta, continúa al paso 6.

---

## Paso 6 — Activar el bot real

En `config.py`:

```python
DRY_RUN = False
```

```powershell
python bot.py
```

El bot inyectará paquetes reales. Empieza con peleas fáciles (mobs de nivel bajo) para validar que castea y pasa turno correctamente.

---

## Paso 7 — Revertir el archivo hosts al terminar

Elimina la línea añadida en el paso 1:

```
# Eliminar esta línea del archivo hosts:
127.0.0.1  co.retro.dofus.com
```

---

## Resumen

| Paso | Qué hacer |
|------|-----------|
| 1 | Editar `hosts` como admin — redirigir `co.retro.dofus.com` a `127.0.0.1` |
| 2 | Correr `tools/sniffer.py`, jugar pelea manual, anotar headers reales |
| 3 | Actualizar `protocol/messages.py` y `game/fight.py` con los headers capturados |
| 4 | Configurar hechizos y estrategia en `config.py` |
| 5 | `DRY_RUN = True` → `python bot.py` → validar lógica en consola |
| 6 | `DRY_RUN = False` → bot activo con inyección real |
| 7 | Revertir `hosts` al terminar la sesión |

> **El paso más crítico es el 2.** Sin los headers reales de combate el bot no puede funcionar — todos los paquetes de combate están marcados `[CONFIRMAR]` hasta que se capturen.
