$ErrorActionPreference = "Stop"

$RootDir = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path

function Find-Python {
    $prevPref = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        if (Get-Command python -ErrorAction SilentlyContinue) {
            try {
                & python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)" *> $null
                if ($LASTEXITCODE -eq 0) {
                    return [PSCustomObject]@{ Exe = "python"; PrefixArgs = @() }
                }
            } catch {
                # Ignore stub/broken python binary and try py launcher
            }
        }
        if (Get-Command py -ErrorAction SilentlyContinue) {
            try {
                & py -3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)" *> $null
                if ($LASTEXITCODE -eq 0) {
                    return [PSCustomObject]@{ Exe = "py"; PrefixArgs = @("-3") }
                }
            } catch {
                # Ignore failed py launcher invocation
            }
        }
    } finally {
        $ErrorActionPreference = $prevPref
    }
    return $null
}

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [string[]]$Arguments = @(),
        [string]$ErrorMessage = ""
    )
    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        if ($ErrorMessage) {
            [Console]::Error.WriteLine($ErrorMessage)
        } else {
            [Console]::Error.WriteLine("Command failed with exit code ${LASTEXITCODE}: $FilePath $($Arguments -join ' ')")
        }
        exit $LASTEXITCODE
    }
}

Push-Location $RootDir
try {
    $Python = Find-Python
    if ($null -eq $Python) {
        [Console]::Error.WriteLine("Python 3.9+ is required. Install it first from https://www.python.org/downloads/")
        exit 1
    }

    $VenvArgs = @($Python.PrefixArgs) + @("-m", "venv", ".venv")
    Invoke-Checked -FilePath $Python.Exe -Arguments $VenvArgs -ErrorMessage "Failed to create virtual environment (.venv)."

    $VenvScripts = Join-Path $RootDir ".venv\Scripts"
    $VenvPython = Join-Path $VenvScripts "python.exe"
    if (-not (Test-Path $VenvPython)) {
        [Console]::Error.WriteLine("Virtual environment Python not found at $VenvPython")
        exit 1
    }

    $env:PATH = "$VenvScripts;$env:PATH"

    Invoke-Checked -FilePath $VenvPython -Arguments @("-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel")
    Invoke-Checked -FilePath $VenvPython -Arguments @("-m", "pip", "install", "hatchling")
    Invoke-Checked -FilePath $VenvPython -Arguments @("-m", "pip", "install", "-e", ".")

    Write-Host "Installing dev dependencies..."
    Invoke-Checked -FilePath $VenvPython -Arguments @("-m", "pip", "install", "-r", "requirements-dev.txt")

    Write-Host "Setting up pre-commit hooks..."
    Invoke-Checked -FilePath (Join-Path $VenvScripts "pre-commit.exe") -Arguments @("install")

    Write-Host "Running static analysis (Ruff, Mypy & Bandit)..."
    Invoke-Checked -FilePath (Join-Path $VenvScripts "ruff.exe") -Arguments @("check", "src/") -ErrorMessage "Build failed: Ruff linting errors found."
    Invoke-Checked -FilePath (Join-Path $VenvScripts "mypy.exe") -Arguments @("src/") -ErrorMessage "Build failed: Mypy type-checking errors found."
    Invoke-Checked -FilePath (Join-Path $VenvScripts "bandit.exe") -Arguments @("-c", "pyproject.toml", "-r", "src/") -ErrorMessage "Build failed: Bandit security issues found."

    $SetupGemma = Join-Path $RootDir "local\scripts\setup_gemma.ps1"
    if (Test-Path $SetupGemma) {
        & $SetupGemma
        if ($LASTEXITCODE -and $LASTEXITCODE -ne 0) {
            exit $LASTEXITCODE
        }
    }

    Write-Host "Installation complete. Run: .\local\scripts\run.ps1"
} finally {
    Pop-Location
}
