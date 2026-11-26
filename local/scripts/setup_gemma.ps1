param(
    [string]$Model = "",
    [double]$HeadroomGb = 10.0
)

$ErrorActionPreference = "Stop"

$RootDir = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$SelectorScript = Join-Path $RootDir "src\maca\local_model_selector.py"
$OllamaUrl = "http://127.0.0.1:11434/api/tags"
$InvariantCulture = [System.Globalization.CultureInfo]::InvariantCulture

if (-not $PSBoundParameters.ContainsKey("Model") -and $env:OLLAMA_MODEL) {
    $Model = $env:OLLAMA_MODEL
}

if (-not $PSBoundParameters.ContainsKey("HeadroomGb") -and $env:MACA_OS_HEADROOM_GB) {
    $parsedHeadroom = 0.0
    if ([double]::TryParse($env:MACA_OS_HEADROOM_GB, [System.Globalization.NumberStyles]::Float, $InvariantCulture, [ref]$parsedHeadroom) -and $parsedHeadroom -ge 0) {
        $HeadroomGb = $parsedHeadroom
    } else {
        [Console]::Error.WriteLine("Error: MACA_OS_HEADROOM_GB must be a non-negative number (got: $env:MACA_OS_HEADROOM_GB).")
        exit 1
    }
}

if ($HeadroomGb -lt 0) {
    [Console]::Error.WriteLine("Error: -HeadroomGb must be non-negative (got: $HeadroomGb).")
    exit 1
}

Write-Host "=== Local Gemma Setup Script ==="

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

function Find-Python3 {
    $venvPython = Join-Path $RootDir ".venv\Scripts\python.exe"
    if (Test-Path $venvPython) {
        return [PSCustomObject]@{ Exe = $venvPython; PrefixArgs = @() }
    }

    $prevPref = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        if (Get-Command python -ErrorAction SilentlyContinue) {
            try {
                & python -c "import sys; raise SystemExit(0 if sys.version_info[0] >= 3 else 1)" *> $null
                if ($LASTEXITCODE -eq 0) {
                    return [PSCustomObject]@{ Exe = "python"; PrefixArgs = @() }
                }
            } catch {
                # Ignore stub or broken python executable
            }
        }
        if (Get-Command py -ErrorAction SilentlyContinue) {
            try {
                & py -3 -c "import sys; raise SystemExit(0 if sys.version_info[0] >= 3 else 1)" *> $null
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

function Format-GbDisplay {
    param($Value)
    if ($null -eq $Value -or "$Value" -eq "" -or "$Value" -eq "unknown" -or "$Value" -eq "None" -or "$Value" -eq "null") {
        return "unknown"
    }
    return "$([math]::Round([double]$Value, 1).ToString('0.0', $InvariantCulture)) GB"
}

$SelectedModel = ""
$SelectedNumCtx = 8192
$SelectedKvCacheType = "q8_0"
$SelectedFlashAttention = "1"
$TotalMemGb = $null
$EffectiveHeadroomGb = $HeadroomGb
$ModelBudgetGb = $null

$PythonInfo = Find-Python3
$SelectionUsed = $false

if ($PythonInfo -and (Test-Path $SelectorScript)) {
    $selectorArgs = @($PythonInfo.PrefixArgs) + @(
        $SelectorScript,
        "--format", "json",
        "--write-config",
        "--headroom-gb", $HeadroomGb.ToString($InvariantCulture)
    )
    if ($Model) {
        $selectorArgs += @("--model", $Model)
    }

    $prevPref = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $jsonOutput = & $PythonInfo.Exe @selectorArgs 2>$null
        if ($LASTEXITCODE -eq 0 -and $jsonOutput) {
            $parsed = ($jsonOutput -join "`n") | ConvertFrom-Json
            if ($parsed -and $parsed.model) {
                $SelectedModel = [string]$parsed.model
                if ($parsed.num_ctx) {
                    $SelectedNumCtx = [int]$parsed.num_ctx
                }
                if ($parsed.kv_cache_type) {
                    $SelectedKvCacheType = [string]$parsed.kv_cache_type
                }
                if ($null -ne $parsed.flash_attention) {
                    $SelectedFlashAttention = if ($parsed.flash_attention -eq $false -or "$($parsed.flash_attention)" -eq "0") { "0" } else { "1" }
                }
                $TotalMemGb = $parsed.total_memory_gb
                if ($null -ne $parsed.os_headroom_gb) {
                    $EffectiveHeadroomGb = [double]$parsed.os_headroom_gb
                }
                $ModelBudgetGb = $parsed.model_budget_gb
                $SelectionUsed = $true
            }
        }
    } catch {
        $SelectionUsed = $false
    } finally {
        $ErrorActionPreference = $prevPref
    }
}

if (-not $SelectionUsed) {
    try {
        $cs = Get-CimInstance -ClassName Win32_ComputerSystem -ErrorAction Stop
        if ($cs -and $cs.TotalPhysicalMemory -gt 0) {
            $TotalMemGb = [math]::Round(($cs.TotalPhysicalMemory / 1GB), 1)
        }
    } catch {
        $TotalMemGb = $null
    }

    if ($null -ne $TotalMemGb) {
        $ModelBudgetGb = [math]::Round([math]::Max(0.0, ($TotalMemGb - $HeadroomGb)), 1)
        $effectiveTotal = $TotalMemGb - ($HeadroomGb - 10.0)
        if ($effectiveTotal -ge 40.0) {
            $tierModel = "gemma4:26b-a4b-it-q8_0"
            $tierNumCtx = 32768
        } elseif ($effectiveTotal -ge 28.0) {
            $tierModel = "gemma4:26b"
            $tierNumCtx = 16384
        } elseif ($effectiveTotal -ge 16.0) {
            $tierModel = "hf.co/crucible-labs/Gemma4-26B-A4B-REAP-25-GGUF:Q3_K-mixed"
            $tierNumCtx = if ($effectiveTotal -ge 18.0) { 16384 } else { 8192 }
        } elseif ($effectiveTotal -ge 12.0) {
            $tierModel = "gemma4:e4b"
            $tierNumCtx = 8192
        } else {
            $tierModel = "gemma4:e2b"
            $tierNumCtx = 8192
        }
    } else {
        $ModelBudgetGb = $null
        $tierModel = "gemma4:e2b"
        $tierNumCtx = if ($Model) { 16384 } else { 8192 }
    }

    $SelectedModel = if ($Model) { $Model } else { $tierModel }
    $SelectedNumCtx = $tierNumCtx
    $SelectedKvCacheType = "q8_0"
    $SelectedFlashAttention = "1"
    $EffectiveHeadroomGb = $HeadroomGb

    $configPath = if ($env:MACA_LOCAL_MODEL_CONFIG) { $env:MACA_LOCAL_MODEL_CONFIG } else { Join-Path $HOME ".maca\local_model.env" }
    if (-not [System.IO.Path]::IsPathRooted($configPath)) {
        $configPath = Join-Path $PWD.Path $configPath
    }
    $configDir = Split-Path -Parent $configPath
    if ($configDir -and -not (Test-Path $configDir)) {
        New-Item -ItemType Directory -Path $configDir -Force | Out-Null
    }
    $configLines = @(
        "OLLAMA_MODEL=$SelectedModel"
        "OLLAMA_NUM_CTX=$SelectedNumCtx"
        "OLLAMA_KV_CACHE_TYPE=$SelectedKvCacheType"
        "OLLAMA_FLASH_ATTENTION=$SelectedFlashAttention"
    )
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($configPath, (($configLines -join "`n") + "`n"), $utf8NoBom)
}

$env:OLLAMA_FLASH_ATTENTION = $SelectedFlashAttention
$env:OLLAMA_KV_CACHE_TYPE = $SelectedKvCacheType
$env:OLLAMA_CONTEXT_LENGTH = "$SelectedNumCtx"

Write-Host "Detected system memory : $(Format-GbDisplay $TotalMemGb)"
Write-Host "Reserved OS headroom   : $(Format-GbDisplay $EffectiveHeadroomGb)"
Write-Host "Available model budget : $(Format-GbDisplay $ModelBudgetGb)"
Write-Host "Selected Gemma model   : $SelectedModel"
Write-Host "Ollama tuning          : KV_CACHE_TYPE=$SelectedKvCacheType, FLASH_ATTENTION=$SelectedFlashAttention, CONTEXT_LENGTH=$SelectedNumCtx"

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

Write-Host "Pulling Gemma model ($SelectedModel)..."
& $OllamaExe pull $SelectedModel
if ($LASTEXITCODE -ne 0) {
    [Console]::Error.WriteLine("Failed to pull model '$SelectedModel' (exit code $LASTEXITCODE).")
    exit $LASTEXITCODE
}

Write-Host "=== Local Gemma Setup Complete ==="
