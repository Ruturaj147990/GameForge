@echo off
setlocal enabledelayedexpansion
title GameForge IDE — Desktop Launcher

REM Resolve base directory from script location (%~dp0)
set "SCRIPT_DIR=%~dp0"
pushd "%SCRIPT_DIR%.."
set "REPO_ROOT=%CD%"
popd

if exist "%SCRIPT_DIR%app\src\gameforge_ide\launcher.py" (
    set "LAUNCH_DIR=%SCRIPT_DIR%"
    set "PYTHONPATH=%SCRIPT_DIR%app;%PYTHONPATH%"
) else if exist "%REPO_ROOT%\src\gameforge_ide\launcher.py" (
    set "LAUNCH_DIR=%REPO_ROOT%"
    set "PYTHONPATH=%REPO_ROOT%;%PYTHONPATH%"
) else (
    set "LAUNCH_DIR=%SCRIPT_DIR%"
)

cd /d "%LAUNCH_DIR%"

REM Find python executable: check environment override, venv, PATH, or py launcher
if defined PYTHON_EXE if exist "%PYTHON_EXE%" goto :have_python

if exist "%LAUNCH_DIR%\.venv\Scripts\python.exe" (
    set "PYTHON_EXE=%LAUNCH_DIR%\.venv\Scripts\python.exe"
    goto :have_python
)

where python >nul 2>&1
if %ERRORLEVEL% equ 0 (
    set "PYTHON_EXE=python"
    goto :have_python
)

where py >nul 2>&1
if %ERRORLEVEL% equ 0 (
    set "PYTHON_EXE=py -3"
    goto :have_python
)

echo [ERROR] Python not found. Please install Python 3.10+ or set PYTHON_EXE.
pause
exit /b 1

:have_python
echo [GameForge IDE] Launching Native PySide6 Desktop Environment...
%PYTHON_EXE% -m src.gameforge_ide.launcher %*
if %ERRORLEVEL% neq 0 (
    echo [ERROR] GameForge IDE exited with error code %ERRORLEVEL%
    pause
)
endlocal
