"""Expresiones tipo Excel para los campos calculados de las tablas dinámicas.

Sintaxis: campos entre corchetes [Carga (t)], números, textos "entre comillas", operadores + - * / ^ &
(concatenar), comparaciones = <> < > <= >=, paréntesis y funciones (en español o inglés; argumentos separados
por coma o punto y coma):

  Lógicas:     SI / IF, Y / AND, O / OR, NO / NOT, SI.ERROR / IFERROR, ESBLANCO / ISBLANK
  Matemáticas: ABS, REDONDEAR / ROUND, ENTERO / INT, RAIZ / SQRT, POTENCIA / POWER, EXP, LN, LOG,
               MIN, MAX (de valores de la fila)
  Texto:       MAYUSC / UPPER, MINUSC / LOWER, LARGO / LEN, IZQUIERDA / LEFT, DERECHA / RIGHT,
               CONCATENAR / CONCAT, TEXTO / TEXT, CONTIENE / CONTAINS
  Resumen:     SUMA / SUM, PROMEDIO / AVERAGE, CONTAR / COUNT, MINIMO / MINIMUM, MAXIMO / MAXIMUM
               (si la expresión usa funciones de resumen, se calcula sobre cada celda de la tabla, p. ej.
               SUMA([Carga (t)]) / SUMA([Carguío (min)]) / 60 → t/h)

Ejemplos:  [Carga (t)] / 1000      SI([Pases] > 4; "Más de 4"; "Hasta 4")      SUMA([Carga (t)]) / CONTAR([Carga (t)])
"""
import math
import re

from perezoso import np, pd


class ErrorExpresion(Exception):
    pass


FUNCIONES = {
    # nombre canónico: (alias, descripción)
    "SI": (("IF",), "SI(condición; valor si verdadero; valor si falso)"),
    "Y": (("AND",), "Y(condición1; condición2; …): verdadero si todas se cumplen"),
    "O": (("OR",), "O(condición1; condición2; …): verdadero si alguna se cumple"),
    "NO": (("NOT",), "NO(condición): invierte la condición"),
    "SI.ERROR": (("IFERROR",), "SI.ERROR(valor; valor si hay error o división por cero)"),
    "ESBLANCO": (("ISBLANK",), "ESBLANCO(valor): verdadero si está vacío"),
    "ABS": ((), "ABS(número): valor absoluto"),
    "REDONDEAR": (("ROUND",), "REDONDEAR(número; decimales)"),
    "ENTERO": (("INT",), "ENTERO(número): parte entera (hacia abajo)"),
    "RAIZ": (("SQRT",), "RAIZ(número): raíz cuadrada"),
    "POTENCIA": (("POWER",), "POTENCIA(base; exponente)"),
    "EXP": ((), "EXP(número): e elevado al número"),
    "LN": ((), "LN(número): logaritmo natural"),
    "LOG": ((), "LOG(número; base): logaritmo (base 10 por defecto)"),
    "MIN": ((), "MIN(valor1; valor2; …): el menor (en una fila) o el mínimo del campo (en resumen)"),
    "MAX": ((), "MAX(valor1; valor2; …): el mayor (en una fila) o el máximo del campo (en resumen)"),
    "MAYUSC": (("UPPER",), "MAYUSC(texto)"),
    "MINUSC": (("LOWER",), "MINUSC(texto)"),
    "LARGO": (("LEN",), "LARGO(texto): N° de caracteres"),
    "IZQUIERDA": (("LEFT",), "IZQUIERDA(texto; n)"),
    "DERECHA": (("RIGHT",), "DERECHA(texto; n)"),
    "CONCATENAR": (("CONCAT",), "CONCATENAR(texto1; texto2; …)"),
    "TEXTO": (("TEXT",), "TEXTO(valor): convierte a texto"),
    "CONTIENE": (("CONTAINS",), "CONTIENE(texto; buscado): verdadero si lo contiene"),
    "SUMA": (("SUM",), "SUMA([Campo]): suma del campo en cada celda de la tabla"),
    "PROMEDIO": (("AVERAGE", "AVG"), "PROMEDIO([Campo]): promedio del campo en cada celda"),
    "CONTAR": (("COUNT",), "CONTAR([Campo]): N° de registros con valor"),
    "MINIMO": (("MINIMUM",), "MINIMO([Campo]): mínimo del campo en cada celda"),
    "MAXIMO": (("MAXIMUM",), "MAXIMO([Campo]): máximo del campo en cada celda"),
}
RESUMEN = {"SUMA", "PROMEDIO", "CONTAR", "MINIMO", "MAXIMO"}
_ALIAS = {}
for _k, (_al, _d) in FUNCIONES.items():
    _ALIAS[_k] = _k
    for _a in _al:
        _ALIAS[_a] = _k
OPERADORES = [("+", "Suma"), ("-", "Resta"), ("*", "Multiplicación"), ("/", "División"), ("^", "Potencia"),
              ("&", "Concatenar textos"), ("=", "Igual"), ("<>", "Distinto"), ("<", "Menor"), (">", "Mayor"),
              ("<=", "Menor o igual"), (">=", "Mayor o igual")]
CONSTANTES = [("VERDADERO", "Valor lógico verdadero"), ("FALSO", "Valor lógico falso"), ("PI", "3.14159…")]

_TOKEN = re.compile(r"""\s*(?:
    (?P<num>\d+(?:[.,]\d+)?(?:[eE][-+]?\d+)?) |
    (?P<txt>"(?:[^"]|"")*") |
    (?P<campo>\[[^\]]+\]) |
    (?P<op><>|<=|>=|[-+*/^&=<>(),;]) |
    (?P<nom>[A-Za-zÁÉÍÓÚÑáéíóúñ_][A-Za-zÁÉÍÓÚÑáéíóúñ_0-9.]*)
)""", re.VERBOSE)


def _tokens(texto):
    pos, salida = 0, []
    texto = texto.strip()
    if texto.startswith("="):
        texto = texto[1:]
    while pos < len(texto):
        m = _TOKEN.match(texto, pos)
        if not m or m.end() == pos:
            if texto[pos:].strip() == "":
                break
            raise ErrorExpresion(f"Carácter no reconocido en la posición {pos + 1}: «{texto[pos]}»")
        pos = m.end()
        for tipo in ("num", "txt", "campo", "op", "nom"):
            v = m.group(tipo)
            if v is not None:
                salida.append((tipo, v))
                break
    return salida


class _Parser:
    def __init__(self, tokens):
        self.t, self.i = tokens, 0

    def ver(self):
        return self.t[self.i] if self.i < len(self.t) else (None, None)

    def tomar(self, valor=None):
        tok = self.ver()
        if valor is not None and tok[1] != valor:
            raise ErrorExpresion(f"Se esperaba «{valor}»" + (f" y se encontró «{tok[1]}»" if tok[1] else ""))
        self.i += 1
        return tok

    def analizar(self):
        if not self.t:
            raise ErrorExpresion("La expresión está vacía.")
        n = self.comparacion()
        if self.i < len(self.t):
            raise ErrorExpresion(f"Sobra «{self.ver()[1]}» al final de la expresión.")
        return n

    def comparacion(self):
        n = self.concat()
        while self.ver()[1] in ("=", "<>", "<", ">", "<=", ">="):
            op = self.tomar()[1]
            n = ("bin", op, n, self.concat())
        return n

    def concat(self):
        n = self.suma()
        while self.ver()[1] == "&":
            self.tomar()
            n = ("bin", "&", n, self.suma())
        return n

    def suma(self):
        n = self.producto()
        while self.ver()[1] in ("+", "-"):
            op = self.tomar()[1]
            n = ("bin", op, n, self.producto())
        return n

    def producto(self):
        n = self.potencia()
        while self.ver()[1] in ("*", "/"):
            op = self.tomar()[1]
            n = ("bin", op, n, self.potencia())
        return n

    def potencia(self):
        n = self.unario()
        while self.ver()[1] == "^":
            self.tomar()
            n = ("bin", "^", n, self.unario())
        return n

    def unario(self):
        if self.ver()[1] in ("-", "+"):
            op = self.tomar()[1]
            n = self.unario()
            return ("neg", n) if op == "-" else n
        return self.primario()

    def primario(self):
        tipo, v = self.ver()
        if tipo == "num":
            self.tomar()
            return ("num", float(v.replace(",", ".")))
        if tipo == "txt":
            self.tomar()
            return ("txt", v[1:-1].replace('""', '"'))
        if tipo == "campo":
            self.tomar()
            return ("campo", v[1:-1].strip())
        if v == "(":
            self.tomar()
            n = self.comparacion()
            self.tomar(")")
            return n
        if tipo == "nom":
            self.tomar()
            nombre = v.upper()
            if nombre in ("VERDADERO", "TRUE"):
                return ("num", 1.0)
            if nombre in ("FALSO", "FALSE"):
                return ("num", 0.0)
            if nombre == "PI" and self.ver()[1] != "(":
                return ("num", math.pi)
            if nombre not in _ALIAS:
                raise ErrorExpresion(f"Función desconocida: {v}")
            self.tomar("(")
            args = []
            if self.ver()[1] != ")":
                args.append(self.comparacion())
                while self.ver()[1] in (",", ";"):
                    self.tomar()
                    args.append(self.comparacion())
            self.tomar(")")
            return ("fn", _ALIAS[nombre], args)
        if tipo is None:
            raise ErrorExpresion("La expresión está incompleta.")
        raise ErrorExpresion(f"Elemento inesperado: «{v}»")


def analizar(texto):
    return _Parser(_tokens(texto or "")).analizar()


def campos_usados(nodo, salida=None):
    salida = salida if salida is not None else []
    if nodo[0] == "campo":
        if nodo[1] not in salida:
            salida.append(nodo[1])
    elif nodo[0] == "bin":
        campos_usados(nodo[2], salida)
        campos_usados(nodo[3], salida)
    elif nodo[0] == "neg":
        campos_usados(nodo[1], salida)
    elif nodo[0] == "fn":
        for a in nodo[2]:
            campos_usados(a, salida)
    return salida


def es_resumen(nodo):
    if nodo[0] == "fn":
        return nodo[1] in RESUMEN or any(es_resumen(a) for a in nodo[2])
    if nodo[0] == "bin":
        return es_resumen(nodo[2]) or es_resumen(nodo[3])
    if nodo[0] == "neg":
        return es_resumen(nodo[1])
    return False


def agregados_usados(nodo, salida=None):
    """[(función, campo)] de las funciones de resumen de la expresión."""
    salida = salida if salida is not None else []
    if nodo[0] == "fn":
        if nodo[1] in RESUMEN:
            if len(nodo[2]) != 1 or nodo[2][0][0] != "campo":
                raise ErrorExpresion(f"{nodo[1]} debe recibir un solo campo entre corchetes, p. ej. {nodo[1]}([Carga (t)]).")
            par = (nodo[1], nodo[2][0][1])
            if par not in salida:
                salida.append(par)
        else:
            for a in nodo[2]:
                agregados_usados(a, salida)
    elif nodo[0] == "bin":
        agregados_usados(nodo[2], salida)
        agregados_usados(nodo[3], salida)
    elif nodo[0] == "neg":
        agregados_usados(nodo[1], salida)
    return salida


def _num(x):
    if isinstance(x, pd.Series):
        if pd.api.types.is_numeric_dtype(x.dtype) and not pd.api.types.is_bool_dtype(x.dtype):
            return x.astype("float64")
        if pd.api.types.is_bool_dtype(x.dtype):
            return x.astype("float64")
        return pd.to_numeric(x.astype(str).str.replace(",", "", regex=False), errors="coerce")
    if isinstance(x, str):
        try:
            return float(x.replace(",", ""))
        except ValueError:
            return float("nan")
    return float(x) if x is not None else float("nan")


def _texto(x):
    if isinstance(x, pd.Series):
        if pd.api.types.is_float_dtype(x.dtype):
            return x.map(lambda v: "" if pd.isna(v) else (f"{v:.0f}" if float(v).is_integer() else f"{v:g}"))
        return x.astype(str).where(x.notna(), "")
    if isinstance(x, float):
        return "" if math.isnan(x) else (f"{x:.0f}" if x.is_integer() else f"{x:g}")
    return str(x)


def _bool(x):
    if isinstance(x, pd.Series):
        if pd.api.types.is_bool_dtype(x.dtype):
            return x
        return _num(x).fillna(0) != 0
    if isinstance(x, str):
        return bool(x)
    return bool(x) and not (isinstance(x, float) and math.isnan(x))


def _limpiar(x):
    if isinstance(x, pd.Series) and pd.api.types.is_float_dtype(x.dtype):
        return x.replace([np.inf, -np.inf], np.nan)
    if isinstance(x, float) and math.isinf(x):
        return float("nan")
    return x


def evaluar(nodo, resolver, indice):
    """resolver(nodo_campo | ('agg', función, campo)) → Series o escalar; indice: índice de salida."""
    t = nodo[0]
    if t == "num":
        return nodo[1]
    if t == "txt":
        return nodo[1]
    if t == "campo":
        return resolver(("campo", nodo[1]))
    if t == "neg":
        return -_num(evaluar(nodo[1], resolver, indice))
    if t == "bin":
        op = nodo[1]
        a, b = evaluar(nodo[2], resolver, indice), evaluar(nodo[3], resolver, indice)
        if op == "&":
            return _texto(a) + _texto(b) if isinstance(_texto(a), pd.Series) or isinstance(_texto(b), pd.Series) \
                else _texto(a) + _texto(b)
        if op in ("=", "<>") and (isinstance(a, str) or isinstance(b, str) or
                                  (isinstance(a, pd.Series) and not pd.api.types.is_numeric_dtype(a.dtype)) or
                                  (isinstance(b, pd.Series) and not pd.api.types.is_numeric_dtype(b.dtype))):
            r = _texto(a) == _texto(b)
            return r if op == "=" else ~r if isinstance(r, pd.Series) else not r
        x, y = _num(a), _num(b)
        with np.errstate(all="ignore"):
            if op == "+":
                return x + y
            if op == "-":
                return x - y
            if op == "*":
                return x * y
            if op == "/":
                if isinstance(y, pd.Series):
                    return _limpiar(x / y.replace(0, np.nan))
                return _limpiar(x / y) if y else (x * float("nan") if isinstance(x, pd.Series) else float("nan"))
            if op == "^":
                return _limpiar(x ** y)
            return {"=": lambda: x == y, "<>": lambda: x != y, "<": lambda: x < y, ">": lambda: x > y,
                    "<=": lambda: x <= y, ">=": lambda: x >= y}[op]()
    if t == "fn":
        f, args = nodo[1], nodo[2]
        if f in RESUMEN:
            return resolver(("agg", f, args[0][1]))
        if f == "SI":
            if len(args) < 2:
                raise ErrorExpresion("SI necesita al menos 2 argumentos: SI(condición; valor si verdadero; valor si falso).")
            c = _bool(evaluar(args[0], resolver, indice))
            v1 = evaluar(args[1], resolver, indice)
            v2 = evaluar(args[2], resolver, indice) if len(args) > 2 else 0.0
            if isinstance(c, pd.Series) or isinstance(v1, pd.Series) or isinstance(v2, pd.Series):
                c = c if isinstance(c, pd.Series) else pd.Series(c, index=indice)
                s1 = v1 if isinstance(v1, pd.Series) else pd.Series(v1, index=indice)
                s2 = v2 if isinstance(v2, pd.Series) else pd.Series(v2, index=indice)
                return s1.where(c, s2)
            return v1 if c else v2
        vals = [evaluar(a, resolver, indice) for a in args]
        if f == "Y":
            r = True
            for v in vals:
                r = r & _bool(v)
            return r
        if f == "O":
            r = False
            for v in vals:
                r = r | _bool(v)
            return r
        if f == "NO":
            b = _bool(vals[0])
            return ~b if isinstance(b, pd.Series) else not b
        if f == "SI.ERROR":
            v, alt = vals[0], vals[1] if len(vals) > 1 else 0.0
            if isinstance(v, pd.Series):
                return v.where(v.notna(), alt)
            return alt if (v is None or (isinstance(v, float) and math.isnan(v))) else v
        if f == "ESBLANCO":
            v = vals[0]
            if isinstance(v, pd.Series):
                return v.isna() | (v.astype(str).str.strip() == "")
            return v is None or str(v).strip() == "" or (isinstance(v, float) and math.isnan(v))
        if f in ("ABS", "ENTERO", "RAIZ", "EXP", "LN"):
            x = _num(vals[0])
            fn = {"ABS": np.abs, "ENTERO": np.floor, "RAIZ": np.sqrt, "EXP": np.exp, "LN": np.log}[f]
            with np.errstate(all="ignore"):
                return _limpiar(fn(x))
        if f == "LOG":
            x = _num(vals[0])
            base = _num(vals[1]) if len(vals) > 1 else 10.0
            with np.errstate(all="ignore"):
                return _limpiar(np.log(x) / np.log(base))
        if f == "REDONDEAR":
            x = _num(vals[0])
            d = int(_num(vals[1])) if len(vals) > 1 else 0
            return x.round(d) if isinstance(x, pd.Series) else round(x, d)
        if f == "POTENCIA":
            with np.errstate(all="ignore"):
                return _limpiar(_num(vals[0]) ** _num(vals[1]))
        if f in ("MIN", "MAX"):
            nums = [_num(v) for v in vals]
            if any(isinstance(v, pd.Series) for v in nums):
                df = pd.concat([v if isinstance(v, pd.Series) else pd.Series(v, index=indice) for v in nums], axis=1)
                return df.min(axis=1) if f == "MIN" else df.max(axis=1)
            return (min if f == "MIN" else max)(nums)
        if f in ("MAYUSC", "MINUSC", "LARGO"):
            s = _texto(vals[0])
            if isinstance(s, pd.Series):
                return s.str.upper() if f == "MAYUSC" else (s.str.lower() if f == "MINUSC" else s.str.len().astype("float64"))
            return s.upper() if f == "MAYUSC" else (s.lower() if f == "MINUSC" else float(len(s)))
        if f in ("IZQUIERDA", "DERECHA"):
            s = _texto(vals[0])
            n = int(_num(vals[1])) if len(vals) > 1 else 1
            if isinstance(s, pd.Series):
                return s.str[:n] if f == "IZQUIERDA" else s.str[-n:]
            return s[:n] if f == "IZQUIERDA" else s[-n:]
        if f == "CONCATENAR":
            r = ""
            for v in vals:
                r = r + _texto(v)
            return r
        if f == "TEXTO":
            return _texto(vals[0])
        if f == "CONTIENE":
            s, q = _texto(vals[0]), _texto(vals[1])
            if isinstance(s, pd.Series):
                return s.str.contains(str(q), case=False, regex=False)
            return str(q).lower() in s.lower()
    raise ErrorExpresion("Expresión no válida.")


def validar(texto, campos_disponibles):
    """Devuelve (nodo, es_resumen) o lanza ErrorExpresion con un mensaje claro."""
    nodo = analizar(texto)
    faltan = [c for c in campos_usados(nodo) if c not in campos_disponibles]
    if faltan:
        raise ErrorExpresion("Campo desconocido: " + ", ".join(f"[{c}]" for c in faltan))
    resumen = es_resumen(nodo)
    if resumen:
        agregados_usados(nodo)
        _sin_agregar(nodo)
    return nodo, resumen


def _sin_agregar(nodo, dentro=False):
    """En una expresión de resumen todo campo debe estar dentro de SUMA, PROMEDIO, CONTAR, MINIMO o MAXIMO."""
    if nodo[0] == "campo" and not dentro:
        raise ErrorExpresion(f"En una expresión de resumen el campo [{nodo[1]}] debe ir dentro de SUMA, PROMEDIO, "
                             "CONTAR, MINIMO o MAXIMO.")
    if nodo[0] == "fn":
        for a in nodo[2]:
            _sin_agregar(a, dentro or nodo[1] in RESUMEN)
    elif nodo[0] == "bin":
        _sin_agregar(nodo[2], dentro)
        _sin_agregar(nodo[3], dentro)
    elif nodo[0] == "neg":
        _sin_agregar(nodo[1], dentro)


def columna_fila(df, nodo):
    """Evalúa una expresión por fila sobre un DataFrame (campo calculado)."""
    def resolver(ref):
        if ref[0] == "campo":
            return df[ref[1]]
        raise ErrorExpresion("Función de resumen no permitida en un campo por fila.")
    r = evaluar(nodo, resolver, df.index)
    if not isinstance(r, pd.Series):
        r = pd.Series(r, index=df.index)
    if pd.api.types.is_bool_dtype(r.dtype):
        r = r.astype("float64")
    return r
