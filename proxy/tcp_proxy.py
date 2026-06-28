"""
Proxy TCP MITM para Dofus Retro 1.48.

Arquitectura de dos servidores:
  1. Login server (puerto 5555): el cliente se conecta aquí primero.
     El servidor responde con la IP:puerto del game server tras la autenticación.
  2. Game server (puerto dinámico): el cliente abre una SEGUNDA conexión.

El proxy:
  - Escucha en LOCAL_LOGIN_PORT (5555) y LOCAL_GAME_PORT (5556).
  - Reenvía el tráfico al servidor real de Ankama.
  - Intercepta el paquete AXK (server_selection_success) del login server para
    reescribir la IP del game server por 127.0.0.1:LOCAL_GAME_PORT, de modo que
    la segunda conexión también pase por este proxy.
  - Llama a on_packet(direction, raw) para cada paquete en ambas conexiones.
"""

import socket
import threading
import re

from proxy.packet_stream import PacketStream

LOCAL_LOGIN_HOST = "127.0.0.1"
LOCAL_LOGIN_PORT = 5555
LOCAL_GAME_PORT = 5556

REAL_LOGIN_HOST = "co.retro.dofus.com"
REAL_LOGIN_PORT = 5555

DIRECTION_CLIENT = "C→S"
DIRECTION_SERVER = "S→C"

BUFSIZE = 16384  # 16 KB — reduce syscalls vs 4K sin añadir latencia perceptible

# Patrón del paquete AXK que entrega IP:puerto del game server.
# Formato aproximado: AXK<ip>:<port>|<ticket>
# El formato exacto debe confirmarse con el sniffer (Fase 0).
_AXK_RE = re.compile(rb"AXK(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}):(\d+)\|")


def _set_nodelay(sock: socket.socket):
    """Deshabilita Nagle para envío inmediato de paquetes pequeños (protocolo de juego)."""
    try:
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    except OSError:
        pass


def _forward(src: socket.socket, dst: socket.socket,
             stream: PacketStream, direction: str,
             rewrite_fn=None,
             stop_event: threading.Event = None):
    """Lee de src, pasa por stream (para callbacks), y reenvía a dst."""
    try:
        while not (stop_event and stop_event.is_set()):
            data = src.recv(BUFSIZE)
            if not data:
                # Par cerró su lado de escritura — propagar EOF limpiamente
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
    def __init__(self, on_packet=None, real_login_host=REAL_LOGIN_HOST,
                 real_login_port=REAL_LOGIN_PORT):
        """
        on_packet: callable(direction: str, raw: str) para cada paquete observado.
                   direction es "C→S" o "S→C".
        """
        self._on_packet = on_packet or (lambda d, r: None)
        self._real_login_host = real_login_host
        self._real_login_port = real_login_port

        # IP:puerto del game server real (se rellena al interceptar AXK).
        self._real_game_host: str | None = None
        self._real_game_port: int | None = None

        self._login_server = None
        self._game_server = None

    # ------------------------------------------------------------------
    # Callbacks de paquetes
    # ------------------------------------------------------------------

    def _make_callback(self, direction: str):
        def cb(raw: str):
            self._on_packet(direction, raw)
        return cb

    # ------------------------------------------------------------------
    # Reescritura del AXK para redirigir game server al proxy local
    # ------------------------------------------------------------------

    def _rewrite_axk(self, data: bytes) -> bytes:
        m = _AXK_RE.search(data)
        if m:
            real_ip = m.group(1).decode()
            real_port = int(m.group(2).decode())
            self._real_game_host = real_ip
            self._real_game_port = real_port
            print(f"[Proxy] Game server real: {real_ip}:{real_port} → redirigido a 127.0.0.1:{LOCAL_GAME_PORT}")
            # Reemplazar IP real por 127.0.0.1 y puerto por LOCAL_GAME_PORT
            replacement = f"AXK127.0.0.1:{LOCAL_GAME_PORT}|".encode()
            data = _AXK_RE.sub(replacement, data, count=1)
        return data

    # ------------------------------------------------------------------
    # Gestión de conexiones
    # ------------------------------------------------------------------

    def _handle_login_client(self, client_sock: socket.socket, addr):
        print(f"[Proxy] Login: cliente conectado desde {addr}")
        _set_nodelay(client_sock)
        try:
            server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server_sock.connect((self._real_login_host, self._real_login_port))
            _set_nodelay(server_sock)
        except OSError as e:
            print(f"[Proxy] No se pudo conectar al login server real: {e}")
            client_sock.close()
            return

        stop = threading.Event()

        s2c_stream = PacketStream(self._make_callback(DIRECTION_SERVER))
        c2s_stream = PacketStream(self._make_callback(DIRECTION_CLIENT))

        t1 = threading.Thread(
            target=_forward,
            args=(server_sock, client_sock, s2c_stream, DIRECTION_SERVER),
            kwargs={"rewrite_fn": self._rewrite_axk, "stop_event": stop},
            daemon=True,
        )
        t2 = threading.Thread(
            target=_forward,
            args=(client_sock, server_sock, c2s_stream, DIRECTION_CLIENT),
            kwargs={"stop_event": stop},
            daemon=True,
        )
        t1.start()
        t2.start()
        stop.wait()
        client_sock.close()
        server_sock.close()
        print(f"[Proxy] Login: sesión cerrada ({addr})")

    def _handle_game_client(self, client_sock: socket.socket, addr):
        print(f"[Proxy] Game: cliente conectado desde {addr}")
        if not self._real_game_host:
            print("[Proxy] Game server real desconocido (¿AXK aún no interceptado?).")
            client_sock.close()
            return

        _set_nodelay(client_sock)
        try:
            server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server_sock.connect((self._real_game_host, self._real_game_port))
            _set_nodelay(server_sock)
        except OSError as e:
            print(f"[Proxy] No se pudo conectar al game server real: {e}")
            client_sock.close()
            return

        stop = threading.Event()

        s2c_stream = PacketStream(self._make_callback(DIRECTION_SERVER))
        c2s_stream = PacketStream(self._make_callback(DIRECTION_CLIENT))

        t1 = threading.Thread(
            target=_forward,
            args=(server_sock, client_sock, s2c_stream, DIRECTION_SERVER),
            kwargs={"stop_event": stop},
            daemon=True,
        )
        t2 = threading.Thread(
            target=_forward,
            args=(client_sock, server_sock, c2s_stream, DIRECTION_CLIENT),
            kwargs={"stop_event": stop},
            daemon=True,
        )
        t1.start()
        t2.start()
        stop.wait()
        client_sock.close()
        server_sock.close()
        print(f"[Proxy] Game: sesión cerrada ({addr})")

    def _accept_loop(self, server_sock: socket.socket, handler):
        while True:
            try:
                client, addr = server_sock.accept()
                t = threading.Thread(target=handler, args=(client, addr), daemon=True)
                t.start()
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
        print(f"[Proxy] Escuchando login en {LOCAL_LOGIN_HOST}:{LOCAL_LOGIN_PORT}")

        self._game_server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._game_server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._game_server.bind((LOCAL_LOGIN_HOST, LOCAL_GAME_PORT))
        self._game_server.listen(5)
        print(f"[Proxy] Escuchando game  en {LOCAL_LOGIN_HOST}:{LOCAL_GAME_PORT}")

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
