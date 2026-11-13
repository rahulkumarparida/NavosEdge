@echo off
REM ==============================================================================
REM NavosEdge — Windows Command Prompt Parent Manager Server Launcher
REM ==============================================================================
setlocal enabledelayedexpansion

set "SCRIPT_DIR=%~dp0"
if "%SCRIPT_DIR:~-1%"=="\" set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"
for %%I in ("%SCRIPT_DIR%\..") do set "PROJECT_DIR=%%~fI"

set "PYTHON_EXE="
set "PYTHON_ARGS="

for %%P in (
    "%SCRIPT_DIR%\.venv\Scripts\python.exe"
    "%SCRIPT_DIR%\venv\Scripts\python.exe"
    "%PROJECT_DIR%\Intelligence\Server\.venv\Scripts\python.exe"
    "%PROJECT_DIR%\Intelligence\Server\venv\Scripts\python.exe"
) do (
    if exist "%%~P" (
        "%%~P" -c "import fastapi, uvicorn, pydantic, httpx" >nul 2>&1
        if not errorlevel 1 (
            set "PYTHON_EXE=%%~P"
            goto :found_python
        )
    )
)

where python >nul 2>&1
if not errorlevel 1 (
    python -c "import fastapi, uvicorn, pydantic, httpx" >nul 2>&1
    if not errorlevel 1 (
        set "PYTHON_EXE=python"
        goto :found_python
    )
)

where py >nul 2>&1
if not errorlevel 1 (
    py -3 -c "import fastapi, uvicorn, pydantic, httpx" >nul 2>&1
    if not errorlevel 1 (
        set "PYTHON_EXE=py"
        set "PYTHON_ARGS=-3"
        goto :found_python
    )
)

echo [ERROR] No Python environment with Manager dependencies found.
echo Install dependencies with: python -m pip install -r Manager\requirements.txt
exit /b 1

:found_python
set "MANAGER_PORT=%NAVOS_MANAGER_PORT%"
if "%MANAGER_PORT%"=="" set "MANAGER_PORT=8430"
set "MANAGER_HOST=%NAVOS_MANAGER_HOST%"
if "%MANAGER_HOST%"=="" set "MANAGER_HOST=0.0.0.0"
set "DISPLAY_HOST=%MANAGER_HOST%"
if "%DISPLAY_HOST%"=="0.0.0.0" set "DISPLAY_HOST=127.0.0.1"

if not exist "%SCRIPT_DIR%\web\dist\index.html" (
    echo [WARN] React build missing at "%SCRIPT_DIR%\web\dist\index.html"
    echo        Build UI with: cd Manager\web ^&^& npm install ^&^& npm run build
)

echo ============================================================
echo       NavosEdge Parent Manager Server ^& Web Dashboard
echo ============================================================
echo   * Python:            %PYTHON_EXE% %PYTHON_ARGS%
echo   * Manager API:       http://%DISPLAY_HOST%:%MANAGER_PORT%/api/v1/overview
echo   * React Dashboard:   http://%DISPLAY_HOST%:%MANAGER_PORT%/
echo ============================================================

pushd "%PROJECT_DIR%"
set "PYTHONPATH=%SCRIPT_DIR%;%PROJECT_DIR%"
"%PYTHON_EXE%" %PYTHON_ARGS% "%SCRIPT_DIR%\app\main.py"
set "EXIT_CODE=%errorlevel%"
popd
exit /b %EXIT_CODE%

