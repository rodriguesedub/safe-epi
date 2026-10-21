@echo off
rem Recria os dados de demonstracao (rode antes de cada apresentacao).
cd /d "%~dp0"
".venv\Scripts\python.exe" manage.py seed_demo --reset
pause
