"""
Registro y despacho de handlers por (dirección, header).

Regla: un solo handler por (dirección, header).
Si dos módulos necesitan el mismo paquete, usar callbacks intermedios en GameState
(patrón aprendido en sesión anterior para evitar sobreescritura de handlers).
"""

from protocol.messages import header_of

DIRECTION_CLIENT = "C→S"
DIRECTION_SERVER = "S→C"
DIRECTION_ANY    = "*"


class Dispatcher:
    def __init__(self):
        # { (direction, header): callable(fields: list[str]) }
        self._handlers: dict[tuple[str, str], callable] = {}

    def on(self, header: str, callback, direction: str = DIRECTION_ANY):
        key = (direction, header)
        if key in self._handlers:
            raise ValueError(
                f"Dispatcher: ya existe un handler para ({direction}, {header!r}). "
                "Usar callbacks intermedios en GameState en lugar de registrar dos veces."
            )
        self._handlers[key] = callback

    def dispatch(self, direction: str, raw: str):
        hdr = header_of(raw)
        # Buscar handler específico primero, luego comodín
        handler = (
            self._handlers.get((direction, hdr))
            or self._handlers.get((DIRECTION_ANY, hdr))
        )
        if handler:
            try:
                # Extraer fields (todo lo que hay después del header)
                rest = raw[len(hdr):]
                if rest.startswith("|"):
                    rest = rest[1:]
                fields = rest.split("|") if rest else []
                handler(fields)
            except Exception as exc:
                print(f"[Dispatcher] Error en handler ({direction}, {hdr!r}): {exc}")

    def registered(self) -> list[tuple[str, str]]:
        return list(self._handlers.keys())
