"""Componentes de interfaz reutilizables.

· Ventanas emergentes (listas desplegables, filtros y herramientas): pegadas al programa, en la misma
  pantalla, movibles, con botón ✕ y una sola a la vez; al abrir otra o cambiar de pestaña se cierra la
  anterior conservando lo que se dejó.
· Tablas a todo el ancho (columnas proporcionales, datos centrados bajo su encabezado), columnas que se
  reordenan arrastrando el encabezado, colores por grupo, filtros/orden desde el encabezado y menú
  Copiar Tabla / con Formato / como Imagen.
· Contenedor con desplazamiento que se reconstruye sin parpadeo, rueda del mouse, avisos y filtros
  vinculados por página.
"""
import re
import tkinter as tk
from tkinter import ttk

from tema import T, ajustar_a_pantalla, centrar, titulo_oscuro

# ----------------------------------------------------------------------------
# Colores por grupo: un color tenue por grupo (filas) y un tono algo más marcado para el título del grupo
# ----------------------------------------------------------------------------
_GRUPOS = {
    "claro": ["#EEF4FC", "#EDF7F0", "#FCF7EA", "#F3F0FC", "#ECF6F7", "#FCF1F0"],
    "oscuro": ["#121E2E", "#112218", "#221D10", "#1C172B", "#0F2224", "#251414"],
}
_GRUPOS_FUERTE = {
    "claro": ["#DCE8F8", "#DCEFE2", "#F7ECCD", "#E6E0F8", "#D9EDEF", "#F7E0DD"],
    "oscuro": ["#1C3453", "#1B3926", "#3B3219", "#2D2547", "#18383A", "#3E211F"],
}


def colores_grupo(i):
    """(color de las filas, mismo color, tono del título) del grupo i (un solo color por grupo)."""
    a = _GRUPOS[T.nombre][i % 6]
    return a, a, _GRUPOS_FUERTE[T.nombre][i % 6]


SANGRIA = "   "
_NUM = re.compile(r"[^0-9.\-]")


def titulo_linea(titulo):
    """Encabezado de tabla en una línea (Tk dibuja una sola línea en los encabezados)."""
    partes = [p.strip() for p in str(titulo).split("\n") if p.strip()]
    if len(partes) <= 1:
        return partes[0] if partes else ""
    texto = partes[0]
    for p in partes[1:]:
        texto += (" " if p.startswith("(") else "  ▸  ") + p
    return texto


def _numero(texto):
    t = _NUM.sub("", str(texto))
    try:
        return float(t) if t not in ("", "-", ".") else None
    except ValueError:
        return None


def nuevo_menu(widget):
    p = T.p
    return tk.Menu(widget, tearoff=0, bg=p["menu"], fg=p["texto"], activebackground=p["acento"],
                   activeforeground=p["acento_txt"], disabledforeground=p["deshab"], font=T.f["base"])


def mostrar_menu(menu, e):
    try:
        menu.tk_popup(e.x_root, e.y_root)
    finally:
        menu.grab_release()


def avisar_estado(widget, texto):
    """Mensaje en la barra de estado de la ventana (si existe)."""
    try:
        top = widget.winfo_toplevel()
        app = getattr(top, "_sima_app", None)
        if app is not None:
            app.mensaje(texto)
    except tk.TclError:
        pass


# ----------------------------------------------------------------------------
# Rueda del mouse: desplaza el contenedor bajo el puntero (no cambia valores de listas)
# ----------------------------------------------------------------------------
def instalar_rueda(root):
    for clase in ("TCombobox", "TSpinbox", "Spinbox", "Treeview", "Text", "Listbox", "TScale", "Scale"):
        root.bind_class(clase, "<MouseWheel>", lambda e: None)
        root.bind_class(clase, "<Shift-MouseWheel>", lambda e: None)
    root.bind_all("<MouseWheel>", lambda e: _rueda(root, e, False))
    root.bind_all("<Shift-MouseWheel>", lambda e: _rueda(root, e, True))


def _rueda(root, e, horizontal):
    try:
        w = root.winfo_containing(e.x_root, e.y_root)
    except (KeyError, tk.TclError):
        return
    pasos = int(-e.delta / 120) * 3 if abs(e.delta) >= 120 else (-1 if e.delta > 0 else 1)
    desplazables = (ttk.Treeview, tk.Text, tk.Listbox, tk.Canvas)

    def mover(obj):
        if obj is None or not isinstance(obj, desplazables) or getattr(obj, "_sin_rueda", False):
            return False
        try:
            a, b = (obj.xview() if horizontal else obj.yview())
        except (tk.TclError, AttributeError, ValueError, TypeError):
            return False
        if (pasos < 0 and float(a) > 0.0) or (pasos > 0 and float(b) < 1.0):
            (obj.xview_scroll if horizontal else obj.yview_scroll)(pasos, "units")
            return True
        return False
    while w is not None:
        if isinstance(w, (ttk.Scrollbar, tk.Scrollbar)):
            if any(mover(s) for s in w.master.winfo_children() if s is not w):
                return "break"
        elif mover(w):
            return "break"
        elif mover(getattr(w, "_lienzo_rueda", None)):
            return "break"
        if isinstance(w, (tk.Tk, tk.Toplevel)):
            break
        w = w.master
    return "break"


# ----------------------------------------------------------------------------
# Ventanas emergentes: una a la vez
# ----------------------------------------------------------------------------
_activa = [None]


def _vive(w):
    try:
        return bool(w is not None and w.winfo_exists())
    except tk.TclError:
        return False


def _pertenece(widget, contenedor):
    w = widget
    while w is not None:
        if w is contenedor:
            return True
        w = getattr(w, "master", None)
    return False


def emergente_activa():
    return _activa[0] if _vive(_activa[0]) else None


def cerrar_emergente(salvo=None, solo_ligeras=False, aplicar=True):
    """Cierra la ventana emergente abierta (conservando lo que se dejó, salvo aplicar=False). Con 'salvo'
    se conserva si pertenece a esa página."""
    v = _activa[0]
    if not _vive(v):
        _activa[0] = None
        return False
    if salvo is not None and _pertenece(getattr(v, "pagina", None), salvo):
        return False
    if solo_ligeras and not isinstance(v, Emergente):
        return False
    _activa[0] = None
    try:
        v.cerrar(aplicar)
    except tk.TclError:
        pass
    return True


def _registrar(v):
    cerrar_emergente()
    _activa[0] = v


class Emergente(tk.Toplevel):
    """Ventana emergente ligera (lista desplegable o filtro): sin marco del sistema, pegada a la ventana del
    programa, con barra de título para moverla y botón ✕. Clic fuera: se cierra conservando los cambios;
    Esc: se cierra sin cambios."""

    def __init__(self, ancla, titulo, pagina=None, abridor=None):
        top = ancla.winfo_toplevel()
        _registrar(self)
        super().__init__(top)
        self.withdraw()
        self.overrideredirect(True)
        self.transient(top)
        self.ancla, self.abridor = ancla, abridor
        self.pagina = pagina if pagina is not None else ancla
        p = T.p
        self.configure(background=p["borde"])
        self.marco = tk.Frame(self, background=p["panel"])
        self.marco.pack(fill="both", expand=True, padx=1, pady=1)
        barra = tk.Frame(self.marco, background=p["panel_alt"], cursor="fleur")
        barra.pack(fill="x")
        self.lbl_titulo = tk.Label(barra, text=titulo_linea(titulo), background=p["panel_alt"], foreground=p["texto"],
                                   font=T.f["negrita"], anchor="w", cursor="fleur")
        self.lbl_titulo.pack(side="left", fill="x", expand=True, padx=(T.px(10), 0), pady=T.px(5))
        x = tk.Label(barra, text="✕", background=p["panel_alt"], foreground=p["suave"], font=T.f["base"],
                     padx=T.px(9), cursor="hand2")
        x.pack(side="right", fill="y")
        x.bind("<Enter>", lambda e: x.configure(background=p["error"], foreground="#FFFFFF"))
        x.bind("<Leave>", lambda e: x.configure(background=p["panel_alt"], foreground=p["suave"]))
        x.bind("<Button-1>", lambda e: self.after_idle(lambda: self._cerrar_desde_x()))
        for w in (barra, self.lbl_titulo):
            w.bind("<ButtonPress-1>", self._ini_mover)
            w.bind("<B1-Motion>", self._mover)
        self.cuerpo = tk.Frame(self.marco, background=p["panel"])
        self.cuerpo.pack(fill="both", expand=True)
        self.bind("<Escape>", lambda e: self.cerrar(False))
        self._id_fuera = top.bind("<ButtonPress-1>", self._clic_fuera, add="+")
        self._top = top
        self.bind("<Destroy>", self._al_destruir)

    # --- posición ---------------------------------------------------------------------------
    def mostrar(self, x=None, y=None):
        """Muestra la ventana bajo el ancla (o en x, y), completa dentro del monitor del programa."""
        self.update_idletasks()
        w, h = self.winfo_reqwidth(), self.winfo_reqheight()
        if x is None:
            x = self.ancla.winfo_rootx()
            y = self.ancla.winfo_rooty() + self.ancla.winfo_height() + 2
        ref = (self.ancla.winfo_rootx() + 4, self.ancla.winfo_rooty() + 4)
        x, y = ajustar_a_pantalla(x, y, w, h, ref, self)
        self.geometry(f"+{x}+{y}")
        self.deiconify()
        self.lift()
        try:
            self.focus_force()
        except tk.TclError:
            pass
        return self

    def _ini_mover(self, e):
        self._dx, self._dy = e.x_root - self.winfo_rootx(), e.y_root - self.winfo_rooty()

    def _mover(self, e):
        self.geometry(f"+{e.x_root - getattr(self, '_dx', 0)}+{e.y_root - getattr(self, '_dy', 0)}")

    # --- cierre -----------------------------------------------------------------------------
    def _clic_fuera(self, ev):
        w = ev.widget
        if self.abridor is not None and _pertenece(w, self.abridor):
            return                       # el botón que la abrió la alterna por sí mismo
        while w is not None:
            if w is self:
                return
            w = getattr(w, "master", None)
        if _activa[0] is self:
            _activa[0] = None
        self.after_idle(lambda: self.cerrar(True))

    def _cerrar_desde_x(self):
        if _activa[0] is self:
            _activa[0] = None
        self.cerrar(True)

    def aplicar(self):
        """Se invoca al cerrar conservando los cambios (las subclases aplican la selección)."""

    def cerrar(self, aplicar=True):
        if _activa[0] is self:
            _activa[0] = None
        if not _vive(self):
            return
        self.withdraw()
        try:
            if aplicar:
                self.aplicar()
        finally:
            if _vive(self):
                self.destroy()

    def _al_destruir(self, ev):
        if ev.widget is self:
            try:
                self._top.unbind("<ButtonPress-1>", self._id_fuera)
            except tk.TclError:
                pass
            if _activa[0] is self:
                _activa[0] = None


class VentanaHerramienta(tk.Toplevel):
    """Ventana de herramienta NO modal (el programa sigue operativo detrás): con barra de título del sistema
    (movible, redimensionable y con ✕), pegada al programa y centrada en su pantalla. Una sola a la vez:
    si se abre otra emergente o se cambia de pestaña, se cierra conservando lo que se dejó."""

    def __init__(self, padre, titulo, al_aceptar=None, redimensionable=True, pagina=None):
        _registrar(self)
        top = padre.winfo_toplevel()
        super().__init__(top)
        self.withdraw()
        self.title(titulo)
        self.transient(top)
        self.resizable(redimensionable, redimensionable)
        self.configure(background=T.p["panel"])
        self.padre_top, self.al_aceptar, self.pagina = top, al_aceptar, pagina
        self.resultado = None
        self.protocol("WM_DELETE_WINDOW", self.cancelar)
        self.bind("<Escape>", lambda e: self.cancelar())
        self.bind("<Destroy>", self._al_destruir)

    def mostrar(self, ancho=None, alto=None):
        titulo_oscuro(self, T.nombre == "oscuro")
        centrar(self, self.padre_top, ancho, alto)
        self.deiconify()
        self.lift()
        self.focus_set()
        return self

    def resultado_actual(self):
        """Estado actual de la ventana; None = nada que aplicar."""
        return self.resultado

    def resultado_al_cerrar(self):
        """Lo que se aplica si la ventana se cierra sola (otra emergente o cambio de pestaña)."""
        return self.resultado_actual()

    def _finalizar(self, r):
        self._quitar()
        if r is not None and self.al_aceptar:
            self.al_aceptar(r)

    def aceptar(self):
        self._finalizar(self.resultado_actual())

    def cancelar(self):
        self._quitar()

    def cerrar(self, aplicar=True):
        if aplicar:
            self._finalizar(self.resultado_al_cerrar())
        else:
            self.cancelar()

    def _quitar(self):
        if _activa[0] is self:
            _activa[0] = None
        if _vive(self):
            self.destroy()

    def _al_destruir(self, ev):
        if ev.widget is self and _activa[0] is self:
            _activa[0] = None


# ----------------------------------------------------------------------------
# Lista con casillas (filtros y listas desplegables): estilo Excel
# ----------------------------------------------------------------------------
LIMITE_BUSCAR = 8                     # con más valores distintos aparece la búsqueda


class ListaChequeo(tk.Frame):
    """«(Seleccionar Todo)» + valores con casillas; búsqueda si hay más de 8 valores.

    habilitado(valor) -> bool permite deshabilitar opciones (texto gris, sin clic). unica=True: un solo valor."""

    def __init__(self, master, valores, seleccion=None, habilitado=None, unica=False, alto=12, ancho=260,
                 etiquetas=None, al_cambiar=None, con_todo=True):
        super().__init__(master, background=T.p["panel"])
        self.valores = list(valores)
        self.etiquetas = etiquetas or {}
        self.habilitado = habilitado or (lambda v: True)
        self.unica, self.al_cambiar = unica, al_cambiar
        self.con_todo = con_todo and not unica
        self.marcados = set(self.valores if seleccion is None else [v for v in self.valores if v in seleccion])
        p = T.p
        self.var_q = tk.StringVar()
        if len(self.valores) > LIMITE_BUSCAR:
            fila = tk.Frame(self, background=p["campo"], highlightthickness=1, highlightbackground=p["borde"],
                            highlightcolor=p["acento"])
            fila.pack(fill="x", padx=T.px(8), pady=(T.px(6), T.px(4)))
            self._lupa = T.icono("buscar", 13, p["suave"])
            tk.Label(fila, image=self._lupa, background=p["campo"]).pack(side="left", padx=(T.px(6), T.px(2)))
            self.entrada = tk.Entry(fila, textvariable=self.var_q, relief="flat", background=p["campo"],
                                    foreground=p["texto"], insertbackground=p["texto"], font=T.f["base"])
            self.entrada.pack(side="left", fill="x", expand=True, ipady=T.px(3))
            self._pista = tk.Label(fila, text="Buscar", background=p["campo"], foreground=p["deshab"], font=T.f["base"])
            self._pista.place(x=T.px(26), rely=0.5, anchor="w")
            self._pista.bind("<Button-1>", lambda e: self.entrada.focus_set())
            self.var_q.trace_add("write", lambda *a: (self._pista.place_forget() if self.var_q.get() else
                                                      self._pista.place(x=T.px(26), rely=0.5, anchor="w"),
                                                      self._pintar()))
        else:
            self.entrada = None
        cont = tk.Frame(self, background=p["panel"])
        cont.pack(fill="both", expand=True, padx=T.px(8), pady=(T.px(2), 0))
        n = min(alto, len(self.valores) + (0 if unica else 1))
        self.lista = ttk.Treeview(cont, show="tree", selectmode="none", height=max(3, n), style="Lista.Treeview")
        self.lista.column("#0", width=T.px(ancho))
        sb = ttk.Scrollbar(cont, orient="vertical", command=self.lista.yview)
        self.lista.configure(yscrollcommand=sb.set)
        self.lista.pack(side="left", fill="both", expand=True)
        if len(self.valores) + 1 > alto:
            sb.pack(side="right", fill="y")
        self.lista.tag_configure("off", foreground=p["deshab"])
        self.lista.tag_configure("todo", font=T.f["negrita"])
        self.lista.bind("<Button-1>", self._clic)
        self._pintar()

    def _img(self, marcado, deshab=False):
        imgs = (getattr(T, "_imgs_ind", {}) or {}).get(T.nombre) or {}
        return imgs.get(("c1" if marcado else "c0") + ("d" if deshab else ""), "")

    def _pintar(self):
        self.lista.delete(*self.lista.get_children())
        q = self.var_q.get().strip().lower()
        visibles = [v for v in self.valores if not q or q in str(self.etiquetas.get(v, v)).lower()]
        if self.con_todo and visibles:
            todos = all(v in self.marcados for v in visibles if self.habilitado(v))
            self.lista.insert("", "end", iid="§todo", text="  (Seleccionar Todo)", image=self._img(todos),
                              tags=("todo",))
        for i, v in enumerate(self.valores):
            if v not in visibles:
                continue
            ok = self.habilitado(v)
            texto = str(self.etiquetas.get(v, v))
            self.lista.insert("", "end", iid=f"v{i}", text="  " + (texto or "(Vacío)"),
                              image=self._img(v in self.marcados, not ok), tags=() if ok else ("off",))

    def _clic(self, e):
        iid = self.lista.identify_row(e.y)
        if not iid:
            return "break"
        if iid == "§todo":
            q = self.var_q.get().strip().lower()
            visibles = [v for v in self.valores if (not q or q in str(self.etiquetas.get(v, v)).lower())
                        and self.habilitado(v)]
            if all(v in self.marcados for v in visibles):
                self.marcados.difference_update(visibles)
            else:
                self.marcados.update(visibles)
        else:
            v = self.valores[int(iid[1:])]
            if not self.habilitado(v):
                return "break"
            if self.unica:
                self.marcados = {v}
            elif v in self.marcados:
                self.marcados.discard(v)
            else:
                self.marcados.add(v)
        pos = self.lista.yview()[0]
        self._pintar()
        self.lista.yview_moveto(pos)
        if self.al_cambiar:
            self.al_cambiar()
        return "break"

    def seleccion(self):
        """None si están todos marcados; si no, la lista de marcados en el orden original."""
        if len(self.marcados) == len(self.valores):
            return None
        return [v for v in self.valores if v in self.marcados]


def _fila_menu(master, texto, comando, icono=None, activo=True):
    """Fila tipo menú (como en el filtro de Excel)."""
    p = T.p
    f = tk.Frame(master, background=p["panel"], cursor="hand2" if activo else "arrow")
    f.pack(fill="x")
    img = T.icono(icono, 14, p["texto"] if activo else p["deshab"]) if icono else None
    f._img = img
    lb = tk.Label(f, text=texto, image=img or "", compound="left", background=p["panel"],
                  foreground=p["texto"] if activo else p["deshab"], font=T.f["base"], anchor="w",
                  padx=T.px(10), pady=T.px(4))
    lb.pack(fill="x")
    if activo:
        for w in (f, lb):
            w.bind("<Enter>", lambda e: (f.configure(background=p["hover"]), lb.configure(background=p["hover"])))
            w.bind("<Leave>", lambda e: (f.configure(background=p["panel"]), lb.configure(background=p["panel"])))
            w.bind("<Button-1>", lambda e: comando())
    return f


class FiltroCabecera(Emergente):
    """Filtro y orden del encabezado de una tabla (estilo Excel): ordenar, limpiar filtro, buscar (más de
    8 valores), (Seleccionar Todo) y casillas. Clic fuera o abrir otra ventana: aplica lo marcado."""

    def __init__(self, ancla, x, y, titulo, valores, seleccion, al_aplicar, al_ordenar, numerico=False,
                 filtrado=False, pagina=None):
        super().__init__(ancla, titulo, pagina=pagina)
        self.valores = list(valores)
        self.al_aplicar, self.al_ordenar = al_aplicar, al_ordenar
        self._inicial = None if seleccion is None else set(seleccion)
        c = self.cuerpo
        _fila_menu(c, "Ordenar de Menor a Mayor" if numerico else "Ordenar de A a Z",
                   lambda: self._ordenar(False), "arriba")
        _fila_menu(c, "Ordenar de Mayor a Menor" if numerico else "Ordenar de Z a A",
                   lambda: self._ordenar(True), "abajo")
        ttk.Frame(c, style="Linea.TFrame", height=1).pack(fill="x", padx=T.px(6), pady=T.px(3))
        _fila_menu(c, f"Limpiar Filtro de «{titulo_linea(titulo)}»", self._quitar, "limpiar_filtro", activo=filtrado)
        ttk.Frame(c, style="Linea.TFrame", height=1).pack(fill="x", padx=T.px(6), pady=T.px(3))
        self.lista = ListaChequeo(c, self.valores, seleccion)
        self.lista.pack(fill="both", expand=True)
        pie = tk.Frame(c, background=T.p["panel"])
        pie.pack(fill="x", padx=T.px(8), pady=T.px(8))
        ttk.Button(pie, text="Aceptar", style="Accent.TButton", command=lambda: self.cerrar(True)).pack(side="right")
        ttk.Button(pie, text="Cancelar", style="Chico.TButton", command=lambda: self.cerrar(False)).pack(
            side="right", padx=(0, T.px(6)))
        self.bind("<Return>", lambda e: self.cerrar(True))
        self.mostrar(x, y)
        if self.lista.entrada is not None:
            self.lista.entrada.focus_set()

    def aplicar(self):
        sel = self.lista.seleccion()
        if sel == []:
            return                        # sin valores marcados no se filtra (se conserva lo anterior)
        if (sel is None and self._inicial is None) or (sel is not None and self._inicial == set(sel)):
            return
        self.al_aplicar(sel)

    def _quitar(self):
        self.cerrar(False)
        self.al_aplicar(None)

    def _ordenar(self, desc):
        self.cerrar(False)
        self.al_ordenar(desc)


# ----------------------------------------------------------------------------
# Filtros por página (vinculados: el filtro de una tabla se aplica a todas las tablas y gráficos)
# ----------------------------------------------------------------------------
class FiltrosPagina:
    """Filtros de encabezado de una página. Vinculados (opción del menú Modelo, activa por defecto): un
    filtro sobre una dimensión se aplica a todas las tablas, tarjetas y gráficos de la página."""

    def __init__(self, esc, pagina, al_cambiar):
        self.esc, self.pagina, self.al_cambiar = esc, pagina, al_cambiar

    @property
    def vinculado(self):
        return bool(self.esc.vistas.get("vincular_filtros", True))

    def _datos(self):
        return self.esc.vistas.setdefault("filtros", {}).setdefault(self.pagina, {})

    def valores(self, dim, tabla=None):
        d = self._datos()
        v = d.get(dim) if self.vinculado else (d.get(f"{tabla}|{dim}") if tabla else None)
        return None if v is None else set(v)

    def permite(self, dim, valor, tabla=None):
        v = self.valores(dim, tabla)
        return v is None or valor in v

    def fijar(self, dim, valores, tabla=None):
        d = self._datos()
        clave = dim if self.vinculado else f"{tabla}|{dim}"
        if valores is None:
            d.pop(clave, None)
        else:
            d[clave] = list(valores)
        self.esc.marcar_sucio()
        if self.al_cambiar:
            self.al_cambiar(self.vinculado)

    def activos(self):
        d = self._datos()
        if self.vinculado:
            return [(k, v) for k, v in d.items() if "|" not in k]
        return [(k.split("|", 1)[1] + " (tabla)", v) for k, v in d.items() if "|" in k]

    def quitar(self, etiqueta):
        d = self._datos()
        for k in list(d):
            nombre = k if "|" not in k else k.split("|", 1)[1] + " (tabla)"
            if nombre == etiqueta:
                d.pop(k)
        self.esc.marcar_sucio()
        if self.al_cambiar:
            self.al_cambiar(True)

    def limpiar(self):
        self._datos().clear()
        self.esc.marcar_sucio()
        if self.al_cambiar:
            self.al_cambiar(True)


from reporte import filtros_vista  # noqa: E402


def barra_filtros(master, contexto, **pack):
    """Filtros activos como etiquetas (con ✕) y «Limpiar Filtros». Solo aparece si hay filtros."""
    activos = contexto.activos()
    if not activos:
        return None
    p = T.p
    barra = tk.Frame(master, background=p["panel"])
    for etq, vals in activos:
        chip = tk.Frame(barra, background=p["sel"], highlightthickness=1, highlightbackground=p["acento"])
        chip.pack(side="left", padx=(0, T.px(8)))
        texto = f"{etq}: " + (", ".join(map(str, vals[:3])) + (f" +{len(vals) - 3}" if len(vals) > 3 else ""))
        tk.Label(chip, text=texto, background=p["sel"], foreground=p["texto"], font=T.f["chica"]).pack(
            side="left", padx=(T.px(6), T.px(2)))
        x = tk.Label(chip, text="✕", background=p["sel"], foreground=p["suave"], cursor="hand2", font=T.f["chica"])
        x.pack(side="left", padx=(0, T.px(5)))
        x.bind("<Button-1>", lambda e, k=etq: contexto.quitar(k))
    ttk.Button(barra, text="Limpiar Filtros", style="Chico.TButton", command=contexto.limpiar).pack(side="left")
    barra.pack(**(pack or {"fill": "x", "pady": (0, T.px(8))}))
    return barra


# ----------------------------------------------------------------------------
# Base de tablas: ancho completo, columnas arrastrables y menú de copia
# ----------------------------------------------------------------------------
_ORDEN_COLUMNAS = {}            # orden de columnas elegido por el usuario (por tabla, durante la sesión)


class _BaseTabla(ttk.Frame):
    """Comportamiento común de TablaDatos y TablaArbol."""

    compacta = False

    def _iniciar_base(self):
        self._pads = {}
        self._contenido = {}           # ancho del contenido por columna (px)
        self._natural = {}             # ancho natural por columna (px)
        self._minimo = {}              # ancho mínimo legible por columna (px)
        self._id_dist = None
        self._arrastre = None
        a = self.arbol
        a.bind("<Configure>", lambda e: self._programar_dist(), add="+")
        a.bind("<ButtonPress-1>", self._presionar, add="+")
        a.bind("<B1-Motion>", self._arrastrar, add="+")
        a.bind("<ButtonRelease-1>", self._soltar, add="+")
        a.bind("<Button-3>", self._contextual)
        a.bind("<Control-c>", lambda e: (self.copiar(), "break")[1])
        a.bind("<Control-C>", lambda e: (self.copiar(), "break")[1])

    # --- claves y orden de columnas ---------------------------------------------------------------
    def _claves_datos(self):
        """Columnas reordenables (sin la columna jerárquica #0)."""
        return list(self.arbol["columns"])

    def _firma(self):
        return (getattr(self, "clave", None),) + tuple(self._titulos_base())

    def _aplicar_orden_guardado(self):
        orden = _ORDEN_COLUMNAS.get(self._firma())
        cols = self._claves_datos()
        if orden and set(orden) == set(cols):
            self.arbol["displaycolumns"] = orden

    def _orden_visible(self):
        d = self.arbol["displaycolumns"]
        if d in ("#all", ("#all",)) or (isinstance(d, (list, tuple)) and list(d) == ["#all"]):
            return self._claves_datos()
        return list(d)

    # --- ancho completo y datos centrados bajo su encabezado ----------------------------------------
    def _programar_dist(self):
        if self._id_dist is None:
            self._id_dist = self.after_idle(self._distribuir)

    def _distribuir(self):
        self._id_dist = None
        try:
            disponible = self.arbol.winfo_width() - T.px(4)
        except tk.TclError:
            return
        if disponible < 60 or not self._natural:
            return
        claves = [k for k in self._columnas_ancho() if k in self._natural]
        total = sum(self._natural[k] for k in claves)
        anchos = dict(self._natural)
        if not self.compacta and total < disponible:
            extra = disponible - total
            fijas = [k for k in claves if self._fija(k)]
            libres = [k for k in claves if k not in fijas] or claves
            base = sum(self._natural[k] for k in libres) or 1
            for k in libres:
                anchos[k] = self._natural[k] + extra * self._natural[k] / base
        elif not self.compacta and total > disponible:
            # espacio insuficiente: se reduce el margen de cada columna (sin cortar encabezados ni datos)
            minimos = {k: min(self._natural[k], self._minimo.get(k, self._natural[k])) for k in claves}
            smin = sum(minimos.values())
            if smin < disponible:
                f = (disponible - smin) / max(1, total - smin)
                for k in claves:
                    anchos[k] = minimos[k] + (self._natural[k] - minimos[k]) * f
            else:
                anchos.update(minimos)
        cambios = False
        for k in claves:
            w = int(anchos[k])
            if abs(int(self.arbol.column(k, "width")) - w) > 1:
                self.arbol.column(k, width=w)
                cambios = True
        if self._recalcular_pads() or cambios:
            self._repintar_textos()

    def _fija(self, clave):
        return False

    def _recalcular_pads(self):
        """Espacios que centran el bloque de datos de cada columna bajo su encabezado."""
        esp = max(1, T.f["tabla"].measure(" "))
        nuevos = {}
        for k, cw in self._contenido.items():
            try:
                w = int(self.arbol.column(k, "width"))
            except tk.TclError:
                continue
            ancla = self._ancla(k)
            if ancla == "center":
                nuevos[k] = 0
                continue
            libre = max(0, (w - cw) / 2 - T.px(4))
            nuevos[k] = max(2 if ancla == "e" else 3, int(libre / esp))
        cambio = nuevos != self._pads
        self._pads = nuevos
        return cambio

    def _texto_celda(self, clave, valor):
        v = "" if valor is None else str(valor)
        if not v:
            return v
        a = self._ancla(clave)
        n = self._pads.get(clave, 3 if a == "w" else 2)
        if a == "e":
            return v + " " * n
        if a == "w":
            return " " * n + v
        return v

    # --- arrastrar encabezados para reordenar columnas ------------------------------------------------
    def _columna_en(self, x):
        col = self.arbol.identify_column(x)
        if not col or col == "#0":
            return None
        try:
            j = int(col.replace("#", "")) - 1
        except ValueError:
            return None
        orden = self._orden_visible()
        return orden[j] if 0 <= j < len(orden) else None

    def _presionar(self, e):
        self._arrastre = None
        if self.arbol.identify_region(e.x, e.y) != "heading":
            return
        clave = self._columna_en(e.x)
        if clave is None:
            if self.arbol.identify_column(e.x) == "#0":
                self._arrastre = {"clave": "#0", "x": e.x_root, "y": e.y_root, "fantasma": None, "ex": e.x}
            return "break"
        self._arrastre = {"clave": clave, "x": e.x_root, "y": e.y_root, "fantasma": None, "ex": e.x}
        return "break"

    def _arrastrar(self, e):
        d = self._arrastre
        if not d or d["clave"] == "#0":
            return
        if d["fantasma"] is None:
            if abs(e.x_root - d["x"]) < T.px(8):
                return
            g = tk.Toplevel(self)
            g.overrideredirect(True)
            g.transient(self.winfo_toplevel())
            try:
                g.attributes("-alpha", 0.88)
            except tk.TclError:
                pass
            tk.Label(g, text="  " + self._titulo_de(d["clave"]) + "  ", background=T.p["acento"], foreground="#FFFFFF",
                     font=T.f["tabla_n"], pady=T.px(4)).pack()
            d["fantasma"] = g
            self.arbol.configure(cursor="sb_h_double_arrow")
        d["fantasma"].geometry(f"+{e.x_root + 10}+{e.y_root + 8}")
        return "break"

    def _soltar(self, e):
        d, self._arrastre = self._arrastre, None
        if not d:
            if self.arbol.identify_region(e.x, e.y) == "separator":       # el usuario cambió un ancho
                self.after_idle(lambda: self._recalcular_pads() and self._repintar_textos())
            return
        if d["fantasma"] is None:
            if self.arbol.identify_region(e.x, e.y) == "heading":
                self._clic_encabezado(d["clave"], e)
            return "break"
        d["fantasma"].destroy()
        self.arbol.configure(cursor="")
        destino = self._columna_en(e.x)
        if destino is None or destino == d["clave"]:
            return "break"
        orden = self._orden_visible()
        orden.remove(d["clave"])
        i = orden.index(destino)
        x0 = sum(int(self.arbol.column(k, "width")) for k in orden[:i]) + (
            int(self.arbol.column("#0", "width")) if "tree" in str(self.arbol.cget("show")) else 0)
        if e.x > x0 + int(self.arbol.column(destino, "width")) / 2:
            i += 1
        orden.insert(i, d["clave"])
        self.arbol["displaycolumns"] = orden
        _ORDEN_COLUMNAS[self._firma()] = list(orden)
        return "break"

    # --- copiar -----------------------------------------------------------------------------------------
    def _contextual(self, e):
        m = nuevo_menu(self)
        if self.arbol.selection():
            m.add_command(label="Copiar Selección (Ctrl+C)", command=lambda: self.copiar(seleccion=True))
            m.add_separator()
        m.add_command(label="Copiar Tabla", command=self.copiar)
        m.add_command(label="Copiar Tabla con Formato", command=self.copiar_formato)
        m.add_command(label="Copiar Tabla como Imagen", command=self.copiar_imagen)
        self._menu_extra(m)
        mostrar_menu(m, e)
        return "break"

    def _menu_extra(self, m):
        pass

    def _estilo_fila(self, tags):
        """Fondo, negrita y color de texto de una fila según sus etiquetas (para copiar con formato)."""
        est = {}
        for t in tags:
            try:
                fondo = self.arbol.tag_configure(t, "background")
                color = self.arbol.tag_configure(t, "foreground")
                fuente = self.arbol.tag_configure(t, "font")
            except tk.TclError:
                continue
            if fondo:
                est["fondo"] = str(fondo)
            if color:
                est["color"] = str(color)
            if fuente and "semibold" in str(fuente).lower():
                est["negrita"] = True
            if t == "total":
                est["negrita"] = True
        return est

    def datos_copia(self, seleccion=False):
        """(títulos, filas de texto, anclas, estilos) de lo visible, en el orden de columnas actual."""
        raise NotImplementedError

    def copiar(self, seleccion=False):
        import portapapeles
        titulos, filas, _a, _e = self.datos_copia(seleccion)
        portapapeles.copiar_texto(portapapeles.tsv(titulos, filas))
        avisar_estado(self, "Tabla copiada al portapapeles")

    def copiar_formato(self):
        import portapapeles
        titulos, filas, anclas, estilos = self.datos_copia()
        estilos = [dict(e, fondo=e.get("fondo") or ("#F7F8FA" if i % 2 else "#FFFFFF")) for i, e in enumerate(estilos)]
        if T.nombre == "oscuro":            # en Office se pega con los colores del modo claro
            estilos = [{"negrita": e.get("negrita")} for e in estilos]
        portapapeles.copiar_html(portapapeles.tabla_html(titulos, filas, anclas, estilos),
                                 portapapeles.tsv(titulos, filas))
        avisar_estado(self, "Tabla copiada con formato: péguela en Excel, Word o PowerPoint")

    def copiar_imagen(self):
        import portapapeles
        import render
        titulos, filas, anclas, estilos = self.datos_copia()
        try:
            portapapeles.copiar_imagen(render.tabla_a_imagen(titulos, filas, anclas, estilos))
            avisar_estado(self, "Tabla copiada como imagen")
        except Exception as ex:  # noqa
            avisar_estado(self, f"No se pudo copiar la imagen: {ex}")


# ----------------------------------------------------------------------------
# Tabla plana
# ----------------------------------------------------------------------------
class TablaDatos(_BaseTabla):
    """Tabla (Treeview) a todo el ancho: encabezados centrados y datos centrados bajo su encabezado, colores
    por grupo (un color por grupo), fila de total, filtro/orden en el encabezado, columnas que se
    reordenan arrastrando el encabezado y menú de copia.

    grupo: 'auto', clave de columna o None. compacta=True: anchos según el contenido (no se estira).
    contexto/dims/clave: filtros por página (FiltrosPagina)."""

    def __init__(self, master, columnas, alto=8, hscroll=True, ordenable=True,
                 modo_seleccion="extended", grupo="auto", ajustar=False, contexto=None, dims=None,
                 clave=None, filtrable=True, compacta=False, llenar=False):
        super().__init__(master, style="Panel.TFrame")
        self.ordenable, self.filtrable = ordenable, filtrable
        self.grupo = grupo
        self.compacta = compacta
        self.ctx, self.dims, self.clave = contexto, dims or {}, clave
        self._filtros = {}
        self._filas = []
        self._vista = []
        self._items = {}
        self._orden = (None, False)
        self.columnas = [dict(c, titulo=titulo_linea(c["titulo"])) for c in columnas]
        self.arbol = ttk.Treeview(self, columns=[c["key"] for c in columnas], show="headings",
                                  height=alto, selectmode=modo_seleccion)
        self.vsb = ttk.Scrollbar(self, orient="vertical", command=self.arbol.yview)
        self.arbol.configure(yscrollcommand=self._ajustar_vsb)
        self.arbol.grid(row=0, column=0, sticky="nsew")
        self.vsb.grid(row=0, column=1, sticky="ns")
        self.hsb = None
        if hscroll:
            self.hsb = ttk.Scrollbar(self, orient="horizontal", command=self.arbol.xview)
            self.arbol.configure(xscrollcommand=self._ajustar_hsb)
            self.hsb.grid(row=1, column=0, sticky="ew")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        for c in self.columnas:
            self.arbol.heading(c["key"], text=c["titulo"], anchor="center")
            self.arbol.column(c["key"], width=T.px(c.get("ancho", 110)), minwidth=T.px(40),
                              anchor=c.get("ancla", "w"), stretch=False)
        self._iniciar_base()
        self._aplicar_orden_guardado()
        self._tags()
        T.registrar(self._tags)

    # utilidades de la base
    def _titulos_base(self):
        return [c["titulo"] for c in self.columnas]

    def _columnas_ancho(self):
        return [c["key"] for c in self.columnas]

    def _ancla(self, clave):
        c = next((x for x in self.columnas if x["key"] == clave), None)
        return (c or {}).get("ancla", "w")

    def _titulo_de(self, clave):
        c = next((x for x in self.columnas if x["key"] == clave), None)
        return (c or {}).get("titulo", clave)

    def _fija(self, clave):
        c = next((x for x in self.columnas if x["key"] == clave), None)
        return bool(c and c.get("estirar") is False)

    def _ajustar_hsb(self, a, b):
        self.hsb.set(a, b)
        if float(a) <= 0.0 and float(b) >= 1.0:
            self.hsb.grid_remove()
        else:
            self.hsb.grid()

    def _ajustar_vsb(self, a, b):
        self.vsb.set(a, b)
        if float(a) <= 0.0 and float(b) >= 1.0:
            self.vsb.grid_remove()
        else:
            self.vsb.grid()

    def _tags(self):
        p = T.p
        self.arbol.tag_configure("alt", background=p["fila_alt"])
        self.arbol.tag_configure("total", background=p["total"], font=T.f["tabla_n"])
        self.arbol.tag_configure("grupo", font=T.f["tabla_n"])
        self.arbol.tag_configure("marca", foreground=p["marca_fila"])
        for i in range(6):
            a, _b, f = colores_grupo(i)
            self.arbol.tag_configure(f"g{i}", background=a)
            self.arbol.tag_configure(f"g{i}f", background=f)
        if self._filas:
            self._pintar()

    def cargar(self, filas):
        """filas: lista de (valores_visibles, valores_orden, es_total[, etiqueta])."""
        self._filas = list(filas)
        self._orden = (None, False)
        self._medir()
        self._pintar()
        self._programar_dist()

    def _medir(self):
        fn, fb = T.f["tabla"], T.f["tabla_n"]
        muestras = self._filas[:500]
        for j, c in enumerate(self.columnas):
            k = c["key"]
            cont = max([(fb if f[2] else fn).measure(str(f[0][j])) for f in muestras if j < len(f[0])] + [0])
            cab = fb.measure(c["titulo"]) + T.px(28)
            self._contenido[k] = cont
            self._natural[k] = max(cab, cont + T.px(34), T.px(c.get("ancho_min", 0) or 0))
            self._minimo[k] = max(cab - T.px(8), cont + T.px(26))

    # --- filtrado ------------------------------------------------------------
    def _permitido(self, fila):
        for j, c in enumerate(self.columnas):
            k = c["key"]
            v = str(fila[0][j]) if j < len(fila[0]) else ""
            if k in self._filtros and v not in self._filtros[k]:
                return False
            dim = self.dims.get(k)
            if dim and self.ctx is not None:
                permitidos = self.ctx.valores(dim, self.clave)
                if permitidos is not None and v not in permitidos:
                    return False
        return True

    def _grupo_col(self, filas):
        if not self.grupo:
            return None
        if self.grupo != "auto":
            return next((j for j, c in enumerate(self.columnas) if c["key"] == self.grupo), None)
        cuerpo = [f for f in filas if not f[2]]
        if len(cuerpo) < 3:
            return None
        for j, c in enumerate(self.columnas[:3]):
            if c.get("ancla", "w") != "w":
                break
            vals = [str(f[0][j]).strip() for f in cuerpo]
            if len(set(vals)) < len(vals) and all(vals):
                return j
        return None

    def _pintar(self, filas=None):
        if filas is None:
            filas = self._vista if self._orden[0] is not None and self._vista else self._filas
        filas = [f for f in filas if f[2] or self._permitido(f)]
        self._vista = filas
        self.arbol.delete(*self.arbol.get_children())
        gcol = self._grupo_col(filas)
        grupo_i, previo = -1, object()
        self._items = {}
        claves = [c["key"] for c in self.columnas]
        for i, fila in enumerate(filas):
            vis, _raw, total = fila[:3]
            if total:
                tags = ("total",)
            elif gcol is not None:
                clave = str(vis[gcol]).strip()
                if clave != previo:
                    grupo_i, previo = grupo_i + 1, clave
                tags = (f"g{grupo_i % 6}",)
            else:
                tags = ("alt",) if i % 2 else ()
            if len(fila) > 3 and fila[3]:
                tags = tags + tuple(fila[3] if isinstance(fila[3], (list, tuple)) else (fila[3],))
            iid = self.arbol.insert("", "end", values=[self._texto_celda(k, v) for k, v in zip(claves, vis)], tags=tags)
            self._items[iid] = (vis, tags)
        self._titulos()

    def _repintar_textos(self):
        claves = [c["key"] for c in self.columnas]
        for iid, (vis, _tags) in getattr(self, "_items", {}).items():
            try:
                self.arbol.item(iid, values=[self._texto_celda(k, v) for k, v in zip(claves, vis)])
            except tk.TclError:
                pass

    def _titulos(self):
        clave_o, desc = self._orden
        for c in self.columnas:
            t = c["titulo"]
            filtrado = c["key"] in self._filtros or (
                self.ctx is not None and self.dims.get(c["key"]) and
                self.ctx.valores(self.dims[c["key"]], self.clave) is not None)
            if filtrado:
                t = "⚑ " + t
            if c["key"] == clave_o:
                t += " ▼" if desc else " ▲"
            self.arbol.heading(c["key"], text=t)

    def etiqueta(self, nombre, **opciones):
        self.arbol.tag_configure(nombre, **opciones)

    def _clic_encabezado(self, clave, e):
        if not (self.filtrable or self.ordenable):
            return
        j = next((i for i, c in enumerate(self.columnas) if c["key"] == clave), None)
        if j is None:
            return
        c = self.columnas[j]
        valores = list(dict.fromkeys(str(f[0][j]) for f in self._filas if not f[2] and j < len(f[0])))
        numerico = c.get("ancla", "w") == "e"
        if numerico:
            valores.sort(key=lambda v: (_numero(v) is None, _numero(v) or 0.0))
        elif not self.dims.get(clave):
            valores.sort(key=str.lower)
        dim = self.dims.get(clave)
        sel = self._filtros.get(clave)
        if dim and self.ctx is not None:
            sel = self.ctx.valores(dim, self.clave)
        FiltroCabecera(self.arbol, e.x_root - T.px(20), e.y_root + T.px(14), c["titulo"], valores, sel,
                       lambda v, k=clave: self._filtrar(k, v), lambda d, k=clave: self._ordenar(k, d),
                       numerico=numerico, filtrado=sel is not None)

    def _filtrar(self, clave, valores):
        dim = self.dims.get(clave)
        if dim and self.ctx is not None:
            self.ctx.fijar(dim, valores, self.clave)
            if not self.ctx.vinculado and _vive(self):
                self._pintar(self._filas)
            return
        if not _vive(self):
            return
        if valores is None:
            self._filtros.pop(clave, None)
        else:
            self._filtros[clave] = set(valores)
        self._pintar(self._filas)

    def _ordenar(self, clave, desc=None):
        if not self.ordenable or not _vive(self):
            return
        idx = [c["key"] for c in self.columnas].index(clave)
        if desc is None:
            desc = not self._orden[1] if self._orden[0] == clave else False
        self._orden = (clave, desc)
        cuerpo = [f for f in self._filas if not f[2]]
        totales = [f for f in self._filas if f[2]]
        if not cuerpo:
            return
        con = [f for f in cuerpo if f[1][idx] is not None]
        sin = [f for f in cuerpo if f[1][idx] is None]
        try:
            con.sort(key=lambda f: f[1][idx], reverse=desc)
        except TypeError:
            con.sort(key=lambda f: str(f[1][idx]).lower(), reverse=desc)
        self._pintar(con + sin + totales)

    def fijar_alto(self, n):
        self.arbol.configure(height=max(1, n))

    # --- selección por valor (p. ej. orígenes) ------------------------------------------------------
    def valores_seleccion(self, j=0):
        return [self._items[i][0][j] for i in self.arbol.selection() if i in self._items]

    def seleccionar_valores(self, valores, j=0):
        valores = set(valores)
        self.arbol.selection_set([i for i, (vis, _t) in self._items.items() if vis[j] in valores])

    def seleccionar_todo(self):
        self.arbol.selection_set(self.arbol.get_children())

    def datos_copia(self, seleccion=False):
        orden = self._orden_visible()
        idx = {c["key"]: j for j, c in enumerate(self.columnas)}
        titulos = [self.columnas[idx[k]]["titulo"] for k in orden]
        anclas = [self.columnas[idx[k]].get("ancla", "w") for k in orden]
        items = self.arbol.selection() if seleccion and self.arbol.selection() else self.arbol.get_children()
        filas, estilos = [], []
        for iid in items:
            vis, tags = self._items.get(iid, ([], ()))
            filas.append([str(vis[idx[k]]) if idx[k] < len(vis) else "" for k in orden])
            estilos.append(self._estilo_fila(tags))
        return titulos, filas, anclas, estilos


# ----------------------------------------------------------------------------
# Tabla jerárquica
# ----------------------------------------------------------------------------
class TablaArbol(_BaseTabla):
    """Tabla con filas desplegables (grupo ▸ detalle ▸ …) y fila de total, a todo el ancho.

    columnas: [{"titulo", "ancho", "ancla"}]; la primera es la jerarquía.
    filas: [{"texto", "valores": [...], "hijos": [...], "total": bool, "tag": str, "abierto": bool}]
    colores=True: cada grupo de primer nivel con su color (un color por grupo)."""

    def __init__(self, master, columnas, alto=6, abiertos=False, ajustar=False, colores=True,
                 contexto=None, dims=None, clave=None, compacta=False):
        super().__init__(master, style="Panel.TFrame")
        self.columnas = columnas = [dict(c, titulo=titulo_linea(c["titulo"])) for c in columnas]
        self.abiertos = abiertos
        self.colores = colores
        self.compacta = compacta
        self.ctx, self.dims, self.clave = contexto, dims or {}, clave
        self._filas = []
        self._filtros = {}
        self._items = {}
        self._orden = (None, False)
        claves = [f"c{j}" for j in range(1, len(columnas))]
        self._claves = ["#0"] + claves
        self.arbol = ttk.Treeview(self, columns=claves, show="tree headings", height=alto, selectmode="extended")
        self.vsb = ttk.Scrollbar(self, orient="vertical", command=self.arbol.yview)
        self.arbol.configure(yscrollcommand=self._ajustar)
        self.arbol.grid(row=0, column=0, sticky="nsew")
        self.vsb.grid(row=0, column=1, sticky="ns")
        # barra horizontal solo cuando las columnas no caben (se oculta sola)
        self.hsb = ttk.Scrollbar(self, orient="horizontal", command=self.arbol.xview)
        self.arbol.configure(xscrollcommand=self._ajustar_hsb)
        self.hsb.grid(row=1, column=0, sticky="ew")
        self.hsb.grid_remove()
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.arbol.heading("#0", text=columnas[0]["titulo"], anchor="center")
        self.arbol.column("#0", width=T.px(columnas[0].get("ancho", 200)), minwidth=T.px(80), stretch=False)
        for k, c in zip(claves, columnas[1:]):
            self.arbol.heading(k, text=c["titulo"], anchor="center")
            self.arbol.column(k, width=T.px(c.get("ancho", 110)), minwidth=T.px(40), anchor=c.get("ancla", "e"),
                              stretch=False)
        self._iniciar_base()
        self._aplicar_orden_guardado()
        self._tags()
        T.registrar(self._tags)

    def _titulos_base(self):
        return [c["titulo"] for c in self.columnas]

    def _ajustar_hsb(self, a, b):
        self.hsb.set(a, b)
        if float(a) <= 0.0 and float(b) >= 1.0:
            self.hsb.grid_remove()
        else:
            self.hsb.grid()

    def _columnas_ancho(self):
        return list(self._claves)

    def _ancla(self, clave):
        if clave == "#0":
            return "tree"
        j = self._claves.index(clave)
        return self.columnas[j].get("ancla", "e")

    def _titulo_de(self, clave):
        return self.columnas[self._claves.index(clave)]["titulo"]

    def _ajustar(self, a, b):
        self.vsb.set(a, b)
        if float(a) <= 0.0 and float(b) >= 1.0:
            self.vsb.grid_remove()
        else:
            self.vsb.grid()

    def _tags(self):
        p = T.p
        self.arbol.tag_configure("total", background=p["total"], font=T.f["tabla_n"])
        self.arbol.tag_configure("grupo", font=T.f["tabla_n"])
        self.arbol.tag_configure("hijo", foreground=p["suave"])
        self.arbol.tag_configure("seccion", background=p["panel_alt"], font=T.f["tabla_n"], foreground=p["acento"])
        self.arbol.tag_configure("alt", background=p["fila_alt"])
        self.arbol.tag_configure("marca", foreground=p["marca_fila"])
        for i in range(6):
            a, _b, f = colores_grupo(i)
            self.arbol.tag_configure(f"g{i}", background=a)
            self.arbol.tag_configure(f"g{i}f", background=f)

    def cargar(self, filas):
        self._filas = list(filas)
        self._medir()
        self._pintar()
        self._programar_dist()

    def _medir(self):
        fn, fb = T.f["tabla"], T.f["tabla_n"]
        anchos = [0] * len(self.columnas)
        prof = [0]

        def medir(f, nivel):
            prof[0] = max(prof[0], nivel)
            anchos[0] = max(anchos[0], fb.measure(str(f.get("texto", ""))) + T.px(22) * (nivel + 1))
            for j, v in enumerate(f.get("valores", [])[:len(anchos) - 1], start=1):
                anchos[j] = max(anchos[j], fb.measure(str(v)))
            for h in f.get("hijos") or []:
                medir(h, nivel + 1)
        for f in self._filas[:400]:
            medir(f, 0)
        for j, (k, c) in enumerate(zip(self._claves, self.columnas)):
            cab = fb.measure(c["titulo"]) + T.px(28)
            if j == 0:
                self._natural[k] = max(cab, anchos[0] + T.px(30))
                self._minimo[k] = max(cab - T.px(8), anchos[0] + T.px(24))
            else:
                self._contenido[k] = anchos[j]
                self._natural[k] = max(cab, anchos[j] + T.px(34))
                self._minimo[k] = max(cab - T.px(8), anchos[j] + T.px(26))

    def _permitido(self, f):
        if f.get("total") or f.get("tag") == "seccion":
            return True
        vals = [f.get("texto", "")] + list(f.get("valores", []))
        for j, k in enumerate(self._claves):
            v = str(vals[j]) if j < len(vals) else ""
            if k in self._filtros and v not in self._filtros[k]:
                return False
            dim = self.dims.get(k)
            if dim and self.ctx is not None:
                ok = self.ctx.valores(dim, self.clave)
                if ok is not None and v not in ok:
                    return False
        return True

    def _pintar(self):
        abiertos = {self.arbol.item(i, "text").strip(): self.arbol.item(i, "open")
                    for i in self.arbol.get_children()} if self.arbol.get_children() else {}
        self.arbol.delete(*self.arbol.get_children())
        self._items = {}
        filas = [f for f in self._filas if self._permitido(f)]
        clave_o, desc = self._orden
        if clave_o is not None:
            j = self._claves.index(clave_o)
            cuerpo = [f for f in filas if not f.get("total")]
            tot = [f for f in filas if f.get("total")]

            def llave(f):
                v = ([f.get("texto", "")] + list(f.get("valores", [])))[j] if j <= len(f.get("valores", [])) else ""
                n = _numero(v) if j else None
                return (0, n, "") if n is not None else (1, 0.0, str(v).lower())
            cuerpo.sort(key=llave, reverse=desc)
            filas = cuerpo + tot
        g = 0
        for f in filas:
            if f.get("total"):
                tags, fam = ("total",), None
            elif f.get("hijos") and self.colores and f.get("tag") != "seccion":
                fam = g % 6
                g += 1
                tags = ("grupo", f"g{fam}f")
            else:
                fam = None
                tags = ("grupo",) if f.get("hijos") else ()
            if f.get("tag"):
                tags = tags + (f["tag"],)
            abierto = abiertos.get(str(f["texto"]), f.get("abierto", self.abiertos))
            iid = self.arbol.insert("", "end", text="  " + str(f["texto"]), values=self._vals(f), tags=tags,
                                    open=abierto)
            self._items[iid] = (f, tags, 0)
            self._hijos(iid, f.get("hijos") or [], fam, 1)
        self._titulos()

    def _vals(self, f):
        return [self._texto_celda(k, v) for k, v in zip(self._claves[1:], f.get("valores", []))]

    def _hijos(self, padre, hijos, fam, nivel):
        for h in hijos:
            tags = (f"g{fam}",) if fam is not None else ()
            tags = tags + (("hijo",) if not h.get("hijos") else ("grupo",))
            if h.get("tag"):
                tags = tags + (h["tag"],)
            iid = self.arbol.insert(padre, "end", text="  " + str(h["texto"]), values=self._vals(h), tags=tags,
                                    open=h.get("abierto", False))
            self._items[iid] = (h, tags, nivel)
            if h.get("hijos"):
                self._hijos(iid, h["hijos"], fam, nivel + 1)

    def _repintar_textos(self):
        for iid, (f, _t, _n) in getattr(self, "_items", {}).items():
            try:
                self.arbol.item(iid, values=self._vals(f))
            except tk.TclError:
                pass

    def _titulos(self):
        clave_o, desc = self._orden
        for k, c in zip(self._claves, self.columnas):
            t = c["titulo"]
            filtrado = k in self._filtros or (self.ctx is not None and self.dims.get(k) and
                                              self.ctx.valores(self.dims[k], self.clave) is not None)
            if filtrado:
                t = "⚑ " + t
            if k == clave_o:
                t += " ▼" if desc else " ▲"
            self.arbol.heading(k, text=t)

    def _clic_encabezado(self, clave, e):
        j = self._claves.index(clave)
        base = [f for f in self._filas if not f.get("total") and f.get("tag") != "seccion"]
        valores = list(dict.fromkeys(str(([f.get("texto", "")] + list(f.get("valores", [])))[j])
                                     for f in base if j <= len(f.get("valores", []))))
        dim = self.dims.get(clave)
        sel = self._filtros.get(clave)
        if dim and self.ctx is not None:
            sel = self.ctx.valores(dim, self.clave)
        FiltroCabecera(self.arbol, e.x_root - T.px(20), e.y_root + T.px(14), self.columnas[j]["titulo"], valores, sel,
                       lambda v, k=clave: self._filtrar(k, v), lambda d, k=clave: self._ordenar(k, d),
                       numerico=j > 0, filtrado=sel is not None)

    def _filtrar(self, clave, valores):
        dim = self.dims.get(clave)
        if dim and self.ctx is not None:
            self.ctx.fijar(dim, valores, self.clave)
            if not self.ctx.vinculado and _vive(self):
                self._pintar()
            return
        if not _vive(self):
            return
        if valores is None:
            self._filtros.pop(clave, None)
        else:
            self._filtros[clave] = set(valores)
        self._pintar()

    def _ordenar(self, clave, desc):
        if _vive(self):
            self._orden = (clave, desc)
            self._pintar()

    def etiqueta(self, nombre, **opciones):
        self.arbol.tag_configure(nombre, **opciones)

    def celda_en(self, e):
        """(fila, índice de columna de datos | 0 para la jerarquía, iid) bajo el puntero, o (None, None, None)."""
        if self.arbol.identify_region(e.x, e.y) not in ("cell", "tree"):
            return None, None, None
        iid = self.arbol.identify_row(e.y)
        col = self.arbol.identify_column(e.x)
        if not iid or iid not in self._items:
            return None, None, None
        if col == "#0":
            return self._items[iid][0], 0, iid
        clave = self._columna_en(e.x)
        return self._items[iid][0], self._claves.index(clave) if clave in self._claves else None, iid

    def _abrir(self, valor):
        def rec(padre):
            for iid in self.arbol.get_children(padre):
                self.arbol.item(iid, open=valor)
                rec(iid)
        rec("")

    def _menu_extra(self, m):
        m.add_separator()
        m.add_command(label="Desplegar Todo", command=lambda: self._abrir(True))
        m.add_command(label="Contraer Todo", command=lambda: self._abrir(False))

    def datos_copia(self, seleccion=False):
        orden = self._orden_visible()
        titulos = [self.columnas[0]["titulo"]] + [self.columnas[self._claves.index(k)]["titulo"] for k in orden]
        anclas = ["w"] + [self._ancla(k) for k in orden]
        filas, estilos = [], []
        sel = set(self.arbol.selection()) if seleccion else None

        def recorrer(padre):
            for iid in self.arbol.get_children(padre):
                f, tags, nivel = self._items.get(iid, ({}, (), 0))
                if sel is None or iid in sel:
                    vals = list(f.get("valores", []))
                    filas.append([str(f.get("texto", ""))] +
                                 [str(vals[self._claves.index(k) - 1]) if self._claves.index(k) - 1 < len(vals) else ""
                                  for k in orden])
                    est = self._estilo_fila(tags)
                    est["sangria"] = nivel
                    estilos.append(est)
                if self.arbol.item(iid, "open") or sel is not None:
                    recorrer(iid)
        recorrer("")
        return titulos, filas, anclas, estilos

    def copiar(self, seleccion=False):
        import portapapeles
        titulos, filas, _a, estilos = self.datos_copia(seleccion)
        filas = [["   " * e.get("sangria", 0) + f[0]] + f[1:] for f, e in zip(filas, estilos)]
        portapapeles.copiar_texto(portapapeles.tsv(titulos, filas))
        avisar_estado(self, "Tabla copiada al portapapeles")


# ----------------------------------------------------------------------------
# Contenedor con desplazamiento vertical (reconstrucción sin parpadeo)
# ----------------------------------------------------------------------------
class ScrollFrame(ttk.Frame):
    """Contenedor con desplazamiento vertical; el contenido va en .interior.

    Para reconstruir sin parpadeo: nuevo = zona.preparar(); …construir en nuevo…; zona.publicar(nuevo)
    (el contenido anterior se reemplaza de una vez, conservando la posición de desplazamiento)."""

    def __init__(self, master, estilo="Panel.TFrame", horizontal=False, margen_inferior=True):
        super().__init__(master, style=estilo)
        self._estilo = estilo
        self.lienzo = tk.Canvas(self, highlightthickness=0, borderwidth=0, yscrollincrement=T.px(12))
        self.vsb = ttk.Scrollbar(self, orient="vertical", command=self.lienzo.yview)
        self.lienzo.configure(yscrollcommand=self._ajustar)
        self.interior = ttk.Frame(self.lienzo, style=estilo)
        self._margen = T.px(14) if margen_inferior else 0
        self._lienzo_rueda = self.lienzo
        self._id = self.lienzo.create_window((0, 0), window=self.interior, anchor="nw")
        self.lienzo.grid(row=0, column=0, sticky="nsew")
        self.vsb.grid(row=0, column=1, sticky="ns")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.interior.bind("<Configure>", lambda e: self._actualizar())
        self.lienzo.bind("<Configure>", self._ancho)
        self._retema()
        T.registrar(self._retema)

    def _retema(self):
        fondo = T.p["panel"] if self._estilo == "Panel.TFrame" else T.p["bg"]
        self.lienzo.configure(background=fondo)

    def _ajustar(self, a, b):
        self.vsb.set(a, b)
        if float(a) <= 0.0 and float(b) >= 1.0:
            self.vsb.grid_remove()
        else:
            self.vsb.grid()

    def _ancho(self, e):
        self.lienzo.itemconfigure(self._id, width=e.width)
        self._llenar_alto()

    def _llenar_alto(self):
        """El contenido ocupa al menos el alto visible (las tablas que «llenan» pueden estirarse)."""
        try:
            h = self.lienzo.winfo_height()
            req = self.interior.winfo_reqheight()
            self.lienzo.itemconfigure(self._id, height=max(h, req) if getattr(self, "_llenar", False) else "")
        except tk.TclError:
            pass

    def _actualizar(self):
        bb = self.lienzo.bbox("all")
        if bb:
            self.lienzo.configure(scrollregion=(bb[0], bb[1], bb[2], bb[3] + self._margen))

    def al_inicio(self):
        self.lienzo.yview_moveto(0)

    def preparar(self):
        """Interior nuevo (aún sin mostrar) para construir el contenido sin parpadeo."""
        return ttk.Frame(self.lienzo, style=self._estilo)

    def publicar(self, nuevo, conservar=True, llenar=False):
        pos = self.lienzo.yview()[0] if conservar else 0.0
        viejo = self.interior
        self.interior = nuevo
        self._llenar = llenar
        nuevo.bind("<Configure>", lambda e: self._actualizar())
        nuevo.update_idletasks()
        self.lienzo.itemconfigure(self._id, window=nuevo, width=max(1, self.lienzo.winfo_width()))
        self._llenar_alto()
        self._actualizar()
        self.lienzo.yview_moveto(pos)
        if viejo is not nuevo:
            viejo.destroy()


class Aviso(ttk.Frame):
    """Banner amarillo en línea; el texto aprovecha todo el ancho disponible."""

    def __init__(self, master, texto, cerrable=False):
        super().__init__(master, style="Aviso.TFrame", padding=(T.px(12), T.px(7)))
        img = T.icono("alerta", 16, T.p["aviso_txt"])
        self._img = img
        if img:
            tk.Label(self, image=img, background=T.p["aviso_bg"]).pack(side="left", anchor="n", pady=(T.px(1), 0))
        self.lbl = ttk.Label(self, text=texto, style="Aviso.TLabel", wraplength=T.px(1400), justify="left")
        self.lbl.pack(side="left", padx=(T.px(8), 0), fill="x", expand=True)
        if cerrable:
            ttk.Button(self, text="✕", width=3, command=self.destroy, style="Icono.TButton").pack(side="right")
        self.bind("<Configure>", self._ajustar_texto)

    def _ajustar_texto(self, e):
        w = max(T.px(200), e.width - T.px(70))
        if abs(int(str(self.lbl.cget("wraplength") or 0)) - w) > 4:
            self.lbl.configure(wraplength=w)


class Placeholder(tk.Canvas):
    """Lienzo gris tenue con mensaje centrado (cuando no hay resultados)."""

    def __init__(self, master, titulo="Sin Resultados", detalle=""):
        super().__init__(master, highlightthickness=0, borderwidth=0)
        self.titulo, self.detalle = titulo, detalle
        self._id = None
        self.bind("<Configure>", lambda e: self._programar())
        T.registrar(self._dibujar)

    def _programar(self):
        if self._id is None:
            self._id = self.after_idle(self._dibujar)

    def poner(self, titulo, detalle=""):
        self.titulo, self.detalle = titulo, detalle
        self._dibujar()

    def _dibujar(self):
        self._id = None
        p = T.p
        self.configure(background=p["vacio"])
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if w < 10:
            return
        self.create_text(w / 2, h / 2 - T.px(14), text=self.titulo, fill=p["suave"], font=T.f["titulo"])
        if self.detalle:
            self.create_text(w / 2, h / 2 + T.px(18), text=self.detalle, fill=p["suave"],
                             font=T.f["base"], width=T.px(560), justify="center")


def caja(master, titulo, nota="", derecha=None):
    """Recuadro con título para un reporte; devuelve (caja, cabecera, cuerpo). La cabecera admite controles
    a la derecha (pack side=right)."""
    p = T.p
    marco = tk.Frame(master, highlightthickness=1, highlightbackground=p["borde"], background=p["panel"])
    cab = tk.Frame(marco, background=p["panel"])
    cab.pack(fill="x", padx=T.px(12), pady=(T.px(8), 0))
    tk.Label(cab, text=titulo, background=p["panel"], foreground=p["texto"], font=T.f["subtitulo"],
             anchor="w").pack(side="left")
    if nota:
        tk.Label(marco, text=nota, background=p["panel"], foreground=p["suave"], font=T.f["chica"],
                 anchor="w", justify="left", wraplength=T.px(760)).pack(fill="x", padx=T.px(12))
    cuerpo = tk.Frame(marco, background=p["panel"])
    cuerpo.pack(fill="both", expand=True, padx=T.px(10), pady=(T.px(6), T.px(10)))
    return marco, cab, cuerpo


def tamano_legible(n):
    if n is None:
        return "–"
    n = float(n)
    for u in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or u == "TB":
            return f"{n:,.0f} {u}" if u == "B" else f"{n:,.1f} {u}"
        n /= 1024
