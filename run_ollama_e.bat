@echo off
set OLLAMA_MODELS=E:\GameForge\models\ollama
echo Starting Ollama with OLLAMA_MODELS=%OLLAMA_MODELS%
"E:\GameForge\ollama_bin\ollama.exe" serve
