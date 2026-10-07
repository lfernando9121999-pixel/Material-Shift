# Material Shift v2.0 — Resumen de la sesión

Sucesor del *Modelo de Reasignación de Materiales v19.5*. Es una app de escritorio (WinForms + WebView2 + motor Python/SciPy) que redistribuye el tonelaje semanal entre chancadoras y destinos donantes, con dos circuitos independientes: **Desmonte** y **Mineral**.

Requerimientos: `Material Shift v2.docx`. Referencia de interfaz: `SimA v1.5 - Resumen General.md`.

Regla de versionado: `Modelo v19.5` (programa y `Corridas`) solo se usó como plantilla y referencia, sin modificarlo. Todas las pruebas se hicieron en la carpeta nueva.

Carpeta de trabajo: `Escritorio\Material Shift`
Entregable final: carpeta portable de 592.7 MB y 15,209 archivos (`Material Shift.exe`, `Escenarios\`, `Inputs\`, `Outputs\`, `Model\`, `Desarrollo\`, `Leame.md`).

---

## 1. Identidad y diseño

- **Nombre:** «Material Shift» con «v2.0» a la derecha (el número sale del documento *Material Shift v2*). Se aplica al exe, a las ventanas, al encabezado del CSV (`Escenario Material Shift;version 3`) y a las propiedades del Excel.
- **Logo:** se redibujó el logo propuesto con el mismo lenguaje visual de SimA. Para gerencia se prefirió un fondo de color sobre el fondo blanco: cuadrado redondeado con degradado azul profundo (`#0B2545 → #134B7A`), flechas de reasignación azul → verde, tres pilas de acopio y los signos −/+. Lo genera `crear_icono.py` (PNG 32/64/128/256 e ICO multi-tamaño) y va embebido en el exe y en las páginas.
- **Interfaz:**
  - grises suaves y encabezado azul igual al del logo;
  - **modo noche** (`Ctrl+Shift+M`);
  - barra lateral redimensionable;
  - la ventana recuerda tamaño, posición y maximizado.
- **Estructura de carpetas igual a SimA:** `Escenarios`, `Inputs`, `Outputs`, `Model` (internos y `Preferencias`), `Desarrollo` (código fuente con `compilar.ps1`, y verificación).

## 2. Lo que se tomó de SimA (primera etapa: lo que ambos programas tienen en común)

| SimA v1.5 | Material Shift v2.0 |
|---|---|
| Nombre con versión, modo claro gris y modo noche | ✅ |
| Explorador de archivos a tamaño medio, centrado sobre el programa | ✅ (Abrir, Guardar, Excel de salida, imágenes y PowerPoint) |
| «Abrir Existente» con recientes | ✅ menú Archivo y portada del dashboard |
| `*` Requerido en rojo oscuro | ✅ Archivo base y Hoja |
| Orden de Reporte (columnas numeradas que se arrastran, Restablecer) | ✅ Prioridad: *1. Donantes* y *2. Fases* |
| Clic derecho en tablas: copiar tabla, con formato o como imagen | ✅ |
| Clic derecho en gráficos: datos, imagen, gráfico de PPT editable | ✅ (incluye guardar imagen y exportar .pptx) |
| Gráficos nativos editables en PowerPoint | ✅ `exportar_ppt.py` (python-pptx) + copia con PowerPoint (COM) |
| Cerrar sin aviso cuando solo se navegó | ✅ el aviso solo aparece si hay cambios sin guardar |
| Tarjetas que se reacomodan a media pantalla | ✅ media pantalla y cuadrante |
| Atajos de teclado y `F1` | ✅ |
| Leame y verificación en `Desarrollo\Verificacion` | ✅ |

**Para una segunda etapa** (existen en SimA pero no aplican directo o son de mayor alcance): filtros estilo Excel en las tablas, columnas reordenables arrastrando el encabezado, desacoplar un escenario a otra ventana, tablas dinámicas, un reporte PowerPoint con todas las pestañas y el manual de usuario en `.docx`.

## 3. Requerimientos del documento

| # | Pedido | Solución |
|---|---|---|
| 1 | Programa «Material Shift.exe» | Exe en la raíz; los DLL de WebView2 van en `Model\bin` (resolución propia y `SetLoaderDllFolderPath`). |
| 2 | Logo mejorado al estilo SimA | Ver §1. |
| 3 | «Datos» → «Inputs» | Hecho, con `*` Requerido y la Hoja elegida de una lista con las hojas del Excel. |
| 4 | Escenario como `.csv` legible | Se guarda solo como CSV (v3). [Objetivos] es una tabla *Parámetro · Desmonte · Mineral*; se agregan [Materiales Mineral] y BOM UTF-8 para los acentos en Excel. Los `.csv/.txt/.json` de v19 se siguen abriendo. |
| 5 | Desmonte y Mineral como subpestañas (evaluar) | Se implementó: subpestañas en Objetivos, Prioridad, Material y en el dashboard. Las tres vistas y las tarjetas KPI quedan **sincronizadas** (elegir Mineral en un lugar lo cambia en todos); también con `Ctrl+Tab`. |
| 6 | Aviso cuando se actualiza el `.csv`, sin perder la corrida | El programa vigila el archivo y compara su contenido (así ignora sus propios guardados). En el pie aparece **«Nuevo escenario disponible… ¿Desea actualizar?»** con *Actualizar / Ignorar*. Al actualizar se recarga la configuración, el dashboard **conserva** la corrida y avisa que está desactualizada. |
| 7 | «Base» → «Plan»; «Modificado» → nombre del escenario | En leyendas, tablas, comparación, tooltips y exportaciones. Los nombres de hojas del Excel (*Plan Base*, *Plan Modificado*) no se cambiaron, para no romper procesos existentes. |
| 8 | Pestaña «Comparar con otros escenarios», A vs B con sus nombres | **Comparar Escenarios** incluye: <br>• selectores A y B, botón ⇄ y *Abrir resultado…*; <br>• gráfico A vs B (Total o por chancadora, semanal o diario); <br>• totales por destino y por tipo de material; <br>• tabla de indicadores con B − A; <br>• detalle por período. <br>Las corridas de la sesión y los `- Resultados.json` guardados están disponibles. |
| 9 | Objetivos (recuadro rojo): el criterio no debe quedar fijo entre circuitos | **Modo, Semanal/Diario, objetivo, tolerancia, unidad y objetivo diario** son independientes por circuito, en la app, en el CSV y en el motor (`--mineral-target-mode`, `--mineral-granularity`, `--mineral-daily-*`). Un escenario de v19 hereda los valores compartidos, así que da el mismo resultado de antes. |
| 10 | Recuadro verde: «Ok» en verde claro y rojo claro si hay error | *Destinos*, *Balance Material* y *Tabla Materiales* muestran «✓ Ok» en verde claro o «! Revisar (n)» en rojo claro (con ícono y texto, no solo color). |
| 11 | Botones Semanal / Diario en el gráfico, con el título dinámico | En cada gráfico del dashboard, en Tabla y en Comparar. El título cambia («Material **Diario** por…»). Las series diarias se generan en toda corrida. |
| 12 | Clic derecho → imagen o gráfico de PPT editable | Ver §2. Verificado: en el portapapeles queda *PowerPoint 12.0 Internal Shapes* (gráfico nativo). |
| 13 | Prioridad: mover como celdas, como lista del otro programa | Columnas *1. Donantes* y *2. Fases* con numeración, asa ≡, casilla para usar o no, **arrastrar y soltar**, `Alt+↑/↓`, *Restablecer* y *Copiar a la otra chancadora*. |
| 14 | Pruebas con Windows-MCP, ergonomía y rendimiento | Ver §6 y `Desarrollo\Verificacion\Verificacion de Calculos.md`. |

## 4. Funcionalidades nuevas además de lo pedido

- **Motor persistente** (`motor_servidor.py`): Python, NumPy y SciPy se cargan una sola vez. La lectura del Excel queda en caché (en memoria y en disco, invalidada por tamaño y fecha). Calcular pasa de ~17 s a **~2 s**.
- **Dashboard sin internet:** v19 descargaba React, Recharts y Babel de unpkg cada vez. Ahora los gráficos son SVG propios (curvas monótonas, tooltip con guía, leyendas), con modo noche e impresión de imagen a 2×.
- **Portada** del dashboard con los pasos, los atajos y los escenarios recientes.
- **Menú Exportar:**
  - Excel · Plan Modificado;
  - Excel · Reporte completo (15 hojas, ambos circuitos);
  - PowerPoint de la vista;
  - Dashboard en el navegador (HTML suelto, para compartir);
  - abrir la carpeta de salida.
- **Escenarios de otra PC:** si el archivo base no existe, se busca por nombre junto al escenario y en `Inputs\`.
- **Encabezado del dashboard** con el criterio del circuito, el escenario y la fecha de la corrida. El estado muestra el tiempo transcurrido mientras calcula.
- **Matriz de materiales:** clic en el encabezado marca o desmarca la columna completa; la ventana se ajusta a las filas.

## 5. Correcciones (errores encontrados)

| # | Problema | Solución |
|---|---|---|
| 1 | **v19.5:** el botón Excel abría un libro **vacío** (`Sheet1`, 5 KB). El plan quedaba en «- Solo Plan Modificado.xlsx». | `--excel-only` escribe el Plan Modificado combinado (ambos circuitos) en el nombre exacto elegido. Verificado: 9,134 × 86. |
| 2 | **v19.5:** las restricciones de la matriz de **Mineral** nunca llegaban al motor (solo se enviaban los destinos de Desmonte) y no se guardaban en el escenario. | Se envían los destinos de ambos circuitos y se guarda [Materiales Mineral]. Solo cambia el resultado de quien había bloqueado materiales en Mineral, que antes se ignoraban. |
| 3 | **v19.5:** el criterio (modo, diario) era común a los dos circuitos. | Ver requerimiento 9. |
| 4 | **v19.5:** el aviso de guardar aparecía siempre al cerrar. | Solo aparece si hay cambios; el título muestra «•» y la barra lateral también. |
| 5 | Prueba: las WebView quedaban **en blanco** al restaurar una ventana que se abrió minimizada. | Se fuerza la visibilidad al restaurar y se abre en tamaño normal. |
| 6 | Prueba: **Alt+F4** no cerraba (la página se tragaba la tecla). | Las páginas reenvían Alt+F4 o AltGr+F4 al programa. |
| 7 | Prueba: `Alt+↑/↓` no movía la fila (el foco quedaba en el documento). | El atajo se escucha a nivel de documento. |
| 8 | Prueba: en Comparar, A y B quedaban iguales si el archivo de resultados de A se sobrescribía. | A pasa a la corrida anterior de la sesión. |
| 9 | Prueba: después de cerrar un diálogo el teclado no volvía a la app. | Se devuelve el foco a la página tras cada diálogo. |
| 10 | Detalles: «-0» en diferencias, tooltip visible bajo el menú contextual, etiquetas A/B cortadas, color de la tolerancia, grupos vacíos en la búsqueda del editor, fondo gris en la matriz. | Corregidos. |

## 6. Pruebas

- **Motor:** idéntico a v19.5 en 3 casos (2034 y 2042; balanceado y fijo; semanal y diario): Plan Modificado celda por celda, datos del dashboard y resumen.
- **Corrida real:** `Corridas\Resultado 42-Caso 4 - Solo Plan Modificado.xlsx` reproducido con **0 diferencias**.
- **2042 con Mineral completo:** Desmonte 270.4 Mt/año con 575 movimientos y Mineral 52.0 Mt/año con 251 movimientos, igual que lo validado en v19.
- **Interfaz (CDP):** 27/27; portapapeles 3/3.
- **Escritorio (Windows-MCP, mouse y teclado reales):** 18 pruebas correctas (detalle en el archivo de verificación).
- **Rendimiento:**

| | v19.5 | Material Shift |
|---|---|---|
| Detección | 8.5–13 s | 0.12–0.2 s (con caché) |
| Calcular | 16–18 s | 1.5–2.0 s |
| Excel | 16 s (vacío) | 6–7 s (completo) |
| Cambio de vista | recarga con Babel | 8–55 ms |

## 7. Hallazgos e interpretaciones

| Indicación | Interpretación |
|---|---|
| «Material Shift v2» (nombre del documento) | Versión del programa: **v2.0**. |
| «Aplicar todo ese cambio para la configuración de la lógica» | Renombrado en exe, títulos, CSV y Excel. Los módulos del motor (`ajuste_plan_ejecutable.py`, `generar_ajuste_plan_2034.py`) mantienen su nombre interno para conservar la trazabilidad con v19. |
| «Lista desplegable así como el otro programa» | El «Orden de Reporte» de SimA (columnas numeradas que se arrastran). |
| «Evaluar» subpestañas | Se adoptaron, sincronizadas en toda la app. |
| Casos 1–4 de `Corridas` | Se copiaron a `Escenarios\` y se apuntaron a `Material Shift\Inputs` y `Outputs`, para no escribir nunca en las carpetas de v19. |
| Casos 1–4 vs `Corridas` | `Modelo v19\Ajuste Plan 2042.xlsx` (4.1 MB) y `Corridas\Ajuste Plan 2042.xlsx` (7.8 MB) son **archivos distintos**: con uno u otro cambian los resultados. La corrida guardada del Caso 4 corresponde al de 7.8 MB, que es el de `Inputs\`. |

## 8. Problemas técnicos

- **Compilador:** `csc.exe` de .NET Framework 4.8 solo acepta C# 5 (sin interpolación ni `?.`). El código está escrito para esa versión. `compilar.ps1 [-Logo]` regenera el exe e incrusta el ícono.
- **Comandos de Windows-MCP:**
  - la tecla «Alt» se envía como **AltGr** (teclado en español); por eso se acepta también AltGr+F4;
  - las capturas con `dxcam` a veces devuelven un cuadro anterior. Se verificó el estado real por CDP antes de concluir.
- **Arrastrar con eventos sintéticos de CDP** no reproduce la captura del puntero. El arrastre se probó con el mouse real (Windows-MCP) y en la prueba automática se usa la alternativa de teclado.
- **Durante las pruebas:**
  - un cálculo de prueba escribió dos archivos de resultados en `Modelo v19\...\outputs`, porque el Caso 1 original apuntaba ahí; se borraron de inmediato;
  - el asistente de acople de Windows movió momentáneamente la ventana de Claude y se devolvió a su monitor;
  - las ventanas del usuario (Excel `.xlsm`, PowerPoint, AnyLogic) no se modificaron.

## 9. Estado final

- `Material Shift.exe` compilado sin errores, con todas las correcciones.
- Motor verificado: idéntico a v19.5 y a la corrida real del Caso 4.
- `Leame.md` (uso, novedades, atajos y notas) y `Desarrollo\Verificacion\Verificacion de Calculos.md` (resultados y cómo repetirlos, con capturas en `Capturas\`).
- Escenarios de ejemplo: Casos 1–4 (de v19.5) y **Caso 5 · Mineral completo** (formato v3).
- `Outputs\` vacío y preferencias reiniciadas para el primer uso.
- `Modelo v19.5` y `Corridas` intactos.

**Pendiente o sugerido:**
- la segunda etapa de SimA (§2);
- firmar el exe para que Windows no lo analice en el primer arranque;
- empaquetar en `.zip` si se va a distribuir.
