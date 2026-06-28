"""
Inyecta paquetes hacia el servidor o hacia el cliente en la sesión de juego.

Mejora vs v1: usa queue.Queue + hilo dedicado de envío por socket en lugar de
threading.Lock + sendall() directo. Esto garantiza thread-safety real para
socket.sendall() (que no es thread-safe con llamadas concurrentes) y separa
limpiamente la producción de paquetes del I/O de red.
"""

import socket
import threading
import queue

DELIMITER = b"\x00"
_SENTINEL = None  # señal de cierre para el hilo de envío


def _sender_thread(sock: socket.socket, q: queue.Queue):
    """Hilo dedicado que consume la cola y envía al socket en serie."""
    while True:
        data = q.get()
        if data is _SENTINEL:
            break
        try:
            sock.sendall(data)
        except OSError:
            break


class Injector:
    """
    Mantiene referencias a los sockets de la sesión de juego activa.
    Cada socket tiene su propia queue + hilo emisor, eliminando contención.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._to_server_sock: socket.socket | None = None
        self._to_client_sock: socket.socket | None = None
        self._server_q: queue.Queue | None = None
        self._client_q: queue.Queue | None = None

    def attach(self, to_server_sock: socket.socket, to_client_sock: socket.socket):
        """Llamado desde tcp_proxy cuando la sesión de juego se establece."""
        with self._lock:
            self._to_server_sock = to_server_sock
            self._to_client_sock = to_client_sock
            self._server_q = queue.Queue()
            self._client_q = queue.Queue()
            threading.Thread(
                target=_sender_thread, args=(to_server_sock, self._server_q),
                daemon=True, name="injector-to-server",
            ).start()
            threading.Thread(
                target=_sender_thread, args=(to_client_sock, self._client_q),
                daemon=True, name="injector-to-client",
            ).start()

    def detach(self):
        """Detiene los hilos emisores y libera los sockets."""
        with self._lock:
            if self._server_q:
                self._server_q.put(_SENTINEL)
            if self._client_q:
                self._client_q.put(_SENTINEL)
            self._to_server_sock = None
            self._to_client_sock = None
            self._server_q = None
            self._client_q = None

    @staticmethod
    def _serialize(header: str, fields: tuple[str, ...]) -> bytes:
        parts = [header] + list(fields)
        return ("|".join(parts)).encode("utf-8") + DELIMITER

    def to_server(self, header: str, *fields: str):
        """Encola un paquete estándar (delimitado por '|') hacia el game server."""
        with self._lock:
            if not self._server_q:
                raise RuntimeError("Injector: no hay sesión de juego activa")
            self._server_q.put(self._serialize(header, fields))

    def to_client(self, header: str, *fields: str):
        """Encola un paquete estándar (delimitado por '|') hacia el cliente."""
        with self._lock:
            if not self._client_q:
                raise RuntimeError("Injector: no hay sesión de juego activa")
            self._client_q.put(self._serialize(header, fields))

    def raw_to_server(self, raw: str):
        """Encola un paquete con formato literal (ya serializado, sin trailing \\x00)."""
        with self._lock:
            if not self._server_q:
                raise RuntimeError("Injector: no hay sesión de juego activa")
            self._server_q.put(raw.encode("utf-8") + DELIMITER)
