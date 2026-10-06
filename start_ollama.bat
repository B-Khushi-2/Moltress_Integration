@echo off
title Ollama Server
set OLLAMA_TMPDIR=E:\OllamaTmp
set OLLAMA_MODELS=E:\OllamaModels
"E:\Ollama\ollama.exe" serve
