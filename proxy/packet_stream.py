"""
Buffer TCP que acumula bytes crudos y emite paquetes completos.
Dofus Retro delimita cada mensaje con un byte nulo \x00.
Un solo segmento TCP puede traer varios mensajes o uno partido.
"""

DELIMITER = b"\x00"


class PacketStream:
    def __init__(self, on_packet):
        """
        on_packet: callable(raw: str) llamado por cada paquete completo (sin el \x00).
        """
        self._buf = b""
        self._on_packet = on_packet

    def feed(self, data: bytes):
        self._buf += data
        while DELIMITER in self._buf:
            packet, self._buf = self._buf.split(DELIMITER, 1)
            if packet:
                try:
                    self._on_packet(packet.decode("utf-8", errors="replace"))
                except Exception as exc:
                    print(f"[PacketStream] Error procesando paquete: {exc}")
