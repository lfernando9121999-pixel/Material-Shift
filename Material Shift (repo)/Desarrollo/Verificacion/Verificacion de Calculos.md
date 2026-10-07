# Verificación de cálculos y pruebas — Material Shift v2.0

Fecha: 07/10/2026. Referencia: motor de *Modelo v19.5* (`AjustePlan2034_Portable_v19.5\app`), sin modificar.

## 1. Motor: Material Shift vs v19.5 (mismos argumentos)

`comparar_resultados.py` compara celda por celda el Plan Modificado, los datos del dashboard por circuito y el resumen (movimientos, brechas, destinos OK, objetivos, chancadoras y donantes).

| Caso | Plan Modificado | Dashboard Desmonte | Dashboard Mineral | Resumen |
|---|---|---|---|---|
| 2042 · Balanceado · Semanal (Desmonte + Mineral) | 9,134 × 86 · **idéntico** | idéntico | idéntico | 3,971 / 241 mov. · idéntico |
| 2042 · Objetivo fijo · Diario (Desmonte + Mineral) | 9,134 × 86 · **idéntico** | idéntico | idéntico | 5,995 / 598 mov. · idéntico |
| 2034 · Objetivo fijo · Semanal (solo Desmonte) | 10,999 × 87 · **idéntico** | idéntico | — | 2,750 mov. · idéntico |

Se verificó dos veces: con el motor de un solo proceso (CLI) y con el proceso persistente (`motor_servidor.py`, con caché de lectura). Las dos dieron **0 diferencias**.

## 2. Corrida real del usuario

`reproducir_escenario.py` reproduce `Corridas\Caso_4 O+W.csv` con los dos motores, usando el mismo `Ajuste Plan 2042.xlsx`.

| Comparación | Filas | Diferencias |
|---|---|---|
| Motor v19.5 vs motor Material Shift | 9,134 | **0** |
| `Corridas\Resultado 42-Caso 4 - Solo Plan Modificado.xlsx` (corrida real de v19.5) vs Material Shift | 9,134 | **0** |

Además, el 2042 con Mineral completo (`Ore1` + `Stk3_Ore1` + `yan_bl_v`) reproduce lo documentado en v19: **Desmonte 270.4 Mt/año con 575 movimientos y Mineral 52.0 Mt/año con 251 movimientos**, todos los indicadores en Ok.

## 3. Rendimiento

Mismo equipo y mismos casos, en segundos.

| Acción | v19.5 | Material Shift | Cómo |
|---|---|---|---|
| Detectar columnas (Excel ya leído) | 8.5 – 13.2 | **0.12 – 0.2** | Proceso persistente + caché (memoria y disco) |
| Detectar columnas (primera lectura del archivo) | 8.5 – 13.2 | 4.0 – 6.6 | Sin el arranque de Python ni de tkinter |
| Calcular ambos circuitos | 16.4 – 18.1 | **1.5 – 2.0** | Sin releer el Excel y sin escribir un xlsx de paso |
| Excel · Plan Modificado | 15.8 – 16.3 (libro vacío) | **6.1 – 6.7** (plan completo) | — |
| Abrir el programa hasta poder calcular | — | < 1 s (detección 0.9 s desde caché en disco) | — |
| Cambiar de pestaña (barra lateral) | — | 3 – 18 ms | — |
| Cambiar de vista del dashboard | recarga del HTML con Babel desde internet | 8 – 55 ms | Gráficos SVG propios, sin internet |

## 4. Prueba automática de la interfaz (`prueba_interfaz.py`, vía CDP)

Resultado: **27/27 correctas**. Las capturas están en `Capturas\`. Cubre:

- Abrir escenarios desde «Abrir existente».
- Detección de Desmonte y Mineral.
- Calcular.
- Indicadores en verde y rojo claro.
- Leyendas «Plan» y el nombre del escenario.
- Semanal / Diario con el título actualizado.
- Las tres vistas y la subpestaña Mineral, sincronizada con la barra lateral.
- Criterios independientes por circuito.
- Aviso de resultados desactualizados.
- `Alt+↑` en Prioridad.
- Aviso al descartar cambios.
- Comparar A vs B con los nombres en la leyenda e intercambio A ⇄ B.
- Menú contextual y copia de datos.
- Tiempos por pestaña.

`prueba_portapapeles.py`: gráfico como imagen (PNG + DIB), tabla como imagen y tabla con formato (HTML + texto): **3/3**.

## 5. Pruebas de escritorio con Windows-MCP (mouse y teclado reales)

| Prueba | Resultado |
|---|---|
| Arrastrar un donante al primer lugar en Prioridad | ✅ |
| Abrir y Guardar como: diálogo a tamaño medio y centrado sobre el programa | ✅ |
| Escenario v19 con ruta inexistente → el archivo base se reubica en `Inputs\` | ✅ |
| Modo de Mineral independiente del de Desmonte | ✅ |
| Aviso «Nuevo escenario disponible… ¿Desea actualizar?» al editar el `.csv` por fuera, conservando los resultados | ✅ |
| Calcular con `F5` | ✅ |
| Diario / Semanal | ✅ |
| Clic derecho → Copiar como gráfico de PowerPoint (se pega como gráfico nativo) | ✅ |
| Comparar escenarios | ✅ |
| Modo noche (`Ctrl+Shift+M`) en ambas páginas | ✅ |
| Minimizar → restaurar (antes quedaba en blanco; corregido) | ✅ |
| Acoplar a media pantalla y a cuadrante: tarjetas y gráficos se reacomodan | ✅ |
| Ventana nativa de la matriz de materiales | ✅ |
| Editor «Columnas detectadas»: activar Mineral desde cero | ✅ |
| `Ctrl+E` → Excel con «Plan Modificado» completo (9,134 × 86) | ✅ |
| Exportar todos los gráficos a PowerPoint (gráficos nativos) | ✅ |
| `Alt+F4` con cambios → «¿Deseas guardarlos?» | ✅ (antes la página se tragaba la tecla; corregido) |
| Cerrar sin cambios → sin aviso | ✅ |

## 6. Cómo repetir

```
Model\python\python.exe Desarrollo\Verificacion\comparar_resultados.py <carpeta_v19.5> <carpeta_MS> <caso...>
set WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS=--remote-debugging-port=9223 & "Material Shift.exe"
Model\python\python.exe Desarrollo\Verificacion\prueba_interfaz.py
```
