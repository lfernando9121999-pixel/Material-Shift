"""Explorador de archivos de Windows con tamaño medio: se abre centrado sobre el programa (en su misma
pantalla), nunca a pantalla completa, y se puede mover y cambiar de tamaño.

Windows recuerda el último tamaño del cuadro de diálogo (incluso maximizado); un hilo auxiliar lo detecta
apenas se crea, lo mantiene transparente mientras lo ubica y le da un tamaño cómodo, y luego lo muestra
(sin el salto visible desde la posición anterior).
"""
import ctypes
import os
import threading
import time
from ctypes import wintypes
from tkinter import filedialog

from tema import area_trabajo

_u32 = ctypes.windll.user32
_EnumProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
_u32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
_u32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                              wintypes.UINT]
_u32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
_u32.GetWindowLongW.restype = ctypes.c_long
_u32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
_u32.SetLayeredWindowAttributes.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_ubyte, wintypes.DWORD]
_GWL_EXSTYLE, _WS_EX_LAYERED, _LWA_ALPHA = -20, 0x80000, 0x2


def _dialogos_propios():
    """Cuadros de diálogo (#32770) de este proceso, visibles u ocultos (recién creados)."""
    pid = os.getpid()
    encontrados = []
    clase = ctypes.create_unicode_buffer(64)

    def cb(hwnd, _l):
        p = wintypes.DWORD()
        _u32.GetWindowThreadProcessId(hwnd, ctypes.byref(p))
        if p.value == pid:
            _u32.GetClassNameW(hwnd, clase, 64)
            if clase.value == "#32770":
                encontrados.append(hwnd)
        return True
    _u32.EnumWindows(_EnumProc(cb), 0)
    return encontrados


def _transparente(h, si, estilo_original=None):
    try:
        if si:
            _u32.SetWindowLongW(h, _GWL_EXSTYLE, _u32.GetWindowLongW(h, _GWL_EXSTYLE) | _WS_EX_LAYERED)
            _u32.SetLayeredWindowAttributes(h, 0, 0, _LWA_ALPHA)
        else:
            _u32.SetLayeredWindowAttributes(h, 0, 255, _LWA_ALPHA)
            if estilo_original is not None and not estilo_original & _WS_EX_LAYERED:
                _u32.SetWindowLongW(h, _GWL_EXSTYLE, estilo_original)
    except Exception:  # noqa
        pass


def _vigilar(previos, rect, fin):
    ocultos = {}                       # hwnd -> estilo extendido original
    limite = time.time() + 8
    try:
        while time.time() < limite and not fin.is_set():
            for h in _dialogos_propios():
                if h in previos:
                    continue
                if h not in ocultos:   # recién creado: invisible hasta quedar en su lugar
                    ocultos[h] = _u32.GetWindowLongW(h, _GWL_EXSTYLE)
                    _transparente(h, True)
                if not _u32.IsWindowVisible(h):
                    continue
                if _u32.IsZoomed(h):
                    _u32.ShowWindow(h, 9)                   # restaurar (no a pantalla completa)
                x, y, w, hh = rect
                _u32.SetWindowPos(h, None, x, y, w, hh, 0x0004 | 0x0010)     # SWP_NOZORDER | SWP_NOACTIVATE
                time.sleep(0.03)                            # el diálogo termina de acomodarse a ese tamaño
                _u32.SetWindowPos(h, None, x, y, w, hh, 0x0004 | 0x0010)
                return
            time.sleep(0.005)
    finally:
        for h, estilo in ocultos.items():                   # siempre vuelve a ser visible
            _transparente(h, False, estilo)


def _rect(padre):
    top = padre.winfo_toplevel()
    cx = top.winfo_rootx() + top.winfo_width() // 2
    cy = top.winfo_rooty() + top.winfo_height() // 2
    x0, y0, x1, y1 = area_trabajo(cx, cy, top)
    w = int(max(860, min(1180, (x1 - x0) * 0.60)))
    h = int(max(540, min(760, (y1 - y0) * 0.70)))
    x = max(x0, min(cx - w // 2, x1 - w))
    y = max(y0, min(cy - h // 2, y1 - h))
    return x, y, w, h


def _con_tamano(funcion, **kw):
    padre = kw.get("parent")
    if padre is None:
        return funcion(**kw)
    previos = set(_dialogos_propios())
    fin = threading.Event()
    hilo = threading.Thread(target=_vigilar, args=(previos, _rect(padre), fin), daemon=True)
    hilo.start()
    try:
        return funcion(**kw)
    finally:
        fin.set()


def abrir(**kw):
    return _con_tamano(filedialog.askopenfilename, **kw)


def abrir_varios(**kw):
    return _con_tamano(filedialog.askopenfilenames, **kw)


def guardar(**kw):
    return _con_tamano(filedialog.asksaveasfilename, **kw)
