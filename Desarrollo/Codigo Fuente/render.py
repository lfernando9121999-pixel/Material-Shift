"""Dibujo de tablas y gráficos como imagen (PIL), sin capturar la pantalla: sirve aunque la tabla tenga
desplazamiento o el gráfico esté parcialmente oculto. Se usa para «Copiar … como Imagen»."""
import os

from tema import T

ESCALA = 2                       # imágenes nítidas al pegarlas en Office


def _ruta_fuente(familia, negrita=False):
    base = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
    f = (familia or "").lower()
    if "semibold" in f or negrita:
        candidatos = ["seguisb.ttf", "segoeuib.ttf"]
    elif "consolas" in f:
        candidatos = ["consola.ttf"]
    else:
        candidatos = ["segoeui.ttf"]
    for c in candidatos + ["segoeui.ttf", "arial.ttf"]:
        r = os.path.join(base, c)
        if os.path.isfile(r):
            return r
    return None


_cache = {}


def fuente_pil(tkfuente, escala=ESCALA):
    """ImageFont equivalente a una fuente de Tk (familia, tamaño y peso)."""
    from PIL import ImageFont
    try:
        a = tkfuente.actual() if hasattr(tkfuente, "actual") else T.root.tk.call("font", "actual", tkfuente)
        if not isinstance(a, dict):
            a = dict(zip(a[::2], a[1::2]))
            a = {k.lstrip("-"): v for k, v in a.items()}
    except Exception:
        a = {"family": "Segoe UI", "size": 9, "weight": "normal"}
    familia, tam = a.get("family", "Segoe UI"), int(a.get("size", 9))
    px = abs(tam) if tam < 0 else tam * 96 / 72
    clave = (familia, round(px * escala), a.get("weight") == "bold")
    if clave not in _cache:
        ruta = _ruta_fuente(familia, a.get("weight") == "bold")
        try:
            _cache[clave] = ImageFont.truetype(ruta, clave[1]) if ruta else ImageFont.load_default()
        except Exception:
            _cache[clave] = ImageFont.load_default()
    return _cache[clave]


def _rgb(color, widget=None):
    if not color:
        return None
    try:
        r, g, b = (widget or T.root).winfo_rgb(color)
        return (r // 257, g // 257, b // 257)
    except Exception:
        return None


# Anclas de Tk → anclas de PIL (horizontal + vertical)
_ANCLA = {"nw": "la", "n": "ma", "ne": "ra", "w": "lm", "center": "mm", "e": "rm", "sw": "ld", "s": "md",
          "se": "rd"}


def lienzo_a_imagen(lienzo, escala=ESCALA):
    """Reproduce los elementos de un Canvas (rectángulos, líneas, óvalos, polígonos y textos) en una imagen."""
    from PIL import Image, ImageDraw
    w, h = max(1, lienzo.winfo_width()), max(1, lienzo.winfo_height())
    fondo = _rgb(lienzo.cget("background"), lienzo) or (255, 255, 255)
    img = Image.new("RGB", (w * escala, h * escala), fondo)
    d = ImageDraw.Draw(img)
    for item in lienzo.find_all():
        if lienzo.itemcget(item, "state") == "hidden" or "tip" in lienzo.gettags(item):
            continue
        tipo = lienzo.type(item)
        c = [v * escala for v in lienzo.coords(item)]
        if not c:
            continue
        try:
            if tipo in ("rectangle", "oval"):
                fill = _rgb(lienzo.itemcget(item, "fill"), lienzo)
                out = _rgb(lienzo.itemcget(item, "outline"), lienzo)
                caja = [min(c[0], c[2]), min(c[1], c[3]), max(c[0], c[2]), max(c[1], c[3])]
                ancho = max(1, int(float(lienzo.itemcget(item, "width") or 1) * escala)) if out else 0
                (d.rectangle if tipo == "rectangle" else d.ellipse)(caja, fill=fill, outline=out, width=ancho)
            elif tipo == "line":
                fill = _rgb(lienzo.itemcget(item, "fill"), lienzo)
                ancho = max(1, int(float(lienzo.itemcget(item, "width") or 1) * escala))
                guion = lienzo.itemcget(item, "dash")
                pts = list(zip(c[::2], c[1::2]))
                if guion:
                    _linea_guion(d, pts, fill, ancho, escala)
                else:
                    d.line(pts, fill=fill, width=ancho)
            elif tipo == "polygon":
                d.polygon(list(zip(c[::2], c[1::2])), fill=_rgb(lienzo.itemcget(item, "fill"), lienzo),
                          outline=_rgb(lienzo.itemcget(item, "outline"), lienzo))
            elif tipo == "text":
                texto = lienzo.itemcget(item, "text")
                if not texto:
                    continue
                f = fuente_pil(lienzo.itemcget(item, "font"), escala)
                fill = _rgb(lienzo.itemcget(item, "fill"), lienzo) or (0, 0, 0)
                ancla = _ANCLA.get(lienzo.itemcget(item, "anchor"), "mm")
                angulo = float(lienzo.itemcget(item, "angle") or 0)
                if angulo:
                    _texto_rotado(img, c[0], c[1], texto, f, fill, ancla, angulo)
                else:
                    d.multiline_text((c[0], c[1]), texto, font=f, fill=fill, anchor=ancla) if "\n" in texto \
                        else d.text((c[0], c[1]), texto, font=f, fill=fill, anchor=ancla)
        except Exception:
            continue
    return img


def _linea_guion(d, pts, fill, ancho, escala):
    import math
    paso = 4 * escala
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        largo = math.hypot(x1 - x0, y1 - y0)
        if not largo:
            continue
        n = int(largo // paso)
        for k in range(0, n, 2):
            a, b = k * paso / largo, min(1.0, (k + 1) * paso / largo)
            d.line([(x0 + (x1 - x0) * a, y0 + (y1 - y0) * a), (x0 + (x1 - x0) * b, y0 + (y1 - y0) * b)],
                   fill=fill, width=ancho)


def _texto_rotado(img, x, y, texto, fuente, fill, ancla, angulo):
    from PIL import Image, ImageDraw
    caja = fuente.getbbox(texto)
    tw, th = caja[2] - caja[0] + 4, caja[3] - caja[1] + 4
    capa = Image.new("RGBA", (tw, th), (0, 0, 0, 0))
    ImageDraw.Draw(capa).text((2 - caja[0], 2 - caja[1]), texto, font=fuente, fill=fill)
    rot = capa.rotate(angulo, expand=True)
    dx = rot.width if ancla[0] == "r" else (rot.width // 2 if ancla[0] == "m" else 0)
    img.paste(rot, (int(x - dx), int(y)), rot)


def tabla_a_imagen(titulos, filas, anclas, estilos=None, escala=ESCALA, ancho_min=None):
    """Imagen de una tabla: encabezado centrado, filas con su fondo (grupos/total) y alineación.

    estilos: por fila {"fondo": color, "negrita": bool, "color": color, "sangria": n}."""
    from PIL import Image, ImageDraw
    p = T.p
    fn, fb = fuente_pil(T.f["tabla"], escala), fuente_pil(T.f["tabla_n"], escala)
    pad, alto = 10 * escala, 22 * escala
    estilos = estilos or [{}] * len(filas)

    def medir(t, f):
        b = f.getbbox(str(t)) if str(t) else (0, 0, 0, 0)
        return b[2] - b[0]
    anchos = []
    for j, t in enumerate(titulos):
        w = medir(t, fb)
        for fila, est in zip(filas, estilos):
            if j < len(fila):
                extra = (est or {}).get("sangria", 0) * 14 * escala if j == 0 else 0
                w = max(w, medir(fila[j], fb if (est or {}).get("negrita") else fn) + extra)
        anchos.append(w + 2 * pad + 6 * escala)
    W = sum(anchos) + 2
    if ancho_min:
        W = max(W, ancho_min * escala)
    H = alto * (len(filas) + 1) + 2
    img = Image.new("RGB", (W, H), _rgb(p["panel"]) or (255, 255, 255))
    d = ImageDraw.Draw(img)
    borde = _rgb(p["borde"])
    d.rectangle([0, 0, W - 1, alto], fill=_rgb(p["cab"]))
    x = 1
    for j, t in enumerate(titulos):
        d.text((x + anchos[j] / 2, alto / 2), str(t), font=fb, fill=_rgb(p["cab_txt"]), anchor="mm")
        x += anchos[j]
    for i, (fila, est) in enumerate(zip(filas, estilos), start=1):
        est = est or {}
        y = alto * i
        fondo = _rgb(est.get("fondo")) if est.get("fondo") else None
        if fondo:
            d.rectangle([1, y, W - 2, y + alto], fill=fondo)
        d.line([(1, y), (W - 2, y)], fill=_rgb(p["rejilla"]) or borde)
        color = _rgb(est.get("color")) or _rgb(p["texto"])
        f = fb if est.get("negrita") else fn
        x = 1
        for j, v in enumerate(fila[:len(anchos)]):
            a = anclas[j] if j < len(anclas) else "w"
            if a == "e":
                d.text((x + anchos[j] - pad, y + alto / 2), str(v), font=f, fill=color, anchor="rm")
            elif a == "center":
                d.text((x + anchos[j] / 2, y + alto / 2), str(v), font=f, fill=color, anchor="mm")
            else:
                extra = est.get("sangria", 0) * 14 * escala if j == 0 else 0
                d.text((x + pad + extra, y + alto / 2), str(v), font=f, fill=color, anchor="lm")
            x += anchos[j]
    d.rectangle([0, 0, W - 1, H - 1], outline=borde)
    return img
