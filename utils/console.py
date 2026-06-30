"""
Fuerza UTF-8 en stdout/stderr para que los print con caracteres no-ASCII
(→, ⚠, ✓, ←, ó, í…) no revienten en la consola de Windows (cp1252).

Sin esto, un print con '→' lanza UnicodeEncodeError, y como los arquetipos
loguean su decisión con '→', el except de CombatAI captura el error y aborta
el turno SIN actuar. Importar este módulo (idempotente) al arrancar cualquier
entry point: `import utils.console`.
"""

from __future__ import annotations
import sys


def force_utf8() -> None:
    """Reconfigura stdout/stderr a UTF-8 con reemplazo (Python ≥3.7)."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                # Stream redirigido a algo no reconfigurable: ignorar.
                pass


# Aplicar al importar — idempotente.
force_utf8()
