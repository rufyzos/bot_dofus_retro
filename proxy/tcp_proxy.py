"""
Proxy TCP MITM para Dofus Retro 1.48 — soporta N sesiones simultáneas.

Arquitectura multisesión:
  - Un único listener en :443 (login) acepta N clientes.
  - Cada cliente de login crea una Session con su propio puerto de game (5600+k).
  - Al interceptar AYK, reescribe host:port → 127.0.0.1:<puerto_sesión>.
  - Cada Session tiene su propio listener de game efímero.
  - Los buffers están completamente aislados por sesión (no se mezclan firmas).

Modo monosesión (retrocompatible):
  Si on_session_created no se provee, se usa el callback legacy on_packet /
  on_game_session igual que antes.
"""

import socket
import threading
import re

from proxy.packet_stream import PacketStream

LOCAL_LOGIN_HOST = "127.0.0.1"
LOCAL_LOGIN_PORT = 443

# IP directa del login server — evita el bucle con el hosts file.
REAL_LOGIN_HOST = "52.17.187.227"
REAL_LOGIN_PORT = 443

DIRECTION_CLIENT = "C→S"
DIRECTION_SERVER = "S→C"

BUFSIZE = 16384

_AYK_RE = re.compile(rb"AYK([^:]+):(\d+);(.+?)(?=\x00|$)")


def _set_nodelay(sock: socket.socket):
    try:
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    except OSError:
        pass


def _forward(src: socket.socket, dst: socket.socket,
             stream: PacketStream,
             rewrite_fn=None,
             stop_event: threading.Event = None,
             raw_log=None):
    try:
        while not (stop_event and stop_event.is_set()):
            data = src.recv(BUFSIZE)
            if not data:
                try:
                    dst.shutdown(socket.SHUT_WR)
                except OSError:
                    pass
                break
            if raw_log:
                raw_log(data)
            if rewrite_fn:
                data = rewrite_fn(data)
            stream.feed(data)
            try:
                dst.sendall(data)
            except OSError:
                break
    except OSError:
        pass
    finally:
        if stop_event:
            stop_event.set()


class DofusProxy:
    def __init__(self,
                 on_packet=None,
                 on_game_session=None,
                 on_session_created=None,
                 real_login_host=REAL_LOGIN_HOST,
                 real_login_port=REAL_LOGIN_PORT):
        """
        Modo legacy (monocuenta):
          on_packet(direction, raw)
          on_game_session(server_sock, client_sock)

        Modo multisesión:
          on_session_created(session_id) → devuelve (on_packet_fn, on_game_fn)
          donde cada fn es específica de esa sesión.
        """
        self._on_packet_legacy       = on_packet or (lambda d, r: None)
        self._on_game_session_legacy = on_game_session or (lambda s, c: None)
        self._on_session_created     = on_session_created  # None = modo legacy

        self._real_login_host = real_login_host
        self._real_login_port = real_login_port

        self._login_server = None
        self._session_counter = 0
        self._session_lock = threading.Lock()

    # ------------------------------------------------------------------
    # Reescritura AYK — por sesión, con puerto propio
    # ------------------------------------------------------------------

    def _make_rewrite_ayk(self, session_state: dict) -> callable:
        """Devuelve un rewrite_fn que redirige AYK al puerto local de esta sesión."""
        def rewrite(data: bytes) -> bytes:
            m = _AYK_RE.search(data)
            if m:
                real_host = m.group(1).decode("utf-8", errors="replace")
                real_port = int(m.group(2))
                ticket    = m.group(3).decode("utf-8", errors="replace")
                session_state["game_host"] = real_host
                session_state["game_port"] = real_port
                local_port = session_state["local_game_port"]
                print(f"[Proxy S{session_state['id']}] AYK: "
                      f"{real_host}:{real_port} → 127.0.0.1:{local_port}")
                replacement = f"AYK127.0.0.1:{local_port};{ticket}".encode("utf-8")
                data = _AYK_RE.sub(replacement, data, count=1)
            return data
        return rewrite

    # ------------------------------------------------------------------
    # Manejo de conexiones de game por sesión
    # ------------------------------------------------------------------

    def _start_game_listener(self, session_state: dict,
                              on_packet_fn, on_game_fn) -> socket.socket:
        """Abre un listener de game en el puerto local asignado a esta sesión."""
        local_port = session_state["local_game_port"]
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind((LOCAL_LOGIN_HOST, local_port))
        srv.listen(1)

        def _accept_once():
            try:
                client_sock, addr = srv.accept()
            except OSError:
                return
            finally:
                srv.close()  # solo una conexión por sesión
            self._handle_game_client(client_sock, session_state,
                                     on_packet_fn, on_game_fn)

        threading.Thread(target=_accept_once, daemon=True).start()
        return srv

    def _handle_game_client(self, client_sock: socket.socket,
                             session_state: dict,
                             on_packet_fn, on_game_fn):
        sid = session_state["id"]
        real_host = session_state.get("game_host")
        real_port = session_state.get("game_port")
        if not real_host:
            print(f"[Proxy S{sid}] Game server desconocido — AYK no recibido.")
            client_sock.close()
            return

        _set_nodelay(client_sock)
        try:
            addrs = socket.getaddrinfo(real_host, real_port,
                                       socket.AF_INET, socket.SOCK_STREAM)
            real_ip = addrs[0][4][0]
        except OSError:
            real_ip = real_host

        try:
            server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server_sock.connect((real_ip, real_port))
            _set_nodelay(server_sock)
        except OSError as e:
            print(f"[Proxy S{sid}] No se pudo conectar al game server: {e}")
            client_sock.close()
            return

        print(f"[Proxy S{sid}] Game: {real_host}→{real_ip}:{real_port}")
        on_game_fn(server_sock, client_sock)

        stop = threading.Event()
        s2c_stream = PacketStream(lambda raw: on_packet_fn(DIRECTION_SERVER, raw))
        c2s_stream = PacketStream(lambda raw: on_packet_fn(DIRECTION_CLIENT, raw))

        threading.Thread(
            target=_forward,
            args=(server_sock, client_sock, s2c_stream),
            kwargs={"stop_event": stop},
            daemon=True,
        ).start()
        threading.Thread(
            target=_forward,
            args=(client_sock, server_sock, c2s_stream),
            kwargs={"stop_event": stop},
            daemon=True,
        ).start()
        stop.wait()
        client_sock.close()
        server_sock.close()
        print(f"[Proxy S{sid}] Game: sesión cerrada")

    # ------------------------------------------------------------------
    # Login
    # ------------------------------------------------------------------

    def _handle_login_client(self, client_sock: socket.socket, addr):
        with self._session_lock:
            self._session_counter += 1
            sid = self._session_counter

        # Puerto de game dedicado a esta sesión (5600, 5601, …)
        local_game_port = 5599 + sid
        session_state = {
            "id":              sid,
            "local_game_port": local_game_port,
            "game_host":       None,
            "game_port":       None,
        }
        print(f"[Proxy] Login: cliente {addr} → sesión {sid} "
              f"(game port {local_game_port})")

        # Resolver callbacks: multisesión o legacy
        if self._on_session_created:
            on_packet_fn, on_game_fn = self._on_session_created(sid)
        else:
            on_packet_fn = self._on_packet_legacy
            on_game_fn   = self._on_game_session_legacy

        _set_nodelay(client_sock)
        try:
            server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server_sock.connect((self._real_login_host, self._real_login_port))
            _set_nodelay(server_sock)
        except OSError as e:
            print(f"[Proxy S{sid}] No se pudo conectar al login server: {e}")
            client_sock.close()
            return

        # Iniciar listener de game antes de arrancar el forwarding de login,
        # porque AYK puede llegar justo después de conectar.
        self._start_game_listener(session_state, on_packet_fn, on_game_fn)

        rewrite_ayk = self._make_rewrite_ayk(session_state)
        stop = threading.Event()
        s2c_stream = PacketStream(lambda raw: on_packet_fn(DIRECTION_SERVER, raw))
        c2s_stream = PacketStream(lambda raw: on_packet_fn(DIRECTION_CLIENT, raw))

        threading.Thread(
            target=_forward,
            args=(server_sock, client_sock, s2c_stream),
            kwargs={"rewrite_fn": rewrite_ayk, "stop_event": stop},
            daemon=True,
        ).start()
        threading.Thread(
            target=_forward,
            args=(client_sock, server_sock, c2s_stream),
            kwargs={"stop_event": stop},
            daemon=True,
        ).start()
        stop.wait()
        client_sock.close()
        server_sock.close()
        print(f"[Proxy S{sid}] Login: sesión cerrada ({addr})")

    def _accept_loop(self, server_sock: socket.socket, handler):
        while True:
            try:
                client, addr = server_sock.accept()
                threading.Thread(target=handler, args=(client, addr), daemon=True).start()
            except OSError:
                break

    # ------------------------------------------------------------------
    # Inicio / parada
    # ------------------------------------------------------------------

    def start(self):
        self._login_server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._login_server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._login_server.bind((LOCAL_LOGIN_HOST, LOCAL_LOGIN_PORT))
        self._login_server.listen(10)
        print(f"[Proxy] Login escuchando en {LOCAL_LOGIN_HOST}:{LOCAL_LOGIN_PORT}")

        threading.Thread(
            target=self._accept_loop,
            args=(self._login_server, self._handle_login_client),
            daemon=True,
        ).start()

    def stop(self):
        if self._login_server:
            self._login_server.close()
