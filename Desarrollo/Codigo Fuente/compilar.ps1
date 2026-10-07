# Compila "SimA - Simulation Analyst" (Windows 10/11, sin Python en el equipo del usuario).
# Uso:  powershell -ExecutionPolicy Bypass -File compilar.ps1 [-Destino "C:\ruta\Carpeta"] [-Python "ruta\python.exe"]
# Por defecto el programa queda en la carpeta principal (dos niveles arriba de «Desarrollo\Codigo Fuente»):
# allí viven el .exe, Model, Escenarios, Inputs y Outputs.
param(
    [string]$Destino = (Split-Path -Parent (Split-Path -Parent $PSScriptRoot)),
    [string]$Python = "python"
)
$ErrorActionPreference = "Stop"
$fuente = $PSScriptRoot
$trabajo = Join-Path $env:TEMP "sima_build"
if (Test-Path $trabajo) { Remove-Item $trabajo -Recurse -Force }
New-Item -ItemType Directory -Force $trabajo | Out-Null

Push-Location $fuente
try {
    & $Python -m pip install --quiet --upgrade pyinstaller pandas numpy openpyxl pillow python-pptx
    & $Python crear_icono.py
    $recursos = Join-Path $fuente "recursos"
    & $Python -m PyInstaller --noconfirm --clean --onedir --windowed `
        --name "SimA - Simulation Analyst" `
        --contents-directory Model `
        --icon (Join-Path $recursos "icono.ico") `
        --add-data "$recursos;recursos" `
        --collect-data pptx `
        --hidden-import pandas --hidden-import numpy `
        --version-file (Join-Path $fuente "version_info.txt") `
        --exclude-module matplotlib --exclude-module scipy --exclude-module IPython `
        --exclude-module pytest --exclude-module pandas.tests --exclude-module numba `
        --exclude-module PIL.AvifImagePlugin --exclude-module PIL._avif --exclude-module PIL.WebPImagePlugin `
        --exclude-module PIL._webp --exclude-module PIL.ImageCms --exclude-module PIL._imagingcms `
        --exclude-module sqlite3 --exclude-module _sqlite3 --exclude-module asyncio --exclude-module _asyncio `
        --exclude-module _overlapped --exclude-module ssl --exclude-module _ssl --exclude-module _hashlib `
        --exclude-module _zstd --exclude-module compression.zstd `
        --exclude-module unittest --exclude-module pydoc --exclude-module doctest --exclude-module pdb `
        --exclude-module numpy.f2py --exclude-module setuptools --exclude-module pip `
        --exclude-module lib2to3 --exclude-module tkinter.test --exclude-module idlelib `
        --distpath (Join-Path $trabajo "dist") --workpath (Join-Path $trabajo "build") `
        --specpath $trabajo main.py
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller terminó con error ($LASTEXITCODE)" }
}
finally { Pop-Location }

$salida = Join-Path $trabajo "dist\SimA - Simulation Analyst"
New-Item -ItemType Directory -Force $Destino | Out-Null
# Se reemplaza la versión anterior del programa; Preferencias, Escenarios, Inputs y Outputs se conservan
$prefs = Join-Path $Destino "Model\Preferencias"
$respaldo = Join-Path $trabajo "Preferencias"
if (Test-Path $prefs) { Copy-Item $prefs $respaldo -Recurse -Force }
$modelo = Join-Path $Destino "Model"
if (Test-Path $modelo) { Remove-Item $modelo -Recurse -Force }
# ejecutables anteriores (incluido el nombre previo a la v1.5)
foreach ($n in "SimA - Simulation Analyst.exe", "SimA - Simulation Analytics.exe") {
    $exe = Join-Path $Destino $n
    if (Test-Path $exe) { Remove-Item $exe -Force }
}
Copy-Item "$salida\*" $Destino -Recurse -Force
if (Test-Path $respaldo) { Copy-Item $respaldo (Join-Path $Destino "Model") -Recurse -Force }

foreach ($c in "Escenarios", "Inputs", "Outputs") { New-Item -ItemType Directory -Force (Join-Path $Destino $c) | Out-Null }
# El código fuente vive solo en «Desarrollo\Codigo Fuente» (no se duplica dentro del programa)
Write-Host "Compilación terminada en: $Destino"