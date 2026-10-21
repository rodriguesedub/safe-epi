@echo off
rem SAFEEPI: prepara o ambiente na primeira vez e sobe o servidor local.
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Criando ambiente virtual .venv ...
  py -3 -m venv .venv 2>nul || python -m venv .venv
)
if not exist ".venv\Scripts\python.exe" (
  echo.
  echo Python nao encontrado. Instale o Python 3.10 ou superior em https://www.python.org/downloads/
  echo e marque a opcao "Add python.exe to PATH" durante a instalacao.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m pip install -q --upgrade pip >nul
".venv\Scripts\python.exe" -m pip install -q -r requirements.txt || goto erro
".venv\Scripts\python.exe" manage.py migrate --noinput -v 0 || goto erro
".venv\Scripts\python.exe" manage.py seed_demo --se-vazio || goto erro
echo.
echo SAFEEPI rodando em http://127.0.0.1:8000  (feche esta janela para parar)
echo Usuarios: operador, tecnico, almox, gestor, operador2, admin. Senha: safeepi123
echo Tutorial: na tela de login, Tutorial guiado ou Reproducao automatica.
echo.
start "" cmd /c "timeout /t 3 >nul & start http://127.0.0.1:8000/"
".venv\Scripts\python.exe" manage.py runserver 127.0.0.1:8000
goto fim
:erro
echo.
echo Algo deu errado na preparacao. Veja a mensagem acima.
pause
:fim
endlocal
