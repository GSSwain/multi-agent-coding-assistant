$ErrorActionPreference = "Stop"

Write-Host "=== Local Gemma Setup Script ==="

$Model = if ($env:OLLAMA_MODEL) { $env:OLLAMA_MODEL } else { "gemma2:2b" }
$OllamaUrl = "http://127.0.0.1:11434/api/tags"

function Test-OllamaReady {
    try {
        Invoke-RestMethod -Uri $OllamaUrl -Method Get -TimeoutSec 2 -ErrorAction Stop | Out-Null
        return $true
    } catch {
        return $false
    }
}

function Resolve-OllamaCommand {
    $cmd = Get-Command ollama -ErrorAction SilentlyContinue
    if ($cmd) {
        return $cmd.Source
    }
    if ($env:LOCALAPPDATA) {
        $defaultPath = Join-Path $env:LOCALAPPDATA "Programs\Ollama\ollama.exe"
        if (Test-Path $defaultPath) {
            return $defaultPath
        }
    }
    return $null
}

$OllamaExe = Resolve-OllamaCommand
if (-not $OllamaExe) {
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        Write-Host "Ollama is not installed. Installing Ollama via winget..."
        & winget install --id Ollama.Ollama --exact --accept-package-agreements --accept-source-agreements
        if ($LASTEXITCODE -ne 0) {
            [Console]::Error.WriteLine("Failed to install Ollama via winget (exit code $LASTEXITCODE).")
            [Console]::Error.WriteLine("Please install Ollama manually from https://ollama.com/download")
            exit $LASTEXITCODE
        }

        $machinePath = [Environment]::GetEnvironmentVariable("Path", "Machine")
        $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
        $pathParts = @($env:PATH, $machinePath, $userPath) | Where-Object { $_ } | ForEach-Object { $_ -split ';' } | Where-Object { $_ } | Select-Object -Unique
        $env:PATH = ($pathParts -join ';')

        $OllamaExe = Resolve-OllamaCommand
        if (-not $OllamaExe) {
            [Console]::Error.WriteLine("Ollama was installed, but 'ollama' was not found in PATH.")
            [Console]::Error.WriteLine("Open a new terminal or add Ollama to PATH, then re-run this script.")
            exit 1
        }
    } else {
        [Console]::Error.WriteLine("Error: Ollama is not installed and winget is not available.")
        [Console]::Error.WriteLine("Please install Ollama from https://ollama.com/download and re-run this script.")
        exit 1
    }
} else {
    Write-Host "Ollama is already installed at: $OllamaExe"
}

if (Test-OllamaReady) {
    Write-Host "Ollama service is already running."
} else {
    Write-Host "Starting Ollama service..."
    Start-Process -FilePath $OllamaExe -ArgumentList "serve" -WindowStyle Hidden

    Write-Host "Waiting for Ollama service to start..."
    $Ready = $false
    for ($i = 0; $i -lt 30; $i++) {
        if (Test-OllamaReady) {
            Write-Host "Ollama service is ready."
            $Ready = $true
            break
        }
        Start-Sleep -Seconds 1
    }

    if (-not $Ready) {
        [Console]::Error.WriteLine("Error: Timed out waiting for Ollama service at $OllamaUrl")
        [Console]::Error.WriteLine("Start Ollama manually with 'ollama serve' and re-run this script.")
        exit 1
    }
}

Write-Host "Pulling Gemma model ($Model)..."
& $OllamaExe pull $Model
if ($LASTEXITCODE -ne 0) {
    [Console]::Error.WriteLine("Failed to pull model '$Model' (exit code $LASTEXITCODE).")
    exit $LASTEXITCODE
}

Write-Host "=== Local Gemma Setup Complete ==="
