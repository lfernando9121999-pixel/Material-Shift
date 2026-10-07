# Material Shift v2.0 — contexto para el asistente

App de escritorio Windows (WinForms C# + WebView2) con motor Python (SciPy/HiGHS) que reasigna el tonelaje semanal de un plan de minado entre chancadoras (receptores) y destinos donantes, para dos circuitos independientes: Desmonte y Mineral. Documentación completa en `README.md` (arquitectura, lógica del modelo, formato de escenario, CLI).

## Dónde está cada cosa
- Motor de cálculo: `Model/app/generar_ajuste_plan_2034.py` (LP, validaciones) y `Model/app/ajuste_plan_ejecutable.py` (orquestación por circuito, salidas, CLI).
- Interfaz: `Model/app/sidebar.html` (configuración) y `Model/app/dashboard.html` (resultados). Se leen al arrancar; no requieren recompilar.
- Ejecutable C#: `Desarrollo/Codigo Fuente/MaterialShift.cs` (C# 5: sin `$""` ni `?.`). Compila con `compilar.ps1`.
- Verificación: `Desarrollo/Verificacion/` (comparación celda por celda, pruebas de interfaz por CDP).

## Reglas
- El motor debe seguir dando resultados idénticos a la versión de referencia: tras cambiar el cálculo, correr `Desarrollo/Verificacion/comparar_resultados.py`.
- `Model/python/` no está en el repositorio (ver `requirements.txt`). Para ejecutar el motor hace falta Python 3.12 con esos paquetes.
- Los Excel de `Inputs/` son datos de trabajo; no modificarlos (el de 2034 pesa 27 MB y cada versión nueva engorda el historial de git).
