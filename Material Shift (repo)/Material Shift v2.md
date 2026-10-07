# Material Shift v2.0

Programa en `Escritorio\Material Shift`.

Los resultados son idénticos a v19.5. Se comprobó celda por celda en 3 casos distintos (2034 y 2042, balanceado y fijo, semanal y diario). También se reprodujo con 0 diferencias la corrida real `Corridas\Resultado 42-Caso 4 - Solo Plan Modificado.xlsx`.

---

## 1. Lo que pide el documento

- **Nombre y logo:** `Material Shift.exe`, con logo nuevo al estilo SimA (fondo azul profundo, flechas azul a verde y pilas de acopio). La estructura de carpetas es la misma de SimA: `Escenarios`, `Inputs`, `Outputs`, `Model` y `Desarrollo`.
- **Inputs:** se llama así en lugar de "Datos", con "\* Requerido" en archivo base y hoja.
- **Escenario `.csv` legible:** los objetivos van en una tabla con columnas Desmonte y Mineral. Los escenarios de v19 se siguen abriendo y dan el mismo resultado.
- **Desmonte y Mineral como subpestañas:** en la barra lateral y en el dashboard, sincronizadas entre sí.
- **Criterio independiente por circuito:** modo, semanal/diario, objetivo y tolerancia son propios de cada circuito (el recuadro rojo). Los indicadores muestran "✓ Ok" en verde claro o "! Revisar" en rojo claro (el recuadro verde).
- **Aviso al cambiar el `.csv` por fuera:** aparece en el pie "Nuevo escenario disponible… ¿Desea actualizar?" y la corrida no se pierde.
- **Plan y nombre del escenario:** reemplazan a "Base" y "Modificado" en el dashboard. Los nombres de hojas del Excel no cambiaron, para no romper procesos que ya los usen.
- **Botones Semanal/Diario** en cada gráfico, con título dinámico.
- **Clic derecho:** copiar datos, imagen o gráfico de PowerPoint editable.
- **Comparar Escenarios:** A contra B, con sus nombres en las leyendas.
- **Prioridad que se arrastra:** columnas numeradas "1. Donantes" y "2. Fases", como el Orden de Reporte de SimA.

---

## 2. Rendimiento

| Acción | v19.5 | Material Shift |
|---|---|---|
| Calcular | ~17 s | ~2 s |
| Detectar columnas | ~9 s | 0.2 s |
| Excel | ~16 s | ~6 s |

El dashboard ya no necesita internet; antes descargaba sus librerías cada vez.

---

## 3. Errores encontrados y corregidos

- **Excel vacío en v19.5:** el botón Excel abría un libro vacío (5 KB) y el plan real quedaba en "Solo Plan Modificado". Ahora sale completo con el nombre elegido.
- **Matriz de Mineral ignorada en v19.5:** las restricciones de materiales de Mineral nunca llegaban al cálculo. Ahora sí llegan; solo cambia el resultado si se habían bloqueado materiales en Mineral.
- **Errores de interfaz detectados en las pruebas:** ventana en blanco al restaurar desde minimizado, Alt+F4 que no cerraba, comparación A=B y foco perdido tras los diálogos. Todos quedaron corregidos.

---

## 4. Pruebas

- Prueba automática de la interfaz: **27/27**.
- Prueba del portapapeles: **3/3**.
- Con Windows-MCP (mouse y teclado reales): **18 pruebas de escritorio** correctas, entre ellas arrastrar, diálogos centrados, media pantalla, modo noche, exportar a Excel y PowerPoint y Alt+F4.

---

## 5. Incidentes durante las pruebas

- Un cálculo escribió dos archivos de resultados en `Modelo v19\...\outputs`, porque el Caso 1 original apuntaba ahí. Se borraron enseguida y las copias de los escenarios se apuntaron a `Material Shift`. `Modelo v19.5` y `Corridas` quedaron intactos.
- El asistente de acople de Windows movió la ventana de Claude al monitor principal; se regresó a su lugar.
- En Excel y PowerPoint solo se abrieron y cerraron los archivos generados por las pruebas. El `.xlsm` del usuario siguió abierto y sin cambios.
- Al final, Excel quedó en la vista "Archivo"; lo único que se hizo ahí fue volver a la hoja.

---

## 6. Segunda etapa sugerida (de SimA)

Filtros tipo Excel, columnas que se reordenan arrastrando, desacoplar un escenario a otra ventana, tablas dinámicas y manual en `.docx`.

---

## 7. Documentos

Todos en `Escritorio\Material Shift`:

- `Resumen_Sesion_Material_Shift_v2.md` — resumen en el formato de v19.
- `Leame.md` — guía de uso, novedades y atajos.
- `Desarrollo\Verificacion\Verificacion de Calculos.md` — resultados de las pruebas y cómo repetirlas.
