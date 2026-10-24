@echo off
setlocal
title GameForge IDE — Desktop Launcher

set "PYTHON_EXE=C:\Users\limbk\AppData\Local\Programs\Python\Python314\python.exe"
set "REPO_ROOT=E:\gameforge_step1"
set "OLLAMA_MODELS=E:\GameForge\models\ollama"

cd /d "%REPO_ROOT%"
echo [GameForge IDE] Launching Native PySide6 Desktop Environment...
"%PYTHON_EXE%" -m src.gameforge_ide.launcher %*
if %ERRORLEVEL% neq 0 (
    echo [ERROR] GameForge IDE exited with error code %ERRORLEVEL%
    pause
)
endlocal
