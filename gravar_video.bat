@echo off
rem SAFEEPI: grava sozinho o video do tutorial em videos\safeepi-tutorial.mp4
rem Opcoes: --720 para arquivo menor, --velocidade 1.25 para mais rapido, --ver para ver a janela.
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" goto temvenv
echo Rode primeiro o iniciar.bat, que prepara o ambiente do SAFEEPI.
pause
exit /b 1
:temvenv
".venv\Scripts\python.exe" -c "import playwright, imageio_ffmpeg" 2>nul
if errorlevel 1 goto instalar
goto navegador
:instalar
echo Instalando o gravador. Isso so acontece na primeira vez...
".venv\Scripts\python.exe" -m pip install -q -r requirements-gravacao.txt || goto erro
:navegador
".venv\Scripts\python.exe" -m playwright install chromium || goto erro
".venv\Scripts\python.exe" ferramentas\gravar_video.py %* || goto erro
echo.
echo Video salvo na pasta videos.
start "" "videos"
pause
goto fim
:erro
echo.
echo Algo deu errado. Veja a mensagem acima.
pause
:fim
endlocal
