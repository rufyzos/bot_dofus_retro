"""
Sniffer MITM para Dofus Retro 1.48 — proxy TCP puro.

Prerequisito (ya hecho):
    C:\Windows\System32\drivers\etc\hosts contiene:
        127.0.0.1  dofusretro-co-production.ankama-games.com

El cliente, tras autenticarse con el Launcher, intenta conectar a
dofusretro-co-production.ankama-games.com:443 → hosts lo redirige a
127.0.0.1:443 → este proxy lo captura, registra los paquetes Dofus,
y reenvía al servidor real de Ankama.

USO (terminal como administrador, necesario para puerto 443):
    cd "c:\\Users\\vicma\\OneDrive\\Escritorio\\Dofus\\Bot"
    python tools/sniffer.py

Luego abre el Launcher → Play → el cliente conecta automáticamente.
"""

import asyncio
import datetime
import os
import re

LOGIN_LISTEN   = ("127.0.0.1", 443)
GAME_LISTEN    = ("127.0.0.1", 5556)
LOGIN_UPSTREAM = ("52.17.187.227", 443)  # IP real — evita bucle con hosts file
LOG_PATH       = os.path.join(os.path.dirname(__file__), "..", "sniffer.log")

_AYK_RE = re.compile(r"^AYK([^:]+):(\d+);(.+)$")  # host puede ser IP o hostname

game_target: dict = {"host": None, "port": None}
_log_lock = None
_conn_counter = 0


def _ts():
    return datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]


async def _log(line: str):
    entry = f"[{_ts()}] {line}"
    print(entry, flush=True)
    async with _log_lock:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(entry + "\n")


def _fmt(direction: str, raw: str) -> str:
    if not raw:
        return ""
    for hlen in (4, 3, 2):
        if len(raw) < hlen:
            continue
        hdr = raw[:hlen]
        rest = raw[hlen:]
        if hdr.isalnum():
            if rest.startswith("|"):
                rest = rest[1:]
            fields = rest.split("|") if rest else []
            field_str = "  ".join(f"[{i}]{v}" for i, v in enumerate(fields))
            return f"{direction}  {hdr:<6}  {field_str}"
    return f"{direction}  {raw}"


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
                # Detectar TLS ClientHello (\x16\x03) → relay ciego, no parsear
                if chunk[0:2] in (b'\x16\x03', b'\x15\x03'):
                    await _log(f"[#{conn_id}] {direction} TLS — relay ciego")
                    writer.write(chunk)
                    await writer.drain()
                    # Modo relay ciego para el resto de la conexión
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
                else:
                    await _log(f"[#{conn_id}] {direction} primer chunk: {chunk[:40]!r}")
            buf += chunk
            msgs, buf = _split_nul(buf)
            for raw_bytes in msgs:
                if not raw_bytes:
                    continue
                raw = raw_bytes.decode("utf-8", errors="replace")
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
        real_ip, real_port, ticket = m.group(1), m.group(2), m.group(3)
        game_target["host"] = real_ip
        game_target["port"] = int(real_port)
        rewritten = f"AYK127.0.0.1:{GAME_LISTEN[1]};{ticket}"
        asyncio.create_task(_log(
            f"[AYK] game real={real_ip}:{real_port} → 127.0.0.1:{GAME_LISTEN[1]}"
        ))
        return rewritten
    return raw


async def handle_login(cr, cw):
    global _conn_counter
    _conn_counter += 1
    cid = _conn_counter
    peer = cw.get_extra_info("peername")
    await _log(f"[#{cid} LOGIN CONNECT] {peer}")
    try:
        sr, sw = await asyncio.open_connection(*LOGIN_UPSTREAM)
    except OSError as e:
        await _log(f"[#{cid} ERR] upstream {LOGIN_UPSTREAM}: {e}")
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
    await _log(f"[#{cid} GAME CONNECT] {peer}")
    if not game_target["host"]:
        await _log("[ERR] game_target vacío (¿falta AYK?)")
        cw.close()
        return
    # Resolver IP real del game server (evitar bucle con hosts file)
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
    await _log(f"[#{cid} GAME] upstream={game_target['host']} → {real_ip}:{game_target['port']}")
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


async def main():
    global _log_lock
    _log_lock = asyncio.Lock()

    print("=" * 60)
    print("  Dofus Retro Sniffer MITM")
    print(f"  Login proxy : {LOGIN_LISTEN[0]}:{LOGIN_LISTEN[1]}  → {LOGIN_UPSTREAM[0]}:{LOGIN_UPSTREAM[1]}")
    print(f"  Game  proxy : {GAME_LISTEN[0]}:{GAME_LISTEN[1]}")
    print(f"  Log         : sniffer.log")
    print("=" * 60)
    print()
    print("Hosts file ya configurado. Abre el Launcher → Play.")
    print("Ctrl+C para detener.")
    print()

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
        print("\n[Sniffer] Detenido.")
