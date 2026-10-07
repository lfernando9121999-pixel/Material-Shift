"""Lectura robusta de CSV: codificación, separador, decimal, encabezados y lectura por bloques.

Pensado para archivos de hasta varios GB, con formatos regionales distintos
(coma, punto y coma, tabulación) y codificaciones habituales de la industria
(UTF-8, UTF-16, Windows-1252, Big5 y otras).
"""
import codecs
import csv
import io
import os
import re
import unicodedata
from collections import Counter
from perezoso import np, pd


EXCLUIDOS = {"o_poliretenido.csv", "o_poliretsolapamiento.csv", "o_sinorigen.csv"}

_BOMS = [
    (codecs.BOM_UTF32_LE, "utf-32"), (codecs.BOM_UTF32_BE, "utf-32"),
    (codecs.BOM_UTF8, "utf-8-sig"),
    (codecs.BOM_UTF16_LE, "utf-16"), (codecs.BOM_UTF16_BE, "utf-16"),
]
_CJK = ("cp950", "big5hkscs", "gb18030", "cp932", "cp949")


class ErrorLectura(Exception):
    """Error legible para el usuario."""


class Cancelado(Exception):
    pass


def es_archivo_modelo(nombre):
    n = os.path.basename(nombre).lower()
    return n.startswith("o_") and n.endswith(".csv") and n not in EXCLUIDOS


# ----------------------------------------------------------------------------
# Texto y encabezados
# ----------------------------------------------------------------------------
def corregir_texto(s):
    """Repara texto UTF-8 mal interpretado como ANSI (p. ej. 'CarguÃ­o' -> 'Carguío')."""
    s = str(s).replace("﻿", "").strip()
    if "Ã" in s or "Â" in s:
        for enc in ("cp1252", "latin-1"):
            try:
                return s.encode(enc).decode("utf-8")
            except (UnicodeEncodeError, UnicodeDecodeError):
                continue
    return s


def norm(s):
    """Clave de comparación: sin acentos, minúsculas, sin unidades entre paréntesis."""
    s = corregir_texto(s)
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"\(.*?\)", " ", s)
    s = re.sub(r"[^0-9a-zA-Z&]+", " ", s)
    return re.sub(r"\s+", " ", s).strip().lower()


def es_vacio(nombre):
    n = norm(nombre)
    n = re.sub(r"\s*\d+$", "", n)
    return n == "" or n.startswith("vacio") or n.startswith("unnamed")


def nombre_unico(nombres):
    vistos = Counter()
    salida = []
    for n in nombres:
        vistos[n] += 1
        salida.append(n if vistos[n] == 1 else f"{n} ({vistos[n]})")
    return salida


# ----------------------------------------------------------------------------
# Detección de formato
# ----------------------------------------------------------------------------
def detectar_codificacion(ruta, muestra=1 << 20):
    with open(ruta, "rb") as f:
        b = f.read(muestra)
    for bom, enc in _BOMS:
        if b.startswith(bom):
            return enc
    if not b:
        return "utf-8"
    try:
        codecs.getincrementaldecoder("utf-8")().decode(b, final=False)
        return "utf-8"
    except UnicodeDecodeError:
        pass
    arr = np.frombuffer(b, dtype=np.uint8)
    alto = arr >= 0x80
    n_alto = int(alto.sum())
    pares = int((alto[:-1] & alto[1:]).sum())
    if n_alto and pares / n_alto > 0.35:
        for enc in _CJK:
            try:
                codecs.getincrementaldecoder(enc)().decode(b, final=False)
                return enc
            except (UnicodeDecodeError, LookupError):
                continue
    try:
        codecs.getincrementaldecoder("cp1252")().decode(b, final=False)
        return "cp1252"
    except UnicodeDecodeError:
        return "latin-1"


def detectar_formato(ruta, enc):
    """Devuelve (delimitador, decimal)."""
    with open(ruta, "rb") as f:
        raw = f.read(256 * 1024)
    truncado = len(raw) == 256 * 1024
    txt = raw.decode(enc, errors="replace").lstrip("﻿")
    lineas = [l for l in txt.splitlines() if l.strip()]
    if truncado and len(lineas) > 1:
        lineas = lineas[:-1]
    lineas = lineas[:40]
    if not lineas:
        return ",", "."
    mejor, clave_mejor = ",", (False, 0)
    for d in (",", ";", "\t", "|"):
        conteos = [l.count(d) for l in lineas]
        moda, veces = Counter(conteos).most_common(1)[0]
        consistente = moda > 0 and veces / len(conteos) >= 0.8
        clave = (consistente, moda)
        if clave > clave_mejor:
            mejor, clave_mejor = d, clave
    if clave_mejor == (False, 0):
        try:
            mejor = csv.Sniffer().sniff("\n".join(lineas[:10]), delimiters=",;\t|").delimiter
        except csv.Error:
            mejor = ","
    decimal = "."
    if mejor != ",":
        coma = punto = 0
        for l in lineas[1:]:
            for tok in l.split(mejor):
                tok = tok.strip().strip('"')
                if re.fullmatch(r"-?\d+,\d+", tok):
                    coma += 1
                elif re.fullmatch(r"-?\d+\.\d+", tok):
                    punto += 1
        if coma > punto:
            decimal = ","
    return mejor, decimal


def leer_encabezado(ruta, enc, delim):
    with open(ruta, "rb") as f:
        raw = f.read(256 * 1024)
    txt = raw.decode(enc, errors="replace").lstrip("﻿")
    primera = io.StringIO(txt)
    try:
        fila = next(csv.reader(primera, delimiter=delim))
    except StopIteration:
        raise ErrorLectura("El archivo está vacío.")
    return [corregir_texto(c) for c in fila]


def contar_filas(ruta):
    n = 0
    ultimo = b""
    with open(ruta, "rb") as f:
        while True:
            bloque = f.read(8 << 20)
            if not bloque:
                break
            n += bloque.count(b"\n")
            ultimo = bloque[-1:]
    if ultimo and ultimo != b"\n":
        n += 1
    return max(0, n - 1)


def inspeccionar(ruta, con_filas=True):
    """Metadatos livianos de un CSV (no carga los datos)."""
    if not os.path.isfile(ruta):
        raise ErrorLectura(f"No se encontró el archivo: {ruta}")
    enc = detectar_codificacion(ruta)
    delim, dec = detectar_formato(ruta, enc)
    cols = leer_encabezado(ruta, enc, delim)
    if len(cols) < 2:
        raise ErrorLectura(
            f"No se pudo identificar el separador de columnas de «{os.path.basename(ruta)}».")
    meta = {
        "nombre": os.path.basename(ruta),
        "ruta": os.path.abspath(ruta),
        "tamano": os.path.getsize(ruta),
        "codificacion": enc,
        "delimitador": delim,
        "decimal": dec,
        "columnas": len(cols),
        "encabezados": cols,
        "filas": contar_filas(ruta) if con_filas else None,
    }
    return meta


# ----------------------------------------------------------------------------
# Lectura con pandas
# ----------------------------------------------------------------------------
def _opciones(meta):
    return dict(
        sep=meta.get("delimitador", ","),
        encoding=meta.get("codificacion", "utf-8"),
        decimal=meta.get("decimal", "."),
        encoding_errors="replace",
        on_bad_lines="skip",
    )


def leer_df(ruta, meta, **kw):
    try:
        df = pd.read_csv(ruta, low_memory=False, **_opciones(meta), **kw)
    except pd.errors.EmptyDataError:
        raise ErrorLectura(f"El archivo «{os.path.basename(ruta)}» está vacío.")
    if not isinstance(df, pd.DataFrame):
        return df
    df.columns = nombre_unico([corregir_texto(c) for c in df.columns])
    return df


def normalizar_replica(serie):
    """Número de réplica como texto («1», «2»…). Si la columna es numérica, los valores no numéricos (p. ej.
    un encabezado «NREP» repetido dentro del archivo) quedan vacíos y no se toman como réplica."""
    num = pd.to_numeric(serie, errors="coerce")
    if num.notna().all():
        if (num == num.round()).all():
            return num.round().astype("int64").astype(str)
        return num.astype(str)
    if num.notna().any():
        validos = num.dropna()
        texto = num.round().astype("Int64").astype(str) if (validos == validos.round()).all() else num.astype(str)
        return texto.where(num.notna(), "")
    s = serie.astype(str).str.strip()
    return s.where(s.str.lower() != "nrep", "")


def cargar_tabla_grande(ruta, meta, progreso=None, cancelar=None, chunk_filas=100_000):
    """Carga un CSV grande optimizando memoria (categorías + float32).

    progreso(fraccion, filas_leidas) se invoca tras cada bloque.
    cancelar() debe devolver True para abortar (lanza Cancelado).
    """
    opciones = _opciones(meta)
    crudas = list(pd.read_csv(ruta, nrows=0, **opciones).columns)
    corregidas = nombre_unico([corregir_texto(c) for c in crudas])
    conservar = [(c, f) for c, f in zip(crudas, corregidas) if not es_vacio(f)]
    if not conservar:
        raise ErrorLectura("El archivo no contiene columnas válidas.")
    usecols = [c for c, _ in conservar]
    renombrar = {c: f for c, f in conservar}

    muestra = pd.read_csv(ruta, nrows=20000, usecols=usecols, low_memory=False, **opciones)
    num_cols = [c for c in usecols if pd.api.types.is_numeric_dtype(muestra[c])]
    del muestra

    total = meta.get("filas") or 0
    partes = []
    leidas = 0
    if progreso:                                # la barra avanza desde el inicio (bloques de 100,000 filas)
        progreso(0.01, 0)
    lector = pd.read_csv(ruta, usecols=usecols, chunksize=chunk_filas,
                         low_memory=False, **opciones)
    for chunk in lector:
        if cancelar and cancelar():
            raise Cancelado()
        for c in usecols:
            if c in num_cols:
                chunk[c] = pd.to_numeric(chunk[c], errors="coerce").astype("float32")
            else:
                chunk[c] = chunk[c].astype("category")
        partes.append(chunk)
        leidas += len(chunk)
        if progreso:
            progreso(min(0.99, leidas / total) if total else 0.0, leidas)
    if not partes:
        raise ErrorLectura("El archivo no contiene filas de datos.")

    columnas = {}
    for c in usecols:
        if c in num_cols:
            columnas[renombrar[c]] = np.concatenate([p[c].to_numpy() for p in partes])
        else:
            columnas[renombrar[c]] = pd.api.types.union_categoricals(
                [p[c] for p in partes], sort_categories=True)
    del partes
    df = pd.DataFrame(columnas)
    if progreso:
        progreso(1.0, leidas)
    return df
