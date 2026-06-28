"""
Localización de la ventana de Dofus y obtención de su rect de área cliente.
Usa pygetwindow (instalado con pyautogui) como primera opción,
con fallback a win32gui si está disponible.
"""

from __future__ import annotations
from dataclasses import dataclass


@dataclass
class WindowRect:
    left: int
    top: int
    width: int
    height: int


def find_dofus_window(title_substr: str = "Dofus") -> WindowRect:
    """
    Busca la ventana de Dofus por subcadena de título y devuelve
    el rect del área cliente (sin bordes ni barra de título).
    Lanza RuntimeError si no encuentra ninguna ventana.
    """
    # Intentar win32gui primero — da las coordenadas de área cliente exactas
    try:
        import win32gui
        import win32con

        results: list[tuple[int, str]] = []

        def _enum_cb(hwnd, _):
            if win32gui.IsWindowVisible(hwnd):
                title = win32gui.GetWindowText(hwnd)
                if title_substr.lower() in title.lower():
                    results.append((hwnd, title))

        win32gui.EnumWindows(_enum_cb, None)

        if not results:
            raise RuntimeError(f"No se encontró ventana con '{title_substr}' en el título.")

        hwnd, title = results[0]
        print(f"[Window] Ventana encontrada: '{title}' hwnd={hwnd}")

        # Coordenadas del área cliente (sin barra de título ni bordes)
        left_client, top_client, right_client, bottom_client = win32gui.GetClientRect(hwnd)
        # GetClientRect da coordenadas relativas a la ventana — convertir a pantalla
        pt = win32gui.ClientToScreen(hwnd, (left_client, top_client))
        pt_br = win32gui.ClientToScreen(hwnd, (right_client, bottom_client))

        return WindowRect(
            left=pt[0],
            top=pt[1],
            width=pt_br[0] - pt[0],
            height=pt_br[1] - pt[1],
        )

    except ImportError:
        pass

    # Fallback: pygetwindow
    import pygetwindow as gw

    windows = gw.getWindowsWithTitle(title_substr)
    if not windows:
        raise RuntimeError(f"No se encontró ventana con '{title_substr}' en el título.")

    win = windows[0]
    print(f"[Window] Ventana encontrada (pygetwindow): '{win.title}'")
    return WindowRect(
        left=win.left,
        top=win.top,
        width=win.width,
        height=win.height,
    )
