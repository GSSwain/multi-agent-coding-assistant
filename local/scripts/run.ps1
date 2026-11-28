$ErrorActionPreference = "Stop"

$RootDir = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$VenvScripts = Join-Path $RootDir ".venv\Scripts"
$MacaExe = Join-Path $VenvScripts "maca.exe"
$VenvPython = Join-Path $VenvScripts "python.exe"

$prevPath = $env:PATH
try {
    if (Test-Path $MacaExe) {
        $env:PATH = "$VenvScripts;$env:PATH"
        & $MacaExe @args
        exit $LASTEXITCODE
    } elseif (Test-Path $VenvPython) {
        $env:PATH = "$VenvScripts;$env:PATH"
        & $VenvPython -m maca.main @args
        exit $LASTEXITCODE
    } else {
        [Console]::Error.WriteLine("Virtual environment not found. Run .\local\scripts\install.ps1 first.")
        exit 1
    }
} finally {
    $env:PATH = $prevPath
}
