"""Genera el logo de Material Shift: dos flechas en ciclo (azul -> verde) que reasignan
material entre pilas de acopio, sobre el mismo fondo azul profundo de SimA.

Produce en ..\\..\\Model\\recursos: icono.png (256 px), logo_64.png, logo_32.png, logo.svg
(no, solo PNG) e icono.ico (multi-tamaño). Se dibuja a 1024 px y se reduce con LANCZOS.
Uso:  Model\\python\\python.exe crear_icono.py
"""
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

RAIZ = Path(__file__).resolve().parents[2]
SALIDA = RAIZ / "Model" / "recursos"


def _hex(c):
    return tuple(int(c[i:i + 2], 16) for i in (1, 3, 5))


def _mezcla(c1, c2, t):
    a, b = _hex(c1), _hex(c2)
    return tuple(int(a[k] + (b[k] - a[k]) * t) for k in range(3))


def _fondo(tam):
    """Cuadrado redondeado con degradado diagonal (mismo azul que SimA) y brillo suave arriba."""
    fondo = Image.new("RGBA", (tam, tam))
    d = ImageDraw.Draw(fondo)
    for y in range(tam):
        d.line([(0, y), (tam, y)], fill=_mezcla("#0B2545", "#134B7A", y / tam) + (255,))
    brillo = Image.new("L", (tam, tam), 0)
    ImageDraw.Draw(brillo).ellipse((-tam * 0.3, -tam * 0.75, tam * 1.3, tam * 0.42), fill=34)
    brillo = brillo.filter(ImageFilter.GaussianBlur(tam * 0.06))
    fondo = Image.composite(Image.new("RGBA", (tam, tam), (255, 255, 255, 255)), fondo, brillo)
    mascara = Image.new("L", (tam, tam), 0)
    ImageDraw.Draw(mascara).rounded_rectangle((0, 0, tam - 1, tam - 1), radius=int(tam * 0.22), fill=255)
    img = Image.new("RGBA", (tam, tam), (0, 0, 0, 0))
    img.paste(fondo, (0, 0), mascara)
    return img, mascara


def _arco(capa, cx, cy, r, ancho, a0, a1, c0, c1, pasos=220):
    """Arco con degradado de color a lo largo del trazo (ángulos en grados, sentido horario)."""
    d = ImageDraw.Draw(capa)
    rr = ancho / 2
    for i in range(pasos + 1):
        t = i / pasos
        a = math.radians(a0 + (a1 - a0) * t)
        x, y = cx + r * math.cos(a), cy + r * math.sin(a)
        col = _mezcla(c0, c1, t) + (255,)
        d.ellipse((x - rr, y - rr, x + rr, y + rr), fill=col)


def _punta(capa, cx, cy, r, ancho, ang, color, largo):
    """Punta de flecha tangente al arco en el ángulo 'ang' (sentido horario)."""
    a = math.radians(ang)
    px, py = cx + r * math.cos(a), cy + r * math.sin(a)
    tx, ty = -math.sin(a), math.cos(a)          # tangente (horario)
    nx, ny = math.cos(a), math.sin(a)           # normal hacia afuera
    w = ancho * 1.25
    pts = [(px + tx * largo, py + ty * largo),
           (px + nx * w, py + ny * w),
           (px - nx * w, py - ny * w)]
    ImageDraw.Draw(capa).polygon(pts, fill=_hex(color) + (255,))


def _pila(d, cxp, base, ancho, alto, relleno, borde, grosor):
    """Pila de acopio: montículo de laderas rectas y cima redondeada (perfil 'campana' suave)."""
    pts = []
    n = 90
    for i in range(n + 1):
        u = -1 + 2 * i / n                      # -1..1
        y = (1 - u * u) ** 0.85                  # domo: laderas suaves, cima redondeada
        pts.append((cxp + u * ancho / 2, base - alto * y))
    d.polygon(pts, fill=relleno)
    d.line(pts, fill=borde, width=grosor, joint="curve")


def dibujar(tam=1024):
    img, mascara = _fondo(tam)
    capa = Image.new("RGBA", (tam, tam), (0, 0, 0, 0))
    cx = cy = tam / 2
    r = tam * 0.315
    ancho = tam * 0.062
    # Flecha superior: azul claro -> azul; flecha inferior: verde -> verde claro.
    _arco(capa, cx, cy, r, ancho, 200, 318, "#7CC4FF", "#2F8FE8")
    _punta(capa, cx, cy, r, ancho, 318, "#2F8FE8", tam * 0.085)
    _arco(capa, cx, cy, r, ancho, 20, 138, "#2BB673", "#8BE3A8")
    _punta(capa, cx, cy, r, ancho, 138, "#8BE3A8", tam * 0.085)

    # Tres pilas de acopio (de menor a mayor), blancas con contorno azul tenue.
    d = ImageDraw.Draw(capa)
    base = cy + tam * 0.125
    g = int(tam * 0.014)
    navy = (11, 37, 69, 255)
    # De atrás hacia adelante: la pila derecha y la izquierda quedan detrás de la central.
    _pila(d, cx + tam * 0.135, base, tam * 0.27, tam * 0.115, (190, 216, 242, 255), navy, g)
    _pila(d, cx - tam * 0.135, base, tam * 0.27, tam * 0.125, (206, 227, 248, 255), navy, g)
    _pila(d, cx, base, tam * 0.32, tam * 0.185, (244, 249, 255, 255), navy, g)
    # Granos de material en la pila central
    for (fx, fy) in [(-0.04, 0.065), (0.035, 0.060), (-0.075, 0.125), (0.0, 0.110), (0.075, 0.125)]:
        rx, ry = cx + tam * fx, base - tam * 0.185 + tam * fy
        rp = tam * 0.012
        d.ellipse((rx - rp, ry - rp, rx + rp, ry + rp), fill=(19, 75, 122, 255))
    # Línea de suelo
    d.rounded_rectangle((cx - tam * 0.29, base - g * 0.4, cx + tam * 0.29, base + g * 0.9), radius=g, fill=(255, 255, 255, 240))

    # Signos: menos (azul, arriba-izq.) y más (verde, abajo-der.) dentro de círculos
    def _badge(x, y, color, signo):
        rb = tam * 0.062
        d.ellipse((x - rb, y - rb, x + rb, y + rb), fill=_hex(color) + (255,), outline=(255, 255, 255, 255), width=int(tam * 0.012))
        l, e = tam * 0.032, int(tam * 0.017)
        d.line([(x - l, y), (x + l, y)], fill=(255, 255, 255, 255), width=e)
        if signo == "+":
            d.line([(x, y - l), (x, y + l)], fill=(255, 255, 255, 255), width=e)

    _badge(cx - tam * 0.215, cy - tam * 0.17, "#2F8FE8", "-")
    _badge(cx + tam * 0.215, cy + tam * 0.215, "#2BB673", "+")

    capa = capa.filter(ImageFilter.GaussianBlur(tam * 0.0008))
    sombra = Image.new("RGBA", (tam, tam), (0, 0, 0, 0))
    sombra.putalpha(capa.split()[3].filter(ImageFilter.GaussianBlur(tam * 0.012)).point(lambda v: int(v * 0.35)))
    img.alpha_composite(Image.composite(sombra, Image.new("RGBA", (tam, tam), (0, 0, 0, 0)), mascara), (0, int(tam * 0.008)))
    img.alpha_composite(Image.composite(capa, Image.new("RGBA", (tam, tam), (0, 0, 0, 0)), mascara))
    return img


def main():
    SALIDA.mkdir(parents=True, exist_ok=True)
    grande = dibujar(1024)
    grande.resize((256, 256), Image.LANCZOS).save(SALIDA / "icono.png")
    grande.resize((128, 128), Image.LANCZOS).save(SALIDA / "logo_128.png")
    grande.resize((64, 64), Image.LANCZOS).save(SALIDA / "logo_64.png")
    grande.resize((32, 32), Image.LANCZOS).save(SALIDA / "logo_32.png")
    grande.save(SALIDA / "icono.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print("Logo generado en", SALIDA)


if __name__ == "__main__":
    main()
