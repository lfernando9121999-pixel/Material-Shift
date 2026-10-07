"""Componentes con el lenguaje visual de GitHub (Primer): pestañas subrayadas con contador,
etiquetas redondeadas, tarjetas de indicadores, controles segmentados y selección múltiple."""
import tkinter as tk
from tkinter import ttk

from tema import T


def _fondo(widget):
    try:
        return widget.cget("background")
    except tk.TclError:
        return T.p["panel"]


class Pildora(tk.Canvas):
    """Etiqueta redondeada (Counter / Label de GitHub)."""

    def __init__(self, master, texto="", color=None, relleno=None, fuente="chica", fondo=None):
        super().__init__(master, highlightthickness=0, borderwidth=0, height=T.px(20), width=10)
        self.texto, self.color, self.relleno, self.fuente, self._fondo = texto, color, relleno, fuente, fondo
        self._dibujar()
        T.registrar(self._dibujar)

    def poner(self, texto=None, color=None, relleno=None):
        if texto is not None:
            self.texto = texto
        if color is not None:
            self.color = color
        if relleno is not None:
            self.relleno = relleno
        self._dibujar()

    def _dibujar(self):
        p = T.p
        f = T.f[self.fuente]
        w = f.measure(self.texto) + T.px(16)
        h = T.px(20)
        fondo = self._fondo or _fondo(self.master)
        self.configure(width=w, height=h, background=fondo)
        self.delete("all")
        relleno = self.relleno or p["contador"]
        r = h / 2
        borde = self.color or relleno
        # rectángulo con extremos semicirculares
        self.create_oval(1, 1, h - 1, h - 1, fill=relleno, outline=borde)
        self.create_oval(w - h + 1, 1, w - 1, h - 1, fill=relleno, outline=borde)
        self.create_rectangle(r, 1, w - r, h - 1, fill=relleno, outline="")
        self.create_line(r, 1, w - r, 1, fill=borde)
        self.create_line(r, h - 1, w - r, h - 1, fill=borde)
        self.create_text(w / 2, h / 2, text=self.texto, font=f, fill=self.color or p["texto"])


class Pestanas(ttk.Frame):
    """Navegación con subrayado (UnderlineNav de GitHub). API compatible con lo usado de ttk.Notebook."""

    def __init__(self, master, fondo="panel", al_cambiar=None, grande=False, alinear="left", tarjeta=False):
        super().__init__(master, style="Panel.TFrame" if fondo == "panel" else "TFrame")
        self._clave_fondo = fondo
        self.al_cambiar = al_cambiar
        self.grande = grande
        self.tarjeta = tarjeta
        self.barra = tk.Frame(self, highlightthickness=0)
        self.barra.pack(fill="x")
        # 'izquierda' contiene las pestañas; 'derecha' admite controles fijos (p. ej. la réplica)
        self.izquierda = tk.Frame(self.barra, highlightthickness=0)
        self.derecha = tk.Frame(self.barra, highlightthickness=0)
        self.derecha.pack(side="right", fill="y")
        self.izquierda.pack(side="right" if alinear == "right" else "left", fill="y")
        self.linea = tk.Frame(self, height=1)
        if not tarjeta:
            self.linea.pack(fill="x")
        # las páginas se muestran dentro de 'contenido' (recuadro con borde tenue si tarjeta=True)
        self.contenido = tk.Frame(self, highlightthickness=1 if tarjeta else 0, borderwidth=0)
        self.contenido.pack(fill="both", expand=True)
        self._tabs = []
        self._actual = None
        self._visibles = None
        # Si las pestañas no caben, las últimas pasan a un menú «»»
        self.mas = tk.Label(self.izquierda, text="  »  ", cursor="hand2")
        self.mas.bind("<Button-1>", self._menu_desborde)
        self.barra.bind("<Configure>", lambda e: self.after_idle(self._ajustar_desborde))
        self.derecha.bind("<Configure>", lambda e: self._reajustar())
        self._pintar()
        T.registrar(self._pintar)

    def _reajustar(self):
        self._visibles = None
        self.after_idle(self._ajustar_desborde)

    def _ajustar_desborde(self):
        try:
            disponible = self.barra.winfo_width() - self.derecha.winfo_reqwidth() - T.px(36)
        except tk.TclError:
            return
        if disponible < 50 or not self._tabs:
            return
        anchos = [t["caja"].winfo_reqwidth() + T.px(2) for t in self._tabs]
        if sum(anchos) <= disponible + T.px(36):
            visibles = set(range(len(self._tabs)))
        else:
            sel = next((i for i, t in enumerate(self._tabs) if t["pagina"] is self._actual), 0)
            visibles, usado = {sel}, anchos[sel]
            for i, a in enumerate(anchos):
                if i != sel and usado + a <= disponible:
                    visibles.add(i)
                    usado += a
                elif i != sel:
                    break
        if visibles == self._visibles:
            return
        self._visibles = visibles
        for t in self._tabs:
            t["caja"].pack_forget()
        self.mas.pack_forget()
        for i, t in enumerate(self._tabs):
            if i in visibles:
                t["caja"].pack(side="left", padx=(0, T.px(2)))
        if len(visibles) < len(self._tabs):
            self.mas.pack(side="left")

    def _menu_desborde(self, e):
        p = T.p
        m = tk.Menu(self, tearoff=0, bg=p["menu"], fg=p["texto"], activebackground=p["acento"],
                    activeforeground=p["acento_txt"], font=T.f["base"])
        for i, t in enumerate(self._tabs):
            if self._visibles is not None and i not in self._visibles:
                m.add_command(label=t["lbl"].cget("text"), command=lambda pg=t["pagina"]: self.select(pg),
                              state="disabled" if t["estado"] == "disabled" else "normal")
        try:
            m.tk_popup(e.x_root, e.y_root)
        finally:
            m.grab_release()

    # API ---------------------------------------------------------------
    def add(self, pagina, text="", contador=None, icono=None):
        caja = tk.Frame(self.izquierda, cursor="hand2")
        caja.pack(side="left", padx=(0, T.px(2)))
        self._visibles = None
        # separador tenue entre pestañas
        sep = tk.Frame(caja, width=1)
        if self._tabs:
            sep.pack(side="left", fill="y", pady=(T.px(9 if self.grande else 7), T.px(7 if self.grande else 6)))
        interior = tk.Frame(caja)
        interior.pack(padx=T.px(8 if self.grande else 9), pady=(T.px(7 if self.grande else 5), T.px(4)))
        lbl = tk.Label(interior, text=text)
        lbl.pack(side="left")
        marca = tk.Label(interior, text="*")
        pil = Pildora(interior, "" if contador is None else str(contador))
        if contador is not None:
            pil.pack(side="left", padx=(T.px(6), 0))
        sub = tk.Frame(caja, height=T.px(2))
        sub.pack(fill="x", side="bottom")
        tab = {"pagina": pagina, "caja": caja, "interior": interior, "lbl": lbl, "pil": pil,
               "sub": sub, "estado": "normal", "contador": contador, "icono": icono,
               "marca": marca, "con_marca": False, "sep": sep}
        self._tabs.append(tab)
        for w in (caja, interior, lbl, pil, marca):
            w.bind("<Button-1>", lambda e, p=pagina: self._clic(p))
            w.bind("<Enter>", lambda e, t=tab: self._hover(t, True))
            w.bind("<Leave>", lambda e, t=tab: self._hover(t, False))
            w.bind("<Button-3>", lambda e, p=pagina: self.event_generate_menu(e, p))
            w.bind("<Button-2>", lambda e, p=pagina: self.event_generate_medio(p))
        if self._actual is None:
            self.select(pagina)
        else:
            self._pintar()

    menu_pestana = None        # callback(evento, pagina)
    medio_pestana = None       # callback(pagina)

    def event_generate_menu(self, e, pagina):
        if self.menu_pestana:
            self.menu_pestana(e, pagina)

    def event_generate_medio(self, pagina):
        if self.medio_pestana:
            self.medio_pestana(pagina)

    def tabs(self):
        return [t["pagina"] for t in self._tabs]

    def _tab(self, pagina):
        for t in self._tabs:
            if t["pagina"] is pagina or str(t["pagina"]) == str(pagina):
                return t
        return None

    def select(self, pagina=None):
        if pagina is None:
            return self._actual
        t = self._tab(pagina)
        if t is None or t["estado"] == "disabled":
            return self._actual
        if self._actual is not None and self._actual is not t["pagina"]:
            self._actual.pack_forget()
        cambio = self._actual is not t["pagina"]
        self._actual = t["pagina"]
        if getattr(self._actual, "_sucia", False) and hasattr(self._actual, "refrescar"):
            self._actual._sucia = False
            self._actual.refrescar()
        self._actual.pack(in_=self.contenido, fill="both", expand=True)
        if cambio:
            # la ventana emergente de otra pestaña se cierra (conservando lo que se dejó)
            from ui_comun import cerrar_emergente
            cerrar_emergente(salvo=self._actual)
        self._pintar()
        if cambio:
            self._visibles = None
            self.after_idle(self._ajustar_desborde)
        if cambio and self.al_cambiar:
            self.al_cambiar(self._actual)
        return self._actual

    def tab(self, pagina, state=None, text=None, contador="__sin__", marca=None):
        t = self._tab(pagina)
        if t is None:
            return
        if state is not None:
            t["estado"] = state
        if text is not None:
            t["lbl"].configure(text=text)
        if marca is not None and marca != t["con_marca"]:
            t["con_marca"] = marca
            if marca:          # * roja: datos obligatorios pendientes
                t["marca"].pack(side="left", after=t["lbl"], padx=(T.px(2), 0))
            else:
                t["marca"].pack_forget()
        if contador != "__sin__":
            t["contador"] = contador
            if contador is None:
                t["pil"].pack_forget()
            else:
                t["pil"].poner(str(contador))
                t["pil"].pack(side="left", padx=(T.px(6), 0))
        if t["estado"] == "disabled" and self._actual is t["pagina"]:
            otro = next((x["pagina"] for x in self._tabs if x["estado"] != "disabled"), None)
            if otro is not None:
                self.select(otro)
        self._pintar()
        self._visibles = None
        self.after_idle(self._ajustar_desborde)

    def forget(self, pagina):
        t = self._tab(pagina)
        if t is None:
            return
        t["caja"].destroy()
        self._tabs.remove(t)
        if self._actual is t["pagina"]:
            t["pagina"].pack_forget()
            self._actual = None
            if self._tabs:
                self.select(self._tabs[0]["pagina"])

    # Visual --------------------------------------------------------------
    def _clic(self, pagina):
        self.select(pagina)

    def _hover(self, t, dentro):
        if t["estado"] == "disabled" or t["pagina"] is self._actual:
            return
        c = T.p["hover"] if dentro else self._color_fondo()
        for w in (t["caja"], t["interior"], t["lbl"], t["marca"]):
            w.configure(background=c)
        t["pil"].configure(background=c)
        t["pil"]._fondo = c
        t["pil"]._dibujar()

    def _color_fondo(self):
        return T.p["panel"] if self._clave_fondo == "panel" else T.p["bg"]

    def marcar_sucias(self, excepto=None):
        """Las páginas ocultas se reconstruyen al mostrarse (la visible se refresca de inmediato)."""
        for t in self._tabs:
            if t["pagina"] is not excepto:
                t["pagina"]._sucia = True

    def _pintar(self):
        p = T.p
        fondo = self._color_fondo()
        for w in (self.barra, self.izquierda, self.derecha):
            w.configure(background=fondo)
        self.linea.configure(background=p["borde"])
        self.contenido.configure(background=p["panel"], highlightbackground=p["borde"], highlightcolor=p["borde"])
        self.mas.configure(background=fondo, foreground=p["acento"], font=T.f["subtitulo"])
        fuente = T.f["grande"] if self.grande else T.f["base"]
        fuente_act = T.f["subtitulo"] if self.grande else T.f["negrita"]
        for t in self._tabs:
            activo = t["pagina"] is self._actual
            deshab = t["estado"] == "disabled"
            for w in (t["caja"], t["interior"]):
                w.configure(background=fondo)
            t["sep"].configure(background=p["separador"])
            t["lbl"].configure(background=fondo, font=fuente_act if activo else fuente,
                               foreground=p["deshab"] if deshab else p["texto"])
            t["marca"].configure(background=fondo, foreground=p["requerido"], font=fuente_act)
            t["caja"].configure(cursor="arrow" if deshab else "hand2")
            t["sub"].configure(background=p["nav_sel"] if activo else fondo)
            t["pil"]._fondo = fondo
            t["pil"]._dibujar()


class Segmentado(ttk.Frame):
    """Control segmentado (botones excluyentes, el elegido resaltado)."""

    def __init__(self, master, opciones, valor=None, al_cambiar=None, estilo="Panel.TFrame"):
        super().__init__(master, style=estilo)
        self.opciones = opciones            # lista de (clave, texto)
        self.var = tk.StringVar(value=valor or opciones[0][0])
        self.al_cambiar = al_cambiar
        for clave, texto in opciones:
            ttk.Radiobutton(self, text=texto, value=clave, variable=self.var, style="Segmento.Toolbutton",
                            command=self._cambio).pack(side="left", padx=(0, 1))

    def _cambio(self):
        if self.al_cambiar:
            self.al_cambiar(self.var.get())

    def get(self):
        return self.var.get()

    def set(self, valor):
        self.var.set(valor)


class TarjetaKPI(tk.Frame):
    """Caja de indicador (Box de GitHub) con franja de color.

    filas: lista opcional [(nombre, valor)] (p. ej. el detalle por flota) alineada a la derecha de la
    tarjeta. columnas: títulos opcionales de la lista (p. ej. ("Flota", "Suma", "Prom.")).
    filas_min: alto constante (mismo alto en todas las subpestañas aunque cambie el N° de flotas).
    """

    def __init__(self, master, titulo, valor, detalle="", color=None, filas=None, columnas=None, filas_min=0):
        super().__init__(master, highlightthickness=1)
        self.color = color
        self._franja = tk.Frame(self, width=T.px(3))
        self._franja.pack(side="left", fill="y")
        self._cuerpo = tk.Frame(self)
        self._cuerpo.pack(side="left", fill="both", expand=True, padx=T.px(11), pady=T.px(7))
        self._t = tk.Label(self._cuerpo, text=titulo, anchor="w")
        self._t.pack(fill="x")
        cont = tk.Frame(self._cuerpo)
        cont.pack(fill="both", expand=True)
        self._labels = [self._cuerpo, cont]
        self._v = self._d = None
        self._cont, self._izq, self._g, self._abajo = cont, None, None, False
        if valor:
            izq = self._izq = tk.Frame(cont)
            izq.pack(side="left", anchor="n")
            self._v = tk.Label(izq, text=valor, anchor="w")
            self._v.pack(fill="x")
            self._labels.append(izq)
            if detalle:
                self._d = tk.Label(izq, text=detalle, anchor="w")
                self._d.pack(fill="x")
        self._lista = []
        filas = list(filas or [])
        if filas or filas_min:
            # detalle alineado a la derecha de la tarjeta (debajo del valor si la tarjeta es angosta)
            g = self._g = tk.Frame(cont)
            g.pack(side="right", anchor="n", padx=(T.px(14), 0))
            cont.bind("<Configure>", self._acomodar, add="+")
            self._labels.append(g)
            r0 = 0
            if columnas:
                for j, c in enumerate(columnas):
                    lb = tk.Label(g, text=c, anchor="e" if j else "w")
                    lb.grid(row=0, column=j, sticky="ew", padx=(0 if j == 0 else T.px(10), 0))
                    self._lista.append((lb, "cab"))
                r0 = 1
            n_col = max([len(f) for f in filas] + [len(columnas or [])] + [2])
            for i in range(max(len(filas), filas_min - r0)):
                fila = filas[i] if i < len(filas) else [""] * n_col
                for j, v in enumerate(fila):
                    lb = tk.Label(g, text=v, anchor="e" if j else "w")
                    lb.grid(row=r0 + i, column=j, sticky="ew", padx=(0 if j == 0 else T.px(10), 0))
                    self._lista.append((lb, "nom" if j == 0 else "val"))
        self._pintar()
        T.registrar(self._pintar)

    def ancho_minimo(self):
        """Ancho con el que se ve todo el contenido (con el detalle debajo del valor)."""
        partes = [self._t.winfo_reqwidth()]
        for w in (self._izq, self._g):
            if w is not None:
                partes.append(w.winfo_reqwidth())
        return max(partes) + T.px(3) + 2 * T.px(11) + 4

    def _acomodar(self, e=None):
        """Si el detalle no cabe a la derecha del valor, pasa debajo (sin cortar nombres ni cifras)."""
        try:
            disponible = self._cont.winfo_width()
            necesario = (self._izq.winfo_reqwidth() if self._izq else 0) + self._g.winfo_reqwidth() + T.px(14)
        except tk.TclError:
            return
        abajo = disponible > 1 and necesario > disponible
        if abajo == self._abajo:
            return
        self._abajo = abajo
        self._g.pack_forget()
        if abajo:
            if self._izq is not None:
                self._izq.pack_configure(side="top", anchor="w")
            self._g.pack(side="top", anchor="w", pady=(T.px(4), 0))
        else:
            if self._izq is not None:
                self._izq.pack_configure(side="left", anchor="n")
            self._g.pack(side="right", anchor="n", padx=(T.px(14), 0))

    def _pintar(self):
        p = T.p
        self.configure(background=p["panel"], highlightbackground=p["borde"], highlightcolor=p["borde"])
        self._franja.configure(background=self.color or p["acento"])
        for w in self._labels:
            w.configure(background=p["panel"])
        self._t.configure(background=p["panel"], foreground=p["suave"], font=T.f["chica"])
        if self._v is not None:
            self._v.configure(background=p["panel"], foreground=p["texto"], font=T.f["kpi"])
        if self._d is not None:
            self._d.configure(background=p["panel"], foreground=p["suave"], font=T.f["chica"])
        for lb, tipo in self._lista:
            lb.configure(background=p["panel"],
                         foreground=p["texto"] if tipo == "val" else p["suave"],
                         font=T.f["negrita"] if tipo == "val" else T.f["chica"])


class MultiSeleccion(ttk.Frame):
    """Lista desplegable con casillas (estilo filtro de Excel): Limpiar Filtro, Buscar (más de 8 valores),
    (Seleccionar Todo) y valores. Se aplica al cerrar la lista (clic fuera, Aceptar u otra ventana)."""

    def __init__(self, master, etiqueta, opciones, al_cambiar=None, plural="Todas", ancho=26, diferido=True,
                 etiquetas=None):
        super().__init__(master, style="Panel.TFrame")
        self.diferido = diferido
        self.etiqueta, self.plural, self.al_cambiar = etiqueta, plural, al_cambiar
        self.opciones = list(opciones)
        self.etiquetas = etiquetas or {}
        self.seleccion = None                 # None = todas
        self._popup = None
        if etiqueta:
            ttk.Label(self, text=etiqueta, style="PanelSuave.TLabel").pack(side="left", padx=(0, T.px(6)))
        self.boton = ttk.Button(self, width=ancho, command=self._abrir, style="TButton")
        self.boton.pack(side="left")
        self._texto()

    def set_opciones(self, opciones, conservar=True):
        self.opciones = list(opciones)
        if self.seleccion is not None:
            self.seleccion = [o for o in self.seleccion if o in self.opciones] if conservar else None
            if not self.seleccion or len(self.seleccion) == len(self.opciones):
                self.seleccion = None
        self._texto()

    def valores(self):
        return list(self.opciones) if self.seleccion is None else list(self.seleccion)

    def _texto(self):
        if self.seleccion is None:
            t = f"{self.plural}  ▾"
        elif not self.seleccion:
            t = "Ninguna  ▾"
        elif len(self.seleccion) == 1:
            t = f"{self.etiquetas.get(self.seleccion[0], self.seleccion[0])}  ▾"
        else:
            t = f"{len(self.seleccion)} Seleccionados  ▾"
        self.boton.configure(text=t)

    def _abrir(self):
        if self._popup is not None and self._popup.winfo_exists():
            self._popup.cerrar(True)
            return
        self._popup = _lista_emergente(self)
        self._popup.mostrar()


def _lista_emergente(m):
    """Emergente de MultiSeleccion (ui_comun se importa al usarla: evita importaciones circulares)."""
    from ui_comun import Emergente, ListaChequeo, _fila_menu

    class Lista(Emergente):
        def __init__(self):
            super().__init__(m.boton, m.etiqueta or m.plural, abridor=m.boton)
            c = self.cuerpo
            _fila_menu(c, f"Limpiar Filtro{(' de «' + m.etiqueta + '»') if m.etiqueta else ''}", self._limpiar,
                       "limpiar_filtro", activo=m.seleccion is not None)
            ttk.Frame(c, style="Linea.TFrame", height=1).pack(fill="x", padx=T.px(6), pady=T.px(3))
            self.lista = ListaChequeo(c, m.opciones, m.seleccion, etiquetas=m.etiquetas, alto=11,
                                      al_cambiar=self._marcado)
            self.lista.pack(fill="both", expand=True)
            pie = tk.Frame(c, background=T.p["panel"])
            pie.pack(fill="x", padx=T.px(8), pady=T.px(8))
            ttk.Button(pie, text="Aceptar", style="Accent.TButton", command=lambda: self.cerrar(True)).pack(
                side="right")
            ttk.Button(pie, text="Cancelar", style="Chico.TButton", command=lambda: self.cerrar(False)).pack(
                side="right", padx=(0, T.px(6)))

        def _marcado(self):
            if not m.diferido:
                self.aplicar()

        def _limpiar(self):
            self.lista.marcados = set(m.opciones)
            self.cerrar(True)

        def aplicar(self):
            sel = self.lista.seleccion()
            if sel == []:
                return
            if sel == m.seleccion or (sel is not None and m.seleccion is not None and set(sel) == set(m.seleccion)):
                return
            m.seleccion = sel
            try:
                m._texto()
            except tk.TclError:
                pass
            if m.al_cambiar:
                m.al_cambiar(m.valores())

        def cerrar(self, aplicar=True):
            super().cerrar(aplicar)
            if getattr(m, "_popup", None) is self:
                m._popup = None
    return Lista()


class TiraVertical(tk.Canvas):
    """Pestañas verticales (texto girado) para elegir, p. ej., la flota de un gráfico."""

    def __init__(self, master, opciones, valor=None, al_cambiar=None, ancho=30, alto_min=90):
        super().__init__(master, width=T.px(ancho), highlightthickness=0, borderwidth=0, cursor="hand2")
        self.opciones, self.al_cambiar = list(opciones), al_cambiar
        self.valor = valor if valor in self.opciones else (self.opciones[0] if self.opciones else None)
        self.alto_min = alto_min
        self.bind("<Configure>", lambda e: self._dibujar())
        self.bind("<Button-1>", self._clic)
        T.registrar(self._dibujar)

    def _cajas(self):
        f = T.f["negrita"]
        y, cajas = 0, []
        for o in self.opciones:
            h = max(T.px(self.alto_min), f.measure(o) + T.px(28))
            cajas.append((o, y, y + h))
            y += h + T.px(4)
        return cajas

    def alto_requerido(self):
        c = self._cajas()
        return c[-1][2] if c else 0

    def _dibujar(self):
        p = T.p
        try:
            self.configure(background=p["panel"])
        except tk.TclError:
            return
        self.delete("all")
        w = self.winfo_width() if self.winfo_width() > 4 else T.px(30)
        for o, y0, y1 in self._cajas():
            activo = o == self.valor
            self.create_rectangle(1, y0, w - 1, y1, fill=p["acento"] if activo else p["panel_alt"],
                                  outline=p["acento"] if activo else p["borde"])
            self.create_text(w / 2, (y0 + y1) / 2, text=o, angle=90, font=T.f["negrita"],
                             fill=p["acento_txt"] if activo else p["texto"])

    def _clic(self, e):
        for o, y0, y1 in self._cajas():
            if y0 <= e.y <= y1 and o != self.valor:
                self.valor = o
                self._dibujar()
                if self.al_cambiar:
                    self.al_cambiar(o)
                return

class Interruptor(tk.Frame):
    """Interruptor encendido/apagado (Toggle Switch) con su etiqueta."""

    def __init__(self, master, texto, valor=False, al_cambiar=None):
        super().__init__(master)
        self.valor, self.al_cambiar = bool(valor), al_cambiar
        self.lienzo = tk.Canvas(self, width=T.px(34), height=T.px(18), highlightthickness=0, borderwidth=0,
                                cursor="hand2")
        self.lienzo.pack(side="left")
        self.lbl = tk.Label(self, text=texto, cursor="hand2")
        self.lbl.pack(side="left", padx=(T.px(6), 0))
        for w in (self.lienzo, self.lbl):
            w.bind("<Button-1>", self._clic)
        self._pintar()
        T.registrar(self._pintar)

    def _clic(self, _e=None):
        self.valor = not self.valor
        self._pintar()
        if self.al_cambiar:
            self.after_idle(lambda: self.al_cambiar(self.valor))

    def _pintar(self):
        p = T.p
        fondo = _fondo(self.master)
        self.configure(background=fondo)
        self.lbl.configure(background=fondo, foreground=p["texto"], font=T.f["chica"])
        c = self.lienzo
        c.configure(background=fondo)
        c.delete("all")
        w, h = T.px(34), T.px(18)
        color = p["acento"] if self.valor else p["borde"]
        r = h / 2
        c.create_oval(1, 1, h - 1, h - 1, fill=color, outline=color)
        c.create_oval(w - h + 1, 1, w - 1, h - 1, fill=color, outline=color)
        c.create_rectangle(r, 1, w - r, h - 1, fill=color, outline=color)
        x = w - r if self.valor else r
        c.create_oval(x - r + 3, 3, x + r - 3, h - 3, fill="#FFFFFF", outline="")


class TarjetaTendencia(tk.Frame):
    """Tarjeta de indicador con mini gráfico de la serie (sparkline de barras) y el periodo destacado.

    Diseño distinto a las demás tarjetas: franja superior de color, valor grande y una tira de barras
    con el comportamiento del periodo; la barra del indicador (máximo, mínimo…) se resalta."""

    def __init__(self, master, titulo, valor, detalle, color, serie=None, destacar=None, linea=None):
        super().__init__(master, highlightthickness=1)
        self.titulo, self.valor, self.detalle, self.color = titulo, valor, detalle, color
        self.serie, self.destacar, self.linea = list(serie or []), destacar, linea
        self.lienzo = tk.Canvas(self, height=T.px(92), highlightthickness=0, borderwidth=0)
        self.lienzo.pack(fill="both", expand=True)
        self._id = None
        self.lienzo.bind("<Configure>", lambda e: self._programar())
        T.registrar(self._pintar)

    def _programar(self):
        if self._id is None:
            self._id = self.after_idle(self._pintar)

    def _pintar(self):
        self._id = None
        p = T.p
        self.configure(background=p["panel"], highlightbackground=p["borde"], highlightcolor=p["borde"])
        c = self.lienzo
        c.configure(background=p["panel"])
        c.delete("all")
        W, H = c.winfo_width(), c.winfo_height()
        if W < 40:
            return
        px = T.px
        c.create_rectangle(0, 0, W, px(3), fill=self.color, outline="")
        c.create_text(px(12), px(14), text=self.titulo, anchor="nw", fill=p["suave"], font=T.f["negrita"])
        c.create_text(px(12), px(32), text=self.valor, anchor="nw", fill=p["texto"], font=T.f["kpi"])
        c.create_text(px(12), H - px(10), text=self.detalle, anchor="sw", fill=self.color, font=T.f["negrita"])
        # mini gráfico a la derecha
        s = [max(0.0, float(v or 0.0)) for v in self.serie]
        if len(s) >= 2 and max(s) > 0:
            x0, x1 = W * 0.50, W - px(12)
            y1, y0 = H - px(12), px(16)
            n = len(s)
            paso = (x1 - x0) / n
            ancho = max(1.0, paso * (0.68 if n <= 60 else 0.9))
            vmax = max(s)
            suave = p["borde"]
            for i, v in enumerate(s):
                h = (y1 - y0) * v / vmax
                col = self.color if i == self.destacar else suave
                xa = x0 + i * paso + (paso - ancho) / 2
                c.create_rectangle(xa, y1 - h, xa + ancho, y1, fill=col, outline="")
            if self.linea is not None and vmax:
                y = y1 - (y1 - y0) * self.linea / vmax
                c.create_line(x0, y, x1, y, fill=self.color, dash=(3, 2))
