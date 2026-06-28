"""
Sniffer — modo "solo log" del proxy.

Arranca el proxy MITM en modo pasivo: solo imprime cada paquete
con su dirección, header y campos. No inyecta nada.

USO (Fase 0 — descubrimiento de protocolo):
  1. Añade esta línea en el archivo hosts de Windows para redirigir
     el cliente al proxy local:
         127.0.0.1  co.retro.dofus.com
     (Editar C:\\Windows\\System32\\drivers\\etc\\hosts como administrador)
  2. Ejecuta:  python tools/sniffer.py
  3. Abre el cliente de Dofus Retro e inicia sesión normalmente.
  4. Entra a una pelea manualmente y observa los paquetes de combate.
  5. Busca en el log:
       - El paquete que el CLIENTE envía al castear un hechizo  → actualiza CAST_SPELL en protocol/messages.py
       - El paquete que el CLIENTE envía al mover en combate    → actualiza MOVE_SPELL
       - El paquete para pasar turno (Gt)                       → confirma
       - El paquete de fin de combate (GE o similar)            → actualiza FIGHT_END
  6. Guarda el log con:  python tools/sniffer.py > sniffer_output.txt 2>&1

NOTA: Recuerda revertir el archivo hosts cuando termines de sniffear.
"""

import sys
import os
import datetime

# Añadir raíz del proyecto al path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from proxy.tcp_proxy import DofusProxy
from protocol.messages import header_of


def format_packet(direction: str, raw: str) -> str:
    hdr = header_of(raw)
    rest = raw[len(hdr):]
    if rest.startswith("|"):
        rest = rest[1:]
    fields = rest.split("|") if rest else []
    ts = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
    field_str = " | ".join(f"[{i}]{v}" for i, v in enumerate(fields)) if fields else "(sin campos)"
    return f"[{ts}] {direction}  {hdr:6s}  {field_str}"


def on_packet(direction: str, raw: str):
    line = format_packet(direction, raw)
    print(line, flush=True)


def main():
    print("=" * 70)
    print("  Dofus Retro Sniffer — Fase 0")
    print("  Escucha en 127.0.0.1:5555 (login) y :5556 (game)")
    print("  Ctrl+C para detener")
    print("=" * 70)

    proxy = DofusProxy(on_packet=on_packet)
    proxy.start()

    try:
        import time
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[Sniffer] Detenido.")
        proxy.stop()


if __name__ == "__main__":
    main()
