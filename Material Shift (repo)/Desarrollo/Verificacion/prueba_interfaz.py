"""Prueba automática de la interfaz real de Material Shift (vía CDP, sin mover el mouse).

1. Lanzar la app con depuración:
     set WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS=--remote-debugging-port=9223
     "Material Shift.exe"
2. ..\\..\\Model\\python\\python.exe prueba_interfaz.py  [carpeta_capturas]

Abre los escenarios Caso_1 y Caso_4 desde «Abrir existente», calcula, recorre todas las vistas
y subpestañas (Desmonte y Mineral, Semanal y Diario), compara A vs B, copia datos con el menú
contextual y mide tiempos. Imprime una tabla de resultados y sale con código 1 si algo falla.
"""
import json
import sys
import time
from pathlib import Path

import cdp

OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).with_name("capturas")
OUT.mkdir(parents=True, exist_ok=True)
RES = []


def ok(nombre, cond, detalle=""):
    RES.append((nombre, bool(cond), detalle))
    print(("OK   " if cond else "FALLA") + f"  {nombre}  {detalle}", flush=True)


def t(fn):
    t0 = time.perf_counter()
    r = fn()
    return r, time.perf_counter() - t0


side, dash = cdp.pagina("Barra lateral"), cdp.pagina("Dashboard")
STT = "document.getElementById('stt').textContent"


def esperar_libre(timeout=120):
    side.esperar("!document.querySelector('.status .spin')", timeout)


esperar_libre()


def abrir_reciente(nombre):
    side.click_sel("[data-menu=archivo]")
    side.esperar("document.getElementById('dd').style.display==='block'", 5)
    idx = side.js(f"Array.from(document.querySelectorAll('#dd .rec')).findIndex(e=>e.textContent.includes({json.dumps(nombre)}))")
    if idx < 0:
        raise RuntimeError("no está en recientes: " + nombre)
    side.click_sel(f"#dd .rec:nth-of-type({idx + 1})") if False else side.click(*side.js(
        f"(()=>{{const e=document.querySelectorAll('#dd .rec')[{idx}];const b=e.getBoundingClientRect();return [b.left+b.width/2,b.top+b.height/2]}})()"))
    side.esperar(f"document.getElementById('scn').textContent.includes({json.dumps(nombre)})", 10)
    side.esperar("!S.detecting && !S.busy && /Escenario cargado|Detectado/.test(S.status)", 60)


def calcular():
    side.esperar("!document.getElementById('calc').disabled && !S.busy", 60)
    n0 = dash.js("Object.keys(S.runs).length")
    side.click_sel("#calc")
    dash.esperar(f"Object.keys(S.runs).length > {n0} && document.querySelector('.kpis')", 180)
    esperar_libre(30)
    return side.js(STT)


# ---------------------------------------------------------------- escenario A
(_, dt) = t(lambda: abrir_reciente("Caso_1"))
ok("Abrir Caso_1 desde «Abrir existente» (con detección)", True, f"{dt:.2f} s")
estado = side.js("({m:S.mineralDisponible, ch:S.chancadoras, mch:S.mineralChancadoras, y:S.activeYear, modeD:S.mode, modeM:S.mineralMode})")
ok("Caso_1: circuitos Desmonte + Mineral detectados", estado["m"] and estado["ch"] == ["Chw2a_1", "Chw2a_2"] and estado["mch"] == ["Ore1"], json.dumps(estado))
(msg, dt) = t(calcular)
ok("Calcular Caso_1", "Listo" in msg, f"{dt:.2f} s · {msg}")
dash.captura(str(OUT / "01_dashboard_desmonte.png"))
side.captura(str(OUT / "01_sidebar.png"))

# KPI de estado: verde claro "Ok" / rojo claro "Revisar"
k = dash.js("Array.from(document.querySelectorAll('.kpi')).map(e=>[e.querySelector('.top span').textContent, e.className, e.querySelector('strong').textContent])")
estados = {x[0]: (x[1], x[2]) for x in k}
ok("KPI Destinos/Balance/Tabla muestran Ok en verde", all("ok" in estados[n][0] and "Ok" in estados[n][1] for n in ("Destinos", "Balance Material", "Tabla Materiales")), json.dumps(estados, ensure_ascii=False))
leyenda = dash.js("Array.from(document.querySelectorAll('#chCons svg text')).map(e=>e.textContent).filter(x=>x==='Plan'||x.startsWith('Caso'))")
ok("Leyenda: «Plan» y nombre del escenario (no Base/Modificado)", "Plan" in leyenda and "Caso_1 O+W" in leyenda, str(leyenda))

# Semanal / Diario con título dinámico
for per, palabra in (("diario", "Diario"), ("semanal", "Semanal")):
    (_, dt) = t(lambda: (dash.click_sel(f"[data-per='mat:{per}']"), dash.esperar(f"document.querySelector('.panel h2').textContent.includes('{palabra}')", 5)))
    ok(f"Gráfico de material en {palabra} (título actualizado)", True, f"{dt * 1000:.0f} ms")

# Vistas y subpestañas
for vista in ("tabla", "materiales", "dashboard"):
    (_, dt) = t(lambda: (dash.click_sel(f"[data-view='{vista}']"), dash.esperar("document.querySelector('#main .panel')", 5)))
    ok(f"Vista {vista}", True, f"{dt * 1000:.0f} ms")
    dash.captura(str(OUT / f"02_{vista}.png"))
(_, dt) = t(lambda: (dash.click_sel("[data-circ='Mineral']"), dash.esperar("S.circuit==='Mineral' && document.querySelector('.kpis')", 5)))
ok("Subpestaña Mineral en el dashboard", True, f"{dt * 1000:.0f} ms")
side.esperar("document.querySelector('.kpicard.on') && document.querySelector('.kpicard.on').dataset.circ==='mineral'", 5)
ok("La barra lateral sigue al circuito elegido en el dashboard", True)
dash.captura(str(OUT / "03_dashboard_mineral.png"))
bal = dash.js("Array.from(document.querySelectorAll('.kpi')).filter(e=>e.textContent.includes('Balance'))[0].className")
ok("Mineral Caso_1: Balance material en rojo claro (falta yan_bl_v como donante, ver v19)", "bad" in bal, bal)
dash.click_sel("[data-circ='Desmonte']")

# ---------------------------------------------------------------- criterios independientes por circuito
side.click_sel("[data-tab=objetivos]")
side.click_sel("[data-circ=mineral]")
side.click_sel("[data-set='mineralMode:objetivo_fijo']")
side.click_sel("[data-circ=desmonte]")
modos = side.js("[S.mode, S.mineralMode]")
ok("Modo por circuito: cambiar Mineral no cambia Desmonte", modos == ["balanceado", "objetivo_fijo"], str(modos))
banner = dash.js("document.getElementById('banner').textContent")
ok("Aviso en el dashboard: resultados desactualizados tras cambiar criterios", "F5" in banner, banner.strip())

# ---------------------------------------------------------------- Prioridad: arrastrar
side.click_sel("[data-tab=prioridad]")
# (El arrastre con el mouse real se prueba con Windows-MCP; los eventos sintéticos de CDP
#  no reproducen la captura del puntero. Aquí se prueba la alternativa de teclado.)
antes = side.js("S.donorsC1.map(x=>x.id)")
side.click_sel("[data-prio=donorsC1]:nth-child(2) .nm")
side.tecla("ArrowUp", "ArrowUp", 38, mods=1)   # Alt
time.sleep(0.4)
despues = side.js("S.donorsC1.map(x=>x.id)")
ok("Prioridad: Alt+↑ sube la fila seleccionada", despues[0] == antes[1] and despues[1] == antes[0], f"{antes} -> {despues}")
side.click_sel("[data-prio-reset]")
time.sleep(0.4)

# ---------------------------------------------------------------- escenario B y comparación
def responder_no(resultado, timeout=15):
    """Busca el cuadro «¿Deseas guardarlos?» del programa y responde No (IDNO)."""
    import ctypes
    from ctypes import wintypes
    u = ctypes.windll.user32
    t0 = time.time()
    while time.time() - t0 < timeout:
        hallado = []

        def cb(h, _):
            cls = ctypes.create_unicode_buffer(64); u.GetClassNameW(h, cls, 64)
            tit = ctypes.create_unicode_buffer(128); u.GetWindowTextW(h, tit, 128)
            if cls.value == "#32770" and tit.value == "Material Shift" and u.IsWindowVisible(h):
                hallado.append(h)
            return True
        u.EnumWindows(ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)(cb), 0)
        if hallado:
            u.SendMessageW(hallado[0], 0x0111, 7, 0)   # WM_COMMAND, IDNO
            resultado.append(True)
            return
        time.sleep(0.2)


import threading
resp = []
hilo = threading.Thread(target=responder_no, args=(resp,), daemon=True)
hilo.start()
abrir_reciente("Caso_4")   # el escenario quedó modificado: el programa pregunta antes de descartar
hilo.join(1)
ok("Al abrir otro escenario con cambios sin guardar, pregunta antes de descartar", bool(resp))
(msg, dt) = t(calcular)
ok("Calcular Caso_4", "Listo" in msg, f"{dt:.2f} s")
(_, dt) = t(lambda: (dash.click_sel("[data-view='comparar']"), dash.esperar("document.getElementById('cmpLine') && document.querySelector('#cmpLine svg')", 10)))
ok("Comparar escenarios: A vs B dibujado", True, f"{dt * 1000:.0f} ms")
nombres = dash.js("Array.from(document.querySelectorAll('#cmpLine svg text')).map(e=>e.textContent).filter(x=>x.startsWith('Caso'))")
ok("Comparación: nombres de los escenarios en la leyenda", any("Caso_1" in n for n in nombres) and any("Caso_4" in n for n in nombres), str(nombres))
dash.captura(str(OUT / "04_comparar.png"))
dash.click_sel("[data-swap]")
ok("Intercambiar A ⇄ B", "Caso_4" in dash.js("document.querySelector('[data-pick=A]').selectedOptions[0].textContent"))

# ---------------------------------------------------------------- menú contextual: copiar datos
dash.click_sel("[data-view='dashboard']")
dash.esperar("document.getElementById('chMat')", 5)
x, y = dash.centro("#chMat")
dash.click(x, y, button="right")
dash.esperar("document.getElementById('cm').style.display==='block'", 5)
items = dash.js("Array.from(document.querySelectorAll('#cm [data-cm]')).map(e=>e.textContent)")
ok("Menú contextual del gráfico (datos, imagen, PowerPoint)", len(items) >= 6, " | ".join(items))
dash.click_sel("#cm [data-cm=data]")
time.sleep(0.5)
ok("Copiar datos del gráfico → portapapeles", "Copiado" in side.js(STT), side.js(STT))

# ---------------------------------------------------------------- tiempos de cambio de pestaña en la barra lateral
for tab in ("inputs", "objetivos", "prioridad", "material"):
    (_, dt) = t(lambda: side.click_sel(f"[data-tab={tab}]"))
    ok(f"Barra lateral: pestaña {tab}", True, f"{dt * 1000:.0f} ms")

falla = [r for r in RES if not r[1]]
print(f"\nRESULTADO: {len(RES) - len(falla)}/{len(RES)} correctas")
(OUT / "resultado.json").write_text(json.dumps(RES, ensure_ascii=False, indent=1), encoding="utf-8")
sys.exit(1 if falla else 0)
