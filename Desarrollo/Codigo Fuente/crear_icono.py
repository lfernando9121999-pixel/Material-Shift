"""Genera el logo de SimA: curvas de nivel (topografía minera) sobre fondo azul profundo.

Produce recursos/icono.png (256 px), recursos/logo_64.png y recursos/icono.ico (multi-tamaño).
Las curvas se trazan con 'marching squares' sobre un relieve suave de dos cerros.
"""
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

BASE = Path(__file__).resolve().parent / "recursos"


def _relieve(x, y):
    """Relieve normalizado 0..1: cerro principal + cerro secundario + leve pendiente."""
    g1 = math.exp(-(((x - 0.60) / 0.24) ** 2 + ((y - 0.56) / 0.20) ** 2))
    g2 = 0.62 * math.exp(-(((x - 0.30) / 0.15) ** 2 + ((y - 0.34) / 0.13) ** 2))
    return 0.92 * g1 + g2 * 0.95 + 0.06 * (1 - y)


def _interp(a, b, va, vb, nivel):
    t = 0.5 if vb == va else (nivel - va) / (vb - va)
    return (a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1]))


def _isolineas(n, nivel):
    """Segmentos de la isolínea 'nivel' en una grilla n x n de [0,1]^2."""
    paso = 1.0 / (n - 1)
    v = [[_relieve(i * paso, j * paso) for i in range(n)] for j in range(n)]
    segs = []
    for j in range(n - 1):
        for i in range(n - 1):
            p = [(i * paso, j * paso), ((i + 1) * paso, j * paso),
                 ((i + 1) * paso, (j + 1) * paso), (i * paso, (j + 1) * paso)]
            val = [v[j][i], v[j][i + 1], v[j + 1][i + 1], v[j + 1][i]]
            pts = []
            for k in range(4):
                a, b = k, (k + 1) % 4
                if (val[a] >= nivel) != (val[b] >= nivel):
                    pts.append(_interp(p[a], p[b], val[a], val[b], nivel))
            if len(pts) == 2:
                segs.append(pts)
            elif len(pts) == 4:
                segs += [pts[:2], pts[2:]]
    return segs


def _mezcla(c1, c2, t):
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    return tuple(int(a[k] + (b[k] - a[k]) * t) for k in range(3))


def dibujar(tam=1024):
    img = Image.new("RGBA", (tam, tam), (0, 0, 0, 0))
    # fondo con degradado vertical
    fondo = Image.new("RGBA", (tam, tam))
    d = ImageDraw.Draw(fondo)
    for y in range(tam):
        d.line([(0, y), (tam, y)], fill=_mezcla("#0B2545", "#134B7A", y / tam) + (255,))
    mascara = Image.new("L", (tam, tam), 0)
    ImageDraw.Draw(mascara).rounded_rectangle((0, 0, tam - 1, tam - 1), radius=int(tam * 0.22), fill=255)
    img.paste(fondo, (0, 0), mascara)

    capa = Image.new("RGBA", (tam, tam), (0, 0, 0, 0))
    dc = ImageDraw.Draw(capa)
    margen = tam * 0.10
    util = tam - 2 * margen
    niveles = [0.14 + k * 0.095 for k in range(9)]
    for k, nivel in enumerate(niveles):
        t = k / (len(niveles) - 1)
        color = _mezcla("#3E8FC7", "#E8F4FF", t) + (255,)
        ancho = max(2, int(tam * (0.010 if k % 3 else 0.016)))     # curvas índice más gruesas
        r = ancho / 2
        for (a, b) in _isolineas(260, nivel):
            pa = (margen + a[0] * util, margen + a[1] * util)
            pb = (margen + b[0] * util, margen + b[1] * util)
            dc.line([pa, pb], fill=color, width=ancho)
            for (x, y) in (pa, pb):                    # extremos redondeados: trazo continuo
                dc.ellipse((x - r, y - r, x + r, y + r), fill=color)
    capa = capa.filter(ImageFilter.GaussianBlur(tam * 0.0012))
    img.alpha_composite(Image.composite(capa, Image.new("RGBA", (tam, tam), (0, 0, 0, 0)), mascara))

    # cumbre: punto de acento
    cx, cy = margen + 0.60 * util, margen + 0.555 * util
    r = tam * 0.032
    ImageDraw.Draw(img).ellipse((cx - r, cy - r, cx + r, cy + r), fill="#F78166",
                                outline="#FFFFFF", width=int(tam * 0.008))
    return img


def main():
    BASE.mkdir(parents=True, exist_ok=True)
    grande = dibujar(1024)
    grande.resize((256, 256), Image.LANCZOS).save(BASE / "icono.png")
    grande.resize((64, 64), Image.LANCZOS).save(BASE / "logo_64.png")
    grande.resize((32, 32), Image.LANCZOS).save(BASE / "logo_32.png")
    grande.save(BASE / "icono.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64),
                                           (128, 128), (256, 256)])
    print("Logo generado en", BASE)


if __name__ == "__main__":
    main()
