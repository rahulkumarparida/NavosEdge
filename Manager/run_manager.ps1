# ==============================================================================
# NavosEdge — Windows PowerShell Parent Manager Server Launcher
# ==============================================================================
$ErrorActionPreference = "Stop"

$ScriptDir = $PSScriptRoot
$ProjectDir = Split-Path -Parent $ScriptDir

$CandidatePythons = @(
    (Join-Path $ScriptDir ".venv\Scripts\python.exe"),
    (Join-Path $ScriptDir "venv\Scripts\python.exe"),
    (Join-Path $ProjectDir "Intelligence\Server\.venv\Scripts\python.exe"),
    (Join-Path $ProjectDir "Intelligence\Server\venv\Scripts\python.exe"),
    "python",
    "py"
)

$PythonExe = $null
$PythonArgs = @()

foreach ($cand in $CandidatePythons) {
    if ($cand -eq "py") {
        $cmd = Get-Command "py" -ErrorAction SilentlyContinue
        if ($cmd) {
            & py -3 -c "import fastapi, uvicorn, pydantic, httpx" 2>$null
            if ($LASTEXITCODE -eq 0) {
                $PythonExe = "py"
                $PythonArgs = @("-3")
                break
            }
        }
    } elseif ($cand -eq "python") {
        $cmd = Get-Command "python" -ErrorAction SilentlyContinue
        if ($cmd) {
            & python -c "import fastapi, uvicorn, pydantic, httpx" 2>$null
            if ($LASTEXITCODE -eq 0) {
                $PythonExe = $cmd.Source
                break
            }
        }
    } elseif (Test-Path $cand) {
        & $cand -c "import fastapi, uvicorn, pydantic, httpx" 2>$null
        if ($LASTEXITCODE -eq 0) {
            $PythonExe = $cand
            break
        }
    }
}

if (-not $PythonExe) {
    Write-Host "[ERROR] No Python environment with Manager dependencies (fastapi, uvicorn, pydantic, httpx) found." -ForegroundColor Red
    Write-Host "Install dependencies with: python -m pip install -r Manager\requirements.txt" -ForegroundColor Yellow
    exit 1
}

$Port = if ($env:NAVOS_MANAGER_PORT) { $env:NAVOS_MANAGER_PORT } else { "8430" }
$HostAddr = if ($env:NAVOS_MANAGER_HOST) { $env:NAVOS_MANAGER_HOST } else { "0.0.0.0" }
$DisplayHost = if ($HostAddr -eq "0.0.0.0") { "127.0.0.1" } else { $HostAddr }

$DistIndex = Join-Path $ScriptDir "web\dist\index.html"
if (-not (Test-Path $DistIndex)) {
    Write-Host "[WARN] React build missing at $DistIndex." -ForegroundColor Yellow
    Write-Host "       Build UI with: cd Manager\web; npm install; npm run build" -ForegroundColor Yellow
}

Write-Host "============================================================"
Write-Host "      NavosEdge Parent Manager Server & Web Dashboard"
Write-Host "============================================================"
Write-Host "  * Python:            $PythonExe $($PythonArgs -join ' ')"
Write-Host "  * Manager API:       http://${DisplayHost}:${Port}/api/v1/overview"
Write-Host "  * React Dashboard:   http://${DisplayHost}:${Port}/"
Write-Host "============================================================"

Push-Location $ProjectDir
try {
    $env:PYTHONPATH = "$ScriptDir;$ProjectDir"
    & $PythonExe @PythonArgs (Join-Path $ScriptDir "app\main.py")
} finally {
    Pop-Location
}

