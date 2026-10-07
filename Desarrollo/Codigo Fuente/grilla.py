"""Grilla de tabla dinámica (Canvas, con dibujo solo de lo visible).

· Encabezados de columnas en varios niveles con celdas combinadas; dimensiones de filas en columnas con
  celdas combinadas (diseño tabular), triángulos para contraer o desplegar grupos y filas/columnas de
  subtotal y total general.
· Encabezados y dimensiones fijos al desplazarse (como «inmovilizar paneles»); rueda del mouse y barras.
· Anchos ajustables arrastrando el borde del encabezado; menú Copiar Tabla / con Formato / como Imagen,
  Expandir Todo y Contraer Todo.
"""
import bisect
import tkinter as tk
from tkinter import ttk

import pivot
from tema import T
from ui_comun import avisar_estado, colores_grupo, mostrar_menu, nuevo_menu


def formateador(formato):
    if formato == "pct" or formato == "0.00%":
        return lambda v: f"{v * 100:,.2f}%"
    if formato == "0.0%":
        return lambda v: f"{v * 100:,.1f}%"
    if formato in ("int", "#,##0"):
        return lambda v: f"{v:,.0f}"
    if formato == "#,##0.0":
        return lambda v: f"{v:,.1f}"
    if formato == "#,##0.00":
        return lambda v: f"{v:,.2f}"
    if formato == "#,##0.000":
        return lambda v: f"{v:,.3f}"
    return None


def formateadores_auto(cubo):
    """Formato por valor: el elegido por el usuario o automático (entero si todos lo son; si no, 1 ó 2
    decimales según la magnitud)."""
    salida = []
    for k, f in enumerate(cubo["formatos"]):
        fn = formateador(f)
        if fn is None:
            muestra = [fila[k] for fila in list(cubo["celdas"].values())[:3000] if k < len(fila) and fila[k] is not None]
            if muestra and all(abs(v - round(v)) < 1e-9 for v in muestra):
                fn = formateador("int")
            elif muestra and max(abs(v) for v in muestra) >= 100:
                fn = formateador("#,##0.0")
            else:
                fn = formateador("#,##0.00")
        salida.append(fn)
    return salida


class _Lienzo(tk.Canvas):
    """Lienzo con desplazamiento propio (compatible con la rueda global y las barras)."""

    def __init__(self, master, grilla):
        super().__init__(master, highlightthickness=0, borderwidth=0)
        self.g = grilla

    def xview(self, *args):
        return self.g._vista("x", *args)

    def yview(self, *args):
        return self.g._vista("y", *args)

    def xview_scroll(self, n, que):
        return self.g._vista("x", "scroll", n, que)

    def yview_scroll(self, n, que):
        return self.g._vista("y", "scroll", n, que)

    def xview_moveto(self, f):
        return self.g._vista("x", "moveto", f)

    def yview_moveto(self, f):
        return self.g._vista("y", "moveto", f)


class GrillaPivot(ttk.Frame):
    def __init__(self, master, al_cambiar_estado=None, nombre="Tabla Dinámica"):
        super().__init__(master, style="Panel.TFrame")
        self.al_cambiar_estado = al_cambiar_estado
        self.nombre = nombre
        self.cubo = None
        self.col_f, self.col_c = set(), set()
        self.opc = dict(pivot.OPCIONES)
        self.fmts = []
        self.xo = self.yo = 0
        self.anchos_val, self.anchos_dim = {}, []
        self._hover = None
        self._redim = None
        self._id = None
        self.lienzo = _Lienzo(self, self)
        self.vsb = ttk.Scrollbar(self, orient="vertical", command=self.lienzo.yview)
        self.hsb = ttk.Scrollbar(self, orient="horizontal", command=self.lienzo.xview)
        self.lienzo.grid(row=0, column=0, sticky="nsew")
        self.vsb.grid(row=0, column=1, sticky="ns")
        self.hsb.grid(row=1, column=0, sticky="ew")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self._tam = None
        self.lienzo.bind("<Configure>", self._al_configurar)
        self.lienzo.bind("<Button-1>", self._clic)
        self.lienzo.bind("<Double-Button-1>", self._doble)
        self.lienzo.bind("<B1-Motion>", self._arrastrar)
        self.lienzo.bind("<ButtonRelease-1>", self._soltar)
        self.lienzo.bind("<Motion>", self._mover)
        self.lienzo.bind("<Leave>", lambda e: self._salir())
        self.lienzo.bind("<Button-3>", self._menu)
        T.registrar(self._programar)

    # ---- datos ---------------------------------------------------------------------------------------
    def cargar(self, cubo, opciones=None, colapsadas_f=None, colapsadas_c=None, formatos=None):
        self.cubo = cubo
        self.opc = dict(pivot.OPCIONES, **(opciones or {}))
        validas_f = set(pivot.todas_las_rutas(cubo["arbol_filas"]))
        validas_c = set(pivot.todas_las_rutas(cubo["arbol_cols"]))
        self.col_f = {tuple(r) for r in (colapsadas_f or []) if tuple(r) in validas_f}
        self.col_c = {tuple(r) for r in (colapsadas_c or []) if tuple(r) in validas_c}
        self.fmts = formatos or formateadores_auto(cubo)
        self._hijos_f = {n["ruta"]: bool(n["hijos"]) for n in self._nodos(cubo["arbol_filas"])}
        self._hijos_c = {n["ruta"]: bool(n["hijos"]) for n in self._nodos(cubo["arbol_cols"])}
        self.xo = self.yo = 0
        self._aplanar()
        self._medir()
        self._programar()

    @staticmethod
    def _nodos(arbol):
        pila = list(arbol)
        while pila:
            n = pila.pop()
            yield n
            pila.extend(n["hijos"])

    def estado(self):
        return {"colapsadas_filas": [list(r) for r in sorted(self.col_f)],
                "colapsadas_columnas": [list(r) for r in sorted(self.col_c)]}

    def _aplanar(self):
        c = self.cubo
        self.filas_v = pivot.filas_vista(c, self.col_f, self.opc["subtotales_filas"], self.opc["totales_generales_filas"])
        self.cols_v = pivot.cols_vista(c, self.col_c, self.opc["subtotales_columnas"],
                                       self.opc["totales_generales_columnas"])
        self.nd = max(1, len(c["dims_filas"]))
        self.nc = len(c["dims_cols"])
        self.fila_valores = len(c["valores"]) > 1 or not c["dims_cols"]
        self.n_hdr = (self.nc + (1 if self.fila_valores else 0)) if self.opc["encabezados_columnas"] else 0
        # tramos combinados de las dimensiones de filas: por nivel, (inicio, fin, clave)
        self.tramos_f = self._tramos([(r, t) for r, t, _n in self.filas_v], self.nd)
        self.tramos_c = self._tramos([(r, t) for r, t, _k in self.cols_v], self.nc, valores=len(c["valores"]))

    @staticmethod
    def _tramos(items, n_niveles, valores=1):
        """Por nivel: lista de (inicio, fin, ruta del grupo desplegado) que se combinan."""
        tramos = [[] for _ in range(max(1, n_niveles))]
        for a in range(n_niveles):
            actual, ini = None, 0
            for i, (ruta, tipo) in enumerate(items):
                clave = ruta[:a + 1] if len(ruta) > a + 1 or (tipo == "subtotal" and len(ruta) > a + 1) else None
                if tipo == "subtotal" and len(ruta) == a + 1:
                    clave = None
                if clave != actual:
                    if actual is not None:
                        tramos[a].append((ini, i - 1, actual))
                    actual, ini = clave, i
            if actual is not None:
                tramos[a].append((ini, len(items) - 1, actual))
        return tramos

    def _medir(self):
        c = self.cubo
        fn, fb = T.f["tabla"], T.f["tabla_n"]
        pad = T.px(22)
        self.RH, self.HH = T.px(22), T.px(24)
        anch = []
        for a in range(self.nd):
            textos = [c["dims_filas"][a] if a < len(c["dims_filas"]) else ""]
            textos += [r[a] + (" Total" if t == "subtotal" else "") for r, t, _n in self.filas_v[:3000] if len(r) > a]
            w = max([fb.measure(x) for x in textos] + [fb.measure("Total General") if a == 0 else 0]) + pad + T.px(14)
            anch.append(min(max(w, T.px(70)), T.px(360)))
        if self.anchos_dim and len(self.anchos_dim) == len(anch):
            anch = [max(a, b) if b else a for a, b in zip(anch, self.anchos_dim)]
        self.anchos_dim = anch
        self.w_dims = sum(anch) if self.opc["encabezados_filas"] else 0
        self.anchos = []
        muestra = self.filas_v[:300]
        for j, (ruta, tipo, k) in enumerate(self.cols_v):
            clave = (tuple(ruta), tipo, k)
            if clave in self.anchos_val:
                self.anchos.append(self.anchos_val[clave])
                continue
            etiquetas = [c["valores"][k]] + ([ruta[-1]] if ruta else []) + (["Total General"] if tipo == "total" else [])
            w = max(fb.measure(x) for x in etiquetas)
            fmt = self.fmts[k]
            for r, _t, _n in muestra:
                v = pivot.valor(c, r, ruta, k)
                if v is not None:
                    w = max(w, fb.measure(fmt(v)))
            self.anchos.append(min(max(w + pad, T.px(70)), T.px(260)))
        self.xs = [0]
        for w in self.anchos:
            self.xs.append(self.xs[-1] + w)

    # ---- desplazamiento ----------------------------------------------------------------------------------
    def _area(self):
        w = max(1, self.lienzo.winfo_width() - self.w_dims)
        h = max(1, self.lienzo.winfo_height() - self.n_hdr * self.HH)
        return w, h

    def _total(self, eje):
        return (self.xs[-1] if self.xs else 0) if eje == "x" else len(self.filas_v) * self.RH

    def _vista(self, eje, *args):
        if self.cubo is None:
            return (0.0, 1.0)
        w, h = self._area()
        visible = w if eje == "x" else h
        total = max(1, self._total(eje))
        off = self.xo if eje == "x" else self.yo
        if not args:
            return (off / total, min(1.0, (off + visible) / total))
        if args[0] == "moveto":
            off = float(args[1]) * total
        elif args[0] == "scroll":
            n, que = int(args[1]), args[2]
            paso = (T.px(60) if eje == "x" else self.RH) if que == "units" else visible * 0.9
            off += n * paso
        off = max(0, min(off, max(0, total - visible)))
        if eje == "x":
            self.xo = off
        else:
            self.yo = off
        self._programar()

    def _barras(self):
        w, h = self._area()
        tx, ty = max(1, self._total("x")), max(1, self._total("y"))
        self.hsb.set(self.xo / tx, min(1.0, (self.xo + w) / tx))
        self.vsb.set(self.yo / ty, min(1.0, (self.yo + h) / ty))
        (self.hsb.grid_remove if tx <= w else self.hsb.grid)()
        (self.vsb.grid_remove if ty <= h else self.vsb.grid)()

    # ---- dibujo ---------------------------------------------------------------------------------------------
    def _al_configurar(self, e):
        tam = (e.width, e.height)
        if tam == self._tam:
            return
        primera = self._tam is None or self._tam[0] < 50
        self._tam = tam
        self._programar(0 if primera else 60)     # al redimensionar se pinta primero la ventana

    def _programar(self, retardo=0):
        if self._id is None:
            self._id = self.after(retardo, self._dibujar) if retardo else self.after_idle(self._dibujar)

    def _colores(self):
        p = T.p
        return {"cab": p["cab"], "dim": p["panel_alt"], "cuerpo": p["panel"], "linea": p["rejilla"],
                "borde": p["borde"], "texto": p["texto"], "suave": p["suave"], "total": p["total"],
                "sub": colores_grupo(0)[2], "sub_col": p["fila_alt"], "hover": p["sel"]}

    def _dibujar(self):
        self._id = None
        cv = self.lienzo
        try:
            cv.delete("all")
        except tk.TclError:
            return
        if self.cubo is None:
            return
        col = self._colores()
        cv.configure(background=col["cuerpo"])
        W, H = cv.winfo_width(), cv.winfo_height()
        w_area, h_area = self._area()
        x0, y0 = self.w_dims, self.n_hdr * self.HH
        # límites de lo visible
        i0 = int(self.yo // self.RH)
        i1 = min(len(self.filas_v) - 1, int((self.yo + h_area) // self.RH) + 1)
        j0 = max(0, bisect.bisect_right(self.xs, self.xo) - 1)
        j1 = min(len(self.cols_v) - 1, bisect.bisect_right(self.xs, self.xo + w_area))
        self._cuerpo(cv, col, x0, y0, i0, i1, j0, j1, W, H)
        if self.opc["encabezados_filas"]:
            self._dims_filas(cv, col, y0, i0, i1, H)
        if self.n_hdr:
            self._encabezados(cv, col, x0, j0, j1, W)
            self._esquina(cv, col)
        cv.create_line(x0, 0, x0, H, fill=col["borde"])
        cv.create_line(0, y0, W, y0, fill=col["borde"])
        self._barras()

    def _y(self, i):
        return self.n_hdr * self.HH + i * self.RH - self.yo

    def _x(self, j):
        return self.w_dims + self.xs[j] - self.xo

    def _cuerpo(self, cv, col, x0, y0, i0, i1, j0, j1, W, H):
        c = self.cubo
        fn, fb = T.f["tabla"], T.f["tabla_n"]
        lh, lv = self.opc["lineas_horizontales"], self.opc["lineas_verticales"]
        for i in range(i0, i1 + 1):
            ruta, tipo, _n = self.filas_v[i]
            y = self._y(i)
            fondo = col["total"] if tipo == "total" else (col["sub"] if tipo == "subtotal" else None)
            if self._hover == i:
                fondo = col["hover"]
            if fondo:
                cv.create_rectangle(x0, y, W, y + self.RH, fill=fondo, outline="")
            negrita = tipo in ("total", "subtotal")
            for j in range(j0, j1 + 1):
                cr, ct, k = self.cols_v[j]
                x = self._x(j)
                if ct != "dato" and not fondo:
                    cv.create_rectangle(x, y, x + self.anchos[j], y + self.RH, fill=col["sub_col"], outline="")
                v = pivot.valor(c, ruta, cr, k)
                if v is not None:
                    cv.create_text(x + self.anchos[j] - T.px(8), y + self.RH / 2, text=self.fmts[k](v), anchor="e",
                                   fill=col["texto"], font=fb if (negrita or ct != "dato") else fn)
                if lv:
                    cv.create_line(x + self.anchos[j], y, x + self.anchos[j], y + self.RH, fill=col["linea"])
            if lh:
                cv.create_line(x0, y + self.RH, W, y + self.RH, fill=col["linea"])

    def _texto_corto(self, texto, ancho, fuente):
        if fuente.measure(texto) <= ancho:
            return texto
        while texto and fuente.measure(texto + "…") > ancho:
            texto = texto[:-1]
        return texto + "…"

    def _dims_filas(self, cv, col, y0, i0, i1, H):
        """Celdas de las dimensiones de filas (combinadas por grupo, con triángulos)."""
        fb, fn = T.f["tabla_n"], T.f["tabla"]
        xs = [0]
        for w in self.anchos_dim:
            xs.append(xs[-1] + w)
        cv.create_rectangle(0, y0, self.w_dims, H, fill=col["dim"], outline="")
        self._zonas_f = []
        # grupos desplegados (celdas combinadas en vertical) por nivel
        for a, tramos in enumerate(self.tramos_f):
            for ini, fin, ruta in tramos:
                if fin < i0 or ini > i1:
                    continue
                ya, yb = self._y(max(ini, i0)), self._y(min(fin, i1) + 1)
                ya_real = self._y(ini)
                cv.create_rectangle(xs[a], max(ya_real, y0), xs[a + 1], yb, fill=col["dim"], outline=col["linea"])
                ty = max(ya, y0) + self.RH / 2
                cv.create_text(xs[a] + T.px(6), ty, text="▾", anchor="w", fill=col["suave"], font=fn)
                cv.create_text(xs[a] + T.px(20), ty, text=self._texto_corto(ruta[-1], self.anchos_dim[a] - T.px(26), fb),
                               anchor="w", fill=col["texto"], font=fb)
                self._zonas_f.append((xs[a], max(ya_real, y0), xs[a + 1], yb, ruta))
        for i in range(i0, i1 + 1):
            ruta, tipo, n = self.filas_v[i]
            y = self._y(i)
            if tipo == "total":
                cv.create_rectangle(0, y, self.w_dims, y + self.RH, fill=col["total"], outline=col["linea"])
                cv.create_text(T.px(8), y + self.RH / 2, text="Total General", anchor="w", fill=col["texto"], font=fb)
                continue
            if not self.cubo["dims_filas"]:
                cv.create_text(T.px(8), y + self.RH / 2, text="Total", anchor="w", fill=col["texto"], font=fb)
                continue
            a = n - 1
            if tipo == "subtotal":
                cv.create_rectangle(xs[a], y, self.w_dims, y + self.RH, fill=col["sub"], outline=col["linea"])
                cv.create_text(xs[a] + T.px(8), y + self.RH / 2,
                               text=self._texto_corto(f"{ruta[-1]} Total", self.w_dims - xs[a] - T.px(10), fb),
                               anchor="w", fill=col["texto"], font=fb)
                continue
            fondo = col["hover"] if self._hover == i else col["dim"]
            cv.create_rectangle(xs[a], y, self.w_dims, y + self.RH, fill=fondo, outline=col["linea"])
            if self._hijos_f.get(ruta):
                cv.create_text(xs[a] + T.px(6), y + self.RH / 2, text="▸", anchor="w", fill=col["suave"], font=fn)
                self._zonas_f.append((xs[a], y, xs[a + 1], y + self.RH, ruta))
                dx = T.px(20)
            else:
                dx = T.px(8)
            cv.create_text(xs[a] + dx, y + self.RH / 2, text=self._texto_corto(ruta[-1], self.anchos_dim[a] - dx - 4, fn),
                           anchor="w", fill=col["texto"], font=fn)

    def _encabezados(self, cv, col, x0, j0, j1, W):
        c = self.cubo
        fb, fn = T.f["tabla_n"], T.f["tabla"]
        hh = self.HH
        cv.create_rectangle(x0, 0, W, self.n_hdr * hh, fill=col["cab"], outline="")
        self._zonas_c = []
        nv = len(c["valores"])
        # niveles de las dimensiones de columnas
        for a in range(self.nc):
            for ini, fin, ruta in self.tramos_c[a]:
                if fin < j0 or ini > j1:
                    continue
                xa, xb = self._x(ini), self._x(fin + 1)
                cv.create_rectangle(max(xa, x0), a * hh, xb, (a + 1) * hh, fill=col["cab"], outline=col["borde"])
                tx = max(xa, x0) + T.px(6)
                cv.create_text(tx, a * hh + hh / 2, text="▾", anchor="w", fill=col["suave"], font=fn)
                cv.create_text(tx + T.px(14), a * hh + hh / 2, text=self._texto_corto(ruta[-1], xb - tx - T.px(18), fb),
                               anchor="w", fill=col["texto"], font=fb)
                self._zonas_c.append((max(xa, x0), a * hh, xb, (a + 1) * hh, ruta))
        j = j0
        while j <= j1:
            ruta, tipo, k = self.cols_v[j]
            # bloque de las columnas de valores del mismo nodo
            fin = j
            while fin + 1 < len(self.cols_v) and self.cols_v[fin + 1][0] == ruta and self.cols_v[fin + 1][1] == tipo:
                fin += 1
            ini = j
            while ini > 0 and self.cols_v[ini - 1][0] == ruta and self.cols_v[ini - 1][1] == tipo:
                ini -= 1
            xa, xb = self._x(ini), self._x(fin + 1)
            if self.nc:
                if tipo == "total":
                    nivel_ini, texto = 0, "Total General"
                elif tipo == "subtotal":
                    nivel_ini, texto = len(ruta) - 1, f"{ruta[-1]} Total"
                else:
                    nivel_ini, texto = len(ruta) - 1, ruta[-1]
                alto = (self.nc - nivel_ini) * hh if tipo != "dato" or len(ruta) < self.nc else hh
                ya = nivel_ini * hh
                cv.create_rectangle(max(xa, x0), ya, xb, ya + alto, fill=col["cab"], outline=col["borde"])
                tx = max(xa, x0) + T.px(6)
                if tipo == "dato" and self._hijos_c.get(ruta):
                    cv.create_text(tx, ya + hh / 2, text="▸", anchor="w", fill=col["suave"], font=fn)
                    self._zonas_c.append((max(xa, x0), ya, xb, ya + hh, ruta))
                    tx += T.px(14)
                cv.create_text(tx, ya + min(alto, hh) / 2 if tipo == "dato" else ya + alto / 2,
                               text=self._texto_corto(texto, xb - tx - T.px(6), fb), anchor="w", fill=col["texto"], font=fb)
            if self.fila_valores:
                yv = self.nc * hh
                for jj in range(j, fin + 1):
                    _r, _t, kk = self.cols_v[jj]
                    xa2, xb2 = self._x(jj), self._x(jj + 1)
                    cv.create_rectangle(xa2, yv, xb2, yv + hh, fill=col["cab"], outline=col["borde"])
                    nombre = c["valores"][kk] + (f" (% {pivot._ABREV[c['modos'][kk]]})" if c["modos"][kk] else "")
                    cv.create_text((xa2 + xb2) / 2, yv + hh / 2, text=self._texto_corto(nombre, xb2 - xa2 - T.px(8), fb),
                                   fill=col["texto"], font=fb)
            j = fin + 1

    def _esquina(self, cv, col):
        c = self.cubo
        fb, fn = T.f["tabla_n"], T.f["chica"]
        hh = self.HH
        cv.create_rectangle(0, 0, self.w_dims, self.n_hdr * hh, fill=col["cab"], outline=col["borde"])
        if not self.opc["encabezados_filas"]:
            return
        xs = [0]
        for w in self.anchos_dim:
            xs.append(xs[-1] + w)
        # nombres de las dimensiones de columnas (arriba) y de filas (última fila del encabezado)
        for a, nombre in enumerate(c["dims_cols"]):
            cv.create_text(self.w_dims - T.px(8), a * hh + hh / 2, text=f"{nombre}  ▸", anchor="e",
                           fill=col["suave"], font=fn)
        if len(c["valores"]) == 1 and c["dims_cols"]:
            cv.create_text(T.px(8), hh / 2, text=c["valores"][0], anchor="w", fill=col["texto"], font=fb)
        ya = (self.n_hdr - 1) * hh
        for a, nombre in enumerate(c["dims_filas"] or ["Total"]):
            cv.create_rectangle(xs[a], ya, xs[a + 1], ya + hh, fill=col["cab"], outline=col["borde"])
            cv.create_text((xs[a] + xs[a + 1]) / 2, ya + hh / 2, text=self._texto_corto(nombre, self.anchos_dim[a] - 8, fb),
                           fill=col["texto"], font=fb)

    # ---- interacción -------------------------------------------------------------------------------------------
    def _fila_en(self, y):
        if y < self.n_hdr * self.HH:
            return None
        i = int((y - self.n_hdr * self.HH + self.yo) // self.RH)
        return i if 0 <= i < len(self.filas_v) else None

    def _borde_columna(self, x, y):
        """Índice de la columna (de valores) o ('d', a) de dimensión cuyo borde derecho está bajo el puntero."""
        if y > self.n_hdr * self.HH or self.cubo is None:
            return None
        if x >= self.w_dims:
            j = bisect.bisect_right(self.xs, x - self.w_dims + self.xo) - 1
            for jj in (j - 1, j):
                if 0 <= jj < len(self.cols_v) and abs(self._x(jj + 1) - x) <= T.px(4):
                    return jj
        else:
            xs = 0
            for a, w in enumerate(self.anchos_dim):
                xs += w
                if abs(xs - x) <= T.px(4):
                    return ("d", a)
        return None

    def _mover(self, e):
        if self._redim:
            return
        borde = self._borde_columna(e.x, e.y)
        self.lienzo.configure(cursor="sb_h_double_arrow" if borde is not None else "")
        i = self._fila_en(e.y)
        if i != self._hover:
            self._hover = i
            self._programar()

    def _salir(self):
        if self._hover is not None:
            self._hover = None
            self._programar()

    def _clic(self, e):
        borde = self._borde_columna(e.x, e.y)
        if borde is not None:
            ancho = self.anchos_dim[borde[1]] if isinstance(borde, tuple) else self.anchos[borde]
            self._redim = (borde, e.x, ancho)
            return
        for x0, y0, x1, y1, ruta in getattr(self, "_zonas_c", []) if e.y < self.n_hdr * self.HH else []:
            if x0 <= e.x <= x0 + T.px(18) and y0 <= e.y <= y1:
                self._alternar(ruta, "c")
                return
        for x0, y0, x1, y1, ruta in getattr(self, "_zonas_f", []) if e.x < self.w_dims else []:
            if x0 <= e.x <= x0 + T.px(18) and y0 <= e.y <= y1:
                self._alternar(ruta, "f")
                return

    def _doble(self, e):
        zonas = getattr(self, "_zonas_c", []) if e.y < self.n_hdr * self.HH else (
            getattr(self, "_zonas_f", []) if e.x < self.w_dims else [])
        eje = "c" if e.y < self.n_hdr * self.HH else "f"
        for x0, y0, x1, y1, ruta in zonas:
            if x0 <= e.x <= x1 and y0 <= e.y <= y1:
                self._alternar(ruta, eje)
                return

    def _arrastrar(self, e):
        if not self._redim:
            return
        borde, x_ini, ancho = self._redim
        nuevo = max(T.px(40), ancho + e.x - x_ini)
        if isinstance(borde, tuple):
            self.anchos_dim[borde[1]] = nuevo
            self.w_dims = sum(self.anchos_dim)
        else:
            self.anchos[borde] = nuevo
            r, t, k = self.cols_v[borde]
            self.anchos_val[(tuple(r), t, k)] = nuevo
            self.xs = [0]
            for w in self.anchos:
                self.xs.append(self.xs[-1] + w)
        self._programar()

    def _soltar(self, _e):
        self._redim = None

    def _alternar(self, ruta, eje):
        conj = self.col_f if eje == "f" else self.col_c
        (conj.discard if ruta in conj else conj.add)(ruta)
        self._aplanar()
        self._medir()
        w, h = self._area()
        self.yo = max(0, min(self.yo, self._total("y") - h))
        self.xo = max(0, min(self.xo, self._total("x") - w))
        self._programar()
        if self.al_cambiar_estado:
            self.al_cambiar_estado(self.estado())

    def expandir_todo(self):
        self.col_f, self.col_c = set(), set()
        self._alternar_global()

    def contraer_todo(self):
        """Contrae al primer nivel de filas y de columnas."""
        self.col_f = {n["ruta"] for n in self.cubo["arbol_filas"] if n["hijos"]}
        self.col_c = {n["ruta"] for n in self.cubo["arbol_cols"] if n["hijos"]}
        self._alternar_global()

    def _alternar_global(self):
        if self.cubo is None:
            return
        self._aplanar()
        self._medir()
        self.xo = self.yo = 0
        self._programar()
        if self.al_cambiar_estado:
            self.al_cambiar_estado(self.estado())

    # ---- copiar ----------------------------------------------------------------------------------------------
    def _menu(self, e):
        if self.cubo is None:
            return
        m = nuevo_menu(self)
        m.add_command(label="Copiar Tabla", command=self.copiar)
        m.add_command(label="Copiar Tabla con Formato", command=self.copiar_formato)
        m.add_command(label="Copiar Tabla como Imagen", command=self.copiar_imagen)
        m.add_separator()
        m.add_command(label="Expandir Todo", command=self.expandir_todo)
        m.add_command(label="Contraer Todo", command=self.contraer_todo)
        mostrar_menu(m, e)

    def datos_copia(self):
        c = self.cubo
        titulos = list(c["dims_filas"] or ["Total"])
        for ruta, tipo, k in self.cols_v:
            nombre = c["valores"][k]
            etq = "Total General" if tipo == "total" else (" · ".join(ruta) + (" Total" if tipo == "subtotal" else ""))
            titulos.append(nombre if not c["dims_cols"] else (f"{etq} · {nombre}" if len(c["valores"]) > 1 else etq))
        filas, estilos = [], []
        p = T.p
        for ruta, tipo, n in self.filas_v:
            if tipo == "total":
                etiquetas = ["Total General"] + [""] * (self.nd - 1)
            elif not c["dims_filas"]:
                etiquetas = ["Total"]
            else:
                etiquetas = list(ruta) + [""] * (self.nd - len(ruta))
                if tipo == "subtotal":
                    etiquetas[len(ruta) - 1] += " Total"
            vals = []
            for cr, _t, k in self.cols_v:
                v = pivot.valor(c, ruta, cr, k)
                vals.append("" if v is None else self.fmts[k](v))
            filas.append(etiquetas + vals)
            estilos.append({"fondo": p["total"], "negrita": True} if tipo == "total" else (
                {"fondo": colores_grupo(0)[2], "negrita": True} if tipo == "subtotal" else {}))
        anclas = ["w"] * len(titulos[:max(1, len(c["dims_filas"]))]) + ["e"] * len(self.cols_v)
        return titulos, filas, anclas, estilos

    def copiar(self):
        import portapapeles
        t, f, _a, _e = self.datos_copia()
        portapapeles.copiar_texto(portapapeles.tsv(t, f))
        avisar_estado(self, "Tabla copiada al portapapeles")

    def copiar_formato(self):
        import portapapeles
        t, f, a, e = self.datos_copia()
        if T.nombre == "oscuro":
            e = [{"negrita": x.get("negrita")} for x in e]
        portapapeles.copiar_html(portapapeles.tabla_html(t, f, a, e), portapapeles.tsv(t, f))
        avisar_estado(self, "Tabla copiada con formato: péguela en Excel, Word o PowerPoint")

    def copiar_imagen(self):
        import portapapeles
        import render
        t, f, a, e = self.datos_copia()
        if len(f) > 400:
            f, e = f[:400], e[:400]
            avisar_estado(self, "Imagen con las primeras 400 filas")
        portapapeles.copiar_imagen(render.tabla_a_imagen(t, f, a, e))
        avisar_estado(self, "Tabla copiada como imagen")


def cubo_desde_filas(dims, periodos, filas, nombre_valor="Tonelaje (t)", formato="int", nombre_col="Periodo"):
    """Cubo para la grilla a partir de filas con jerarquía fija (p. ej. Fase ▸ Flota Pala ▸ ID Pala) y una
    columna por periodo. filas: [{"claves": (fase, flota, id), "valores": [por periodo]}]."""
    celdas, arbol, idx = {}, [], {}
    nd = len(dims)

    def sumar(rp, cp, v):
        fila = celdas.setdefault((rp, cp), [0.0])
        fila[0] += v
    for f in filas:
        claves = tuple(str(x) for x in f["claves"])
        nivel = arbol
        for i in range(nd):
            ruta = claves[:i + 1]
            nodo = idx.get(ruta)
            if nodo is None:
                nodo = {"etq": claves[i], "ruta": ruta, "hijos": []}
                idx[ruta] = nodo
                nivel.append(nodo)
            nivel = nodo["hijos"]
        for j, v in enumerate(f["valores"]):
            if not v:
                continue
            cp = (periodos[j],)
            for i in range(nd + 1):
                sumar(claves[:i], cp, v)
                sumar(claves[:i], (), v)
    arbol_c = [{"etq": p, "ruta": (p,), "hijos": []} for p in periodos]
    return {"dims_filas": list(dims), "dims_cols": [nombre_col], "valores": [nombre_valor], "formatos": [formato],
            "modos": [None], "arbol_filas": arbol, "arbol_cols": arbol_c, "celdas": celdas, "avisos": []}
