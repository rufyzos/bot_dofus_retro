"""
Herramienta de calibración del grid isométrico de combate.

MODELO (ver input/coords.py): numeración base-1, filas alternas 14/15 celdas.
    screen_x = rect.left + MAP_ORIGIN_X + col*CELL_W   + odd*ODD_DX
    screen_y = rect.top  + MAP_ORIGIN_Y + bloque*ROW_H + odd*ODD_DY
donde (col, fila) = cell_to_colrow(cell), bloque = fila//2, odd = fila%2.

MODO 1 — Mover cursor a celda (verificación visual):
    python tools/calibrate.py <cell_id> [cell_id2 ...]
    Mueve el cursor (sin click) al píxel calculado para cada celda.

MODO 2 — Ajuste por mínimos cuadrados (calibración precisa):
    python tools/calibrate.py --fit
    Pide pares "cell_id screen_x screen_y" medidos con Window Spy sobre el
    CENTRO del rombo. Recomendado >=5 celdas: filas par E impar, columnas
    extremas. Calcula MAP_ORIGIN_X/Y, CELL_W, ROW_H, ODD_DX, ODD_DY.

MODO 3 — Verificar calibración actual contra muestras guardadas:
    python tools/calibrate.py --verify
    Lee data/calibration_samples.txt y muestra el error por muestra + RMS.

Ejemplos:
    python tools/calibrate.py 15 268 463
    python tools/calibrate.py --fit
    python tools/calibrate.py --verify
"""

import sys
import time
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pyautogui
import config
from input.window import find_dofus_window, WindowRect
from input.coords import cell_to_screen, cell_to_colrow, CELL_W, ROW_H, ODD_DX, ODD_DY

pyautogui.FAILSAFE = False

SAMPLES_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "calibration_samples.txt")


def _load_samples(path: str) -> list[tuple[int, int, int]]:
    """Lee muestras de calibración de un archivo .txt. Devuelve lista de (cell, sx, sy)."""
    samples = []
    if not os.path.exists(path):
        return samples
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.split("#")[0].strip()
            if not line:
                continue
            parts = line.split()
            if len(parts) != 3:
                continue
            try:
                samples.append((int(parts[0]), int(parts[1]), int(parts[2])))
            except ValueError:
                continue
    return samples


# ── Modo cursor (verificacion visual) ────────────────────────────────────────

def mode_cursor(cell_ids: list[int]):
    print(f"Buscando ventana '{config.WINDOW_TITLE_SUBSTR}'...")
    rect = find_dofus_window(config.WINDOW_TITLE_SUBSTR)
    print(f"  Ventana: left={rect.left} top={rect.top} {rect.width}x{rect.height}")
    print(f"  MAP_ORIGIN=({config.MAP_ORIGIN_X},{config.MAP_ORIGIN_Y})")
    print()
    print("Iniciando en 2s — pon el foco en la ventana de Dofus...")
    time.sleep(2)

    for cell in cell_ids:
        col, fila = cell_to_colrow(cell)
        px, py = cell_to_screen(cell, rect, config.MAP_ORIGIN_X, config.MAP_ORIGIN_Y,
                                config.MAP_SCALE, scale_x=config.MAP_SCALE_X,
                                scale_y=config.MAP_SCALE_Y)
        par = "par" if fila % 2 == 0 else "impar"
        print(f"  cell={cell:>4} (col={col:>2},fila={fila:>2},{par}) -> ({px:>5}, {py:>5})")
        pyautogui.moveTo(px, py, duration=0.15)
        time.sleep(1.5)

    print("\nVerificacion completada.")
    print("Si el cursor no cae en la celda correcta, ejecuta --fit para recalibrar.")


# ── Modo verificacion (regresion contra muestras guardadas) ──────────────────

def mode_verify():
    samples = _load_samples(SAMPLES_PATH)
    if not samples:
        print(f"No hay muestras en {SAMPLES_PATH}")
        print("Mide con Window Spy y ejecuta --fit primero.")
        sys.exit(1)

    # Las muestras se midieron con la ventana en rect.left=0 top=23.
    # Si la ventana está minimizada/movida, win32 devuelve coords basura
    # (p.ej. -32000); usamos el rect de referencia de las muestras.
    rect = WindowRect(left=0, top=23, width=2560, height=1377)
    try:
        live = find_dofus_window(config.WINDOW_TITLE_SUBSTR)
        if live.width > 0 and live.left > -10000:
            rect = live
    except RuntimeError:
        pass

    print(f"Verificando {len(samples)} muestras (rect.left={rect.left} top={rect.top})...")
    print(f"  MAP_ORIGIN=({config.MAP_ORIGIN_X},{config.MAP_ORIGIN_Y})")
    print(f"  CELL_W={CELL_W}  ROW_H={ROW_H}  ODD_DX={ODD_DX}  ODD_DY={ODD_DY}")
    print()

    sum_sq = 0.0
    max_err = 0.0
    for cell, sx, sy in samples:
        col, fila = cell_to_colrow(cell)
        px, py = cell_to_screen(cell, rect, config.MAP_ORIGIN_X, config.MAP_ORIGIN_Y,
                                config.MAP_SCALE, scale_x=config.MAP_SCALE_X,
                                scale_y=config.MAP_SCALE_Y)
        ex, ey = px - sx, py - sy
        err = (ex**2 + ey**2) ** 0.5
        sum_sq += ex**2 + ey**2
        max_err = max(max_err, err)
        par = "par" if fila % 2 == 0 else "impar"
        warn = "  <- MAL" if err > 5 else ""
        print(f"  celda {cell:>3} (col={col:>2},fila={fila:>2},{par:>5}): "
              f"pred=({px},{py}) med=({sx},{sy}) err=({ex:+d},{ey:+d}) |{err:.1f}px|{warn}")

    rms = (sum_sq / len(samples)) ** 0.5
    print()
    print(f"  RMS={rms:.2f}px   MAX={max_err:.1f}px   (objetivo: RMS<5px, MAX<10px)")
    if rms < 5.0 and max_err < 10.0:
        print("  OK — calibracion correcta.")
    else:
        print("  AVISO: error alto. Ejecuta --fit con nuevas muestras.")


# ── Modo ajuste (minimos cuadrados) ──────────────────────────────────────────

def mode_fit():
    try:
        import numpy as np
    except ImportError:
        print("ERROR: numpy no esta instalado. Ejecuta: pip install numpy")
        sys.exit(1)

    print("Buscando ventana de Dofus para obtener rect.top/left...")
    try:
        rect = find_dofus_window(config.WINDOW_TITLE_SUBSTR)
        print(f"  Ventana: left={rect.left} top={rect.top} {rect.width}x{rect.height}")
    except RuntimeError as e:
        print(f"  Ventana no encontrada ({e}). Usando rect.left=0 rect.top=23 (defecto).")
        rect = WindowRect(left=0, top=23, width=2560, height=1377)

    print()
    print("=" * 60)
    print("  MODO AJUSTE — Minimos cuadrados (modelo geométrico 14/15)")
    print("=" * 60)
    print()
    print("Pon el cursor en el CENTRO visual de la celda (el rombo) con Window Spy.")
    print("Incluye celdas de filas PARES e IMPARES y columnas extremas.")
    print("Formato: <cell_id> <screen_x> <screen_y>   (ej: 268 1284 623)")
    print("Escribe 'listo' o deja la linea vacia cuando termines.")
    print()

    samples = []
    while True:
        try:
            line = input(f"  [{len(samples)+1}] cell screen_x screen_y (o 'listo'): ").strip()
        except EOFError:
            break
        if not line or line.lower() in ("listo", "done", "q", "exit"):
            break
        parts = line.split()
        if len(parts) != 3:
            print("    -> Formato incorrecto. Usa: cell_id screen_x screen_y")
            continue
        try:
            cell, sx, sy = int(parts[0]), int(parts[1]), int(parts[2])
        except ValueError:
            print("    -> Valores no numericos.")
            continue
        col, fila = cell_to_colrow(cell)
        cx = sx - rect.left
        cy = sy - rect.top
        samples.append((cell, col, fila % 2, fila // 2, cx, cy, sx, sy))
        par = "par" if fila % 2 == 0 else "impar"
        print(f"    -> celda {cell} (col={col},fila={fila},{par})  client=({cx},{cy})  OK")

    if len(samples) < 4:
        print("\nNecesitas al menos 4 muestras para el ajuste. Cancelando.")
        sys.exit(1)

    parities = set(s[2] for s in samples)
    if len(parities) < 2:
        print("\nAVISO: todas las muestras son de filas del mismo tipo (par/impar).")
        print("  ODD_DX/ODD_DY no se calibran bien. Añade filas del otro tipo.")

    print(f"\nAjustando con {len(samples)} muestras...")

    # screen_x - rect.left = MAP_ORIGIN_X + col*CELL_W   + odd*ODD_DX
    # screen_y - rect.top  = MAP_ORIGIN_Y + blk*ROW_H    + odd*ODD_DY
    Ax = np.array([[1, col, odd] for (_, col, odd, blk, cx, cy, sx, sy) in samples], float)
    bx = np.array([cx for (_, col, odd, blk, cx, cy, sx, sy) in samples], float)
    Ay = np.array([[1, blk, odd] for (_, col, odd, blk, cx, cy, sx, sy) in samples], float)
    by = np.array([cy for (_, col, odd, blk, cx, cy, sx, sy) in samples], float)

    solx, *_ = np.linalg.lstsq(Ax, bx, rcond=None)
    soly, *_ = np.linalg.lstsq(Ay, by, rcond=None)
    NEW_OX, NEW_CW, NEW_ODX = solx
    NEW_OY, NEW_RH, NEW_ODY = soly

    print()
    print("--- Residuales por muestra ---")
    max_err = 0.0
    sum_sq = 0.0
    bad = False
    for (cell, col, odd, blk, cx, cy, sx, sy) in samples:
        px_c = NEW_OX + col * NEW_CW + odd * NEW_ODX
        py_c = NEW_OY + blk * NEW_RH + odd * NEW_ODY
        ex = px_c + rect.left - sx
        ey = py_c + rect.top  - sy
        err = (ex**2 + ey**2) ** 0.5
        max_err = max(max_err, err)
        sum_sq += ex**2 + ey**2
        warn = "  <- REMEDIR" if err > 8 else ""
        if err > 8:
            bad = True
        par = "par" if odd == 0 else "impar"
        print(f"  celda {cell:>3} (col={col:>2},fila={blk*2+odd:>2},{par:>5}): "
              f"err=({ex:+.1f},{ey:+.1f})  |err|={err:.1f}px{warn}")

    rms = (sum_sq / len(samples)) ** 0.5
    print(f"\n  RMS={rms:.2f}px   MAX={max_err:.1f}px   (objetivo: RMS<5px, MAX<10px)")

    print()
    print("--- Pegar en input/coords.py ---")
    print(f"CELL_W:  float = {NEW_CW:.4f}")
    print(f"ROW_H:   float = {NEW_RH:.4f}")
    print(f"ODD_DX:  float = {NEW_ODX:.4f}")
    print(f"ODD_DY:  float = {NEW_ODY:.4f}")

    print()
    print("--- Pegar en config.py ---")
    print(f"MAP_ORIGIN_X: float = {NEW_OX:.4f}   # rect.left={rect.left}")
    print(f"MAP_ORIGIN_Y: float = {NEW_OY:.4f}   # rect.top={rect.top}")

    print()
    if rms > 5.0 or bad:
        print("AVISO: RMS alto o muestras con error >8px. Revisa las mediciones.")
    else:
        cells_str = " ".join(str(s[0]) for s in samples)
        print("OK — Calibracion correcta. Verifica visualmente con:")
        print(f"   python tools/calibrate.py {cells_str}")
        print("Y automaticamente con:  python tools/calibrate.py --verify")


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    args = sys.argv[1:]

    if not args:
        print(__doc__)
        print("Uso: python tools/calibrate.py <cell_id> [...]")
        print("     python tools/calibrate.py --fit")
        print("     python tools/calibrate.py --verify")
        sys.exit(1)

    if args[0] == "--fit":
        mode_fit()
        return

    if args[0] == "--verify":
        mode_verify()
        return

    cell_ids = []
    for arg in args:
        try:
            cell_ids.append(int(arg))
        except ValueError:
            print(f"cell_id invalido: {arg!r}")
            sys.exit(1)

    mode_cursor(cell_ids)


if __name__ == "__main__":
    main()
