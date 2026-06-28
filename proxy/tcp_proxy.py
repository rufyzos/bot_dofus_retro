"""
Proxy TCP MITM para Dofus Retro 1.48.

Arquitectura de dos servidores:
  1. Login server (puerto 443): el cliente se conecta aquí primero.
     El hosts file redirige dofusretro-co-production.ankama-games.com → 127.0.0.1
  2. Game server (puerto 5556): la segunda conexión del cliente.

El proxy:
  - Escucha en :443 (login) y :5556 (game).
  - Upstream de login: IP directa para evitar el bucle con hosts file.
  - Intercepta AYK (server_selection_success) y reescribe host:port → 127.0.0.1:5556.
  - Llama a on_packet(direction, raw) por cada paquete en ambas conexiones.
  - Llama a on_game_session(server_sock, client_sock) cuando la sesión de game está activa,
    para que el Injector pueda engancharse.
"""

import socket
import threading
import re

from proxy.packet_stream import PacketStream

LOCAL_LOGIN_HOST = "127.0.0.1"
LOCAL_LOGIN_PORT = 443
LOCAL_GAME_PORT  = 5556

# IP directa del login server — evita el bucle con el hosts file.
# Si cambia: nslookup dofusretro-co-production.ankama-games.com 8.8.8.8
REAL_LOGIN_HOST = "52.17.187.227"
REAL_LOGIN_PORT = 443

DIRECTION_CLIENT = "C→S"
DIRECTION_SERVER = "S→C"

BUFSIZE = 16384

# AYK viene como: AYK<hostname>:<port>;<ticket>
# hostname puede ser IP numérica o nombre de dominio.
_AYK_RE = re.compile(rb"AYK([^:]+):(\d+);(.+?)(?=\x00|$)")


def _set_nodelay(sock: socket.socket):
    try:
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    except OSError:
        pass


def _forward(src: socket.socket, dst: socket.socket,
             stream: PacketStream,
             rewrite_fn=None,
             stop_event: threading.Event = None):
    try:
        while not (stop_event and stop_event.is_set()):
            data = src.recv(BUFSIZE)
            if not data:
                try:
                    dst.shutdown(socket.SHUT_WR)
                except OSError:
                    pass
                break
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
    def __init__(self, on_packet=None, on_game_session=None,
                 real_login_host=REAL_LOGIN_HOST,
                 real_login_port=REAL_LOGIN_PORT):
        """
        on_packet(direction, raw)      — callback por cada paquete observado.
        on_game_session(srv, cli)      — callback cuando la sesión de game se abre;
                                         recibe (server_sock, client_sock) para el Injector.
        """
        self._on_packet       = on_packet or (lambda d, r: None)
        self._on_game_session = on_game_session or (lambda s, c: None)
        self._real_login_host = real_login_host
        self._real_login_port = real_login_port

        self._real_game_host: str | None = None
        self._real_game_port: int | None = None
        self._game_lock = threading.Lock()

        self._login_server = None
        self._game_server  = None

    # ------------------------------------------------------------------
    # Reescritura AYK
    # ------------------------------------------------------------------

    def _rewrite_ayk(self, data: bytes) -> bytes:
        m = _AYK_RE.search(data)
        if m:
            real_host = m.group(1).decode("utf-8", errors="replace")
            real_port = int(m.group(2))
            ticket    = m.group(3).decode("utf-8", errors="replace")
            with self._game_lock:
                self._real_game_host = real_host
                self._real_game_port = real_port
            print(f"[Proxy] AYK: game real={real_host}:{real_port} → 127.0.0.1:{LOCAL_GAME_PORT}")
            replacement = f"AYK127.0.0.1:{LOCAL_GAME_PORT};{ticket}".encode("utf-8")
            # Reemplazar solo el payload AYK, conservar el \x00 de fin de paquete
            data = _AYK_RE.sub(replacement, data, count=1)
        return data

    # ------------------------------------------------------------------
    # Callbacks de paquetes
    # ------------------------------------------------------------------

    def _make_callback(self, direction: str):
        def cb(raw: str):
            self._on_packet(direction, raw)
        return cb

    # ------------------------------------------------------------------
    # Conexiones
    # ------------------------------------------------------------------

    def _handle_login_client(self, client_sock: socket.socket, addr):
        print(f"[Proxy] Login: cliente {addr}")
        _set_nodelay(client_sock)
        try:
            server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server_sock.connect((self._real_login_host, self._real_login_port))
            _set_nodelay(server_sock)
        except OSError as e:
            print(f"[Proxy] No se pudo conectar al login server: {e}")
            client_sock.close()
            return

        stop = threading.Event()
        s2c_stream = PacketStream(self._make_callback(DIRECTION_SERVER))
        c2s_stream = PacketStream(self._make_callback(DIRECTION_CLIENT))

        threading.Thread(
            target=_forward,
            args=(server_sock, client_sock, s2c_stream),
            kwargs={"rewrite_fn": self._rewrite_ayk, "stop_event": stop},
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
        print(f"[Proxy] Login: sesión cerrada ({addr})")

    def _handle_game_client(self, client_sock: socket.socket, addr):
        print(f"[Proxy] Game: cliente {addr}")
        with self._game_lock:
            real_host = self._real_game_host
            real_port = self._real_game_port
        if not real_host:
            print("[Proxy] Game server desconocido — AYK aún no recibido.")
            client_sock.close()
            return

        _set_nodelay(client_sock)
        # Resolver hostname a IP para evitar el bucle con hosts file
        try:
            loop_info = socket.getaddrinfo(real_host, real_port,
                                           socket.AF_INET, socket.SOCK_STREAM)
            real_ip = loop_info[0][4][0]
        except OSError:
            real_ip = real_host

        try:
            server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server_sock.connect((real_ip, real_port))
            _set_nodelay(server_sock)
        except OSError as e:
            print(f"[Proxy] No se pudo conectar al game server {real_ip}:{real_port}: {e}")
            client_sock.close()
            return

        print(f"[Proxy] Game: upstream={real_host} → {real_ip}:{real_port}")

        # Notificar al Injector ANTES de arrancar los hilos de forwarding
        self._on_game_session(server_sock, client_sock)

        stop = threading.Event()
        s2c_stream = PacketStream(self._make_callback(DIRECTION_SERVER))
        c2s_stream = PacketStream(self._make_callback(DIRECTION_CLIENT))

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
        print(f"[Proxy] Game: sesión cerrada ({addr})")

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
        self._login_server.listen(5)
        print(f"[Proxy] Login escuchando en {LOCAL_LOGIN_HOST}:{LOCAL_LOGIN_PORT}")

        self._game_server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._game_server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._game_server.bind((LOCAL_LOGIN_HOST, LOCAL_GAME_PORT))
        self._game_server.listen(5)
        print(f"[Proxy] Game  escuchando en {LOCAL_LOGIN_HOST}:{LOCAL_GAME_PORT}")

        threading.Thread(
            target=self._accept_loop,
            args=(self._login_server, self._handle_login_client),
            daemon=True,
        ).start()
        threading.Thread(
            target=self._accept_loop,
            args=(self._game_server, self._handle_game_client),
            daemon=True,
        ).start()

    def stop(self):
        if self._login_server:
            self._login_server.close()
        if self._game_server:
            self._game_server.close()
