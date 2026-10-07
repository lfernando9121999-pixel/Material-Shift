"""Prueba del menú contextual → portapapeles en la app real (vía CDP).
Requiere la app abierta con depuración y una corrida calculada. Verifica:
  - gráfico: «Copiar como imagen» deja una imagen (PNG + mapa de bits);
  - tabla: «Copiar como imagen» (captura de la parte visible) y «Copiar con formato» (HTML).
"""
import ctypes
import time

import cdp

CF_BITMAP, CF_DIB, CF_UNICODETEXT = 2, 8, 13
u = ctypes.windll.user32


def formatos():
    for _ in range(20):
        if u.OpenClipboard(None):
            break
        time.sleep(0.05)
    try:
        f, out = 0, []
        while True:
            f = u.EnumClipboardFormats(f)
            if not f:
                break
            buf = ctypes.create_unicode_buffer(64)
            n = u.GetClipboardFormatNameW(f, buf, 64)
            out.append(buf.value if n else {CF_BITMAP: "Bitmap", CF_DIB: "DIB", CF_UNICODETEXT: "Texto"}.get(f, str(f)))
        return out
    finally:
        u.CloseClipboard()


d, s = cdp.pagina("Dashboard"), cdp.pagina("Barra lateral")
d.click_sel("[data-view=dashboard]")
time.sleep(0.4)
x, y = d.centro("#chMat")
d.click(x, y, "right")
d.click_sel("#cm [data-cm=img]")
time.sleep(1.5)
f = formatos()
print("Gráfico como imagen:", "OK" if "PNG" in f and ("DIB" in f or "Bitmap" in f) else "FALLA", "|", s.js("S.status"), "|", f)

d.click_sel("[data-view=tabla]")
time.sleep(0.6)
x, y = d.centro("table.dt")
d.click(x, y, "right")
d.click_sel("#cm [data-cm=timg]")
time.sleep(2)
f = formatos()
print("Tabla como imagen:", "OK" if "PNG" in f else "FALLA", "|", s.js("S.status"), "|", f)

d.click(x, y, "right")
d.click_sel("#cm [data-cm=html]")
time.sleep(1)
f = formatos()
print("Tabla con formato:", "OK" if "HTML Format" in f and "Texto" in f else "FALLA", "|", s.js("S.status"), "|", f)
d.click_sel("[data-view=dashboard]")
