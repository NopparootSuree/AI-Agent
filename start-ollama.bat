@echo off
echo Starting Ollama with host binding...
set OLLAMA_HOST=0.0.0.0:11434
ollama serve
pause