"""Portapapeles de Windows: texto, tabla con formato (HTML), imagen (PNG + DIB) y gráficos nativos de
PowerPoint (se arman con python-pptx y PowerPoint los copia como gráfico editable).

Todo con ctypes (sin dependencias adicionales). Las funciones devuelven True si la copia se realizó.
"""
import ctypes
import html
import io
import os
import subprocess
import tempfile
import threading
from ctypes import wintypes

CF_UNICODETEXT = 13
CF_DIB = 8
GMEM_MOVEABLE = 0x0002

_k32 = ctypes.windll.kernel32
_u32 = ctypes.windll.user32
_k32.GlobalAlloc.restype = wintypes.HGLOBAL
_k32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
_k32.GlobalLock.restype = wintypes.LPVOID
_k32.GlobalLock.argtypes = [wintypes.HGLOBAL]
_k32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
_u32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
_u32.SetClipboardData.restype = wintypes.HANDLE
_u32.OpenClipboard.argtypes = [wintypes.HWND]
_u32.RegisterClipboardFormatW.argtypes = [wintypes.LPCWSTR]
_u32.RegisterClipboardFormatW.restype = wintypes.UINT


def _global(datos):
    h = _k32.GlobalAlloc(GMEM_MOVEABLE, len(datos))
    p = _k32.GlobalLock(h)
    ctypes.memmove(p, datos, len(datos))
    _k32.GlobalUnlock(h)
    return h


def _abrir():
    for _ in range(10):                      # otro programa puede tener abierto el portapapeles
        if _u32.OpenClipboard(None):
            return True
        _k32.Sleep(30)
    return False


def poner(formatos):
    """formatos: [(id_formato | nombre registrado, bytes)]. Reemplaza el contenido del portapapeles."""
    if not _abrir():
        return False
    try:
        _u32.EmptyClipboard()
        for f, datos in formatos:
            if isinstance(f, str):
                f = _u32.RegisterClipboardFormatW(f)
            _u32.SetClipboardData(f, _global(datos))
        return True
    finally:
        _u32.CloseClipboard()


def _texto_bytes(texto):
    return (texto.replace("\r\n", "\n").replace("\n", "\r\n") + "\0").encode("utf-16-le")


def copiar_texto(texto):
    return poner([(CF_UNICODETEXT, _texto_bytes(texto))])


def _cf_html(fragmento):
    """Encabezado CF_HTML con los desplazamientos en bytes (UTF-8)."""
    plantilla = ("Version:0.9\r\nStartHTML:{0:010d}\r\nEndHTML:{1:010d}\r\nStartFragment:{2:010d}\r\n"
                 "EndFragment:{3:010d}\r\n")
    pre = "<html><head><meta charset=\"utf-8\"></head><body><!--StartFragment-->"
    post = "<!--EndFragment--></body></html>"
    vacio = plantilla.format(0, 0, 0, 0)
    inicio_html = len(vacio.encode("utf-8"))
    inicio_frag = inicio_html + len(pre.encode("utf-8"))
    fin_frag = inicio_frag + len(fragmento.encode("utf-8"))
    fin_html = fin_frag + len(post.encode("utf-8"))
    return (plantilla.format(inicio_html, fin_html, inicio_frag, fin_frag) + pre + fragmento + post).encode("utf-8")


def tabla_html(titulos, filas, alineaciones=None, estilos=None, fondo_cab="#F1F3F6"):
    """Tabla HTML con estilos en línea (Excel, Word y PowerPoint conservan el formato al pegar).

    filas: listas de textos; estilos: por fila {"fondo": "#RRGGBB", "negrita": bool, "color": "#..."}."""
    alineaciones = alineaciones or ["left"] * len(titulos)
    estilos = estilos or [{}] * len(filas)
    base = "font-family:'Segoe UI',Arial;font-size:9pt;border:1px solid #D6DCE2;padding:3px 8px;"
    partes = ["<table style=\"border-collapse:collapse;\">", "<tr>"]
    for t in titulos:
        partes.append(f"<th style=\"{base}background:{fondo_cab};font-weight:600;text-align:center;\">"
                      f"{html.escape(str(t))}</th>")
    partes.append("</tr>")
    for fila, est in zip(filas, estilos):
        est = est or {}
        extra = ""
        if est.get("fondo"):
            extra += f"background:{est['fondo']};"
        if est.get("negrita"):
            extra += "font-weight:600;"
        if est.get("color"):
            extra += f"color:{est['color']};"
        partes.append("<tr>")
        for v, al in zip(fila, alineaciones):
            al = {"e": "right", "w": "left", "center": "center"}.get(al, al)
            partes.append(f"<td style=\"{base}{extra}text-align:{al};white-space:nowrap;\">{html.escape(str(v))}</td>")
        partes.append("</tr>")
    partes.append("</table>")
    return "".join(partes)


def copiar_html(fragmento, texto):
    return poner([(CF_UNICODETEXT, _texto_bytes(texto)), ("HTML Format", _cf_html(fragmento))])


def copiar_imagen(img, dpi=192):
    """Imagen PIL: PNG (con resolución, Office la respeta) y mapa de bits DIB."""
    png = io.BytesIO()
    img.save(png, "PNG", dpi=(dpi, dpi))
    bmp = io.BytesIO()
    img.convert("RGB").save(bmp, "BMP", dpi=(dpi, dpi))
    return poner([("PNG", png.getvalue()), (CF_DIB, bmp.getvalue()[14:])])


def tsv(titulos, filas):
    return "\n".join(["\t".join(str(t).replace("\n", " ") for t in titulos)] +
                     ["\t".join(str(v).strip() for v in f) for f in filas])


# ----------------------------------------------------------------------------------------
# Gráfico como formato de PowerPoint (gráfico nativo y editable)
# ----------------------------------------------------------------------------------------
_SCRIPT_PPT = r"""
$ErrorActionPreference = 'Stop'
$app = New-Object -ComObject PowerPoint.Application
$abiertas = $app.Presentations.Count
$p = $app.Presentations.Open('{ruta}', -1, 0, 0)
$p.Slides.Item(1).Shapes.Item(1).Copy()
$p.Close()
if ($abiertas -eq 0 -and $app.Presentations.Count -eq 0) {{ $app.Quit() }}
"""


def copiar_pptx_en_segundo_plano(ruta_pptx, al_terminar=None):
    """Abre la lámina con PowerPoint (sin ventana) y copia su gráfico al portapapeles. Se ejecuta en un hilo;
    al_terminar(ok, mensaje) se invoca al finalizar (desde el hilo: usar after() para tocar la interfaz)."""
    def trabajo():
        ok, msg = False, ""
        try:
            script = _SCRIPT_PPT.format(ruta=ruta_pptx.replace("'", "''"))
            r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                                "-Command", script], capture_output=True, text=True, timeout=90,
                               creationflags=0x08000000)
            ok = r.returncode == 0
            msg = (r.stderr or r.stdout or "").strip()[:300]
        except Exception as e:  # noqa
            msg = str(e)
        finally:
            try:
                os.remove(ruta_pptx)
            except OSError:
                pass
        if al_terminar:
            al_terminar(ok, msg)
    threading.Thread(target=trabajo, daemon=True).start()


def ruta_temporal(sufijo=".pptx"):
    fd, ruta = tempfile.mkstemp(prefix="sima_", suffix=sufijo)
    os.close(fd)
    return ruta
