# Compila "Material Shift.exe" en la carpeta principal del programa.
#   powershell -ExecutionPolicy Bypass -File compilar.ps1 [-Logo]
# -Logo vuelve a generar el ícono (crear_icono.py) e incrustarlo en las páginas HTML.
param([switch]$Logo)
$ErrorActionPreference = 'Stop'
$src  = $PSScriptRoot
$root = Resolve-Path (Join-Path $src '..\..')
$bin  = Join-Path $root 'Model\bin'
$py   = Join-Path $root 'Model\python\python.exe'
$csc  = Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'
$fw   = Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319'

if ($Logo) {
    & $py (Join-Path $src 'crear_icono.py')
    & $py (Join-Path $src 'incrustar_logo.py')
}

$out = Join-Path $root 'Material Shift.exe'
$refs = @(
    (Join-Path $bin 'Microsoft.Web.WebView2.Core.dll'),
    (Join-Path $bin 'Microsoft.Web.WebView2.WinForms.dll'),
    (Join-Path $fw 'System.Web.Extensions.dll'),
    (Join-Path $fw 'Microsoft.CSharp.dll'),
    'System.dll', 'System.Core.dll', 'System.Drawing.dll', 'System.Windows.Forms.dll'
) | ForEach-Object { "/r:`"$_`"" }

$cscArgs = @('/nologo', '/target:winexe', '/platform:x64', '/optimize+', "/out:`"$out`"",
             "/win32icon:`"$(Join-Path $root 'Model\recursos\icono.ico')`"") + $refs + @("`"$(Join-Path $src 'MaterialShift.cs')`"")
& $csc @cscArgs
if ($LASTEXITCODE -ne 0) { throw "La compilación falló ($LASTEXITCODE)." }
Write-Host "OK -> $out"
