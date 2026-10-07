"""SimA – Simulation Analyst: punto de entrada."""
import logging
import os
import sys
from logging.handlers import RotatingFileHandler

# Permite ejecutar desde cualquier ubicación (el .exe y el código fuente son agnósticos a la ruta)
if not getattr(sys, "frozen", False):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config


def _configurar_registro():
    try:
        ruta = config.dir_preferencias() / "sima.log"
        h = RotatingFileHandler(ruta, maxBytes=512_000, backupCount=2, encoding="utf-8")
        h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        raiz = logging.getLogger()
        raiz.addHandler(h)
        raiz.setLevel(logging.INFO)
    except Exception:
        pass


def _autoprueba(carpeta_csv, salida, ruta_plan=None):
    """Verificación sin interfaz del ejecutable: importa, calcula, guarda y exporta."""
    import traceback
    os.makedirs(salida, exist_ok=True)
    log = open(os.path.join(salida, "autoprueba.log"), "w", encoding="utf-8")
    try:
        import csvio, escenario, export_excel, export_plan, export_pptx, pivot, plan, registro
        e = escenario.Escenario()
        metas = [csvio.inspeccionar(os.path.join(carpeta_csv, f)) for f in sorted(os.listdir(carpeta_csv))
                 if csvio.es_archivo_modelo(f)]
        e.incorporar_archivos(metas)
        e.aplicar_carga(e.preparar_carga())
        avisos = e.ejecutar()
        if ruta_plan:
            datos = plan.leer_excel(ruta_plan)
            plan.vincular(e, datos["filas"])
            e.set_plan({"nombre": datos["nombre"], "archivo": os.path.basename(ruta_plan), "hoja": datos["hoja"],
                        "fecha": "", "filas": datos["filas"]})
            export_plan.exportar(os.path.join(salida, "autoprueba_plan.xlsx"), e)
        ruta = e.guardar(os.path.join(salida, "autoprueba.simx"))
        export_excel.exportar_reporte(os.path.join(salida, "autoprueba.xlsx"), e)
        export_pptx.exportar_reporte(os.path.join(salida, "autoprueba.pptx"), e)
        f = e.resultados["clases"]["perforadoras"]["flota"][0]
        log.write(f"OK nombre={e.nombre} clases={list(e.clases)} avisos={avisos} "
                  f"flota0={f['nombre']} hp={f['horas_productivas']:.3f} disp={f['disponibilidad']:.6f}\n")
        if e.resultados.get("cargas"):
            o = registro.por_tipo_origen(e.resultados["cargas"], e.origenes)
            log.write(f"CARGAS OK origenes={len(e.origenes)} total_t={o['total']:.2f}\n")
        reg = [m for m in metas if m["nombre"].lower() == "o_registro_cargas.csv"]
        if reg:
            df = csvio.cargar_tabla_grande(reg[0]["ruta"], reg[0])
            t = pivot.calcular(df, {"filas": [{"campo": "Flota Acarreo"}],
                                    "valores": [{"campo": "Carga (t)", "agg": "sum"}]})
            log.write(f"PIVOT OK filas={len(t['filas'])} total={t['filas'][-1][-1]:.2f}\n")
        log.write("FIN\n")
    except Exception:
        log.write("ERROR\n" + traceback.format_exc())
    finally:
        log.close()


def main():
    _configurar_registro()
    if len(sys.argv) >= 4 and sys.argv[1] == "--autoprueba":
        _autoprueba(sys.argv[2], sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else None)
        return
    from app import App
    App().ejecutar_bucle()


if __name__ == "__main__":
    main()
