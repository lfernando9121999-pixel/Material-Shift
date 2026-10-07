"""Formatos regionales: fecha DD/MM/YYYY, números #,###.0 y porcentajes ##.##%.

El formato es propio del programa y no depende de la configuración regional de Windows.
"""
import math
import re
import unicodedata
from datetime import date, datetime

ARTICULOS = {
    "a", "al", "ante", "bajo", "con", "contra", "de", "del", "desde", "e", "el", "en",
    "entre", "hacia", "hasta", "la", "las", "lo", "los", "o", "para", "por", "sin",
    "sobre", "tras", "u", "un", "una", "unos", "unas", "y",
}

NODATO = "–"

# Formatos equivalentes para Excel
XL_ENTERO = "#,##0"
XL_UN_DECIMAL = "#,##0.0"
XL_PORCENTAJE = "0.00%"
XL_FECHA = "dd/mm/yyyy"


def _valido(x):
    if x is None:
        return False
    try:
        return not (isinstance(x, float) and math.isnan(x)) and not math.isinf(float(x))
    except (TypeError, ValueError):
        return False


def entero(x):
    return f"{float(x):,.0f}" if _valido(x) else NODATO


def decimal1(x):
    return f"{float(x):,.1f}" if _valido(x) else NODATO


def porcentaje(x):
    """x en fracción (0.7926 -> 79.26%)."""
    return f"{float(x) * 100:,.2f}%" if _valido(x) else NODATO


def fecha(d=None):
    d = d or date.today()
    if isinstance(d, datetime):
        d = d.date()
    return d.strftime("%d/%m/%Y")


def fecha_hora(d=None):
    d = d or datetime.now()
    return d.strftime("%d/%m/%Y %H:%M")


def nombre_propio(texto):
    """Mayúscula inicial en cada palabra, excepto artículos y preposiciones.

    Respeta siglas y códigos (KOM930, SimA, P&H4800) que ya contienen mayúsculas
    internas o dígitos.
    """
    palabras = str(texto).split(" ")
    salida = []
    for i, p in enumerate(palabras):
        if not p:
            salida.append(p)
            continue
        if any(c.isdigit() for c in p) or any(c.isupper() for c in p[1:]):
            salida.append(p)
        elif i > 0 and p.lower() in ARTICULOS:
            salida.append(p.lower())
        else:
            salida.append(p[:1].upper() + p[1:].lower())
    return " ".join(salida)


_INVALIDOS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVADOS = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)),
               *(f"lpt{i}" for i in range(1, 10))}


def nombre_archivo_seguro(texto, por_defecto="Escenario Sin Título"):
    """Convierte cualquier texto (con : , ; @ etc.) en un nombre de archivo válido en Windows."""
    t = unicodedata.normalize("NFC", str(texto or "")).strip()
    t = _INVALIDOS.sub("_", t)
    t = re.sub(r"\s+", " ", t).strip(" .")
    if not t or t.lower() in _RESERVADOS:
        return por_defecto
    return t[:150]


def sin_acentos(texto):
    t = unicodedata.normalize("NFKD", str(texto))
    return "".join(c for c in t if not unicodedata.combining(c))
