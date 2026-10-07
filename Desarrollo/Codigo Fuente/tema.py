"""Tema visual (claro / noche), tipografías, iconos y utilidades de ventana."""
import ctypes
import tkinter as tk
import tkinter.font as tkfont
import weakref
from tkinter import ttk

# Paletas basadas en el sistema de diseño Primer (GitHub), modo claro y oscuro
PALETAS = {
    # Modo claro con grises tenues alternados: fondo gris perla, recuadros blancos, franjas de menú y de
    # escenarios en grises distintos (los gráficos conservan sus colores)
    "claro": {
        "bg": "#ECEFF3", "panel": "#FFFFFF", "panel_alt": "#F5F7F9", "borde": "#D6DCE2",
        "texto": "#1F2328", "suave": "#5F6873", "acento": "#0969DA", "acento_hover": "#0757B8",
        "acento_txt": "#FFFFFF", "cab": "#F1F3F6", "cab_txt": "#1F2328", "fila_alt": "#F7F8FA",
        "sel": "#DDEEFF", "menu": "#F7F8FA", "hover": "#E6EAEF", "aviso_bg": "#FFF8C5",
        "aviso_borde": "#D4A72C", "aviso_txt": "#4D2D00", "ok": "#1A7F37", "error": "#D1242F",
        "total": "#EBEEF2", "vacio": "#F5F7F9", "campo": "#FFFFFF", "deshab": "#8C959F",
        "nav_sel": "#FD8C73", "contador": "#E3E7EC", "primario": "#1F883D",
        "primario_hover": "#1A7F37", "rejilla": "#EBEEF2", "barra_docs": "#E3E7EC",
        "separador": "#DCE1E6", "requerido": "#A4161A", "marca_fila": "#B42318",
        "est_TP": "#1A7F37", "est_DPP": "#0969DA", "est_DPNP": "#8250DF",
        "est_DEP": "#BF8700", "est_DENP": "#BC4C00", "est_SB": "#6E7781",
    },
    "oscuro": {
        "bg": "#010409", "panel": "#0D1117", "panel_alt": "#161B22", "borde": "#30363D",
        "texto": "#E6EDF3", "suave": "#7D8590", "acento": "#2F81F7", "acento_hover": "#4493F8",
        "acento_txt": "#FFFFFF", "cab": "#161B22", "cab_txt": "#E6EDF3", "fila_alt": "#161B22",
        "sel": "#1F3A5F", "menu": "#010409", "hover": "#21262D", "aviso_bg": "#272115",
        "aviso_borde": "#9E6A03", "aviso_txt": "#E3B341", "ok": "#3FB950", "error": "#F85149",
        "total": "#21262D", "vacio": "#0D1117", "campo": "#0D1117", "deshab": "#484F58",
        "nav_sel": "#F78166", "contador": "#2F353D", "primario": "#238636",
        "primario_hover": "#2EA043", "rejilla": "#21262D", "barra_docs": "#010409",
        "separador": "#262C34", "requerido": "#F85149", "marca_fila": "#FF7B72",
        "est_TP": "#3FB950", "est_DPP": "#4493F8", "est_DPNP": "#A371F7",
        "est_DEP": "#D29922", "est_DENP": "#DB6D28", "est_SB": "#8B949E",
    },
}


class _ColorEstado:
    """Color de cada estado según el modo activo (más vivo en fondo oscuro)."""

    def __getitem__(self, clave):
        return T.p["est_" + clave]

    def get(self, clave, defecto=None):
        return T.p.get("est_" + clave, defecto)


COLOR_ESTADO = _ColorEstado()

GLIFOS = {
    "nuevo": 0xE7C3, "abrir": 0xE838, "guardar": 0xE74E, "guardar_como": 0xE792,
    "noche": 0xE708, "info": 0xE946, "importar": 0xE896, "excel": 0xE8A9, "ppt": 0xE8AE,
    "ejecutar": 0xE768, "herramientas": 0xE713, "analitica": 0xE9D9, "cerrar": 0xE711,
    "pin": 0xE718, "alerta": 0xE7BA, "ok": 0xE73E, "actualizar": 0xE72C, "filtro": 0xE71C,
    "buscar": 0xE721, "borrar": 0xE74D, "agregar": 0xE710, "csv": 0xE9F9, "salir": 0xE7E8,
    "carpeta": 0xE838, "archivo": 0xE8A5, "arriba": 0xE74A, "abajo": 0xE74B, "copiar": 0xE8C8,
    "error": 0xEA39, "tabla": 0xE8A9, "ajustes": 0xE713, "mas": 0xE710,
    "pivote": 0xE80A, "agregar_archivo": 0xE8F4, "cambiar": 0xE895, "abrir_externo": 0xE8A7,
    "calendario": 0xE787, "ordenar": 0xE8CB, "expandir": 0xE710, "contraer": 0xE738,
    "ventana": 0xE8A7, "reciente": 0xE823, "imagen": 0xEB9F, "campos": 0xE8FD, "funcion": 0xE943,
    "formato": 0xE8D2, "editar": 0xE70F, "opciones": 0xE713, "limpiar_filtro": 0xE894,
}


def _fuente_iconos():
    import os
    base = os.environ.get("WINDIR", r"C:\Windows")
    for nombre in ("segmdl2.ttf", "SegoeIcons.ttf"):
        ruta = os.path.join(base, "Fonts", nombre)
        if os.path.isfile(ruta):
            return ruta
    return None


class _Tema:
    def __init__(self):
        self.nombre = "claro"
        self.p = PALETAS["claro"]
        self.escala = 1.0
        self.root = None
        self.f = {}
        self._cb = []
        self._cache = {}
        self._ruta_iconos = _fuente_iconos()

    # ------------------------------------------------------------------
    def px(self, n):
        return int(round(n * self.escala))

    def iniciar(self, root, nombre="claro"):
        self.root = root
        try:
            self.escala = max(1.0, root.winfo_fpixels("1i") / 96.0)
        except tk.TclError:
            self.escala = 1.0
        for n in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont", "TkCaptionFont",
                  "TkSmallCaptionFont", "TkIconFont", "TkTooltipFont"):
            try:
                tkfont.nametofont(n).configure(family="Segoe UI", size=9)
            except tk.TclError:
                pass
        # Tamaños sobrios (Segoe UI 9 pt es el tamaño estándar de Windows); tablas en 9 pt
        self.f = {
            "base": tkfont.Font(root=root, family="Segoe UI", size=9),
            "negrita": tkfont.Font(root=root, family="Segoe UI Semibold", size=9),
            "titulo": tkfont.Font(root=root, family="Segoe UI Semibold", size=12),
            "subtitulo": tkfont.Font(root=root, family="Segoe UI Semibold", size=10),
            "chica": tkfont.Font(root=root, family="Segoe UI", size=8),
            "mono": tkfont.Font(root=root, family="Consolas", size=9),
            "grande": tkfont.Font(root=root, family="Segoe UI", size=10),
            "kpi": tkfont.Font(root=root, family="Segoe UI Semibold", size=13),
            "tabla": tkfont.Font(root=root, family="Segoe UI", size=9),
            "tabla_n": tkfont.Font(root=root, family="Segoe UI Semibold", size=9),
        }
        self.aplicar(nombre)

    def registrar(self, metodo):
        try:
            self._cb.append(weakref.WeakMethod(metodo))
        except TypeError:
            self._cb.append(lambda m=metodo: m)

    def _avisar(self):
        vivos = []
        for ref in self._cb:
            fn = ref()
            if fn is None:
                continue
            try:
                fn()
                vivos.append(ref)
            except tk.TclError:
                pass
        self._cb = vivos

    # ------------------------------------------------------------------
    def aplicar(self, nombre):
        self.nombre = nombre if nombre in PALETAS else "claro"
        p = self.p = PALETAS[self.nombre]
        self._cache.clear()
        root = self.root
        st = ttk.Style(root)
        st.theme_use("clam")
        base = self.f["base"]
        px = self.px
        root.configure(background=p["bg"])

        st.configure(".", background=p["bg"], foreground=p["texto"], fieldbackground=p["campo"],
                     bordercolor=p["borde"], lightcolor=p["borde"], darkcolor=p["borde"],
                     troughcolor=p["panel_alt"], focuscolor=p["acento"], font=base,
                     selectbackground=p["sel"], selectforeground=p["texto"],
                     insertcolor=p["texto"])
        st.map(".", foreground=[("disabled", p["deshab"])])

        st.configure("TFrame", background=p["bg"])
        st.configure("Panel.TFrame", background=p["panel"])
        st.configure("Alt.TFrame", background=p["panel_alt"])
        st.configure("Docs.TFrame", background=p["barra_docs"])
        st.configure("Tarjeta.TFrame", background=p["panel"], bordercolor=p["borde"],
                     relief="solid", borderwidth=1)
        st.configure("Aviso.TFrame", background=p["aviso_bg"], bordercolor=p["aviso_borde"],
                     relief="solid", borderwidth=1)
        st.configure("Cab.TFrame", background=p["cab"])
        st.configure("Menu.TFrame", background=p["menu"])
        st.configure("Linea.TFrame", background=p["borde"])

        st.configure("TLabel", background=p["bg"], foreground=p["texto"])
        st.configure("Panel.TLabel", background=p["panel"], foreground=p["texto"])
        st.configure("Alt.TLabel", background=p["panel_alt"], foreground=p["texto"])
        st.configure("Suave.TLabel", background=p["bg"], foreground=p["suave"])
        st.configure("PanelSuave.TLabel", background=p["panel"], foreground=p["suave"])
        st.configure("Titulo.TLabel", background=p["panel"], foreground=p["texto"],
                     font=self.f["titulo"])
        st.configure("Subtitulo.TLabel", background=p["panel"], foreground=p["texto"],
                     font=self.f["subtitulo"])
        st.configure("Negrita.TLabel", background=p["panel"], foreground=p["texto"],
                     font=self.f["negrita"])
        st.configure("Aviso.TLabel", background=p["aviso_bg"], foreground=p["aviso_txt"])
        st.configure("Menu.TLabel", background=p["menu"], foreground=p["texto"],
                     padding=(px(10), px(4)))
        st.configure("Estado.TLabel", background=p["panel_alt"], foreground=p["suave"],
                     font=self.f["chica"])
        st.configure("Cab.TLabel", background=p["cab"], foreground=p["cab_txt"])
        st.configure("Escenario.TLabel", background=p["panel"], foreground=p["acento"],
                     font=self.f["subtitulo"])
        st.configure("Chip.TLabel", background=p["contador"], foreground=p["texto"],
                     font=self.f["chica"], padding=(px(8), px(2)))
        st.configure("ChipOk.TLabel", background=p["ok"], foreground="#FFFFFF",
                     font=self.f["chica"], padding=(px(8), px(2)))
        st.configure("ChipAviso.TLabel", background=p["aviso_borde"], foreground="#2B2200",
                     font=self.f["chica"], padding=(px(8), px(2)))

        st.configure("TButton", background=p["panel_alt"], foreground=p["texto"],
                     bordercolor=p["borde"], padding=(px(10), px(3)), relief="flat",
                     focusthickness=1)
        st.map("TButton",
               background=[("pressed", p["hover"]), ("active", p["hover"]),
                           ("disabled", p["panel_alt"])],
               foreground=[("disabled", p["deshab"])],
               bordercolor=[("focus", p["acento"])])
        st.configure("Accent.TButton", background=p["primario"], foreground="#FFFFFF",
                     bordercolor=p["primario"], padding=(px(12), px(3)))
        st.map("Accent.TButton",
               background=[("pressed", p["primario_hover"]), ("active", p["primario_hover"]),
                           ("disabled", p["borde"])],
               foreground=[("disabled", p["deshab"])])
        st.configure("Pendiente.TButton", background=p["aviso_borde"], foreground="#2B2200",
                     bordercolor=p["aviso_borde"], padding=(px(10), px(3)))
        st.map("Pendiente.TButton",
               background=[("active", "#C9A32F"), ("pressed", "#C9A32F")])
        st.configure("Listo.TButton", background=p["panel_alt"], foreground=p["ok"],
                     bordercolor=p["borde"], padding=(px(10), px(3)))
        st.configure("Chico.TButton", background=p["panel_alt"], foreground=p["texto"],
                     bordercolor=p["borde"], padding=(px(8), px(2)), font=self.f["chica"])
        st.map("Chico.TButton", background=[("pressed", p["hover"]), ("active", p["hover"])])
        st.configure("Tool.TButton", background=p["menu"], foreground=p["texto"],
                     padding=(px(6), px(5)), relief="flat", borderwidth=0)
        st.map("Tool.TButton", background=[("active", p["hover"]), ("pressed", p["hover"]),
                                           ("disabled", p["menu"])])
        st.configure("Icono.TButton", background=p["panel"], foreground=p["texto"],
                     padding=(px(4), px(3)), relief="flat", borderwidth=0)
        st.map("Icono.TButton", background=[("active", p["hover"]), ("pressed", p["hover"])])
        st.configure("Cab.TButton", background=p["cab"], foreground=p["cab_txt"],
                     padding=(px(4), px(2)), relief="flat", borderwidth=0)
        st.map("Cab.TButton", background=[("active", p["acento"])])

        st.configure("TEntry", fieldbackground=p["campo"], foreground=p["texto"],
                     bordercolor=p["borde"], padding=(px(5), px(2)), insertcolor=p["texto"])
        st.map("TEntry", bordercolor=[("focus", p["acento"])])
        st.configure("TCombobox", fieldbackground=p["campo"], foreground=p["texto"],
                     background=p["panel_alt"], arrowcolor=p["suave"], bordercolor=p["borde"],
                     padding=(px(5), px(1)), selectbackground=p["campo"],
                     selectforeground=p["texto"], arrowsize=px(12))
        st.map("TCombobox", fieldbackground=[("readonly", p["campo"])],
               foreground=[("readonly", p["texto"])], bordercolor=[("focus", p["acento"])],
               background=[("active", p["hover"])])
        root.option_add("*TCombobox*Listbox.background", p["campo"])
        root.option_add("*TCombobox*Listbox.foreground", p["texto"])
        root.option_add("*TCombobox*Listbox.selectBackground", p["acento"])
        root.option_add("*TCombobox*Listbox.selectForeground", p["acento_txt"])
        root.option_add("*TCombobox*Listbox.font", base)
        st.configure("TSpinbox", fieldbackground=p["campo"], foreground=p["texto"],
                     arrowcolor=p["suave"], bordercolor=p["borde"])

        self._indicadores(st)
        st.configure("TCheckbutton", background=p["bg"], foreground=p["texto"],
                     indicatorcolor=p["campo"], indicatorbackground=p["campo"])
        st.map("TCheckbutton", indicatorcolor=[("selected", p["acento"]), ("pressed", p["hover"])],
               background=[("active", p["bg"])])
        st.configure("Panel.TCheckbutton", background=p["panel"])
        st.map("Panel.TCheckbutton", background=[("active", p["panel"])],
               indicatorcolor=[("selected", p["acento"]), ("pressed", p["hover"])])
        st.configure("TRadiobutton", background=p["bg"], foreground=p["texto"],
                     indicatorcolor=p["campo"])
        st.map("TRadiobutton", indicatorcolor=[("selected", p["acento"])],
               background=[("active", p["bg"])])
        st.configure("Panel.TRadiobutton", background=p["panel"])
        st.map("Panel.TRadiobutton", background=[("active", p["panel"])],
               indicatorcolor=[("selected", p["acento"])])
        # Opciones tipo botón (segmentadas)
        st.configure("Segmento.Toolbutton", background=p["panel_alt"], foreground=p["texto"],
                     bordercolor=p["borde"], padding=(px(9), px(3)), relief="flat",
                     anchor="center")
        st.map("Segmento.Toolbutton",
               background=[("selected", p["acento"]), ("active", p["hover"])],
               foreground=[("selected", p["acento_txt"])],
               bordercolor=[("selected", p["acento"])])

        st.configure("TNotebook", background=p["bg"], borderwidth=0, bordercolor=p["borde"],
                     tabmargins=(px(2), px(4), px(2), 0), lightcolor=p["bg"], darkcolor=p["bg"])
        st.configure("TNotebook.Tab", background=p["panel_alt"], foreground=p["suave"],
                     padding=(px(16), px(7)), bordercolor=p["borde"], lightcolor=p["panel_alt"],
                     darkcolor=p["panel_alt"], font=base)
        st.map("TNotebook.Tab",
               background=[("selected", p["panel"]), ("disabled", p["bg"]), ("active", p["hover"])],
               foreground=[("selected", p["acento"]), ("disabled", p["deshab"])],
               lightcolor=[("selected", p["panel"])], darkcolor=[("selected", p["panel"])],
               expand=[("selected", (0, 0, 0, 0))])
        st.layout("TNotebook.Tab", st.layout("TNotebook.Tab"))
        st.configure("Sub.TNotebook", background=p["panel"], borderwidth=0,
                     tabmargins=(px(2), px(2), px(2), 0))
        st.configure("Sub.TNotebook.Tab", padding=(px(14), px(6)))

        st.configure("Treeview", background=p["panel"], fieldbackground=p["panel"],
                     foreground=p["texto"], rowheight=px(22), bordercolor=p["borde"],
                     lightcolor=p["panel"], darkcolor=p["panel"], borderwidth=1, font=self.f["tabla"])
        st.map("Treeview", background=[("selected", p["sel"])],
               foreground=[("selected", p["texto"])])
        st.configure("Treeview.Heading", background=p["cab"], foreground=p["cab_txt"],
                     relief="flat", padding=(px(6), px(4)), font=self.f["tabla_n"],
                     bordercolor=p["borde"], lightcolor=p["cab"], darkcolor=p["borde"])
        st.map("Treeview.Heading", background=[("active", p["hover"])])
        st.configure("Lista.Treeview", rowheight=px(26))

        for o in ("Vertical", "Horizontal"):
            st.configure(f"{o}.TScrollbar", background=p["borde"], troughcolor=p["panel_alt"],
                         bordercolor=p["panel_alt"], arrowcolor=p["suave"],
                         lightcolor=p["borde"], darkcolor=p["borde"], gripcount=0,
                         arrowsize=px(14))
            st.map(f"{o}.TScrollbar", background=[("active", p["suave"]), ("pressed", p["acento"])])
        st.configure("Horizontal.TProgressbar", background=p["acento"], troughcolor=p["panel_alt"],
                     bordercolor=p["borde"], lightcolor=p["acento"], darkcolor=p["acento"])
        st.configure("TSeparator", background=p["borde"])
        st.configure("TPanedwindow", background=p["bg"])
        st.configure("Sash", sashthickness=px(5), background=p["borde"])
        st.configure("TLabelframe", background=p["panel"], bordercolor=p["borde"],
                     relief="solid")
        st.configure("TLabelframe.Label", background=p["panel"], foreground=p["texto"],
                     font=self.f["negrita"])
        st.configure("Tarjeta.TLabelframe", background=p["panel"], bordercolor=p["borde"],
                     relief="solid")
        st.configure("Tarjeta.TLabelframe.Label", background=p["panel"], foreground=p["acento"],
                     font=self.f["subtitulo"])

        self._avisar()

    # ------------------------------------------------------------------
    def _indicadores(self, st):
        """Casillas y opciones con aspecto limpio (en lugar de la 'X' predeterminada)."""
        try:
            from PIL import Image, ImageDraw, ImageTk
        except Exception:
            return
        p = self.p
        s, k = self.px(18), 4

        def lienzo():
            return Image.new("RGBA", (s * k, s * k), (0, 0, 0, 0))

        def caja(marcado, deshab):
            im = lienzo()
            d = ImageDraw.Draw(im)
            borde = p["deshab"] if deshab else (p["acento"] if marcado else p["suave"])
            fondo = p["panel_alt"] if deshab else (p["acento"] if marcado else p["campo"])
            m = 2 * k
            d.rounded_rectangle((m, m, s * k - m, s * k - m), radius=3 * k, fill=fondo,
                                outline=borde, width=max(2, int(1.4 * k)))
            if marcado:
                d.line([(s * k * 0.27, s * k * 0.52), (s * k * 0.44, s * k * 0.69),
                        (s * k * 0.74, s * k * 0.33)], fill="#FFFFFF", width=int(2.2 * k), joint="curve")
            return ImageTk.PhotoImage(im.resize((s, s), Image.LANCZOS), master=self.root)

        def opcion(marcado, deshab):
            im = lienzo()
            d = ImageDraw.Draw(im)
            borde = p["deshab"] if deshab else (p["acento"] if marcado else p["suave"])
            m = 2 * k
            d.ellipse((m, m, s * k - m, s * k - m), fill=p["campo"], outline=borde,
                      width=max(2, int(1.4 * k)))
            if marcado:
                c = s * k / 2
                r = s * k * 0.20
                d.ellipse((c - r, c - r, c + r, c + r), fill=borde)
            return ImageTk.PhotoImage(im.resize((s, s), Image.LANCZOS), master=self.root)

        n = self.nombre
        todas = self.__dict__.setdefault("_imgs_ind", {})      # una colección por tema (Tk no las libera)
        if n not in todas:
            imgs = {"c0": caja(False, False), "c1": caja(True, False), "c0d": caja(False, True),
                    "c1d": caja(True, True), "r0": opcion(False, False), "r1": opcion(True, False),
                    "r0d": opcion(False, True), "r1d": opcion(True, True)}
            todas[n] = imgs
            for base, o in (("Checkbutton", "c"), ("Radiobutton", "r")):
                st.element_create(f"Sima.{base}.{n}", "image", imgs[f"{o}0"],
                                  ("disabled", "selected", imgs[f"{o}1d"]),
                                  ("disabled", imgs[f"{o}0d"]),
                                  ("selected", imgs[f"{o}1"]))
        for base in ("Checkbutton", "Radiobutton"):
            elemento = f"Sima.{base}.{n}"
            st.layout(f"T{base}", [(f"{base}.padding", {"sticky": "nswe", "children": [
                (elemento, {"side": "left", "sticky": ""}),
                (f"{base}.focus", {"side": "left", "sticky": "w", "children": [
                    (f"{base}.label", {"sticky": "nswe"})]})]})])

    def icono(self, nombre, tam=16, color=None):
        """PhotoImage del glifo (Segoe MDL2). Devuelve None si no se puede generar."""
        color = color or self.p["texto"]
        clave = (nombre, tam, color)
        if clave in self._cache:
            return self._cache[clave]
        img = None
        try:
            from PIL import Image, ImageDraw, ImageFont, ImageTk
            if self._ruta_iconos and nombre in GLIFOS:
                t = self.px(tam)
                s = t * 4
                lienzo = Image.new("RGBA", (s, s), (0, 0, 0, 0))
                fuente = ImageFont.truetype(self._ruta_iconos, int(s * 0.80))
                ImageDraw.Draw(lienzo).text((s / 2, s / 2), chr(GLIFOS[nombre]), font=fuente,
                                            fill=color, anchor="mm")
                img = ImageTk.PhotoImage(lienzo.resize((t, t), Image.LANCZOS), master=self.root)
        except Exception:
            img = None
        self._cache[clave] = img
        return img


T = _Tema()


# ----------------------------------------------------------------------------
# Utilidades de ventana
# ----------------------------------------------------------------------------
def titulo_oscuro(ventana, oscuro):
    """Barra de título oscura en Windows 10/11 (si el sistema lo soporta)."""
    try:
        ventana.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(ventana.winfo_id()) or ventana.winfo_id()
        valor = ctypes.c_int(1 if oscuro else 0)
        for atributo in (20, 19):
            if ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    hwnd, atributo, ctypes.byref(valor), ctypes.sizeof(valor)) == 0:
                break
    except Exception:
        pass


def area_trabajo(x, y, widget=None):
    """(x0, y0, x1, y1) del área de trabajo (sin barra de tareas) del monitor que contiene el punto.
    Funciona con varias pantallas: las ventanas emergentes se quedan en la pantalla del programa."""
    try:
        from ctypes import wintypes

        class MONITORINFO(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                        ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]
        u32 = ctypes.windll.user32
        u32.MonitorFromPoint.argtypes = [wintypes.POINT, wintypes.DWORD]
        u32.MonitorFromPoint.restype = ctypes.c_void_p
        u32.GetMonitorInfoW.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        h = u32.MonitorFromPoint(wintypes.POINT(int(x), int(y)), 2)        # el más cercano
        mi = MONITORINFO()
        mi.cbSize = ctypes.sizeof(MONITORINFO)
        if h and u32.GetMonitorInfoW(h, ctypes.byref(mi)):
            r = mi.rcWork
            return r.left, r.top, r.right, r.bottom
    except Exception:
        pass
    w = widget or T.root
    return 0, 0, w.winfo_screenwidth(), w.winfo_screenheight()


def ajustar_a_pantalla(x, y, w, h, referencia=None, widget=None):
    """Posición (x, y) para una ventana de w×h que quede completa dentro del monitor del punto de
    referencia (por defecto, el propio punto)."""
    rx, ry = referencia if referencia else (x + 10, y + 10)
    x0, y0, x1, y1 = area_trabajo(rx, ry, widget)
    x = max(x0 + 4, min(int(x), x1 - int(w) - 4))
    y = max(y0 + 4, min(int(y), y1 - int(h) - 4))
    return x, y


def centrar(ventana, padre=None, ancho=None, alto=None):
    """Centra una ventana sobre su ventana principal, en el mismo monitor."""
    ventana.update_idletasks()
    w = ancho or ventana.winfo_reqwidth()
    h = alto or ventana.winfo_reqheight()
    if padre is not None and padre.winfo_viewable():
        cx = padre.winfo_rootx() + padre.winfo_width() // 2
        cy = padre.winfo_rooty() + padre.winfo_height() // 2
    else:
        x0, y0, x1, y1 = area_trabajo(ventana.winfo_pointerx(), ventana.winfo_pointery(), ventana)
        cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
    x0, y0, x1, y1 = area_trabajo(cx, cy, ventana)
    w, h = min(w, x1 - x0 - 16), min(h, y1 - y0 - 16)
    x, y = ajustar_a_pantalla(cx - w // 2, cy - h // 2, w, h, (cx, cy), ventana)
    if ancho or alto:
        ventana.geometry(f"{int(w)}x{int(h)}+{x}+{y}")
    else:
        ventana.geometry(f"+{x}+{y}")


class Tooltip:
    def __init__(self, widget, texto, retraso=500):
        self.widget, self.texto, self.retraso = widget, texto, retraso
        self.ventana = None
        self._id = None
        widget.bind("<Enter>", self._programar, add="+")
        widget.bind("<Leave>", self._ocultar, add="+")
        widget.bind("<ButtonPress>", self._ocultar, add="+")

    def _programar(self, _e=None):
        self._ocultar()
        self._id = self.widget.after(self.retraso, self._mostrar)

    def _mostrar(self):
        if self.ventana or not self.texto:
            return
        p = T.p
        try:
            if not self.widget.winfo_viewable():
                return
        except tk.TclError:
            return
        self.ventana = tk.Toplevel(self.widget)
        self.ventana.wm_overrideredirect(True)
        # pegada al programa (no queda por encima de otras aplicaciones)
        self.ventana.transient(self.widget.winfo_toplevel())
        lbl = tk.Label(self.ventana, text=self.texto, background=p["panel"], foreground=p["texto"],
                       relief="solid", borderwidth=1, padx=T.px(8), pady=T.px(4),
                       font=T.f["chica"], wraplength=T.px(420), justify="left")
        lbl.pack()
        self.ventana.update_idletasks()
        x = self.widget.winfo_rootx() + 10
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
        x, y = ajustar_a_pantalla(x, y, lbl.winfo_reqwidth(), lbl.winfo_reqheight(),
                                  (self.widget.winfo_rootx() + 2, self.widget.winfo_rooty() + 2), self.widget)
        self.ventana.geometry(f"+{x}+{y}")

    def _ocultar(self, _e=None):
        if self._id:
            try:
                self.widget.after_cancel(self._id)
            except tk.TclError:
                pass
            self._id = None
        if self.ventana:
            try:
                self.ventana.destroy()
            except tk.TclError:
                pass
            self.ventana = None
