"""
dump_maps.py — Pobla data/maps.json capturando GDM en vivo.

Funciona como el sniffer (MITM en :443 y :5556) pero además:
  - Intercepta cada paquete GDM
  - Descifra el mapData con la clave del propio paquete (XOR cíclico)
  - Extrae los flags mov/los de cada celda (10 bytes por celda)
  - Escribe el resultado en data/maps.json (formato que lee map_data.py)

ALGORITMO DE DESCIFRADO (fuente: Emudofus/Dofus CellData.as):
  - GDM = "GDM<mapId>|<key>|<encryptedData>"
  - encryptedData: string de chars. Cada char XOR key[(i % len(key))] → byte descifrado.
  - 10 bytes por celda:
      byte 0: _floor * 10  (si -128 la celda no existe, mov=false)
      byte 1: _losmov      → bit0=mov, bit1=los, bit2=nonWalkableDuringFight, ...
      byte 2: speed
      byte 3: mapChangeData
      byte 4+: más flags (version > 5/7)
  - Celdas totales: 560 (cellId 0..559)

USO (como administrador):
    python tools/dump_maps.py

Luego abre el Launcher → Play → camina por el mundo.
Cada mapa nuevo se añade a data/maps.json automáticamente.
Ctrl+C para detener.
"""

import asyncio
import datetime
import json
import os
import re

# ── Paths ──────────────────────────────────────────────────────────────────────
_HERE       = os.path.dirname(__file__)
_ROOT       = os.path.join(_HERE, "..")
MAPS_DB     = os.path.join(_ROOT, "data", "maps.json")
LOG_PATH    = os.path.join(_ROOT, "sniffer.log")

LOGIN_LISTEN   = ("127.0.0.1", 443)
GAME_LISTEN    = ("127.0.0.1", 5556)
LOGIN_UPSTREAM = ("52.17.187.227", 443)

MAP_CELLS = 560  # celdas por mapa Dofus Retro

_AYK_RE = re.compile(r"^AYK([^:]+):(\d+);(.+)$")
_GDM_RE = re.compile(r"^GDM([^|]+)\|([^|]*)\|(.+)$", re.DOTALL)

# ── Estado compartido ─────────────────────────────────────────────────────────
game_target: dict = {"host": None, "port": None}
_log_lock    = None
_db_lock     = None
_conn_counter = 0
_maps_db: dict = {}   # map_id (str) → {cells: [...]}


# ── BD de mapas ───────────────────────────────────────────────────────────────

def _load_db():
    global _maps_db
    if os.path.exists(MAPS_DB):
        try:
            with open(MAPS_DB, encoding="utf-8") as f:
                _maps_db = json.load(f)
            print(f"[DumpMaps] BD cargada: {len(_maps_db)} mapas en {MAPS_DB}")
        except Exception as e:
            print(f"[DumpMaps] Error cargando BD: {e}")
            _maps_db = {}
    else:
        _maps_db = {}
        print(f"[DumpMaps] BD nueva: {MAPS_DB}")


async def _save_db():
    async with _db_lock:
        tmp = MAPS_DB + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(_maps_db, f, indent=2, ensure_ascii=False)
        os.replace(tmp, MAPS_DB)


# ── Descifrado y parseo de celdas ─────────────────────────────────────────────

def _decrypt_map_data(encrypted: str, key: str) -> bytes:
    """XOR cíclico: encrypted[i] XOR key[i % len(key)] → byte descifrado."""
    if not key:
        # Sin clave: datos ya en claro (algunos mapas de test)
        return bytes(ord(c) for c in encrypted)
    key_len = len(key)
    return bytes(
        (ord(encrypted[i]) ^ ord(key[i % key_len]))
        for i in range(len(encrypted))
    )


def _parse_cells(raw_bytes: bytes, map_version: int = 8) -> list[dict]:
    """
    Extrae las 560 celdas del stream binario descifrado.

    Estructura por celda (CellData.as fromRaw):
      byte 0: floor (int8) * 10; si == -128 → celda inexistente
      byte 1: losmov (uint8)
                bit 0 → mov (¿cambiable?)
                bit 1 → los (¿línea de visión?)
                bit 2 → nonWalkableDuringFight
                bit 3 → red (celda roja de inicio combate)
                bit 4 → blue (celda azul de inicio combate)
                bit 5 → farmCell
                bit 6 → visible
                bit 7 → nonWalkableDuringRP
      byte 2: speed (int8)
      byte 3: mapChangeData (uint8)
      byte 4: moveZone (uint8)  — si mapVersion > 5
      byte 5: arrow bits (int8) — si mapVersion > 7

    Devuelve lista de 560 dicts {id, mov, los, fight_start_pos, ...}
    """
    cells = []
    idx = 0
    bytes_per_cell = 4
    if map_version > 5:
        bytes_per_cell += 1
    if map_version > 7:
        bytes_per_cell += 1

    for cell_id in range(MAP_CELLS):
        if idx + bytes_per_cell > len(raw_bytes):
            # Stream más corto de lo esperado: rellenar como no-transitables
            cells.append({"id": cell_id, "mov": False, "los": True})
            continue

        floor_byte = raw_bytes[idx]
        # floor_byte es uint8; el int8 equivalente:
        floor_signed = floor_byte if floor_byte < 128 else floor_byte - 256
        if floor_signed == -128:
            # Celda inexistente
            cells.append({"id": cell_id, "mov": False, "los": True})
            idx += bytes_per_cell
            continue

        losmov = raw_bytes[idx + 1]
        mov    = bool(losmov & 0x01)
        los    = bool((losmov & 0x02) >> 1)
        non_walkable_fight = bool((losmov & 0x04) >> 2)
        red    = bool((losmov & 0x08) >> 3)
        blue   = bool((losmov & 0x10) >> 4)

        cell = {
            "id":  cell_id,
            "mov": mov,
            "los": los,
        }
        # Añadir info de posición de inicio de combate si la tiene
        if red:
            cell["fight_start"] = "red"
        elif blue:
            cell["fight_start"] = "blue"
        if non_walkable_fight:
            cell["no_fight"] = True

        # mapChangeData: direcciones de cambio de mapa (bits 0-3: top/bottom/right/left)
        map_change = raw_bytes[idx + 3]
        if map_change:
            cell["map_change"] = map_change

        cells.append(cell)
        idx += bytes_per_cell

    return cells


async def _process_gdm(raw: str):
    """Parsea GDM, descifra, extrae celdas, guarda en BD."""
    m = _GDM_RE.match(raw)
    if not m:
        return

    map_id   = m.group(1).strip()
    key      = m.group(2).strip()
    enc_data = m.group(3).strip()

    if not enc_data:
        await _log(f"[DumpMaps] GDM mapa {map_id}: sin datos de celdas (enc_data vacío)")
        return

    if map_id in _maps_db:
        await _log(f"[DumpMaps] Mapa {map_id} ya en BD ({len(_maps_db[map_id]['cells'])} celdas) — skip")
        return

    await _log(f"[DumpMaps] Procesando mapa {map_id} | key_len={len(key)} | data_len={len(enc_data)}")

    try:
        raw_bytes = _decrypt_map_data(enc_data, key)
    except Exception as e:
        await _log(f"[DumpMaps] Error descifrando mapa {map_id}: {e}")
        return

    # Inferir versión de mapa según longitud de datos
    # 560 * 6 = 3360 → version 8 (completo)
    # 560 * 5 = 2800 → version 6-7
    # 560 * 4 = 2240 → version ≤ 5
    data_len = len(raw_bytes)
    if data_len >= 560 * 6:
        map_version = 8
    elif data_len >= 560 * 5:
        map_version = 6
    else:
        map_version = 4

    cells = _parse_cells(raw_bytes, map_version)
    movable = sum(1 for c in cells if c["mov"])

    _maps_db[map_id] = {"cells": cells}
    await _save_db()
    await _log(f"[DumpMaps] ✓ Mapa {map_id} guardado: {movable}/{MAP_CELLS} celdas transitables")


# ── Sniffer MITM (mismo patrón que tools/sniffer.py) ─────────────────────────

def _ts():
    return datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]


async def _log(line: str):
    entry = f"[{_ts()}] {line}"
    print(entry, flush=True)
    async with _log_lock:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(entry + "\n")


def _split_nul(buf: bytes) -> tuple[list[bytes], bytes]:
    parts = buf.split(b"\x00")
    return parts[:-1], parts[-1]


def _fmt(direction: str, raw: str) -> str:
    if not raw:
        return ""
    for hlen in (4, 3, 2):
        if len(raw) < hlen:
            continue
        hdr = raw[:hlen]
        if hdr.isalnum():
            rest = raw[hlen:]
            if rest.startswith("|"):
                rest = rest[1:]
            # Truncar para logs legibles (GDM puede ser muy largo)
            preview = rest[:80] + ("..." if len(rest) > 80 else "")
            return f"{direction}  {hdr:<6}  {preview}"
    return f"{direction}  {raw[:100]}"


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
                    await _log(f"[#{conn_id}] {direction} TLS — relay ciego")
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

                # Interceptar GDM para dump de celdas
                if raw.startswith("GDM"):
                    asyncio.create_task(_process_gdm(raw))

                await _log(_fmt(direction, raw))
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
        rewritten = f"AYK127.0.0.1:{GAME_LISTEN[1]};{ticket}"
        asyncio.create_task(_log(
            f"[AYK] game real={real_host}:{real_port} → 127.0.0.1:{GAME_LISTEN[1]}"
        ))
        return rewritten
    return raw


async def handle_login(cr, cw):
    global _conn_counter
    _conn_counter += 1
    cid = _conn_counter
    peer = cw.get_extra_info("peername")
    await _log(f"[#{cid} LOGIN] {peer}")
    try:
        sr, sw = await asyncio.open_connection(*LOGIN_UPSTREAM)
    except OSError as e:
        await _log(f"[#{cid} ERR] upstream: {e}")
        cw.close()
        return
    await asyncio.gather(
        _pump(sr, cw, "S→C", _login_transform, cid),
        _pump(cr, sw, "C→S", None, cid),
    )
    await _log(f"[#{cid} LOGIN CLOSE] {peer}")


async def handle_game(cr, cw):
    global _conn_counter
    _conn_counter += 1
    cid = _conn_counter
    peer = cw.get_extra_info("peername")
    await _log(f"[#{cid} GAME] {peer}")
    if not game_target["host"]:
        await _log("[ERR] game_target vacío (¿falta AYK?)")
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
        await _log(f"[#{cid} ERR] game upstream: {e}")
        cw.close()
        return
    await asyncio.gather(
        _pump(sr, cw, "S→C", None, cid),
        _pump(cr, sw, "C→S", None, cid),
    )
    await _log(f"[#{cid} GAME CLOSE] {peer}")


# ── Entry point ───────────────────────────────────────────────────────────────

async def main():
    global _log_lock, _db_lock
    _log_lock = asyncio.Lock()
    _db_lock  = asyncio.Lock()

    _load_db()

    print("=" * 60)
    print("  Dofus Retro — Dump de Mapas MITM")
    print(f"  Login proxy : {LOGIN_LISTEN[0]}:{LOGIN_LISTEN[1]}  → {LOGIN_UPSTREAM[0]}:{LOGIN_UPSTREAM[1]}")
    print(f"  Game  proxy : {GAME_LISTEN[0]}:{GAME_LISTEN[1]}")
    print(f"  BD mapas    : {os.path.abspath(MAPS_DB)}")
    print("=" * 60)
    print()
    print("Hosts file debe tener: 127.0.0.1  dofusretro-co-production.ankama-games.com")
    print("Abre el Launcher → Play → camina por todos los mapas que quieras capturar.")
    print("Cada mapa nuevo se guarda automáticamente en data/maps.json")
    print("Ctrl+C para detener.\n")

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
        print(f"\n[DumpMaps] Detenido. BD: {len(_maps_db)} mapas guardados en {MAPS_DB}")
