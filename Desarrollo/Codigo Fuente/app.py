"""Aplicación principal: ventanas, menús, pestañas de escenarios y flujos de trabajo.

Cada ventana (App) tiene sus menús, barra de herramientas, pestañas de escenarios y barra de estado. Un
escenario puede sacarse a otra ventana (arrastrando su pestaña fuera de la barra o con el menú
contextual) para verlo en otra pantalla; la ventana principal cierra todo al salir.
"""
import logging
import os
import subprocess
import sys
import tkinter as tk
import traceback
from pathlib import Path
from tkinter import ttk

import config
import csvio
import dialogo_archivos as da
import fmt
import modelo
from archivo_manager import ErrorEscenario, GestorEscenarios
from dialogos import VentanaModal, aviso, confirmar, con_progreso, error
from escenario import Escenario
from tema import T, Tooltip, ajustar_a_pantalla, titulo_oscuro
from ui_comun import cerrar_emergente
from vista_escenario import VistaEscenario

log = logging.getLogger("sima")
FILTROS_SIMX = [("Escenario de SimA (*.simx)", "*.simx"), ("Todos los Archivos", "*.*")]
MAX_RECIENTES = 10


class BarraDocs(ttk.Frame):
    """Pestañas de escenarios abiertos (una por documento). Arrastrar una pestaña fuera de la barra la
    lleva a una ventana nueva (o a la barra de otra ventana de SimA)."""

    def __init__(self, master, app):
        super().__init__(master, style="Docs.TFrame")
        self.app = app
        self.items = {}
        self._firma = None
        self._arr = None

    @staticmethod
    def _texto(doc):
        texto = ("● " if doc.esc.sucio else "") + doc.esc.nombre_visible
        return texto[:33] + "…" if len(texto) > 34 else texto

    def reconstruir(self):
        firma = (tuple(id(d) for d in self.app.docs), id(self.app.actual), T.nombre)
        if firma == self._firma and set(self.items) == set(self.app.docs):
            for doc, lbl in self.items.items():
                t = self._texto(doc)
                if lbl.cget("text") != t:
                    lbl.configure(text=t)
            return
        self._firma = firma
        for w in self.winfo_children():
            w.destroy()
        self.items = {}
        p = T.p
        self.configure(style="Docs.TFrame")
        for doc in self.app.docs:
            activo = doc is self.app.actual
            fondo = p["panel"] if activo else p["barra_docs"]
            marco = tk.Frame(self, background=fondo)
            marco.pack(side="left", padx=(0, 1))
            linea = tk.Frame(marco, background=p["acento"] if activo else p["barra_docs"], height=T.px(3))
            linea.pack(fill="x")
            interior = tk.Frame(marco, background=fondo)
            interior.pack(fill="x")
            lbl = tk.Label(interior, text=self._texto(doc), background=fondo,
                           foreground=p["texto"] if activo else p["suave"],
                           font=T.f["negrita"] if activo else T.f["base"],
                           padx=T.px(12), pady=T.px(6), cursor="hand2")
            lbl.pack(side="left")
            cerrar = tk.Label(interior, image=T.icono("cerrar", 12, p["suave"]), background=fondo,
                              padx=T.px(6), cursor="hand2")
            cerrar.pack(side="left", padx=(0, T.px(4)))
            for w in (lbl, interior, marco):
                w.bind("<ButtonPress-1>", lambda e, d=doc: self._presionar(e, d))
                w.bind("<B1-Motion>", self._arrastrar)
                w.bind("<ButtonRelease-1>", self._soltar)
                w.bind("<Button-2>", lambda e, d=doc: self.app.cerrar(d))
                w.bind("<Button-3>", lambda e, d=doc: self._menu(e, d))
            Tooltip(lbl, "Arrastre la pestaña fuera de la barra para abrir el escenario en otra ventana "
                         "(clic derecho: más opciones)", retraso=900)
            cerrar.bind("<Button-1>", lambda e, d=doc: self.app.cerrar(d))
            cerrar.bind("<Enter>", lambda e, c=cerrar: c.configure(image=T.icono("cerrar", 12, T.p["error"])))
            cerrar.bind("<Leave>", lambda e, c=cerrar: c.configure(image=T.icono("cerrar", 12, T.p["suave"])))
            self.items[doc] = lbl
        nuevo = tk.Label(self, image=T.icono("agregar", 14, p["suave"]), background=p["barra_docs"],
                         padx=T.px(10), pady=T.px(8), cursor="hand2")
        nuevo.pack(side="left")
        nuevo.bind("<Button-1>", lambda e: self.app.nuevo())
        Tooltip(nuevo, "Nuevo Escenario (Ctrl+N)")

    # --- arrastrar una pestaña a otra ventana ------------------------------------------------------
    def _presionar(self, e, doc):
        self.app.seleccionar(doc)
        self._arr = {"doc": doc, "x": e.x_root, "y": e.y_root, "fantasma": None}

    def _fuera(self, x, y):
        top = self.winfo_toplevel()
        bx0, by0 = self.winfo_rootx(), self.winfo_rooty()
        dentro_barra = bx0 - 30 <= x <= bx0 + self.winfo_width() + 30 and by0 - 40 <= y <= by0 + self.winfo_height() + 40
        return not dentro_barra, (top.winfo_rootx() <= x <= top.winfo_rootx() + top.winfo_width()
                                  and top.winfo_rooty() <= y <= top.winfo_rooty() + top.winfo_height())

    def _arrastrar(self, e):
        d = self._arr
        if not d:
            return
        fuera, _ = self._fuera(e.x_root, e.y_root)
        if d["fantasma"] is None:
            if not fuera:
                return
            g = tk.Toplevel(self)
            g.overrideredirect(True)
            g.transient(self.winfo_toplevel())
            try:
                g.attributes("-alpha", 0.9)
            except tk.TclError:
                pass
            img = T.icono("ventana", 14, "#FFFFFF")
            g._img = img
            tk.Label(g, text=f"  {d['doc'].esc.nombre_visible}  ·  Soltar para abrir en otra ventana  ",
                     image=img, compound="left", background=T.p["acento"], foreground="#FFFFFF",
                     font=T.f["negrita"], padx=T.px(8), pady=T.px(5)).pack()
            d["fantasma"] = g
        d["fantasma"].geometry(f"+{e.x_root + 12}+{e.y_root + 10}")

    def _soltar(self, e):
        d, self._arr = self._arr, None
        if not d or d["fantasma"] is None:
            return
        d["fantasma"].destroy()
        # ¿sobre la barra de escenarios de otra ventana?
        for v in App.ventanas:
            if v is self.app or not v.vivo():
                continue
            b = v.tabs
            if b.winfo_rootx() <= e.x_root <= b.winfo_rootx() + b.winfo_width() and \
                    b.winfo_rooty() - 20 <= e.y_root <= b.winfo_rooty() + b.winfo_height() + 20:
                self.app.mover_doc(d["doc"], v)
                return
        self.app.mover_doc(d["doc"], None, (e.x_root, e.y_root))

    def _menu(self, e, doc):
        from ui_comun import mostrar_menu, nuevo_menu
        m = nuevo_menu(self)
        m.add_command(label="Abrir en Ventana Nueva", command=lambda: self.app.mover_doc(doc, None))
        otras = [v for v in App.ventanas if v is not self.app and v.vivo()]
        for v in otras:
            nombre = "Ventana Principal" if v.es_principal else f"Ventana {App.ventanas.index(v) + 1}"
            m.add_command(label=f"Mover a {nombre}", command=lambda vv=v: self.app.mover_doc(doc, vv))
        m.add_separator()
        m.add_command(label="Cerrar Escenario", command=lambda: self.app.cerrar(doc))
        mostrar_menu(m, e)


class App:
    """Una ventana de SimA. La primera (principal) crea la aplicación; las demás muestran escenarios
    llevados a otra ventana."""

    ventanas = []

    def __init__(self, principal=None, posicion=None):
        self.es_principal = principal is None
        self.principal = self if principal is None else principal
        if self.es_principal:
            self._preparar_sistema()
            self.root = tk.Tk()
            self.prefs = config.cargar_preferencias()
            T.iniciar(self.root, self.prefs.get("tema", "claro"))
            from ui_comun import instalar_rueda
            instalar_rueda(self.root)
            self.gestor = GestorEscenarios()
        else:
            self.root = tk.Toplevel(principal.root)
            self.prefs = principal.prefs
            self.gestor = principal.gestor
        self.root._sima_app = self
        App.ventanas.append(self)
        self.panel_fijo = bool(self.prefs.get("panel_fijo", True))
        self.docs = []
        self.actual = None
        self._ico = None
        self._msg_id = None
        self._iconos_menu = []
        self._pos_previa = None

        self.root.title(config.NOMBRE_PROGRAMA)
        self.root.minsize(T.px(1000), T.px(640))
        self._geometria_inicial(posicion)
        self._icono_ventana()
        self.root.report_callback_exception = self._excepcion
        self.root.protocol("WM_DELETE_WINDOW", self.salir if self.es_principal else self.cerrar_ventana)
        self.root.configure(background=T.p["bg"])

        # estructura: una franja con los menús, la barra de herramientas y la marca
        self.barra_herr = ttk.Frame(self.root, style="Menu.TFrame")
        self.barra_herr.pack(fill="x")
        self.zona_menus = ttk.Frame(self.barra_herr, style="Menu.TFrame")
        self.zona_menus.pack(side="left")
        self.zona_herr = ttk.Frame(self.barra_herr, style="Menu.TFrame")
        self.zona_herr.pack(side="left")
        self.zona_marca = ttk.Frame(self.barra_herr, style="Menu.TFrame")
        self.zona_marca.pack(side="right", padx=(0, T.px(12)))
        ttk.Frame(self.root, style="Linea.TFrame", height=1).pack(fill="x")
        self.tabs = BarraDocs(self.root, self)
        self.tabs.pack(fill="x")
        self.estado = ttk.Frame(self.root, style="Alt.TFrame")
        self.estado.pack(side="bottom", fill="x")
        ttk.Frame(self.root, style="Linea.TFrame", height=1).pack(side="bottom", fill="x")
        self.var_msg = tk.StringVar(value="Listo")
        self.var_info = tk.StringVar()
        ttk.Label(self.estado, textvariable=self.var_msg, style="Estado.TLabel",
                  padding=(T.px(12), T.px(4))).pack(side="left")
        ttk.Label(self.estado, textvariable=self.var_info, style="Estado.TLabel",
                  padding=(T.px(12), T.px(4))).pack(side="right")
        self.contenedor = ttk.Frame(self.root)
        self.contenedor.pack(fill="both", expand=True)

        self._construir_menus()
        self._construir_toolbar()
        self._construir_marca()
        T.registrar(self._tras_tema)
        self._atajos()
        titulo_oscuro(self.root, T.nombre == "oscuro")
        # las listas desplegables se cierran si la ventana se mueve o cambia de tamaño
        self.root.bind("<Configure>", self._al_configurar, add="+")

        if self.es_principal:
            self.nuevo()
            import perezoso
            self.root.after(300, perezoso.precargar)
            for arg in sys.argv[1:]:
                if arg.lower().endswith(config.EXTENSION) and os.path.isfile(arg):
                    self.root.after(150, lambda a=arg: self.abrir(a))
                    break

    # ------------------------------------------------------------------------------------
    def vivo(self):
        try:
            return bool(self.root.winfo_exists())
        except tk.TclError:
            return False

    def _geometria_inicial(self, posicion):
        if self.es_principal:
            ancho, alto = T.px(1440), T.px(860)
            sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
            ancho, alto = min(ancho, sw - 60), min(alto, sh - 100)
            self.root.geometry(f"{ancho}x{alto}+{(sw - ancho) // 2}+{max(0, (sh - alto) // 3)}")
            return
        p = self.principal.root
        ancho = max(T.px(1000), int(p.winfo_width() * 0.9))
        alto = max(T.px(640), int(p.winfo_height() * 0.9))
        x, y = posicion if posicion else (p.winfo_rootx() + T.px(60), p.winfo_rooty() + T.px(40))
        x, y = ajustar_a_pantalla(x - T.px(120), y - T.px(14), ancho, alto, (x, y), p)
        self.root.geometry(f"{ancho}x{alto}+{x}+{y}")

    @staticmethod
    def _preparar_sistema():
        try:
            import ctypes
            try:
                ctypes.windll.shcore.SetProcessDpiAwareness(2)
            except Exception:
                ctypes.windll.user32.SetProcessDPIAware()
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("SimA.SimulationAnalyst")
        except Exception:
            pass

    def _icono_ventana(self):
        try:
            png = config.dir_recursos() / "icono.png"
            if png.is_file():
                self._ico = tk.PhotoImage(file=str(png), master=self.root)
                self.root.iconphoto(True, self._ico)
        except Exception:
            pass

    def _excepcion(self, tipo, valor, tb):
        texto = "".join(traceback.format_exception(tipo, valor, tb))
        log.error("Error no controlado:\n%s", texto)
        try:
            error(self.root, "Error Inesperado",
                  ["Ocurrió un error inesperado. El detalle quedó registrado en el archivo de "
                   "registro del programa.", f"{tipo.__name__}: {valor}"])
        except Exception:
            pass

    def _al_configurar(self, e):
        if e.widget is not self.root:
            return
        pos = (e.x, e.y, e.width, e.height)
        if self._pos_previa is not None and pos != self._pos_previa:
            cerrar_emergente(solo_ligeras=True)
        self._pos_previa = pos

    # ---- menús -----------------------------------------------------------------------------
    def _menu_popup(self, **kw):
        p = T.p
        return tk.Menu(self.root, tearoff=0, bg=p["menu"], fg=p["texto"], activebackground=p["acento"],
                       activeforeground=p["acento_txt"], disabledforeground=p["deshab"],
                       selectcolor=p["acento"], relief="flat", borderwidth=1, font=T.f["base"],
                       activeborderwidth=0, **kw)

    def _item(self, menu, texto, comando, icono=None, atajo=""):
        img = T.icono(icono, 16) if icono else None
        if img:
            self._iconos_menu.append(img)
        opciones = dict(label=texto, command=comando, accelerator=atajo)
        if img:
            opciones.update(image=img, compound="left")
        menu.add_command(**opciones)

    def _construir_menus(self):
        for w in self.zona_menus.winfo_children():
            w.destroy()
        for m in getattr(self, "menus", {}).values():
            m.destroy()
        self._iconos_menu = []
        self.menus = {}

        m = self._menu_popup()
        self._item(m, "Nuevo", self.nuevo, "nuevo", "Ctrl+N")
        self._item(m, "Abrir…", self.abrir, "abrir", "Ctrl+O")
        self.menu_recientes = self._menu_popup(postcommand=self._llenar_recientes)
        img = T.icono("reciente", 16)
        self._iconos_menu.append(img)
        m.add_cascade(label="Abrir Existente", menu=self.menu_recientes, image=img, compound="left")
        m.add_separator()
        self._item(m, "Guardar", self.guardar, "guardar", "Ctrl+S")
        self._item(m, "Guardar Como…", self.guardar_como, "guardar_como", "Ctrl+Shift+S")
        m.add_separator()
        self._item(m, "Desactivar Modo Noche" if T.nombre == "oscuro" else "Activar Modo Noche",
                   self.alternar_noche, "noche", "Ctrl+Shift+M")
        m.add_separator()
        self._item(m, "Cerrar Escenario", self.cerrar_actual, "cerrar", "Ctrl+W")
        if self.es_principal:
            self._item(m, "Salir", self.salir, "salir", "Alt+F4")
        else:
            self._item(m, "Cerrar Ventana", self.cerrar_ventana, "salir", "Alt+F4")
        self.menus["Archivo"] = m

        m = self._menu_popup(postcommand=self._actualizar_menu_modelo)
        self._item(m, "Importar Resultados Simulación CSV…", self.importar, "importar", "Ctrl+I")
        self._item(m, "Importar Métricas Plan…", lambda: self.importar_plan(), "tabla")
        self._item(m, "Ejecutar Análisis", self.ejecutar, "ejecutar", "F5")
        m.add_separator()
        self._item(m, "Vincular Filtros entre Tablas y Gráficos", self.alternar_vincular, "filtro")
        self._idx_vincular = m.index("end")
        m.add_separator()
        self._item(m, "Exportar Reporte Excel…", self.exportar_excel, "excel", "Ctrl+E")
        self._item(m, "Exportar Reporte PowerPoint…", self.exportar_pptx, "ppt", "Ctrl+Shift+E")
        self._item(m, "Exportar Resultados Plan vs Simulación…", lambda: self.exportar_plan(), "excel",
                   "Ctrl+Shift+P")
        self.menus["Modelo"] = m

        m = self._menu_popup()
        self._item(m, "Análisis de Estados (Pivot)", self.tool_estados_pivot, "tabla", "Ctrl+Shift+A")
        self._item(m, "Registro de Cargas (Pivot)", self.tool_registro_cargas, "analitica", "Ctrl+Shift+R")
        m.add_separator()
        self._item(m, "Abrir Escenario en Ventana Nueva", lambda: self.actual and self.mover_doc(self.actual, None),
                   "ventana")
        self.menus["Tools"] = m

        ttk.Frame(self.zona_menus, style="Menu.TFrame", width=T.px(4)).pack(side="left")
        for texto, tecla in (("Archivo", "a"), ("Modelo", "m"), ("Tools", "t")):
            etq = ttk.Label(self.zona_menus, text=texto, style="Menu.TLabel", cursor="hand2")
            etq.pack(side="left")
            self._enlazar_menu(etq, self.menus[texto])
            self.root.bind(f"<Alt-{tecla}>", lambda e, w=etq, mm=self.menus[texto]: self._abrir_menu(w, mm))
        acerca = ttk.Label(self.zona_menus, text="Acerca de SimA", style="Menu.TLabel", cursor="hand2")
        acerca.pack(side="left")
        ttk.Frame(self.zona_menus, style="Linea.TFrame", width=1).pack(side="left", fill="y",
                                                                       padx=T.px(8), pady=T.px(6))
        acerca.bind("<Button-1>", lambda e: self.acerca())
        acerca.bind("<Enter>", lambda e: acerca.configure(background=T.p["hover"]))
        acerca.bind("<Leave>", lambda e: acerca.configure(background=T.p["menu"]))
        self.root.bind("<Alt-s>", lambda e: self.acerca())

    def _actualizar_menu_modelo(self):
        d = self.actual
        activo = bool(d is None or d.esc.vistas.get("vincular_filtros", True))
        try:
            self.menus["Modelo"].entryconfigure(self._idx_vincular, label=(
                "Desvincular Filtros entre Tablas y Gráficos" if activo else "Vincular Filtros entre Tablas y Gráficos"))
        except tk.TclError:
            pass

    def alternar_vincular(self):
        d = self.actual
        if d is None:
            return
        v = not d.esc.vistas.get("vincular_filtros", True)
        d.esc.vistas["vincular_filtros"] = v
        d.esc.marcar_sucio()
        d.refrescar_todo()
        self.mensaje("Filtros vinculados: un filtro de encabezado se aplica a toda la pestaña" if v else
                     "Filtros independientes: cada filtro de encabezado se aplica solo a su tabla")

    def _llenar_recientes(self):
        m = self.menu_recientes
        m.delete(0, "end")
        recientes = [r for r in (config.cargar_preferencias().get("recientes") or []) if os.path.isfile(r)]
        if not recientes:
            m.add_command(label="(Sin escenarios recientes)", state="disabled")
            return
        for r in recientes:
            carpeta = Path(r).parent.name
            m.add_command(label=f"{Path(r).name}    —  {carpeta}", command=lambda rr=r: self.abrir(rr))
        m.add_separator()
        m.add_command(label="Limpiar Lista", command=self._limpiar_recientes)

    @staticmethod
    def _recordar_reciente(ruta):
        prefs = config.cargar_preferencias()
        lista = [r for r in (prefs.get("recientes") or []) if os.path.normcase(r) != os.path.normcase(ruta)]
        prefs["recientes"] = ([str(ruta)] + lista)[:MAX_RECIENTES]
        config.guardar_preferencias(prefs)

    @staticmethod
    def _limpiar_recientes():
        prefs = config.cargar_preferencias()
        prefs["recientes"] = []
        config.guardar_preferencias(prefs)

    def _enlazar_menu(self, etq, menu):
        etq.bind("<Enter>", lambda e: etq.configure(background=T.p["hover"]))
        etq.bind("<Leave>", lambda e: etq.configure(background=T.p["menu"]))
        etq.bind("<Button-1>", lambda e: self._abrir_menu(etq, menu))

    def _abrir_menu(self, etq, menu):
        cerrar_emergente(solo_ligeras=True)
        x = etq.winfo_rootx()
        y = etq.winfo_rooty() + etq.winfo_height()
        try:
            menu.tk_popup(x, y)
        finally:
            menu.grab_release()

    def _construir_toolbar(self):
        for w in self.zona_herr.winfo_children():
            w.destroy()
        self._iconos_barra = []

        def boton(icono, tip, cmd, color=None):
            img = T.icono(icono, 16, color)
            self._iconos_barra.append(img)
            b = ttk.Button(self.zona_herr, image=img, style="Tool.TButton", command=cmd, takefocus=False)
            b.pack(side="left", padx=(T.px(1), 0), pady=T.px(2))
            Tooltip(b, tip)
            return b

        def sep():
            f = ttk.Frame(self.zona_herr, style="Linea.TFrame", width=1)
            f.pack(side="left", fill="y", padx=T.px(6), pady=T.px(6))

        boton("nuevo", "Nuevo (Ctrl+N)", self.nuevo)
        boton("abrir", "Abrir (Ctrl+O)", self.abrir)
        boton("guardar", "Guardar (Ctrl+S)", self.guardar)
        sep()
        boton("importar", "Importar Resultados Simulación CSV (Ctrl+I)", self.importar)
        boton("ejecutar", "Ejecutar Análisis (F5)", self.ejecutar, T.p["ok"])
        sep()
        boton("excel", "Exportar Reporte Excel (Ctrl+E)", self.exportar_excel)
        boton("ppt", "Exportar Reporte PowerPoint (Ctrl+Shift+E)", self.exportar_pptx)
        boton("tabla", "Exportar Resultados Plan vs Simulación (Ctrl+Shift+P)", lambda: self.exportar_plan())
        sep()
        boton("pivote", "Análisis de Estados (Pivot) (Ctrl+Shift+A)", self.tool_estados_pivot)
        boton("analitica", "Registro de Cargas (Pivot) (Ctrl+Shift+R)", self.tool_registro_cargas)
        boton("ventana", "Abrir Escenario en Ventana Nueva", lambda: self.actual and self.mover_doc(self.actual, None))

    def _construir_marca(self):
        """Logo, nombre y versión del programa a la derecha de la barra de menús."""
        for w in self.zona_marca.winfo_children():
            w.destroy()
        p = T.p
        try:
            png = config.dir_recursos() / "icono.png"
            img = tk.PhotoImage(file=str(png), master=self.root)
            factor = max(1, img.width() // T.px(18))
            self._logo = img.subsample(factor, factor)
            tk.Label(self.zona_marca, image=self._logo, background=p["menu"]).pack(side="left", padx=(0, T.px(6)))
        except Exception:
            pass
        tk.Label(self.zona_marca, text="SimA", background=p["menu"], foreground=p["texto"],
                 font=T.f["subtitulo"]).pack(side="left")
        tk.Label(self.zona_marca, text="Simulation Analyst", background=p["menu"], foreground=p["suave"],
                 font=T.f["chica"]).pack(side="left", padx=(T.px(5), 0), pady=(T.px(2), 0))
        from ui_github import Pildora
        Pildora(self.zona_marca, config.VERSION_CORTA, color=p["acento"], relleno=p["sel"],
                fondo=p["menu"]).pack(side="left", padx=(T.px(8), 0))

    def _tras_tema(self):
        if not self.vivo():
            return
        self.root.configure(background=T.p["bg"])
        self._construir_menus()
        self._construir_toolbar()
        self._construir_marca()
        self.tabs.reconstruir()

    def _atajos(self):
        r = self.root

        def ligar(secuencia, fn):
            r.bind(secuencia, lambda e: (fn(), "break")[1])

        for letra, fn in (("n", self.nuevo), ("o", self.abrir), ("s", self.guardar),
                          ("w", self.cerrar_actual), ("i", self.importar), ("e", self.exportar_excel)):
            ligar(f"<Control-{letra}>", fn)
        for letra, fn in (("s", self.guardar_como), ("e", self.exportar_pptx),
                          ("r", self.tool_registro_cargas), ("a", self.tool_estados_pivot),
                          ("m", self.alternar_noche), ("p", lambda: self.exportar_plan())):
            ligar(f"<Control-Shift-{letra.upper()}>", fn)
            ligar(f"<Control-Shift-{letra}>", fn)
        ligar("<F5>", self.ejecutar)
        ligar("<F1>", self.acerca)
        ligar("<Control-Tab>", lambda: self._ciclar(1))
        ligar("<Control-Shift-Tab>", lambda: self._ciclar(-1))
        ligar("<Control-ISO_Left_Tab>", lambda: self._ciclar(-1))

    def _ciclar(self, paso):
        if len(self.docs) > 1 and self.actual in self.docs:
            i = (self.docs.index(self.actual) + paso) % len(self.docs)
            self.seleccionar(self.docs[i])

    # ---- documentos --------------------------------------------------------------------------
    def nuevo(self):
        return self._abrir_doc(Escenario())

    def _abrir_doc(self, esc):
        vista = VistaEscenario(self.contenedor, self, esc)
        self.docs.append(vista)
        self.seleccionar(vista)
        return vista

    def seleccionar(self, doc):
        if self.actual is not None and self.actual is not doc:
            cerrar_emergente()
            self.actual.pack_forget()
        self.actual = doc
        doc.pack(fill="both", expand=True)
        doc.al_mostrar()
        self.refrescar_titulos()
        self.actualizar_barra_estado()

    def refrescar_titulos(self):
        titulo = config.NOMBRE_PROGRAMA if self.actual is None else \
            f"{config.NOMBRE_PROGRAMA}: {self.actual.esc.nombre_visible}"
        if self.root.title() != titulo:
            self.root.title(titulo)
        self.tabs.reconstruir()
        self.actualizar_barra_estado()

    def actualizar_barra_estado(self):
        d = self.actual
        if d is None:
            self.var_info.set("")
            return
        e = d.esc
        partes = [f"Escenario: {e.nombre_visible}",
                  "Resultados: Ejecutado" if e.estado == "ejecutado" else
                  ("Resultados: Desactualizados" if e.resultados else "Resultados: Sin Ejecutar")]
        if e.replicas:
            partes.append(f"Réplica: {e.replica}")
        if e.ruta:
            partes.append(Path(e.ruta).name)
        texto = "   ·   ".join(partes)
        if self.var_info.get() != texto:
            self.var_info.set(texto)

    def mensaje(self, texto, ms=7000):
        self.var_msg.set(texto)
        if self._msg_id:
            self.root.after_cancel(self._msg_id)
        self._msg_id = self.root.after(ms, lambda: self.var_msg.set("Listo"))

    def cerrar_actual(self):
        if self.actual:
            self.cerrar(self.actual)

    def cerrar(self, doc, sin_reemplazo=False):
        if doc.esc.sucio and not self._es_vacio(doc):
            self.seleccionar(doc)
            r = confirmar(self.root, "Cambios sin Guardar",
                          f"El escenario «{doc.esc.nombre_visible}» tiene cambios sin guardar.",
                          ("Guardar", "No Guardar", "Cancelar"), cancelar=2)
            if r == 2:
                return False
            if r == 0 and not self.guardar(doc):
                return False
        self._quitar_doc(doc, sin_reemplazo)
        return True

    def _quitar_doc(self, doc, sin_reemplazo=False):
        cerrar_emergente(aplicar=False)
        idx = self.docs.index(doc)
        self.docs.remove(doc)
        doc.pack_forget()
        doc.destroy()
        if self.actual is doc:
            self.actual = None
        if not self.docs:
            if self.es_principal:
                if not sin_reemplazo:
                    self.nuevo()
            elif not sin_reemplazo:
                self.root.after_idle(self._destruir_ventana)
                return
        elif self.actual is None:
            self.seleccionar(self.docs[max(0, idx - 1)])
        else:
            self.refrescar_titulos()

    def mover_doc(self, doc, destino=None, posicion=None):
        """Lleva un escenario a otra ventana (destino=None: ventana nueva en la posición indicada)."""
        if doc is None or doc not in self.docs:
            return
        if destino is self:
            return
        if destino is None:
            if posicion is None:
                posicion = (self.root.winfo_rootx() + T.px(80), self.root.winfo_rooty() + T.px(60))
            destino = App(principal=self.principal, posicion=posicion)
        pestana = doc.pestana_actual()
        nueva = destino._abrir_doc(doc.esc)
        nueva.df_registro, nueva._registro_fallido = doc.df_registro, doc._registro_fallido
        nueva.mostrar_pestana(pestana)
        # una ventana nueva no conserva el escenario vacío inicial
        self._quitar_doc(doc)
        destino.root.deiconify()
        destino.root.lift()
        destino.root.focus_force()
        destino.mensaje(f"Escenario «{doc.esc.nombre_visible}» abierto en esta ventana")

    @staticmethod
    def _es_vacio(doc):
        e = doc.esc
        return not e.archivos and not e.nombre.strip() and not e.descripcion.strip() and not e.ruta

    def cerrar_ventana(self):
        """Ventana secundaria: cierra sus escenarios (con confirmación) y la ventana."""
        for d in list(self.docs):
            if not self.cerrar(d, sin_reemplazo=True):
                return False
        self._destruir_ventana()
        return True

    def _destruir_ventana(self):
        if self in App.ventanas:
            App.ventanas.remove(self)
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    def salir(self):
        for v in [v for v in App.ventanas if v is not self and v.vivo()]:
            if not v.cerrar_ventana():
                return
        for d in list(self.docs):
            if not self.cerrar(d, sin_reemplazo=True):
                if not self.docs:
                    self.nuevo()
                return
        previas = config.cargar_preferencias()
        previas.update({"tema": T.nombre, "panel_fijo": self.panel_fijo})
        config.guardar_preferencias(previas)
        self.root.destroy()

    def todas_las_vistas(self):
        return [d for v in App.ventanas if v.vivo() for d in v.docs]

    # ---- tema y panel -------------------------------------------------------------------------------
    def alternar_noche(self):
        T.aplicar("claro" if T.nombre == "oscuro" else "oscuro")
        for v in App.ventanas:
            if v.vivo():
                titulo_oscuro(v.root, T.nombre == "oscuro")
                for d in v.docs:
                    d.refrescar_todo()
        previas = config.cargar_preferencias()
        previas["tema"] = T.nombre
        config.guardar_preferencias(previas)

    def set_panel_fijo(self, fijo):
        self.panel_fijo = fijo
        for v in App.ventanas:
            v.panel_fijo = fijo
            for d in v.docs:
                d.set_panel_fijo(fijo)
        previas = config.cargar_preferencias()
        previas["panel_fijo"] = fijo
        config.guardar_preferencias(previas)

    # ---- abrir / guardar ----------------------------------------------------------------------------------
    def _dir_inicial(self):
        d = config.cargar_preferencias().get("ultima_carpeta")
        return d if d and os.path.isdir(d) else str(config.dir_escenarios())

    def _dir_importar(self):
        d = config.cargar_preferencias().get("ultima_carpeta_csv")
        return d if d and os.path.isdir(d) else str(config.dir_escritorio())

    def _recordar_importar(self, ruta):
        previas = config.cargar_preferencias()
        previas["ultima_carpeta_csv"] = str(Path(ruta).parent)
        config.guardar_preferencias(previas)

    def _recordar_carpeta(self, ruta):
        previas = config.cargar_preferencias()
        previas["ultima_carpeta"] = str(Path(ruta).parent)
        config.guardar_preferencias(previas)

    def abrir(self, ruta=None):
        cerrar_emergente()
        if not ruta:
            ruta = da.abrir(parent=self.root, title="Abrir Escenario", initialdir=self._dir_inicial(),
                            filetypes=FILTROS_SIMX)
        if not ruta:
            return
        ruta = os.path.normpath(ruta)
        for v in App.ventanas:
            for d in v.docs:
                if d.esc.ruta and os.path.normcase(d.esc.ruta) == os.path.normcase(ruta):
                    v.seleccionar(d)
                    v.root.lift()
                    return
        try:
            esc = Escenario.desde_archivo(ruta, self.gestor)
        except ErrorEscenario as e:
            error(self.root, "No se Pudo Abrir el Escenario", str(e))
            return
        self._recordar_carpeta(ruta)
        self._recordar_reciente(ruta)
        previo = self.actual if (self.actual and self._es_vacio(self.actual)) else None
        vista = self._abrir_doc(esc)
        if previo is not None:
            self.docs.remove(previo)
            previo.destroy()
            self.refrescar_titulos()
        faltan = [a["nombre"] for a in esc.archivos if a.get("incluido", True) and not a.get("encontrado", True)]
        vista.mostrar_pestana("analisis" if esc.estado == "ejecutado" else "inputs")
        self.mensaje(f"Escenario abierto: {esc.nombre_visible}")
        if faltan:
            aviso(self.root, "Archivos CSV No Encontrados",
                  ["Los siguientes archivos del escenario no se encuentran en este equipo:",
                   "  •  " + "\n  •  ".join(faltan),
                   "Puede revisar la configuración y los resultados guardados. Para recalcular, "
                   "seleccione el archivo en el panel «Archivos del Modelo» y use el botón «Cambiar Input»."])

    def guardar(self, doc=None):
        doc = doc if isinstance(doc, VistaEscenario) else self.actual
        if doc is None:
            return False
        esc = doc.esc
        if not esc.ruta:
            return self.guardar_como(doc)
        return self._guardar_en(doc, esc.ruta)

    def guardar_como(self, doc=None):
        doc = doc if isinstance(doc, VistaEscenario) else self.actual
        if doc is None:
            return False
        esc = doc.esc
        inicial = Path(esc.ruta).parent if esc.ruta else self._dir_inicial()
        ruta = da.guardar(parent=self.root, title="Guardar Escenario Como", initialdir=str(inicial),
                          initialfile=fmt.nombre_archivo_seguro(esc.nombre_visible) + config.EXTENSION,
                          defaultextension=config.EXTENSION, filetypes=FILTROS_SIMX)
        if not ruta:
            return False
        return self._guardar_en(doc, os.path.normpath(ruta))

    def _guardar_en(self, doc, ruta):
        esc = doc.esc
        solo_config = False
        if esc.resultados and not esc.vigente:
            r = confirmar(self.root, "Resultados Desactualizados",
                          ["Los resultados guardados ya no corresponden a la configuración actual.",
                           "Se guardará únicamente la configuración (sin resultados). "
                           "Ejecute el análisis (F5) antes de guardar si desea conservarlos."],
                          ("Guardar sin Resultados", "Cancelar"), cancelar=1)
            if r != 0:
                return False
            solo_config = True
        try:
            destino = esc.guardar(ruta, self.gestor, solo_config)
        except ErrorEscenario as e:
            error(self.root, "No se Pudo Guardar", str(e))
            return False
        self._recordar_carpeta(destino)
        self._recordar_reciente(str(destino))
        for v in App.ventanas:
            if v.vivo():
                v.refrescar_titulos()
        self.mensaje(f"Guardado: {destino}  ({'con resultados' if esc.estado == 'ejecutado' else 'solo configuración'})")
        return True

    # ---- importar y cargar --------------------------------------------------------------------------------
    def importar(self):
        doc = self.actual
        if doc is None:
            return
        cerrar_emergente()
        rutas = da.abrir_varios(parent=self.root, title="Importar Resultados Simulación CSV",
                                initialdir=self._dir_importar(),
                                filetypes=[("Resultados de Simulación (o_*.csv)", "o_*.csv")])
        if not rutas:
            return
        self._recordar_importar(rutas[0])
        validas, ignoradas = [], []
        for r in rutas:
            (validas if csvio.es_archivo_modelo(r) else ignoradas).append(r)
        if ignoradas:
            aviso(self.root, "Archivos Omitidos",
                  ["Solo se importan archivos que inicien con «o_» y terminen en .csv "
                   "(excepto o_poliRetenido, o_poliRetSolapamiento y o_sinOrigen).",
                   "Se omitieron:\n  •  " + "\n  •  ".join(os.path.basename(i) for i in ignoradas)])
        if not validas:
            return

        def trabajo(prog, cancelado):
            metas, errores = [], []
            for i, r in enumerate(validas):
                if cancelado():
                    raise csvio.Cancelado()
                prog(i / len(validas), f"Analizando {os.path.basename(r)}…")
                try:
                    metas.append(csvio.inspeccionar(r))
                except csvio.ErrorLectura as e:
                    errores.append(f"{os.path.basename(r)}: {e}")
                except Exception as e:  # noqa
                    errores.append(f"{os.path.basename(r)}: {e}")
            return metas, errores

        res, exc = con_progreso(self.root, "Importando Archivos", trabajo)
        if exc is not None:
            if not isinstance(exc, csvio.Cancelado):
                error(self.root, "No se Pudo Importar", str(exc))
            return
        metas, errores = res
        if errores:
            aviso(self.root, "Archivos con Problemas", errores)
        if not metas:
            return
        doc.esc.incorporar_archivos(metas)
        self.mensaje(f"{len(metas)} archivo(s) importado(s)")
        self.seleccionar_inputs(doc)

    def seleccionar_inputs(self, doc):
        from panel_archivos import DialogoInputs
        esc = doc.esc
        if not esc.archivos:
            aviso(self.root, "Sin Archivos", "Primero importe archivos desde Modelo ▸ Importar "
                  "Resultados Simulación CSV.")
            return
        esc.resolver_archivos(Path(esc.ruta).parent if esc.ruta else config.dir_inputs())

        def aplicar(sel):
            if not doc.winfo_exists():
                return
            esc.aplicar_seleccion(sel)
            if any(sel.values()):
                self.cargar_datos(doc)
            else:
                doc.refrescar_todo()
        DialogoInputs(self.root, esc, aplicar, pagina=doc).mostrar()

    def cargar_datos(self, doc):
        """Lee los archivos marcados (nombre, réplicas, flotas). Devuelve True si terminó bien."""
        esc = doc.esc

        def trabajo(prog, cancelado):
            return esc.preparar_carga(lambda f, n: prog(f, f"Leyendo {n}…"), cancelado)

        pq, exc = con_progreso(self.root, "Cargando Datos", trabajo)
        if exc is not None:
            if isinstance(exc, csvio.Cancelado):
                self.mensaje("Carga cancelada")
            else:
                error(self.root, "No se Pudo Cargar los Datos", str(exc))
            return False
        esc.aplicar_carga(pq)
        doc.df_registro, doc._registro_fallido = None, None
        doc.refrescar_todo()
        if esc.advertencias_carga:
            aviso(self.root, "Avisos de la Carga", esc.advertencias_carga)
        doc.mostrar_pestana("inputs")
        self.mensaje(esc.memoria_aplicada or ("Datos cargados: " + ", ".join(
            f"{modelo.CLASES[c]['plural']} ({esc.clases[c]['n_equipos']})" for c in esc.clases)),
            15000 if esc.memoria_aplicada else 7000)
        return True

    @staticmethod
    def _necesita_carga(esc):
        for a in esc.archivos:
            if not (a.get("incluido", True) and a.get("encontrado", True)):
                continue
            clase = modelo.clase_de_archivo(a["nombre"])
            if clase and clase not in esc.datos:
                return True
            if a["nombre"].lower() == "o_registro_cargas.csv" and esc.registro is None \
                    and os.path.isfile(a.get("ruta") or ""):
                return True
        return False

    def recargar_si_corresponde(self, doc, recargar=True):
        esc = doc.esc
        if recargar and self._necesita_carga(esc):
            self.cargar_datos(doc)
        else:
            doc.refrescar_todo()

    def reubicar(self, doc, nombre):
        ruta = da.abrir(parent=self.root, title=f"Ubicar {nombre}", initialdir=self._dir_importar(),
                        filetypes=[(nombre, nombre)])
        if not ruta:
            return
        if os.path.basename(ruta).lower() != nombre.lower():
            aviso(self.root, "Archivo Distinto",
                  f"Se esperaba un archivo llamado «{nombre}». Seleccione el archivo correcto.")
            return
        try:
            meta = csvio.inspeccionar(ruta)
        except csvio.ErrorLectura as e:
            error(self.root, "No se Pudo Leer el Archivo", str(e))
            return
        doc.esc.reubicar_archivo(nombre, meta)
        self.recargar_si_corresponde(doc, True)

    # ---- configuración de tiempos -----------------------------------------------------------------------------
    def configurar_tiempos(self, doc, clase):
        from vista_inputs import DialogoTiempos
        esc = doc.esc
        cfg = esc.clases.get(clase)
        if not cfg:
            return

        def aplicar(nuevo):
            if not doc.winfo_exists() or clase not in esc.clases or nuevo == esc.clases[clase]["mapa_estados"]:
                return
            esc.set_mapa_estados(clase, nuevo)
            self.reejecutar_si_corresponde(doc)
        DialogoTiempos(self.root, clase, cfg["columnas"], cfg["mapa_estados"], aplicar,
                       pagina=doc.pag_inputs).mostrar()

    # ---- ejecución -------------------------------------------------------------------------------------------------
    def ejecutar(self, doc=None):
        doc = doc if isinstance(doc, VistaEscenario) else self.actual
        if doc is None:
            return False
        cerrar_emergente()
        esc = doc.esc
        if not esc.archivos:
            aviso(self.root, "Sin Archivos",
                  "Importe los archivos del modelo (Modelo ▸ Importar Resultados Simulación CSV) "
                  "antes de ejecutar el análisis.")
            return False
        if esc.clases and esc.faltan_datos() and not self._necesita_carga(esc):
            faltan = ", ".join(modelo.CLASES[c]["archivo"] for c in esc.faltan_datos())
            aviso(self.root, "No se Puede Recalcular",
                  [f"No se encontraron los archivos necesarios en este equipo: {faltan}.",
                   "Se conservan la configuración y los resultados guardados. Para recalcular, "
                   "seleccione el archivo en el panel «Archivos del Modelo» y use el botón «Cambiar Input»."])
            return False
        if not esc.clases or esc.faltan_datos() or self._necesita_carga(esc):
            if not self.cargar_datos(doc):
                return False
        # Todos los datos requeridos (General, Configuración de Equipos, Origen y Destino) deben estar completos
        pend = esc.detalle_pendientes()
        if pend:
            aviso(self.root, "Datos Requeridos Incompletos",
                  ["Complete los datos marcados con * Requerido antes de ejecutar el análisis:",
                   "  •  " + "\n  •  ".join(pend)])
            doc.mostrar_pestana("inputs")
            doc.pag_inputs.ir_a_pendiente()
            return False
        try:
            avisos = esc.ejecutar()
        except csvio.ErrorLectura as e:
            aviso(self.root, "No se Pudo Ejecutar el Análisis", str(e))
            return False
        except Exception as e:  # noqa
            log.exception("Error al ejecutar")
            error(self.root, "Error en el Cálculo", f"{e}")
            return False
        doc.refrescar_todo()
        doc.mostrar_pestana("analisis")
        self.mensaje("Análisis ejecutado correctamente")
        if avisos:
            aviso(self.root, "Avisos del Análisis", avisos)
        return True

    def cambiar_replica(self, doc, replica):
        esc = doc.esc
        esc.set_replica(replica)
        if esc.resultados and not esc.vigente:
            self.reejecutar_si_corresponde(doc)
        else:
            doc.refrescar_todo()
        self.mensaje(f"Réplica activa: {replica}")

    def reejecutar_si_corresponde(self, doc):
        """Tras cambiar réplica, estados o tipos: recalcula si el escenario ya tenía resultados."""
        esc = doc.esc
        if not esc.resultados:
            doc.refrescar_todo()
            return
        try:
            if esc.faltan_datos():
                if self._necesita_carga(esc):
                    if not self.cargar_datos(doc):
                        return
                else:
                    doc.refrescar_todo()
                    return
            if esc.detalle_pendientes():
                doc.refrescar_todo()
                return
            esc.ejecutar()
            self.mensaje("Resultados actualizados")
        except Exception as e:  # noqa
            doc.refrescar_todo()
            aviso(self.root, "Resultados Desactualizados", str(e))

    # ---- exportación --------------------------------------------------------------------------------------------------
    def _requiere_resultados(self, doc):
        if doc is None or not doc.esc.resultados:
            aviso(self.root, "Sin Resultados",
                  "No hay resultados para exportar. Ejecute primero el análisis (F5).")
            return False
        if not doc.esc.vigente:
            r = confirmar(self.root, "Resultados Desactualizados",
                          "Los resultados no corresponden a la configuración actual. ¿Exportar de todas formas?",
                          ("Exportar", "Cancelar"), cancelar=1)
            return r == 0
        return True

    def _ruta_exportacion(self, doc, sufijo, ext, tipo):
        return da.guardar(parent=self.root, title=f"Exportar {tipo}", initialdir=str(config.dir_outputs()),
                          initialfile=f"{fmt.nombre_archivo_seguro(doc.esc.nombre_visible)} - {sufijo}{ext}",
                          defaultextension=ext, filetypes=[(tipo, f"*{ext}")])

    def _tras_exportar(self, ruta):
        ruta = os.path.normpath(ruta)
        r = confirmar(self.root, "Reporte Exportado", ruta, ("Abrir Archivo", "Cerrar"), cancelar=1)
        if r == 0:
            try:
                os.startfile(ruta)
            except OSError:
                pass

    def _exportar(self, ruta, funcion, titulo):
        doc = self.actual

        def trabajo(prog, cancelado):
            return funcion(ruta, doc.esc, prog)
        _r, exc = con_progreso(self.root, titulo, trabajo, cancelable=False)
        if exc is None:
            self._tras_exportar(ruta)
        elif isinstance(exc, PermissionError):
            error(self.root, "No se Pudo Exportar",
                  "El archivo está abierto en otro programa o no tiene permiso de escritura. "
                  "Ciérrelo e inténtelo nuevamente.")
        else:
            log.error("Exportar: %s", "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)))
            error(self.root, "No se Pudo Exportar", f"{exc}")

    def exportar_excel(self):
        doc = self.actual
        if not self._requiere_resultados(doc):
            return
        ruta = self._ruta_exportacion(doc, "Reporte", ".xlsx", "Libro de Excel")
        if not ruta:
            return
        import export_excel
        self._exportar(ruta, export_excel.exportar_reporte, "Exportando Reporte Excel")

    def exportar_pptx(self):
        doc = self.actual
        if not self._requiere_resultados(doc):
            return
        ruta = self._ruta_exportacion(doc, "Reporte", ".pptx", "Presentación de PowerPoint")
        if not ruta:
            return
        import export_pptx
        self._exportar(ruta, export_pptx.exportar_reporte, "Exportando Reporte PowerPoint")

    # ---- Vector Plan -------------------------------------------------------------------------------------------------
    def importar_plan(self, doc=None):
        import plan
        from datetime import datetime
        from vista_inputs import DialogoNombrePlan
        doc = doc if isinstance(doc, VistaEscenario) else self.actual
        if doc is None:
            return
        cerrar_emergente()
        esc = doc.esc
        ruta = da.abrir(parent=self.root, title="Importar Métricas Plan", initialdir=self._dir_importar(),
                        filetypes=[("Libro de Excel", "*.xlsx *.xlsm"), ("Todos", "*.*")])
        if not ruta:
            return
        try:
            datos = plan.leer_excel(ruta)
        except plan.ErrorPlan as e:
            error(self.root, "No se Pudo Leer el Plan", str(e))
            return
        except Exception as e:  # noqa
            log.exception("Leer plan")
            error(self.root, "No se Pudo Leer el Plan", f"{e}")
            return
        # se conservan los vínculos y variaciones de un plan anterior con los mismos textos
        previos = {f["texto"].strip(): f for f in (esc.plan or {}).get("filas", []) if f["tipo"] == "item"}
        for f in datos["filas"]:
            p = previos.get(f["texto"].strip())
            if p and f["tipo"] == "item":
                f["variacion"], f["vinculo"] = p.get("variacion"), p.get("vinculo")
        plan.vincular(esc, datos["filas"])
        nombre = DialogoNombrePlan(self.root, datos["nombre"]).mostrar()
        if nombre is None:
            return
        esc.set_plan({"nombre": nombre, "archivo": os.path.basename(ruta), "hoja": datos["hoja"],
                      "fecha": fmt.fecha_hora(datetime.now()), "filas": datos["filas"]})
        doc.refrescar_todo()
        doc.mostrar_pestana("inputs")
        doc.pag_inputs.sub.select(doc.pag_inputs.vplan)
        self.mensaje(f"Plan importado: {nombre}. Revise el Indicador Simulador (B) y la Variación de cada parámetro.")

    def exportar_plan(self, doc=None):
        import plan
        doc = doc if isinstance(doc, VistaEscenario) else self.actual
        if doc is None:
            return
        esc = doc.esc
        if not esc.plan:
            aviso(self.root, "Sin Vector Plan", "Importe primero las métricas del plan (Modelo ▸ Importar "
                  "Métricas Plan o Inputs ▸ Vector Plan).")
            return
        if not plan.replicas_resultados(esc) or not self._requiere_resultados(doc):
            if not plan.replicas_resultados(esc):
                aviso(self.root, "Sin Resultados", "Ejecute primero el análisis (F5).")
            return
        ruta = da.guardar(parent=self.root, title="Exportar Resultados Plan vs Simulación",
                          initialdir=str(config.dir_outputs()),
                          initialfile=f"Resultados {fmt.nombre_archivo_seguro(esc.nombre_visible)}.xlsx",
                          defaultextension=".xlsx", filetypes=[("Libro de Excel", "*.xlsx")])
        if not ruta:
            return
        import export_plan
        self._exportar(ruta, lambda r, e, _p: export_plan.exportar(r, e), "Exportando Plan vs Simulación")

    def exportar_tabla_pivot(self, doc, tabla, cfg):
        ruta = self._ruta_exportacion(doc, "Tabla Dinámica", ".xlsx", "Libro de Excel")
        if not ruta:
            return
        import export_excel
        self._exportar(ruta, lambda r, e, _p: export_excel.exportar_pivot(r, e, tabla, cfg), "Exportando Tabla Dinámica")

    # ---- tools -----------------------------------------------------------------------------------------------------------
    def tool_registro_cargas(self):
        if self.actual is not None:
            self.actual.mostrar_pestana("registro")

    def tool_estados_pivot(self):
        if self.actual is not None:
            self.actual.mostrar_pestana("pivot")

    # ---- archivos del modelo (panel lateral) ----------------------------------------------------------------------------
    def abrir_archivo(self, ruta):
        if not ruta or not os.path.isfile(ruta):
            aviso(self.root, "Archivo No Encontrado", f"No se encontró el archivo:\n{ruta}")
            return
        try:
            os.startfile(ruta)
        except OSError as e:
            error(self.root, "No se Pudo Abrir el Archivo", str(e))

    def mostrar_carpeta(self, ruta):
        try:
            if ruta and os.path.isfile(ruta):
                subprocess.Popen(["explorer", "/select,", os.path.normpath(ruta)])
            elif ruta and os.path.isdir(os.path.dirname(ruta)):
                os.startfile(os.path.dirname(ruta))
        except OSError:
            pass

    def eliminar_archivos(self, doc, nombres):
        """Quita archivos del escenario (no los borra del disco)."""
        if not nombres:
            return
        r = confirmar(self.root, "Eliminar del Escenario",
                      ["Se quitarán del escenario los siguientes archivos (no se borran del disco):",
                       "  •  " + "\n  •  ".join(nombres)], ("Eliminar", "Cancelar"), cancelar=1)
        if r != 0:
            return
        for n in nombres:
            doc.esc.quitar_archivo(n)
        self.recargar_si_corresponde(doc, False)
        self.mensaje(f"{len(nombres)} archivo(s) quitado(s) del escenario")

    def cargar_registro(self, doc):
        """Carga o_registro_cargas.csv para el pivote (una vez por escenario). Devuelve True si quedó cargado."""
        import registro
        esc = doc.esc
        a = esc.archivo("o_registro_cargas.csv")
        clave = (a or {}).get("ruta"), (a or {}).get("tamano")
        if doc._registro_fallido == clave:
            return False
        doc._registro_fallido = clave
        if not a or not a.get("incluido", True):
            return False
        if not os.path.isfile(a.get("ruta") or ""):
            esc.resolver_archivos(Path(esc.ruta).parent if esc.ruta else config.dir_inputs())
        if not a.get("encontrado", True) or not os.path.isfile(a.get("ruta") or ""):
            return False
        gb = (a.get("tamano") or 0) / 1024 ** 3
        if gb >= 2.0:
            r = confirmar(self.root, "Archivo Muy Grande",
                          f"o_registro_cargas.csv pesa {gb:,.1f} GB. Cargarlo puede tardar varios minutos "
                          "y requerir bastante memoria RAM.",
                          ("Continuar", "Cancelar"), cancelar=1)
            if r != 0:
                return False
        try:
            meta = csvio.inspeccionar(a["ruta"], con_filas=a.get("filas") is None)
            if a.get("filas") is not None:
                meta["filas"] = a["filas"]
        except csvio.ErrorLectura as e:
            error(self.root, "No se Pudo Leer el Archivo", str(e))
            return False

        def trabajo(prog, cancelado):
            df = csvio.cargar_tabla_grande(
                a["ruta"], meta, progreso=lambda f, n: prog(f * 0.9, f"{n:,} filas leídas…"), cancelar=cancelado)
            prog(0.95, "Preparando campos (Réplica, Fecha, Mes, Fase, ID Pala)…")
            return registro.preparar_df_registro(df, esc.anio)

        df, exc = con_progreso(self.root, "Cargando Registro de Cargas", trabajo)
        if exc is not None:
            if isinstance(exc, csvio.Cancelado):
                self.mensaje("Carga cancelada")
            elif isinstance(exc, MemoryError):
                error(self.root, "Memoria Insuficiente",
                      "No hay memoria suficiente para cargar este archivo. Cierre otros programas "
                      "e inténtelo nuevamente.")
            else:
                error(self.root, "No se Pudo Cargar el Archivo", str(exc))
            return False
        doc.df_registro = df
        doc._registro_fallido = None
        self.mensaje(f"Registro de Cargas listo: {len(df):,} filas")
        return True

    # ---- acerca de -----------------------------------------------------------------------------------------------------------
    def acerca(self):
        d = VentanaModal(self.root, f"Acerca de {config.NOMBRE_CORTO}")
        p = T.p
        marco = tk.Frame(d, background=p["panel"])
        marco.pack(padx=T.px(26), pady=T.px(22))
        fila = tk.Frame(marco, background=p["panel"])
        fila.pack()
        try:
            png = config.dir_recursos() / "icono.png"
            img = tk.PhotoImage(file=str(png), master=d)
            factor = max(1, img.width() // T.px(64))
            d._logo = img.subsample(factor, factor)
            tk.Label(fila, image=d._logo, background=p["panel"]).pack(side="left", padx=(0, T.px(20)))
        except Exception:
            pass
        textos = tk.Frame(fila, background=p["panel"])
        textos.pack(side="left")
        tk.Label(textos, text=config.NOMBRE_PROGRAMA, background=p["panel"], foreground=p["texto"],
                 font=T.f["subtitulo"], anchor="w").pack(anchor="w")
        tk.Label(textos, text=f"Version: {config.VERSION}", background=p["panel"], foreground=p["texto"],
                 font=T.f["base"], anchor="w").pack(anchor="w", pady=(T.px(6), 0))
        tk.Label(textos, text=f"Date Release: {config.FECHA_LANZAMIENTO}", background=p["panel"],
                 foreground=p["texto"], font=T.f["base"], anchor="w").pack(anchor="w")
        ttk.Button(marco, text="Aceptar", style="Accent.TButton", command=d.destroy).pack(
            anchor="e", pady=(T.px(18), 0))
        d.bind("<Return>", lambda e: d.destroy())
        d.mostrar()

    def ejecutar_bucle(self):
        self.root.mainloop()
