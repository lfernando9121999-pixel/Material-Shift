"""Modelo de datos de un escenario (documento de trabajo) de SimA."""
import os
from collections import Counter
from datetime import datetime
from pathlib import Path


import config
import csvio
import fmt
import modelo
import registro
from archivo_manager import GestorEscenarios
from perezoso import pd


def _norm_replica(valor):
    v = str(valor).strip()
    try:
        f = float(v.replace(",", "."))
        if f == int(f):
            return str(int(f))
    except ValueError:
        pass
    return v


def _clave_orden(v):
    try:
        return (0, float(v), v)
    except ValueError:
        return (1, 0.0, v)


def leer_escenario_y_replicas(ruta, meta, progreso=None, cancelar=None):
    """Lee solo las dos primeras columnas (ESCENARIO y NREP) de un CSV, por bloques."""
    opciones = csvio._opciones(meta)
    crudas = list(pd.read_csv(ruta, nrows=0, **opciones).columns)
    claves = [csvio.norm(c) for c in crudas]
    i_esc = claves.index("escenario") if "escenario" in claves else 0
    i_rep = claves.index("nrep") if "nrep" in claves else (1 if len(crudas) > 1 else 0)
    usar = list(dict.fromkeys([crudas[i_esc], crudas[i_rep]]))
    nombres, replicas = Counter(), set()
    total = meta.get("filas") or 0
    leidas = 0
    for chunk in pd.read_csv(ruta, usecols=usar, dtype=str, chunksize=500_000,
                             low_memory=False, **opciones):
        if cancelar and cancelar():
            raise csvio.Cancelado()
        vals = chunk[crudas[i_rep]].dropna().str.strip()
        validas = vals.str.lower() != "nrep"
        nombres.update(chunk.loc[validas.reindex(chunk.index, fill_value=False), crudas[i_esc]]
                       .dropna().str.strip().value_counts().to_dict())
        replicas.update(_norm_replica(v) for v in vals[validas].unique())
        leidas += len(chunk)
        if progreso and total:
            progreso(min(0.99, leidas / total))
    return nombres, replicas


class PaqueteCarga:
    """Resultado de leer los archivos (se construye en un hilo, se aplica en el principal)."""

    def __init__(self):
        self.datos = {}          # clase -> DatosEstado
        self.inventarios = {}    # clase -> dict
        self.nombres = Counter()
        self.replicas = set()
        self.avisos = []
        self.registro = None     # agregados de o_registro_cargas.csv (registro.agregar)


class Escenario:
    def __init__(self):
        self.nombre = ""
        self.nombre_manual = False
        self.descripcion = ""
        self.replica = "Todas"
        self.replicas = []
        self.archivos = []           # lista de dicts (metadatos + incluido/encontrado)
        self.clases = {}             # clase -> {columnas, flotas, n_equipos, mapa_estados, tipos}
        self.resultados = None       # {"fecha", "replica", "clases": {...}}
        self.vigente = False         # resultados coherentes con la configuración
        self.ruta = None
        self.sucio = False
        self.datos = {}              # clase -> DatosEstado (solo en memoria)
        self.pivot = None            # Registro de Cargas: {"config": ..., "resultado": ...}
        self.pivots = {}             # Análisis de Estados (Pivot): clase -> {"config": ...}
        self.dias = 365              # días del período (Análisis por Tiempos, h/día-eq)
        self.anio = None             # año de la simulación (fechas del registro de cargas)
        self.perfil_cfg = {"modo": "mes", "filtros": {}}   # vista del Perfil de Alimentación
        # Lo que se ve en pantalla (se usa también al exportar los reportes)
        self.vistas = {"unidad_tiempos": "dia", "modo_tiempos": "tabla", "productividad_id": False,
                       "tiempos_flotas": {}, "tiempos_ids": {}, "vincular_filtros": True, "filtros": {},
                       "registro_modo": "n"}
        self.memoria_aplicada = ""   # resumen de la configuración copiada de la última corrida
        self.origenes = {}           # origen -> {"tipo", "condicion", "carga"}
        self.destinos = {}           # destino -> {"tipo", "carga", "tipo_csv"}
        self.plan = None             # Vector Plan importado: {"nombre", "archivo", "filas": [...]}
        self.registro = None         # agregados del registro de cargas (solo en memoria)
        self.advertencias_carga = []
        self._oyentes = []

    # --- observadores -------------------------------------------------
    def conectar(self, fn):
        self._oyentes.append(fn)

    def desconectar(self, fn):
        self._oyentes = [f for f in self._oyentes if f != fn]

    def notificar(self, que="todo"):
        for fn in list(self._oyentes):
            try:
                fn(que)
            except Exception:
                pass

    def marcar_sucio(self):
        self.sucio = True

    @property
    def nombre_visible(self):
        return self.nombre.strip() or "Escenario Sin Título"

    @property
    def estado(self):
        return "ejecutado" if (self.resultados and self.vigente) else "no_ejecutado"

    # --- archivos --------------------------------------------------------
    def archivo(self, nombre):
        for a in self.archivos:
            if a["nombre"].lower() == nombre.lower():
                return a
        return None

    def clase_habilitada(self, clase):
        a = self.archivo(modelo.CLASES[clase]["archivo"])
        return bool(a and a.get("incluido", True))

    def clase_disponible(self, clase):
        a = self.archivo(modelo.CLASES[clase]["archivo"])
        return bool(a and a.get("incluido", True) and a.get("encontrado", True))

    def incorporar_archivos(self, metas):
        for m in metas:
            m = dict(m)
            m["incluido"] = True
            m["encontrado"] = True
            previo = self.archivo(m["nombre"])
            if previo:
                self.archivos[self.archivos.index(previo)] = m
            else:
                self.archivos.append(m)
            clase = modelo.clase_de_archivo(m["nombre"])
            if clase:                       # el archivo cambió: los datos en memoria ya no sirven
                self.datos.pop(clase, None)
        self.archivos.sort(key=lambda a: a["nombre"].lower())
        self.invalidar()

    def quitar_archivo(self, nombre):
        a = self.archivo(nombre)
        if a:
            self.archivos.remove(a)
            clase = modelo.clase_de_archivo(nombre)
            if clase:
                self.clases.pop(clase, None)
                self.datos.pop(clase, None)
            self.invalidar()

    def reubicar_archivo(self, nombre, meta):
        a = self.archivo(nombre)
        if a is not None:
            incluido = a.get("incluido", True)
            self.archivos[self.archivos.index(a)] = {**meta, "incluido": incluido, "encontrado": True}
            self.invalidar()

    def aplicar_seleccion(self, seleccion):
        """seleccion: {nombre: bool}. Devuelve True si hubo cambios."""
        cambio = False
        for a in self.archivos:
            nuevo = bool(seleccion.get(a["nombre"], a.get("incluido", True)))
            if nuevo != a.get("incluido", True):
                a["incluido"] = nuevo
                cambio = True
        if cambio:
            for clase in list(self.clases):
                if not self.clase_habilitada(clase):
                    self.datos.pop(clase, None)
            self.invalidar()
        return cambio

    def invalidar(self):
        self.vigente = False
        self.marcar_sucio()
        self.notificar("archivos")

    # --- carga de datos (se ejecuta en hilo) ---------------------------------
    def preparar_carga(self, progreso=None, cancelar=None):
        """Lee los archivos marcados. No toca la interfaz."""
        pq = PaqueteCarga()
        activos = [a for a in self.archivos if a.get("incluido", True)]
        faltantes = [a["nombre"] for a in activos if not os.path.isfile(a["ruta"])]
        if faltantes:
            pq.avisos.append("No se encontraron los siguientes archivos (se omiten): "
                             + ", ".join(faltantes))
        activos = [a for a in activos if os.path.isfile(a["ruta"])]
        n = max(1, len(activos))
        for i, a in enumerate(activos):
            if cancelar and cancelar():
                raise csvio.Cancelado()

            def sub(f, i=i):
                if progreso:
                    progreso((i + f) / n, a["nombre"])

            # Los archivos grandes no se vuelven a recorrer si no cambiaron (tamaño y fecha)
            try:
                clave = (os.path.getsize(a["ruta"]), os.path.getmtime(a["ruta"]))
            except OSError:
                clave = None
            es_registro = a["nombre"].lower() == registro.ARCHIVO
            cache = a.get("_cache")
            if cache and clave and cache["clave"] == clave:
                meta, nombres, reps = cache["meta"], cache["nombres"], cache["reps"]
                if es_registro:
                    pq.registro = cache.get("agregados")
            else:
                try:
                    meta = csvio.inspeccionar(a["ruta"])
                except csvio.ErrorLectura as e:
                    pq.avisos.append(f"{a['nombre']}: {e}")
                    continue
                nombres, reps, agregados = Counter(), set(), None
                try:
                    if es_registro:
                        # una sola lectura: escenario, réplicas y agregados de cargas
                        nombres, reps, agregados = registro.agregar(a["ruta"], meta, sub, cancelar)
                        pq.registro = agregados
                    else:
                        nombres, reps = leer_escenario_y_replicas(a["ruta"], meta, sub, cancelar)
                    if clave:
                        a["_cache"] = {"clave": clave, "meta": meta, "nombres": nombres, "reps": reps,
                                       "agregados": agregados}
                except csvio.Cancelado:
                    raise
                except Exception as e:
                    pq.avisos.append(f"{a['nombre']}: no se pudo leer el archivo ({e})")
            a.update({k: meta[k] for k in
                      ("ruta", "tamano", "codificacion", "delimitador", "decimal",
                       "columnas", "filas")})
            a["encontrado"] = True
            pq.nombres.update(nombres)
            pq.replicas.update(reps)
            clase = modelo.clase_de_archivo(a["nombre"])
            if clase:
                try:
                    d = modelo.leer_estado(a["ruta"], meta)
                    pq.datos[clase] = d
                    pq.inventarios[clase] = modelo.inventario(d)
                except (csvio.ErrorLectura, Exception) as e:
                    pq.avisos.append(f"{a['nombre']}: {e}")
            sub(1.0)
        return pq

    def aplicar_carga(self, pq):
        """Aplica el paquete a la configuración (hilo principal)."""
        prefs = config.cargar_preferencias()
        nuevo = not self.origenes and not self.clases and not self.resultados
        self.datos = dict(pq.datos)
        self.advertencias_carga = list(pq.avisos)
        if pq.registro is not None:
            self.registro = pq.registro
            self.origenes, self.destinos = registro.configurar_od(pq.registro, self.origenes, self.destinos)
        elif not self.registro_habilitado():
            self.registro = None
        if not self.anio:
            self.set_anio(self._detectar_anio(pq.nombres), notificar=False)

        if pq.nombres and not self.nombre_manual:
            self.nombre = pq.nombres.most_common(1)[0][0]
        elif pq.nombres and not self.nombre.strip():
            self.nombre = pq.nombres.most_common(1)[0][0]
        if len({n for n in pq.nombres}) > 1:
            self.advertencias_carga.append(
                "Los archivos contienen distintos nombres de escenario ("
                + ", ".join(f"{n}: {c:,} filas" for n, c in pq.nombres.most_common(4))
                + "). Se utilizó el de mayor cantidad de datos.")

        if pq.replicas:                       # si no se pudo leer ningún archivo se conserva lo guardado
            self.replicas = sorted(pq.replicas, key=_clave_orden)
        if len(self.replicas) > 1 and "Todas" not in self.replicas:
            opciones = self.replicas + ["Todas"]
        else:
            opciones = list(self.replicas)
        if self.replica not in opciones:
            self.replica = "Todas" if len(self.replicas) > 1 else (self.replicas[0] if self.replicas else "Todas")

        for clase in modelo.ORDEN_CLASES:
            inv = pq.inventarios.get(clase)
            if not inv:
                a = self.archivo(modelo.CLASES[clase]["archivo"])
                # Un archivo ausente (no encontrado) conserva su configuración guardada
                if not (a and a.get("incluido", True) and not os.path.isfile(a.get("ruta") or "")):
                    self.clases.pop(clase, None)
                continue
            previo = self.clases.get(clase, {})
            prefs_estados = (prefs.get("mapa_estados") or {}).get(clase) or {}
            prefs_tipos = (prefs.get("tipos") or {}).get(clase) or {}
            mapa = {}
            for col in inv["columnas"]:
                v = (previo.get("mapa_estados") or {}).get(col)
                if v not in modelo.CLAVES:
                    v = modelo.estado_por_defecto(clase, col, prefs_estados)
                mapa[col] = v
            tipos = {}
            for flota in inv["flotas"]:
                t = modelo.normalizar_tipo(clase, (previo.get("tipos") or {}).get(flota))
                if t is None:
                    t = modelo.normalizar_tipo(clase, prefs_tipos.get(modelo._clave_flota(flota)))
                if t is None:
                    t = modelo.tipo_por_defecto(clase, flota)
                tipos[flota] = t
            self.clases[clase] = {"columnas": inv["columnas"], "flotas": inv["flotas"],
                                  "n_equipos": inv["n_equipos"],
                                  "mapa_estados": mapa, "tipos": tipos,
                                  "orden": modelo.orden_normalizado(
                                      clase, previo.get("orden") or (prefs.get("orden") or {}).get(clase),
                                      list(inv["flotas"]))}
            if clase == "perforadoras":
                previa = previo.get("energia") or {}
                self.clases[clase]["energia"] = {
                    f: previa.get(f) if previa.get(f) in modelo.ENERGIAS else modelo.energia_por_defecto(f)
                    for f in inv["flotas"]}
        if nuevo:
            self._aplicar_memoria(prefs.get("ultima_corrida"))
        self.revincular_plan()
        self.vigente = False
        self.marcar_sucio()
        self.notificar("inventario")

    # --- memoria de la última corrida (los inputs de un caso nuevo se parecen al anterior) -------
    @staticmethod
    def _sin_prefijo(nombre):
        """Polígono sin el prefijo AAMM del año (2701_F11_… → F11_…) para reconocerlo entre años."""
        import re
        return re.sub(r"^\d{4}[_\-]", "", str(nombre))

    def _aplicar_memoria(self, mem):
        if not isinstance(mem, dict):
            return
        partes = []
        mismo_anio = bool(mem.get("anio") and self.anio and int(mem["anio"]) == int(self.anio))
        m_o = mem.get("origenes") or {}
        m_o_sp = {self._sin_prefijo(k): v for k, v in m_o.items()}
        n = 0
        for o, cfg in self.origenes.items():
            v = m_o.get(o) or m_o_sp.get(self._sin_prefijo(o))
            if not v:
                continue
            if v.get("tipo") in registro.TIPOS_ORIGEN:
                cfg["tipo"] = v["tipo"]
            if v.get("condicion") in registro.CONDICIONES:
                cfg["condicion"] = v["condicion"]
            n += 1
        if n:
            partes.append(f"{n:,} orígenes")
        m_d = mem.get("destinos") or {}
        n = 0
        for d, cfg in self.destinos.items():
            if m_d.get(d) in registro.TIPOS_DESTINO:
                cfg["tipo"] = m_d[d]
                n += 1
        if n:
            partes.append(f"{n:,} destinos")
        perf = self.clases.get("perforadoras")
        m_e = mem.get("energia") or {}
        if perf is not None:
            n = 0
            for f in perf.get("energia", {}):
                if m_e.get(f) in modelo.ENERGIAS:
                    perf["energia"][f] = m_e[f]
                    n += 1
            if n:
                partes.append("fuente de energía")
        if mismo_anio and mem.get("plan") and not self.plan:
            import copy
            self.plan = copy.deepcopy(mem["plan"])
            partes.append(f"plan «{self.plan.get('nombre', 'Plan')}»")
        if partes:
            origen = f"año {mem.get('anio')}" if mem.get("anio") else "última corrida"
            self.memoria_aplicada = (f"Se copió la configuración de la última corrida ({origen}"
                                     + ("" if mismo_anio else ", solo los elementos repetidos") + "): "
                                     + ", ".join(partes) + ".")

    def recordar_corrida(self):
        """Guarda los inputs de esta corrida para sugerirlos en el próximo caso."""
        prefs = config.cargar_preferencias()
        prefs["ultima_corrida"] = {
            "anio": self.anio,
            "origenes": {o: {"tipo": c.get("tipo"), "condicion": c.get("condicion")} for o, c in self.origenes.items()},
            "destinos": {d: c.get("tipo") for d, c in self.destinos.items()},
            "energia": dict((self.clases.get("perforadoras") or {}).get("energia") or {}),
            "plan": self.plan,
        }
        config.guardar_preferencias(prefs)

    def _ordenar_resultados(self):
        """Tablas por flota e ID en el orden de reporte (tipo y fuente de energía)."""
        res = self.resultados or {}
        for r in (res.get("por_replica") or {}).values():
            for clase, rc in (r.get("clases") or {}).items():
                modelo.ordenar_resultado(rc, clase, self.clases.get(clase))
            for clase, t in (r.get("tiempos") or {}).items():
                modelo.ordenar_tiempos(t, clase, self.clases.get(clase))

    def set_fases_relleno(self, marcar, desmarcar):
        """Condición Relleno para todos los polígonos de las fases marcadas; Insitu para las desmarcadas."""
        cambio = False
        for o, cfg in self.origenes.items():
            fase = cfg.get("fase") or registro.fase_de(o)
            nueva = "Relleno" if fase in marcar else ("Insitu" if fase in desmarcar else None)
            if nueva and cfg.get("condicion") != nueva:
                cfg["condicion"] = nueva
                cambio = True
        if cambio:
            self.marcar_sucio()
            self.notificar("resultados")
        return cambio

    def fases_en_relleno(self):
        """Fases cuyos polígonos están todos en condición Relleno."""
        por = {}
        for o, cfg in self.origenes.items():
            por.setdefault(cfg.get("fase") or registro.fase_de(o), []).append(cfg.get("condicion") == "Relleno")
        return sorted(f for f, v in por.items() if v and all(v))

    # --- edición de parámetros -----------------------------------------------
    def set_mapa_estados(self, clase, mapa):
        self.clases[clase]["mapa_estados"] = dict(mapa)
        self._recordar("mapa_estados", clase, {csvio.norm(k): v for k, v in mapa.items() if v})
        self.invalidar()

    def set_tipos(self, clase, tipos):
        self.clases[clase]["tipos"] = dict(tipos)
        self._recordar("tipos", clase,
                       {modelo._clave_flota(k): v for k, v in tipos.items() if v})
        self.invalidar()

    @property
    def opciones_replica(self):
        reps = list(self.replicas)
        return reps + ["Todas"] if len(reps) > 1 else reps

    def set_replica(self, replica):
        """Cambia la réplica activa. Si ya fue calculada se muestra al instante (también sin CSV)."""
        if replica == self.replica:
            return
        self.replica = replica
        por = (self.resultados or {}).get("por_replica") or {}
        if self.vigente and replica in por:
            self.resultados["replica"] = replica
            self.resultados["clases"] = por[replica]["clases"]
            self.resultados["tiempos"] = por[replica].get("tiempos", {})
            self.resultados["cargas"] = por[replica].get("cargas")
            self.marcar_sucio()
            self.notificar("resultados")
        else:
            self.invalidar()

    def _detectar_anio(self, nombres=None):
        """Año sugerido: prefijo AAMM de los polígonos, un año en el nombre del escenario o el año actual."""
        import re
        a = registro.anio_de_origenes(self.origenes) if self.origenes else None
        if a is None:
            for texto in [self.nombre] + list(nombres or []):
                m = re.search(r"(20\d{2})", str(texto))
                if m:
                    a = int(m.group(1))
                    break
        return a or datetime.now().year

    def set_anio(self, anio, notificar=True):
        """Año de la simulación; los días del periodo se ajustan a 365 o 366 (año bisiesto)."""
        import calendar
        anio = int(anio)
        if anio == self.anio:
            return
        self.anio = anio
        self.dias = 366 if calendar.isleap(anio) else 365
        self.marcar_sucio()
        if notificar:
            self.notificar("resultados")

    def set_energia(self, flota, energia):
        cfg = self.clases.get("perforadoras")
        if cfg is not None and energia in modelo.ENERGIAS:
            cfg.setdefault("energia", {})[flota] = energia
            self._ordenar_resultados()
            self.revincular_plan()
            self.marcar_sucio()
            self.notificar("resultados")

    def revincular_plan(self):
        """Completa los vínculos del Vector Plan que estén vacíos (p. ej. tras definir la fuente de energía)."""
        if self.plan and self.plan.get("filas"):
            import plan as _plan
            _plan.vincular(self, self.plan["filas"])

    def set_dias(self, dias):
        dias = float(dias)
        if dias > 0 and dias != self.dias:
            self.dias = dias
            self.marcar_sucio()
            self.notificar("resultados")

    # --- orígenes, destinos y vector plan (no requieren recalcular) ---------------------------
    def registro_habilitado(self):
        a = self.archivo(registro.ARCHIVO)
        return bool(a and a.get("incluido", True))

    def set_origenes(self, nombres, tipo=None, condicion=None):
        cambio = False
        for o in nombres:
            cfg = self.origenes.get(o)
            if cfg is None:
                continue
            if tipo in registro.TIPOS_ORIGEN and cfg.get("tipo") != tipo:
                cfg["tipo"] = tipo
                cambio = True
            if condicion in registro.CONDICIONES and cfg.get("condicion") != condicion:
                cfg["condicion"] = condicion
                cambio = True
        if cambio:
            self.marcar_sucio()
            self.notificar("resultados")
        return cambio

    def set_destinos(self, tipos):
        cambio = False
        for d, t in tipos.items():
            cfg = self.destinos.get(d)
            if cfg is not None and t in registro.TIPOS_DESTINO and cfg.get("tipo") != t:
                cfg["tipo"] = t
                cambio = True
        if cambio:
            self.marcar_sucio()
            self.notificar("resultados")
        return cambio

    def set_plan(self, plan):
        self.plan = plan
        self.marcar_sucio()
        self.notificar("resultados")

    def pendientes(self):
        """Datos requeridos incompletos por subpestaña de Inputs: {'general'|'equipos'|'od': [mensajes]}.
        El Vector Plan es opcional; la Descripción también."""
        p = {}
        g = []
        if not self.archivos:
            g.append("General: importe los archivos de resultados (Inputs para Análisis)")
        elif not any(a.get("incluido", True) for a in self.archivos):
            g.append("General: seleccione al menos un archivo en Inputs para Análisis")
        if not self.nombre.strip():
            g.append("General: Nombre del Escenario")
        if not self.anio:
            g.append("General: Año")
        if g:
            p["general"] = g
        e = []
        for clase in modelo.ORDEN_CLASES:
            cfg = self.clases.get(clase)
            if not cfg or not self.clase_habilitada(clase):
                continue
            plural = modelo.CLASES[clase]["plural"]
            sin = [c for c, v in cfg["mapa_estados"].items() if not v]
            if sin:
                e.append(f"Configuración de Equipos: {plural} – {len(sin)} columna(s) de tiempo sin estado")
            sin_t = [f for f, v in cfg["tipos"].items() if not v]
            if sin_t:
                e.append(f"Configuración de Equipos: {plural} – tipo sin asignar ({', '.join(sin_t)})")
            if clase == "perforadoras":
                cat = cfg.get("energia") or {}
                sin_c = [f for f in cfg["flotas"] if cat.get(f) not in modelo.ENERGIAS]
                if sin_c:
                    e.append(f"Configuración de Equipos: {plural} – categoría sin asignar ({', '.join(sin_c)})")
        if e:
            p["equipos"] = e
        o = []
        if self.registro_habilitado() and (self.origenes or self.destinos):
            n_o = sum(1 for c in self.origenes.values() if c.get("tipo") not in registro.TIPOS_ORIGEN
                      or c.get("condicion") not in registro.CONDICIONES)
            if n_o:
                o.append(f"Origen y Destino: {n_o:,} origen(es) sin Tipo de Origen o Condición")
            n_d = sum(1 for c in self.destinos.values() if c.get("tipo") not in registro.TIPOS_DESTINO)
            if n_d:
                o.append(f"Origen y Destino: {n_d:,} destino(s) sin Tipo de Destino")
        if o:
            p["od"] = o
        return p

    def detalle_pendientes(self):
        return [m for v in self.pendientes().values() for m in v]

    def pendientes_inputs(self):
        return set(self.pendientes())

    # --- orden de reporte (Configuración de Equipos) -----------------------------------------------
    def set_orden(self, clase, orden):
        cfg = self.clases.get(clase)
        if cfg is None:
            return
        cfg["orden"] = modelo.orden_normalizado(clase, orden, list(cfg.get("flotas") or {}))
        self._recordar_orden(clase, cfg["orden"])
        self._ordenar_resultados()
        self.marcar_sucio()
        self.notificar("resultados")

    @staticmethod
    def _recordar_orden(clase, orden):
        prefs = config.cargar_preferencias()
        prefs.setdefault("orden", {})[clase] = orden
        config.guardar_preferencias(prefs)

    def _recordar(self, seccion, clase, valores):
        prefs = config.cargar_preferencias()
        prefs.setdefault(seccion, {}).setdefault(clase, {}).update(valores)
        config.guardar_preferencias(prefs)

    # --- ejecución -----------------------------------------------------------------
    def clases_a_calcular(self):
        return [c for c in modelo.ORDEN_CLASES if c in self.clases and self.clase_habilitada(c)]

    def faltan_datos(self):
        return [c for c in self.clases_a_calcular() if c not in self.datos]

    def ejecutar(self):
        """Calcula Análisis de Estados. Devuelve lista de avisos."""
        avisos = []
        clases = self.clases_a_calcular()
        if not clases:
            raise csvio.ErrorLectura(
                "No hay archivos de estados habilitados. Importe o marque "
                "o_estado_perforadoras, o_estado_cargadoras u o_estado_camiones.")
        faltan = self.faltan_datos()
        if faltan:
            nombres = ", ".join(modelo.CLASES[c]["archivo"] for c in faltan)
            raise csvio.ErrorLectura(f"Faltan datos para calcular: {nombres}.")
        # Se calculan todas las réplicas (y su promedio): cambiar de réplica es inmediato y
        # funciona aunque quien abra el .simx no tenga los CSV.
        opciones = self.opciones_replica or ["Todas"]
        if self.replica not in opciones:
            self.replica = opciones[0]
        # Registro de cargas: agregados por réplica (o los guardados si el CSV no está disponible)
        cargas_rep = {}
        if self.registro_habilitado():
            if self.registro:
                cargas_rep = dict(self.registro.get("por_replica", {}))
            else:
                previas = (self.resultados or {}).get("por_replica") or {}
                cargas_rep = {r: v["cargas"] for r, v in previas.items() if r != "Todas" and v.get("cargas")}
        por = {}
        for rep in opciones:
            clases_r, tiempos_r = {}, {}
            for c in clases:
                cfg = self.clases[c]
                clases_r[c] = modelo.calcular(self.datos[c], c, cfg["mapa_estados"], cfg["tipos"], rep)
                tiempos_r[c] = modelo.tiempos(self.datos[c], c, cfg["mapa_estados"], cfg["tipos"], rep)
            por[rep] = {"clases": clases_r, "tiempos": tiempos_r}
            if cargas_rep:
                if rep in cargas_rep:
                    por[rep]["cargas"] = cargas_rep[rep]
                elif rep == "Todas":
                    por[rep]["cargas"] = registro.combinar([cargas_rep[r] for r in sorted(cargas_rep, key=_clave_orden)])
        for c in clases:
            avisos.extend(f"{modelo.CLASES[c]['plural']}: {a}"
                          for a in por[self.replica]["clases"][c]["advertencias"])
        self.resultados = {"fecha": datetime.now().isoformat(timespec="seconds"),
                           "replica": self.replica, "replicas": opciones, "por_replica": por,
                           "clases": por[self.replica]["clases"],
                           "tiempos": por[self.replica]["tiempos"],
                           "cargas": por[self.replica].get("cargas")}
        self._ordenar_resultados()
        self.vigente = True
        self.marcar_sucio()
        try:
            self.recordar_corrida()
        except Exception:
            pass
        self.notificar("resultados")
        return avisos

    # --- serialización ---------------------------------------------------------------
    def a_config(self):
        return {
            "nombre": self.nombre,
            "nombre_manual": self.nombre_manual,
            "descripcion": self.descripcion,
            "replica": self.replica,
            "replicas": self.replicas,
            "archivos": [
                {k: a.get(k) for k in ("nombre", "ruta", "tamano", "incluido", "filas", "columnas",
                                        "codificacion", "delimitador", "decimal")}
                for a in self.archivos],
            "clases": self.clases,
            "pivot": self.pivot,
            "pivots": self.pivots,
            "dias": self.dias,
            "origenes": self.origenes,
            "destinos": self.destinos,
            "plan": self.plan,
            "anio": self.anio,
            "perfil_cfg": self.perfil_cfg,
            "vistas": self.vistas,
        }

    def guardar(self, ruta, gestor=None, solo_config=False):
        gestor = gestor or GestorEscenarios()
        cfg = self.a_config()
        nombre = self.nombre_visible
        if self.resultados and self.vigente and not solo_config:
            # "clases"/"tiempos" de la réplica activa se reconstruyen al abrir (no se duplican)
            res = {k: v for k, v in self.resultados.items() if k not in ("clases", "tiempos", "cargas")} \
                if self.resultados.get("por_replica") else self.resultados
            destino = gestor.guardar_con_resultados(ruta, nombre, cfg, res)
        else:
            destino = gestor.guardar_configuracion(ruta, nombre, cfg)
        self.ruta = str(destino)
        self.sucio = False
        return destino

    @classmethod
    def desde_archivo(cls, ruta, gestor=None):
        gestor = gestor or GestorEscenarios()
        datos = gestor.cargar_escenario(ruta)
        e = cls()
        c = datos["configuracion"]
        e.nombre = str(c.get("nombre") or datos["metadata"].get("nombre") or "")
        e.nombre_manual = bool(c.get("nombre_manual", True))
        e.descripcion = str(c.get("descripcion") or "")
        e.replica = str(c.get("replica") or "Todas")
        e.replicas = [str(r) for r in (c.get("replicas") or [])]
        e.archivos = []
        for a in c.get("archivos") or []:
            if isinstance(a, dict) and a.get("nombre"):
                a = dict(a)
                a["incluido"] = bool(a.get("incluido", True))
                a["encontrado"] = True
                e.archivos.append(a)
        e.clases = {k: v for k, v in (c.get("clases") or {}).items() if k in modelo.CLASES}
        for k, v in e.clases.items():
            v.setdefault("mapa_estados", {})
            v.setdefault("tipos", {})
            v.setdefault("columnas", list(v["mapa_estados"]))
            v.setdefault("flotas", {})
            v["orden"] = modelo.orden_normalizado(k, v.get("orden"), list(v.get("flotas") or v["tipos"]))
        e.pivot = c.get("pivot")
        e.pivots = c.get("pivots") or {}
        e.origenes = c.get("origenes") or {}
        e.destinos = c.get("destinos") or {}
        e.plan = c.get("plan") or None
        e.anio = c.get("anio") or None
        e.perfil_cfg = c.get("perfil_cfg") or {"modo": "mes", "filtros": {}}
        e.vistas.update(c.get("vistas") or {})
        for o, v in e.origenes.items():          # v1.2 no guardaba la fase
            v.setdefault("fase", registro.fase_de(o))
        perf = e.clases.get("perforadoras")
        if perf is not None and not perf.get("energia"):
            perf["energia"] = {f: modelo.energia_por_defecto(f) for f in perf.get("flotas") or perf.get("tipos", {})}
            e.revincular_plan()
        for clase, v in e.clases.items():      # v1.1 guardaba «Ultraclass»
            v["tipos"] = {f: modelo.normalizar_tipo(clase, t) or t for f, t in v["tipos"].items()}
        try:
            e.dias = float(c.get("dias") or 365)
        except (TypeError, ValueError):
            e.dias = 365
        if datos.get("resultados") and datos["metadata"].get("estado") == "ejecutado":
            res = datos["resultados"]
            por = res.get("por_replica")
            if not por:                     # formato v1.0: una sola réplica, sin tiempos
                rep = str(res.get("replica") or e.replica)
                por = {rep: {"clases": res.get("clases", {}), "tiempos": {}}}
                res["por_replica"], res["replicas"] = por, [rep]
            if e.replica not in por:
                e.replica = next(iter(por))
            res["replica"] = e.replica
            res["clases"] = por[e.replica]["clases"]
            res["tiempos"] = por[e.replica].get("tiempos", {})
            res["cargas"] = por[e.replica].get("cargas")
            if not e.replicas:
                e.replicas = [r for r in por if r != "Todas"]
            e.resultados = res
            e.vigente = True
            e._ordenar_resultados()
        e.ruta = str(ruta)
        e.resolver_archivos(Path(ruta).parent)
        e.sucio = False
        return e

    def resolver_archivos(self, carpeta_simx):
        """Ubica los CSV aunque el escenario se haya movido de equipo o de carpeta."""
        faltantes = []
        for a in self.archivos:
            if os.path.isfile(a.get("ruta") or ""):
                a["encontrado"] = True
                continue
            candidatas = [Path(carpeta_simx) / a["nombre"],
                          Path(carpeta_simx) / config.CARPETA_INPUTS / a["nombre"],
                          config.dir_inputs() / a["nombre"]]
            for cand in candidatas:
                if cand.is_file():
                    a["ruta"] = str(cand)
                    a["encontrado"] = True
                    break
            else:
                a["encontrado"] = False
                if a.get("incluido", True):
                    faltantes.append(a["nombre"])
        return faltantes
