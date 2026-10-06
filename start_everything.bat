@echo off
echo Starting Ollama Engine...
start cmd /k "start_ollama.bat"

echo Starting Moltress Backend...
start cmd /k "start_backend.bat"

echo Starting Moltress Frontend...
start cmd /k "start_frontend.bat"

echo All three processes have been launched in separate windows!
