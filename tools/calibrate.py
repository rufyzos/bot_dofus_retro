"""
Herramienta de calibración del grid isométrico de combate.

MODO 1 — Mover cursor a celda (verificación visual):
    python tools/calibrate.py <cell_id> [cell_id2 ...]
    Mueve el cursor (sin click) al píxel calculado para cada celda.
    Observa si cae sobre la celda correcta en el cliente.

MODO 2 — Ajuste por mínimos cuadrados (calibración precisa):
    python tools/calibrate.py --fit

    El script te pide pares "cell_id screen_x screen_y" medidos con Window Spy
    sobre el CENTRO de cada celda. Recomendado >=5 celdas repartidas por el mapa:
    filas par E impar (cruciales para calibrar CELL_HW), columnas extremas.

    El ajuste calcula los 5 coeficientes del modelo isométrico canónico:
        screen_x = rect.left + MAP_ORIGIN_X + col*CELL_W + parity*CELL_HW + row*CELL_RW
        screen_y = rect.top  + MAP_ORIGIN_Y + row*CELL_HH
    donde row=x+y, parity=row%2, col=(x-y-parity)//2  (x,y = coords Arakne)
    CELL_RW es el skew horizontal del grid (negativo = se inclina izquierda al bajar).

    Celdas recomendadas (cubren filas par/impar y columnas extremas):
        0, 13, 27, 14, 270, 283, 532, 545, 559

MODO 3 — Verificar calibración actual contra muestras guardadas:
    python tools/calibrate.py --verify
    Lee data/calibration_samples.txt y muestra el error por muestra + RMS.
    Objetivo: RMS < 2px, MAX < 5px.

Ejemplos:
    python tools/calibrate.py 0 200 400 559
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
from input.coords import cell_to_screen, cell_to_arakne, MAP_WIDTH, CELL_W, CELL_HW, CELL_HH, CELL_RW, CELL_CY

pyautogui.FAILSAFE = False

SAMPLES_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "calibration_samples.txt")


def _cell_features(cell: int) -> tuple[int, int, int]:
    """Devuelve (col, parity, row) canónicos para un cell_id."""
    x, y = cell_to_arakne(cell)
    row    = x + y
    parity = row % 2
    col    = (x - y - parity) // 2
    return col, parity, row


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
        col, parity, row = _cell_features(cell)
        px, py = cell_to_screen(cell, rect, config.MAP_ORIGIN_X, config.MAP_ORIGIN_Y,
                                config.MAP_SCALE, scale_x=config.MAP_SCALE_X,
                                scale_y=config.MAP_SCALE_Y)
        print(f"  cell={cell:>4} (row={row:>2},col={col:>2},par={parity}) -> ({px:>5}, {py:>5})")
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

    try:
        rect = find_dofus_window(config.WINDOW_TITLE_SUBSTR)
    except RuntimeError:
        rect = WindowRect(left=0, top=23, width=2560, height=1377)

    print(f"Verificando {len(samples)} muestras con config actual...")
    print(f"  MAP_ORIGIN=({config.MAP_ORIGIN_X},{config.MAP_ORIGIN_Y})")
    print(f"  CELL_W={CELL_W}  CELL_HW={CELL_HW}  CELL_HH={CELL_HH}  CELL_RW={CELL_RW}  CELL_CY={CELL_CY}")
    print()

    sum_sq = 0.0
    max_err = 0.0
    for cell, sx, sy in samples:
        col, parity, row = _cell_features(cell)
        px, py = cell_to_screen(cell, rect, config.MAP_ORIGIN_X, config.MAP_ORIGIN_Y,
                                config.MAP_SCALE, scale_x=config.MAP_SCALE_X,
                                scale_y=config.MAP_SCALE_Y)
        ex, ey = px - sx, py - sy
        err = (ex**2 + ey**2) ** 0.5
        sum_sq += ex**2 + ey**2
        max_err = max(max_err, err)
        warn = "  <- MAL" if err > 5 else ""
        print(f"  celda {cell:>3} (row={row:>2},col={col:>2},par={parity}): "
              f"pred=({px},{py}) med=({sx},{sy}) err=({ex:+d},{ey:+d}) |{err:.1f}px|{warn}")

    rms = (sum_sq / len(samples)) ** 0.5
    print()
    print(f"  RMS={rms:.2f}px   MAX={max_err:.1f}px   (objetivo: RMS<2px, MAX<5px)")
    if rms < 2.0 and max_err < 5.0:
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
    print("  MODO AJUSTE — Minimos cuadrados (modelo isométrico canónico)")
    print("=" * 60)
    print()
    print("Introduce pares de medicion con Window Spy.")
    print("Pon el cursor en el CENTRO visual de la celda (el rombo isométrico).")
    print("Usa las coordenadas de la linea 'Screen:' de Window Spy.")
    print()
    print("IMPORTANTE: incluye celdas de filas PARES e IMPARES para calibrar")
    print("el offset de filas impares (CELL_HW). Recomendadas:")
    print("  0, 13, 27, 14, 270, 283, 532, 545, 559")
    print()
    print("Formato: <cell_id> <screen_x> <screen_y>")
    print("Ejemplo: 312 1359 719")
    print()
    print("Escribe 'listo' o deja la linea vacia cuando hayas terminado.")
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
        if not 0 <= cell <= 559:
            print("    -> cell_id debe estar entre 0 y 559.")
            continue
        col, parity, row = _cell_features(cell)
        cx = sx - rect.left
        cy = sy - rect.top
        samples.append((cell, col, parity, row, cx, cy, sx, sy))
        print(f"    -> celda {cell} (row={row},col={col},par={parity})  client=({cx},{cy})  OK")

    if len(samples) < 3:
        print("\nNecesitas al menos 3 muestras para el ajuste. Cancelando.")
        sys.exit(1)

    # Verificar cobertura de paridad
    parities = set(s[2] for s in samples)
    if len(parities) < 2:
        print("\nAVISO: todas las muestras son de filas del mismo tipo (par/impar).")
        print("  CELL_HW no se puede calibrar bien. Añade celdas de filas impares:")
        print("  Filas impares: 1,3,5... -> celdas 1,3,5,15,29,43...")

    rows_seen = [s[3] for s in samples]
    cols_seen = [s[1] for s in samples]
    if max(rows_seen) - min(rows_seen) < 8:
        print(f"\nAVISO: poca diversidad de filas (rango={max(rows_seen)-min(rows_seen)}). "
              f"Añade celdas en filas mas separadas para un ajuste robusto de CELL_HH.")
    if max(cols_seen) - min(cols_seen) < 5:
        print(f"\nAVISO: poca diversidad de columnas (rango={max(cols_seen)-min(cols_seen)}). "
              f"Añade celdas con col 0-2 o col 10-13 para un ajuste robusto de CELL_W.")

    print(f"\nAjustando con {len(samples)} muestras...")

    # screen_x - rect.left = MAP_ORIGIN_X + col*CELL_W + parity*CELL_HW + row*CELL_RW
    # screen_y - rect.top  = MAP_ORIGIN_Y + row*CELL_HH
    Ax = np.array([[1, col, parity, row] for (_, col, parity, row, cx, cy, sx, sy) in samples], float)
    bx = np.array([cx for (_, col, parity, row, cx, cy, sx, sy) in samples], float)
    Ay = np.array([[1, row, col] for (_, col, parity, row, cx, cy, sx, sy) in samples], float)
    by = np.array([cy for (_, col, parity, row, cx, cy, sx, sy) in samples], float)

    solx, *_ = np.linalg.lstsq(Ax, bx, rcond=None)
    soly, *_ = np.linalg.lstsq(Ay, by, rcond=None)
    NEW_OX, NEW_CW, NEW_HW, NEW_RW = solx
    NEW_OY, NEW_HH, NEW_CY = soly

    # Residuales
    print()
    print("--- Residuales por muestra ---")
    max_err = 0.0
    sum_sq = 0.0
    bad = False
    for (cell, col, parity, row, cx, cy, sx, sy) in samples:
        px_c = NEW_OX + col * NEW_CW + parity * NEW_HW + row * NEW_RW
        py_c = NEW_OY + row * NEW_HH + col * NEW_CY
        ex = px_c + rect.left - sx
        ey = py_c + rect.top  - sy
        err = (ex**2 + ey**2) ** 0.5
        max_err = max(max_err, err)
        sum_sq += ex**2 + ey**2
        warn = "  <- REMEDIR" if err > 5 else ""
        if err > 5:
            bad = True
        print(f"  celda {cell:>3} (row={row:>2},col={col:>2},par={parity}): "
              f"err=({ex:+.1f},{ey:+.1f})  |err|={err:.1f}px{warn}")

    rms = (sum_sq / len(samples)) ** 0.5
    print(f"\n  RMS={rms:.2f}px   MAX={max_err:.1f}px   (objetivo: RMS<2px, MAX<5px)")

    print()
    print("--- Coeficientes calculados ---")
    print(f"  MAP_ORIGIN_X={NEW_OX:.4f}  CELL_W={NEW_CW:.4f}  CELL_HW={NEW_HW:.4f}  CELL_RW={NEW_RW:.4f}")
    print(f"  MAP_ORIGIN_Y={NEW_OY:.4f}  CELL_HH={NEW_HH:.4f}  CELL_CY={NEW_CY:.4f}")
    print(f"  rect.left={rect.left}  rect.top={rect.top}")

    print()
    print("--- Pegar en input/coords.py ---")
    print(f"CELL_W:  float = {NEW_CW:.4f}")
    print(f"CELL_HW: float = {NEW_HW:.4f}")
    print(f"CELL_HH: float = {NEW_HH:.4f}")
    print(f"CELL_RW: float = {NEW_RW:.4f}")
    print(f"CELL_CY: float = {NEW_CY:.4f}")

    print()
    print("--- Pegar en config.py ---")
    print(f"MAP_ORIGIN_X: float = {NEW_OX:.4f}   # client_x celda 0 (rect.left={rect.left})")
    print(f"MAP_ORIGIN_Y: float = {NEW_OY:.4f}   # client_y celda 0 (rect.top={rect.top})")

    print()
    if rms > 2.0 or bad:
        print("AVISO: RMS alto o muestras con error >5px. Revisa las mediciones y vuelve a medir.")
    else:
        cells_str = " ".join(str(s[0]) for s in samples)
        print("OK — Calibracion correcta. Verifica visualmente con:")
        print(f"   python tools/calibrate.py {cells_str}")
        print("Y verifica automaticamente con:")
        print("   python tools/calibrate.py --verify")


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
