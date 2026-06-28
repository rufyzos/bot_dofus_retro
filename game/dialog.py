"""
Diálogos PNJ — máquina de estados para interacciones con NPCs.

Flujo:
  1. C→S DC<npc_id>        → iniciar diálogo
  2. S→C DCK               → diálogo abierto
  3. S→C DQ<pregunta>|<op1>|<op2>... → opciones disponibles
  4. C→S DR<opcion_id>     → elegir opción
  5. C→S DV                → salir del diálogo

El actuador usa clicks en la UI — no inyectamos C→S.
Por eso el DialogManager solo rastrea el estado y los callbacks;
la actuación física la hace el código de nivel superior (HDV, Navigator).
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Callable


@dataclass
class DialogOption:
    id: str
    text: str


class DialogManager:
    def __init__(self):
        self.in_dialog:    bool = False
        self.npc_id:       str | None = None
        self.options:      list[DialogOption] = []

        # Callback llamado cuando llegan opciones nuevas
        self.on_question: Callable[[list[DialogOption]], None] | None = None
        # Callback cuando el diálogo se cierra
        self.on_closed:   Callable[[], None] | None = None

    # ------------------------------------------------------------------
    # Handlers de paquetes
    # ------------------------------------------------------------------

    def handle_dck(self, fields: list[str]):
        """DCK — diálogo creado."""
        self.in_dialog = True
        self.npc_id = fields[0] if fields else None
        self.options = []
        print(f"[Dialog] Abierto con NPC {self.npc_id}")

    def handle_dq(self, fields: list[str]):
        """
        DQ — pregunta con opciones.
        Formato aproximado: DQ<question_id>|<op_id>;<texto>|<op_id>;<texto>|...
        """
        self.options = []
        # El primer field puede ser el ID de pregunta; los siguientes, las opciones
        for f in fields[1:]:
            parts = f.split(";", 1)
            if len(parts) >= 2:
                self.options.append(DialogOption(id=parts[0], text=parts[1]))
            elif parts[0]:
                self.options.append(DialogOption(id=parts[0], text=parts[0]))
        print(f"[Dialog] Opciones: {[o.id for o in self.options]}")
        if self.on_question:
            self.on_question(self.options)

    def handle_dv(self, fields: list[str]):
        """DV — diálogo cerrado."""
        print("[Dialog] Cerrado")
        self.in_dialog = False
        self.npc_id    = None
        self.options   = []
        if self.on_closed:
            self.on_closed()

    def register_handlers(self, dispatcher):
        from protocol.messages import DCK, DQ, DV
        from protocol.dispatcher import DIRECTION_SERVER
        dispatcher.on(DCK, self.handle_dck, DIRECTION_SERVER)
        dispatcher.on(DQ,  self.handle_dq,  DIRECTION_SERVER)
        dispatcher.on(DV,  self.handle_dv,  DIRECTION_SERVER)
        print("[Dialog] Handlers registrados: DCK, DQ, DV")


# Instancia global compartida
dialog = DialogManager()
