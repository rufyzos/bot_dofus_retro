"""
capture_spells.py — Captura automática de spell_ids durante el combate.

Intercepta los paquetes GA (C→S) que el cliente envía al castear un hechizo
y muestra qué spell_id corresponde a cada slot de tecla.

CÓMO USARLO:
  1. Ejecutar como admin (requiere puerto 443):
       python tools/capture_spells.py

  2. Abrir Launcher → Play → entrar en combate.

  3. En tu turno, pulsar cada tecla de hechizo (1, 2, 3…) y hacer click en
     una celda. El script imprime y guarda en capture_spells.json:
       [Slot 1] spell_id=191  cell=245  ap_cost=?  → Zarzas Múltiples

  4. Copiar los spell_ids al SPELLS de config.py.

FORMATO GA de cast (C→S, confirmado con sniffer):
  GA<seq>\\n<spell_id>;<cell_id>\\n
  Ejemplo: "GA300\\n191;245\\n"

El script distingue GA de cast (tiene spell_id;cell) de GA de movimiento
(action_id=1, tiene fighter_id;path) por la presencia de ';' y estructura
numérica.
"""

import asyncio
import datetime
import json
import os
import re

_HERE    = os.path.dirname(__file__)
_ROOT    = os.path.join(_HERE, "..")
OUT_PATH = os.path.join(_ROOT, "capture_spells.json")
LOG_PATH = os.path.join(_ROOT, "sniffer.log")

LOGIN_LISTEN   = ("127.0.0.1", 443)
GAME_LISTEN    = ("127.0.0.1", 5556)
LOGIN_UPSTREAM = ("52.17.187.227", 443)

_AYK_RE = re.compile(r"^AYK([^:]+):(\d+);(.+)$")

game_target: dict = {"host": None, "port": None}
_log_lock = None
_conn_counter = 0

# Acumulado de hechizos capturados: spell_id → {slot_key, count, last_cell}
_spells_seen: dict[str, dict] = {}

# Cargamos si ya existe un capture previo
if os.path.exists(OUT_PATH):
    try:
        with open(OUT_PATH, encoding="utf-8") as f:
            _spells_seen = json.load(f)
    except Exception:
        _spells_seen = {}


def _ts():
    return datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]


async def _log(line: str):
    entry = f"[{_ts()}] {line}"
    print(entry, flush=True)
    async with _log_lock:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(entry + "\n")


def _save_spells():
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(_spells_seen, f, indent=2, ensure_ascii=False)


def _parse_ga_cast(raw: str) -> tuple[str, str] | None:
    """
    Intenta extraer (spell_id, cell_id) de un paquete GA C→S.

    Formato cast: GA<seq>\\n<spell_id>;<cell_id>\\n
    Ignoramos GA de movimiento (action_id=1) y GA sin estructura numérica.
    """
    if not raw.startswith("GA"):
        return None
    # Quitar header GA + número de secuencia hasta el primer \\n
    body = raw[2:]
    lines = [l.strip() for l in body.split("\n") if l.strip()]
    if not lines:
        return None

    for line in lines:
        parts = line.split(";")
        if len(parts) < 2:
            continue
        try:
            spell_id = str(int(parts[0]))   # debe ser numérico
            cell_id  = str(int(parts[1]))   # debe ser numérico
            # Descartar action_id=1 (movimiento)
            if parts[0] == "1":
                continue
            return spell_id, cell_id
        except ValueError:
            continue
    return None


async def _on_client_packet(raw: str):
    """Procesa paquetes C→S buscando casts de hechizos."""
    result = _parse_ga_cast(raw)
    if result is None:
        return
    spell_id, cell_id = result

    if spell_id not in _spells_seen:
        _spells_seen[spell_id] = {"count": 0, "cells": []}

    entry = _spells_seen[spell_id]
    entry["count"] += 1
    if cell_id not in entry["cells"]:
        entry["cells"].append(cell_id)
    _save_spells()

    await _log(
        f"[CaptureSpells] ✓ spell_id={spell_id}  cell={cell_id}  "
        f"(visto {entry['count']}x)  → config: "
        f'SpellConfig("{spell_id}", ap_cost=?, min_range=?, max_range=?, slot_key="?")'
    )


# ── Sniffer (igual que sniffer.py / dump_maps.py) ────────────────────────────

def _split_nul(buf: bytes) -> tuple[list[bytes], bytes]:
    parts = buf.split(b"\x00")
    return parts[:-1], parts[-1]


async def _pump(reader, writer, direction: str, transform=None, conn_id: int = 0):
    buf = b""
    first = True
    try:
        while True:
            chunk = await reader.read(4096)
            if not chunk:
                break
            if first:
                first = False
                if chunk[0:2] in (b'\x16\x03', b'\x15\x03'):
                    writer.write(chunk)
                    await writer.drain()
                    try:
                        while True:
                            data = await reader.read(4096)
                            if not data:
                                break
                            writer.write(data)
                            await writer.drain()
                    except (ConnectionResetError, BrokenPipeError, OSError):
                        pass
                    return
            buf += chunk
            msgs, buf = _split_nul(buf)
            for raw_bytes in msgs:
                if not raw_bytes:
                    continue
                raw = raw_bytes.decode("utf-8", errors="replace")
                if direction == "C→S" and raw.startswith("GA"):
                    asyncio.create_task(_on_client_packet(raw))
                out = transform(raw) if transform else raw
                if out is None:
                    continue
                writer.write(out.encode("utf-8") + b"\x00")
            await writer.drain()
    except (asyncio.IncompleteReadError, ConnectionResetError, BrokenPipeError, OSError):
        pass
    finally:
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass


def _login_transform(raw: str):
    m = _AYK_RE.match(raw)
    if m:
        real_host, real_port, ticket = m.group(1), m.group(2), m.group(3)
        game_target["host"] = real_host
        game_target["port"] = int(real_port)
        asyncio.create_task(_log(
            f"[AYK] game real={real_host}:{real_port} → 127.0.0.1:{GAME_LISTEN[1]}"
        ))
        return f"AYK127.0.0.1:{GAME_LISTEN[1]};{ticket}"
    return raw


async def handle_login(cr, cw):
    global _conn_counter
    _conn_counter += 1
    cid = _conn_counter
    try:
        sr, sw = await asyncio.open_connection(*LOGIN_UPSTREAM)
    except OSError as e:
        await _log(f"[#{cid} ERR] {e}")
        cw.close()
        return
    await asyncio.gather(
        _pump(sr, cw, "S→C", _login_transform, cid),
        _pump(cr, sw, "C→S", None, cid),
    )


async def handle_game(cr, cw):
    global _conn_counter
    _conn_counter += 1
    cid = _conn_counter
    if not game_target["host"]:
        await _log("[ERR] game_target vacío")
        cw.close()
        return
    import socket as _socket
    try:
        loop = asyncio.get_event_loop()
        real_ip = await loop.run_in_executor(
            None, lambda: _socket.getaddrinfo(
                game_target["host"], game_target["port"],
                _socket.AF_INET, _socket.SOCK_STREAM
            )[0][4][0]
        )
    except Exception:
        real_ip = game_target["host"]
    try:
        sr, sw = await asyncio.open_connection(real_ip, game_target["port"])
    except OSError as e:
        await _log(f"[#{cid} ERR] game: {e}")
        cw.close()
        return
    await asyncio.gather(
        _pump(sr, cw, "S→C", None, cid),
        _pump(cr, sw, "C→S", None, cid),
    )


async def main():
    global _log_lock
    _log_lock = asyncio.Lock()

    print("=" * 60)
    print("  Dofus Retro — Captura de Spell IDs")
    print(f"  Login proxy : {LOGIN_LISTEN[0]}:{LOGIN_LISTEN[1]}")
    print(f"  Game  proxy : {GAME_LISTEN[0]}:{GAME_LISTEN[1]}")
    print(f"  Salida      : {os.path.abspath(OUT_PATH)}")
    print("=" * 60)
    print()
    if _spells_seen:
        print(f"Hechizos ya capturados: {list(_spells_seen.keys())}")
    print("Entra en combate y castea cada hechizo al menos una vez.")
    print("Ctrl+C para ver el resumen final.\n")

    login_srv = await asyncio.start_server(handle_login, *LOGIN_LISTEN)
    game_srv  = await asyncio.start_server(handle_game,  *GAME_LISTEN)

    async with login_srv, game_srv:
        await asyncio.gather(
            login_srv.serve_forever(),
            game_srv.serve_forever(),
        )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n" + "=" * 60)
        print("  Resumen de hechizos capturados:")
        print("=" * 60)
        for spell_id, data in sorted(_spells_seen.items(), key=lambda x: x[1]["count"], reverse=True):
            print(f'  SpellConfig("{spell_id}", ap_cost=?, min_range=?, max_range=?, '
                  f'slot_key="?")  — visto {data["count"]}x, celdas: {data["cells"][:5]}')
        print()
        print(f"Guardado en: {OUT_PATH}")
