@echo off
setlocal
title Panel Liga de Lincoln
cd /d "%~dp0"

set "PYTHON="
if defined LIGA_PYTHON (
    if exist "%LIGA_PYTHON%" (
        if not exist "%LIGA_PYTHON%\." set "PYTHON=%LIGA_PYTHON%"
    )
)

if not defined PYTHON if exist "%~dp0backend\venv\Scripts\python.exe" (
    set "PYTHON=%~dp0backend\venv\Scripts\python.exe"
)

if not defined PYTHON if exist "%~dp0backend\venv\bin\python" (
    "%~dp0backend\venv\bin\python" --version >nul 2>&1
    if not errorlevel 1 set "PYTHON=%~dp0backend\venv\bin\python"
)

if not defined PYTHON (
    echo ERROR: no se encontro Python en LIGA_PYTHON ni en el entorno virtual del proyecto. 1>&2
    exit /b 1
)

"%PYTHON%" "%~dp0scripts\control-panel\app.py"
set "EXIT_CODE=%ERRORLEVEL%"
exit /b %EXIT_CODE%
