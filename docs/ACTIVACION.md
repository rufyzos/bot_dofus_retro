# Guía de activación del bot

## Paso 1 — Hosts file (una sola vez, requiere admin)

Abre Notepad **como Administrador** y edita:

```
C:\Windows\System32\drivers\etc\hosts
```

Añade al final:

```
127.0.0.1  dofusretro-co-production.ankama-games.com
```

Guarda y cierra. Esto hace que el cliente conecte al proxy local en lugar de a Ankama directamente. **No tocar la línea de `co.retro.dofus.com` si existe — es obsoleta.**

---

## Paso 2 — Arrancar el sniffer o el bot (terminal como administrador)

El proxy escucha en el puerto 443, que requiere permisos de administrador.

**Para snifear / observar el protocolo:**

```powershell
cd "c:\Users\vicma\OneDrive\Escritorio\Dofus\Bot"
python tools/sniffer.py
```

**Para correr el bot en DRY_RUN (sin inyectar nada):**

```powershell
python bot.py
```

---

## Paso 3 — Abrir el juego

1. Abre el **Ankama Launcher** normalmente
2. Pulsa **Play** en Dofus Retro
3. El cliente carga y conecta automáticamente — no hay que elegir ningún servidor manualmente

El sniffer/bot mostrará en consola:

```
[#1 LOGIN CONNECT] ('127.0.0.1', ...)
[#1] S→C primer chunk: b'HC...'
S→C  HC      [0]<salt>
C→S  #Z
<zaap_token>
...
S→C  AYK     dofusretro-ga-<servidor>.ankama-games.com:443;<ticket>
[AYK] game real=... → 127.0.0.1:5556
[#2 GAME CONNECT] ...
S→C  GCK     [0]1  [1]<nombre_personaje>
```

---

## Paso 4 — Configurar hechizos

Edita `config.py` con los spell IDs reales de tu personaje. Los IDs aparecen en los paquetes `GA` C→S cuando casteas en combate con el sniffer activo:

```python
SPELLS = [
    SpellConfig(spell_id="6",  ap_cost=4, min_range=1, max_range=5),
    SpellConfig(spell_id="13", ap_cost=3, min_range=1, max_range=3),
]
TARGET_STRATEGY = "nearest"   # opciones: "nearest", "lowest_hp"
```

---

## Paso 5 — Validar en DRY_RUN

Con `DRY_RUN = True` (default), el bot imprime lo que haría sin inyectar nada:

```
[CombatAI] Es mi turno.
[CombatAI DRY_RUN] Cast <Spell 6 ap=4 range=1-5> → mob en celda 145
[CombatAI DRY_RUN] Pasar turno (Gt)
```

---

## Paso 6 — Activar el bot real

En `config.py`:

```python
DRY_RUN = False
```

```powershell
python bot.py
```

El bot inyectará paquetes reales. Empieza con peleas fáciles para validar.

---

## Resumen

| Paso | Qué hacer |
|------|-----------|
| 1 | Añadir `127.0.0.1  dofusretro-co-production.ankama-games.com` al hosts file (admin, una vez) |
| 2 | Terminal como admin → `python tools/sniffer.py` o `python bot.py` |
| 3 | Launcher → Play — el cliente conecta solo |
| 4 | Configurar spell IDs en `config.py` |
| 5 | `DRY_RUN = True` → validar lógica en consola |
| 6 | `DRY_RUN = False` → bot activo |

## Notas técnicas

- El proxy usa la IP directa `52.17.187.227:443` para el upstream de login (evita bucle con el hosts file). Si falla la conexión, verificar con `nslookup dofusretro-co-production.ankama-games.com 8.8.8.8`.
- El game server llega como hostname en el paquete `AYK` (ej: `dofusretro-ga-fallanster-2.ankama-games.com:443`). El proxy lo resuelve por DNS normalmente (no está en el hosts file).
- El protocolo es TCP en texto plano — el puerto 443 es solo para sortear firewalls, no hay TLS.
- **No editar el `config.xml` del cliente** — el método actual no lo requiere.
